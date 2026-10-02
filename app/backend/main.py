import asyncio
import io
import re
import os
import sys
from pathlib import Path
from datetime import timedelta
from flask import Flask, request, jsonify, send_file
from sqlalchemy.orm import Session
from .document_versions import fingerprint, document_similarity, sentence_diff, serialize_results, deserialize_results, SAME_DOCUMENT_SIMILARITY
import os
from datetime import timedelta
import pymupdf
from flask import Flask, request, jsonify, send_file
from sqlalchemy.orm import Session
from .document_versions import fingerprint, document_similarity, sentence_diff, serialize_results, deserialize_results, SAME_DOCUMENT_SIMILARITY

from . import (
    models,
    auth,
    payments,
    plagiarism,
    database,
)
from .database import (
    SessionLocal,
    engine,
)

from .reports import build_pdf_report

from .auth import (
    verify_password,
    create_access_token,
    get_password_hash,
    get_current_active_user,
)


# ============================================================
# CONFIGURACIÓN DE RUTAS
# ============================================================

# app/backend/main.py
#
# parents[0] = backend
# parents[1] = app
# parents[2] = DoctorPlagio

PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]


# Garantizar que el proyecto raíz esté disponible
# para los imports del paquete.

if str(PROJECT_ROOT) not in sys.path:

    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


# ============================================================
# FLASK
# ============================================================

template_dir = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "frontend",
    )
)


app = Flask(
    __name__,
    static_folder=template_dir,
    static_url_path="/",
)
# ============================================================
# BASE DE DATOS
# ============================================================

def get_db():
    """
    Crea una sesión de SQLAlchemy y garantiza su cierre.
    """
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


# ============================================================
# RUTA PRINCIPAL
# ============================================================

@app.route("/")
def home():

    index_path = os.path.join(
        template_dir,
        "index.html",
    )

    if not os.path.exists(index_path):

        return (
            f"Error: No encontré el index.html en "
            f"{index_path}. Revisa la carpeta.",
            404,
        )

    return app.send_static_file("index.html")


# ============================================================
# LOGIN
# ============================================================

@app.route("/token", methods=["POST"])
def login_for_access_token():

    data = request.json or {}

    db: Session = SessionLocal()

    try:

        username = data.get("username")
        password = data.get("password")

        user = (
            db.query(models.User)
            .filter(
                models.User.username == username
            )
            .first()
        )

        if not user or not verify_password(
            password,
            user.hashed_password,
        ):

            return jsonify({
                "detail": "Usuario o contraseña incorrectos"
            }), 401

        access_token_expires = timedelta(
            minutes=30
        )

        access_token = create_access_token(
            data={"sub": user.username},
            expires_delta=access_token_expires,
        )

        return jsonify({
            "access_token": access_token,
            "token_type": "bearer",
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

    finally:

        db.close()


# ============================================================
# ANALIZAR DOCUMENTO
# ============================================================

@app.route("/analyze", methods=["POST"])
def analyze_document():
    """Analyze a document, reusing the previous result when its content is unchanged."""
    db = SessionLocal()
    try:
        text = request.form.get("text")
        file = request.files.get("file") or request.files.get("document")
        if not text and not file:
            return jsonify({"detail": "Debe proveer texto o un archivo"}), 400

        raw = None
        if file:
            filename = file.filename or "documento"
            raw = file.read()
            if filename.lower().endswith(".pdf"):
                with pymupdf.open(stream=raw, filetype="pdf") as pdf:
                    page_parts = []
                    for page_number, page in enumerate(pdf, start=1):
                        page_parts.append(f"[[PAGE:{page_number}]]\n{page.get_text('text')}")
                    document_content = "\n\n".join(page_parts)
            else:
                document_content = raw.decode("utf-8", errors="ignore")
        else:
            document_content = text
            filename = "Entrada_Manual"

        if not document_content or not document_content.strip():
            return jsonify({"detail": "El documento no contiene texto."}), 400

        fp = fingerprint(document_content, raw)
        text_hash = fp["text_hash"]
        file_hash = fp["file_hash"]

        print("\n" + "=" * 70)
        print("📄 INICIANDO RESOLUCIÓN DE VERSIÓN")
        print(f"📁 Archivo: {filename}")
        print(f"📝 Caracteres normalizados: {fp['normalized_chars']:,}")

        # Exact content identity: do not spend CPU/GPU on a document already evaluated.
        exact_version = (
            db.query(models.DocumentVersion)
            .filter(models.DocumentVersion.text_hash == text_hash)
            .order_by(models.DocumentVersion.created_at.desc())
            .first()
        )

        previous = None
        if exact_version:
            previous = exact_version
        else:
            # Look for the latest likely revision. We only use this to describe history;
            # changed documents are still analyzed again.
            candidates = (
                db.query(models.DocumentVersion)
                .join(models.Document)
                .order_by(models.DocumentVersion.created_at.desc())
                .limit(20)
                .all()
            )
            best = None
            best_similarity = 0.0
            for candidate in candidates:
                old_doc = candidate.document
                sim = document_similarity(old_doc.content or "", document_content)
                if sim > best_similarity:
                    best_similarity = sim
                    best = candidate
            if best is not None and best_similarity >= SAME_DOCUMENT_SIMILARITY:
                previous = best

        if exact_version is not None:
            previous_doc = exact_version.document
            new_doc = models.Document(filename=filename, content=document_content)
            db.add(new_doc)
            db.flush()
            version = models.DocumentVersion(
                document_id=new_doc.id,
                previous_version_id=exact_version.id,
                version_number=(exact_version.version_number or 1) + 1,
                file_hash=file_hash,
                text_hash=text_hash,
                normalized_chars=fp["normalized_chars"],
                similarity_to_previous=1.0,
                status="unchanged_reused",
                diff_json=serialize_results({"similarity": 1.0, "change_count": 0, "changes": []}),
                analysis_json=exact_version.analysis_json,
            )
            db.add(version)
            db.commit()
            cached = deserialize_results(exact_version.analysis_json) or {}
            cached.setdefault("version_history", {})
            cached["version_history"].update({
                "status": "unchanged_reused",
                "message": "El contenido del documento coincide exactamente con una evaluación anterior.",
                "previous_document_id": previous_doc.id,
                "previous_version_id": exact_version.id,
                "version_number": version.version_number,
                "similarity_to_previous": 1.0,
                "reused_previous_evaluation": True,
                "file_hash_equal": file_hash == exact_version.file_hash if file_hash else False,
                "text_hash_equal": True,
            })
            print("♻️ DOCUMENTO SIN CAMBIOS: se reutilizó la última evaluación.")
            return jsonify({"status": "success", "document_id": new_doc.id, "version_id": version.id, "results": cached})

        similarity = None
        diff = None
        previous_version_id = None
        version_number = 1
        if previous is not None:
            previous_version_id = previous.id
            version_number = (previous.version_number or 1) + 1
            similarity = document_similarity(previous.document.content or "", document_content)
            diff = sentence_diff(previous.document.content or "", document_content)
            print(f"🔁 Posible revisión detectada: similitud={similarity:.4f}")
        else:
            diff = {"similarity": 0.0, "change_count": 0, "changes": []}

        print("🔎 Ejecutando análisis completo...")
        previous_ai_report = None
        if previous is not None:
            previous_cached = deserialize_results(previous.analysis_json)
            if isinstance(previous_cached, dict):
                previous_ai_report = previous_cached.get("ai_analysis")
        analysis_results = asyncio.run(plagiarism.analyze_plagiarism(document_content, db, previous_ai_report=previous_ai_report))

        # Add version history metadata to the returned report.
        analysis_results["version_history"] = {
            "status": "new_analysis" if previous is None else "revised_document",
            "message": (
                "Primera evaluación registrada."
                if previous is None else
                "Se detectó una versión anterior del mismo documento; esta versión fue analizada nuevamente."
            ),
            "previous_document_id": previous.document_id if previous else None,
            "previous_version_id": previous_version_id,
            "version_number": version_number,
            "similarity_to_previous": similarity,
            "reused_previous_evaluation": False,
            "file_hash_equal": False,
            "text_hash_equal": False,
            "change_count": diff.get("change_count", 0) if diff else 0,
            "changes": diff.get("changes", []) if diff else [],
        }

        new_doc = models.Document(filename=filename, content=document_content)
        db.add(new_doc)
        db.flush()
        version = models.DocumentVersion(
            document_id=new_doc.id,
            previous_version_id=previous_version_id,
            version_number=version_number,
            file_hash=file_hash,
            text_hash=text_hash,
            normalized_chars=fp["normalized_chars"],
            similarity_to_previous=similarity,
            status="new_analysis" if previous is None else "revised_document",
            diff_json=serialize_results(diff or {}),
            analysis_json=serialize_results(analysis_results),
        )
        db.add(version)
        db.commit()

        print("✅ ANÁLISIS COMPLETADO")
        print(f"🗄️ Documento ID: {new_doc.id} | Versión: {version.version_number}")
        print("=" * 70 + "\n")
        return jsonify({"status": "success", "document_id": new_doc.id, "version_id": version.id, "results": analysis_results})

    except Exception as e:
        db.rollback()
        print("\n❌ ERROR EN EL MOTOR DE ANÁLISIS")
        print(f"❌ {e}")
        print(f"❌ Tipo: {type(e).__name__}\n")
        return jsonify({"error": f"Error en el motor de análisis: {str(e)}"}), 500
    finally:
        db.close()


# ============================================================
# INFORME PDF
# ============================================================

@app.route("/report/<int:version_id>", methods=["GET"])
def download_report(version_id: int):
    """Genera y descarga el PDF usando el análisis ya almacenado."""
    db = SessionLocal()
    try:
        version = db.query(models.DocumentVersion).filter(
            models.DocumentVersion.id == version_id
        ).first()

        if version is None:
            return jsonify({"detail": "No se encontró la versión solicitada."}), 404

        results = deserialize_results(version.analysis_json) or {}
        if not results:
            return jsonify({"detail": "La versión no tiene un análisis almacenado."}), 404

        document = version.document
        filename = document.filename if document else "documento"
        pdf_bytes = build_pdf_report(results, filename=filename)

        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).stem) or "documento"
        download_name = f"DoctorPlagio_Informe_{safe_name}_v{version.version_number}.pdf"

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=download_name,
        )
    except Exception as exc:
        print(f"❌ Error generando informe PDF: {exc}")
        return jsonify({"detail": f"No fue posible generar el informe PDF: {exc}"}), 500
    finally:
        db.close()


# ============================================================
# ARRANQUE DIRECTO
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 70)
    print("🚀 DOCTORPLAGIO")
    print("=" * 70)

    # --------------------------------------------------------
    # Crear tablas si no existen
    # --------------------------------------------------------

    with app.app_context():

        print(
            "🛠️ Verificando tablas de base de datos..."
        )

        models.Base.metadata.create_all(
            bind=engine
        )

        print("✅ Tablas verificadas.")

    print()
    print("🌐 Servidor:")
    print("   http://127.0.0.1:5000")
    print()
    print("🧠 Motor IA:")
    print("   GPT-OSS 20B / llama.cpp")
    print("   llama.cpp")
    print()
    print("🗃️ Base de datos:")
    print("   PostgreSQL / SQLAlchemy")
    print()
    print("🔎 Plagio:")
    print("   ChromaDB + motor híbrido")
    print("=" * 70)
    print()

    # --------------------------------------------------------
    # IMPORTANTE PARA VS CODE DEBUG
    # --------------------------------------------------------
    #
    # use_reloader=False evita que Flask cree un segundo
    # proceso, lo cual suele interferir con debugpy.
    #

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False,
    )   