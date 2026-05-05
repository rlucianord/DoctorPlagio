import sys
import asyncio # Necesario para procesar la lógica async de plagiarism
from pathlib import Path
from flask import Flask, request, jsonify
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import os

# --- AJUSTE DE PATH ---
root_path = Path(__file__).resolve().parents[1]
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))

# --- IMPORTS DEL PROYECTO ---
from backend import models, auth, payments, plagiarism, database
from backend.database import SessionLocal, engine 
from backend.auth import (
    verify_password, create_access_token, 
    get_password_hash, get_current_active_user
)
template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
app = Flask(__name__, 
            static_folder=template_dir, 
            static_url_path="/")

# Dependencia para obtener la sesión de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- RUTAS ---

@app.route("/")
def home():
    # Verificamos si el archivo existe antes de enviarlo para darte un error claro
    index_path = os.path.join(template_dir, "index.html")
    if not os.path.exists(index_path):
        return f"Error: No encontré el index.html en {index_path}. Revisa la carpeta.", 404
        
    return app.send_static_file("index.html")

@app.route("/token", methods=["POST"])

def login_for_access_token():
    data = request.json
    db: Session = SessionLocal()
    try:
        username = data.get("username")
        password = data.get("password")

        # Sintaxis SQLAlchemy 2.0[cite: 1]
        user = db.query(models.User).filter(models.User.username == username).first()

        if not user or not verify_password(password, user.hashed_password):
            return jsonify({"detail": "Usuario o contraseña incorrectos"}), 401

        access_token_expires = timedelta(minutes=30)
        access_token = create_access_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )

        return jsonify({"access_token": access_token, "token_type": "bearer"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
@app.route("/analyze", methods=["POST"])
def analyze_document():
    db = next(get_db())
    
    # Soporte para texto directo o archivo
    text = request.form.get("text")
    file = request.files.get("file")
    
    if not text and not file:
        return jsonify({"detail": "Debe proveer texto o un archivo"}), 400

    # Extraer contenido
    if file:
        document_content = file.read().decode("utf-8", errors="ignore")
        filename = file.filename
    else:
        document_content = text
        filename = "Entrada_Manual"
    
    try:
        # 1. Ejecutamos el análisis (Ollama + ChromaDB)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        analysis_results = loop.run_until_complete(plagiarism.analyze_plagiarism(document_content, db))
        loop.close()

        # 2. Persistencia en base de datos (SQLAlchemy)[cite: 2]
        # Aquí puedes vincularlo al current_user.id si ya tienes el login listo
        new_doc = models.Document(filename=filename, content=document_content)
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)

        return jsonify({
            "status": "success",
            "document_id": new_doc.id,
            "results": analysis_results
        })
    except Exception as e:
        return jsonify({"error": f"Error en el motor de análisis: {str(e)}"}), 500

if __name__ == "__main__":
    # Aseguramos que las tablas existan antes de arrancar[cite: 2]
    with app.app_context():
        print("🛠️ Verificando tablas de base de datos...")
        models.Base.metadata.create_all(bind=engine)
        
    app.run(host="0.0.0.0", port=5000, debug=True,use_reloader=False)