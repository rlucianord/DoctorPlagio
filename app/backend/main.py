import sys
from pathlib import Path
sys.path[0] = str(Path(sys.path[0]).parent)
print(sys.path[1])

from flask import Flask, request, jsonify
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from backend import models, auth, payments, plagiarism, database
from backend.config import DATABASE_URL
from backend.auth import verify_password, create_access_token,get_current_active_user,get_current_user,get_password_hash
from backend.database import SessionLocal
from backend.models import User, Document, PlagiarismResult, Subscription
from backend import payments, plagiarism, auth
# Configuración de la base de datos
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Crear la aplicación Flask
app = Flask(__name__)

@app.route("/")
def home():
    return "Hello, Flask!"

 
# Dependencia para obtener la sesión de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Rutas
@app.route("/register", methods=["POST"])
def register_user():
    data = request.json
    db = next(get_db())
    db_user = db.query(models.User).filter(models.User.username == data["username"]).first()
    if db_user:
        return jsonify({"detail": "Username already registered"}), 400
    db_email = db.query(models.User).filter(models.User.email == data["email"]).first()
    if db_email:
        return jsonify({"detail": "Email already registered"}), 400
    hashed_password = get_password_hash(data["password"])
    db_user = models.User(username=data["username"], email=data["email"], hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return jsonify({"id": db_user.id, "username": db_user.username, "email": db_user.email})

@app.route("/token", methods=["POST"])
def login_for_access_token():
    #db: Session = SessionLocal()
    data = request.json
    db: Session = SessionLocal()
    try:
    
    # Log para verificar los datos recibidos
        print(f"Datos recibidos: {data}")

        username = data.get("username")
        password = data.get("password")  # No vuelvas a hashear la contraseña aquí

    # Log para verificar los valores extraídos
        print(f"Username: {username}, Password: {password}")

        user = db.query(models.User).where(models.User.username.contains(username)).first()
        

    # Log para verificar si el usuario existe
        if not user:
            print("Usuario no encontrado",DATABASE_URL)
            return jsonify({"detail": "Usuario o contraseña incorrectos"}), 401

    # Log para verificar la contraseña
        if not verify_password(password, user.hashed_password):
            print("Contraseña incorrecta")
            return jsonify({"detail": "Usuario o contraseña incorrectos"}), 401

    # Log para confirmar que el usuario fue autenticado
        print(f"Usuario autenticado: {user.username}")

        access_token_expires = timedelta(minutes=30)
        access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    # Log para confirmar que el token fue generado
        print(f"Token generado para {user.username}: {access_token}")

        return jsonify({"access_token": access_token, "token_type": "bearer"})
    except Exception as e:
        jsonify(f"Error al crear el usuario de prueba: {e}")
    finally:
        db.close()

@app.route("/users/me", methods=["GET"])
def read_users_me():
    current_user = auth.get_current_active_user()
    return jsonify({"id": current_user.id, "username": current_user.username, "email": current_user.email})

@app.route("/upload", methods=["POST"])
def upload_document():
    file = request.files["file"]
    db = next(get_db())
    current_user = auth.get_current_active_user()
    file_content = file.read().decode("utf-8", errors="ignore")
    document = models.Document(
        owner_id=current_user.id,
        filename=file.filename,
        content=file_content,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return jsonify({"id": document.id, "filename": document.filename, "content": document.content})

@app.route("/analyze", methods=["POST"])
def analyze_document():
    db = next(get_db())
    current_user = auth.get_current_active_user()
    text = request.form.get("text")
    file = request.files.get("file")
    if not text and not file:
        return jsonify({"detail": "Either 'text' or 'file' must be provided"}), 400

    if file:
        file_content = file.read().decode("utf-8", errors="ignore")
        document_content = file_content
        filename = file.filename
    else:
        document_content = text
        filename = "Text Input"

    document = models.Document(owner_id=current_user.id, filename=filename, content=document_content)
    db.add(document)
    db.commit()
    db.refresh(document)

    analysis_results = plagiarism.analyze_plagiarism(document_content, db)
    plagiarism_result = models.PlagiarismResult(document_id=document.id, **analysis_results)
    db.add(plagiarism_result)
    db.commit()
    db.refresh(plagiarism_result)
    return jsonify({
        "id": plagiarism_result.id,
        "document_id": plagiarism_result.document_id,
        "plagiarism_percentage_text": analysis_results.get("plagiarism_percentage_text"),
        "plagiarism_details_text": analysis_results.get("plagiarism_details_text"),
        "ai_detection_percentage": analysis_results.get("ai_detection_percentage"),
        "ai_detection_details": analysis_results.get("ai_detection_details"),
        "report_path": analysis_results.get("report_path"),
    })

@app.route("/results/<int:document_id>", methods=["GET"])
def get_analysis_results(document_id):
    db = next(get_db())
    current_user = auth.get_current_active_user()
    document = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not document:
        return jsonify({"detail": "Document not found"}), 404
    if document.owner_id != current_user.id:
        return jsonify({"detail": "You do not have permission to access this document"}), 403
    result = db.query(models.PlagiarismResult).filter(models.PlagiarismResult.document_id == document_id).first()
    if not result:
        return jsonify({"detail": "Analysis results not found for this document"}), 404
    return jsonify({"id": result.id, "document_id": result.document_id})

@app.route("/subscribe", methods=["POST"])
def subscribe_user():
    db = next(get_db())
    current_user = auth.get_current_active_user()
    subscription_data = {
        "customer": "cus_123",
        "plan_name": "basic",
        "current_period_start": int(datetime.now().timestamp()),
        "current_period_end": int((datetime.now() + timedelta(days=30)).timestamp()),
        "status": "active",
    }
    payments.update_user_subscription(db, current_user, subscription_data)
    return jsonify({"message": "Subscription successful"})

@app.route("/payment_history", methods=["GET"])
def get_payment_history():
    current_user = auth.get_current_active_user()
    return jsonify([
        {"date": "2024-01-15", "amount": 29.99, "status": "paid"},
        {"date": "2023-12-15", "amount": 29.99, "status": "paid"}
    ])

if __name__ == "__main__":
    app.debug = True
    app.run()#host="0.0.0.0", port=5000