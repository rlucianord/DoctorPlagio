import asyncio
import os
import sys
from pathlib import Path
from datetime import timedelta
from flask import Flask, request, jsonify
from sqlalchemy.orm import Session
import os
from datetime import timedelta
import pymupdf
from flask import Flask, request, jsonify
from sqlalchemy.orm import Session

from . import (
    models,
    auth,
    payments,
    plagiarism,
    database,
)
from app.backend.database import (
    SessionLocal,
    engine,
)

from app.backend.auth import (
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

    # --------------------------------------------------------
    # Crear sesión DB
    # --------------------------------------------------------

    db = SessionLocal()

    try:

        # ----------------------------------------------------
        # Soporte para texto directo o archivo
        # ----------------------------------------------------

        text = request.form.get("text")

        file = (
            request.files.get("file")
            or request.files.get("document")
        )

        if not text and not file:

            return jsonify({
                "detail": "Debe proveer texto o un archivo"
            }), 400

        # ----------------------------------------------------
        # Extraer contenido
        # ----------------------------------------------------

        if file:

            filename = (
                file.filename
                or "documento"
            )

            raw = file.read()

            # -----------------------------------------------
            # PDF
            # -----------------------------------------------

            if filename.lower().endswith(".pdf"):

                with pymupdf.open(
                    stream=raw,
                    filetype="pdf",
                ) as pdf:
                

                    document_content = "\n".join(
                        page.get_text("text")
                        for page in pdf
                    )

            # -----------------------------------------------
            # Otros archivos
            # -----------------------------------------------

            else:

                document_content = raw.decode(
                    "utf-8",
                    errors="ignore",
                )

        else:

            document_content = text
            filename = "Entrada_Manual"

        # ----------------------------------------------------
        # Validación
        # ----------------------------------------------------

        if not document_content or not document_content.strip():

            return jsonify({
                "detail": "El documento no contiene texto."
            }), 400

        print()
        print("=" * 70)
        print("📄 INICIANDO ANÁLISIS")
        print("=" * 70)
        print(f"📁 Archivo: {filename}")
        print(
            f"📝 Caracteres: {len(document_content):,}"
        )
        print("=" * 70)

        # ----------------------------------------------------
        # Ejecutar análisis asíncrono
        #
        # Qwen local + llama.cpp
        # ChromaDB
        # motor híbrido
        # ----------------------------------------------------

        analysis_results = asyncio.run(
            plagiarism.analyze_plagiarism(
                document_content,
                db,
            )
        )

        # ----------------------------------------------------
        # Persistencia
        # ----------------------------------------------------

        new_doc = models.Document(
            filename=filename,
            content=document_content,
        )

        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)

        print()
        print("✅ ANÁLISIS COMPLETADO")
        print(
            f"🗄️ Documento guardado con ID: "
            f"{new_doc.id}"
        )
        print("=" * 70)
        print()

        # ----------------------------------------------------
        # Respuesta
        # ----------------------------------------------------

        return jsonify({
            "status": "success",
            "document_id": new_doc.id,
            "results": analysis_results,
        })

    except Exception as e:

        # ----------------------------------------------------
        # Rollback de DB si ocurrió un error
        # ----------------------------------------------------

        db.rollback()

        print()
        print("❌ ERROR EN EL MOTOR DE ANÁLISIS")
        print(f"❌ {e}")
        print(
            f"❌ Tipo: {type(e).__name__}"
        )
        print()

        return jsonify({
            "error": (
                "Error en el motor de análisis: "
                f"{str(e)}"
            )
        }), 500

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
    print("   Qwen2.5-3B-Instruct")
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