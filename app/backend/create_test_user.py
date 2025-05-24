from sqlalchemy.orm import Session
from database import SessionLocal
from backend.models import User
from backend.auth import get_password_hash,verify_password
import backend.auth as auth
def create_test_user():
    # Crear una sesión de base de datos
    db: Session = SessionLocal()

    try:
        # Verificar si el usuario ya existe
        username = "testuser"
        email = "testuser@example.com"
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            print(f"El usuario '{username}' ya existe.")
            return

        # Crear un nuevo usuario
        hashed_password = get_password_hash("password123")
        test_user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            is_active=True
        )
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        print(f"Usuario de prueba creado: {test_user.username} (ID: {test_user.id})")
    except Exception as e:
        print(f"Error al crear el usuario de prueba: {e}")
    finally:
        db.close()

  
#$2b$12$FDjMADCMKpf9jDRusYRIG.umEFKnCootlq/dJrEBUqyGzCjlfGiHm
plain_password = "password123"  # Reemplaza con la contraseña que estás probando
hashed_password =   hashed_password = get_password_hash(plain_password)
if verify_password(plain_password, hashed_password):
    print("La contraseña es correcta")
else:
    print("La contraseña es incorrecta")

if __name__ == "__main__":
    create_test_user()
    verify_password(plain_password, hashed_password)