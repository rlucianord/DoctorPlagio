import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase # Cambio a DeclarativeBase

# --- AJUSTE DE PATH ---
# Esto asegura que siempre encuentre 'backend.config' subiendo un nivel
root_path = Path(__file__).resolve().parents[1]
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))

from backend.config import DATABASE_URL 

# --- CONFIGURACIÓN DB ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Nueva forma SQLAlchemy 2.0 (Adiós Warnings)
class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()