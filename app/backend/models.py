import sys
from pathlib import Path
from datetime import datetime 
from typing import List, Optional

# --- AJUSTE DE PATH ---
root_path = Path(__file__).resolve().parents[1]
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime, func, create_engine
from sqlalchemy.orm import relationship, sessionmaker
from pydantic import BaseModel, ConfigDict # Importamos ConfigDict
from backend import database
from backend.config import DATABASE_URL

# Configuración de Engine
engine = create_engine(DATABASE_URL)
Base = database.Base

# ==========================================
# 1. MODELOS DE BASE DE DATOS (SQLAlchemy)
# ==========================================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    registration_date = Column(DateTime, default=func.now())
    
    documents = relationship("Document", back_populates="owner")
    subscriptions = relationship("Subscription", back_populates="user")

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    upload_date = Column(DateTime, default=func.now())
    filename = Column(String)
    content = Column(String)
    
    owner = relationship("User", back_populates="documents")
    analysis_results = relationship("PlagiarismResult", back_populates="document")

class PlagiarismResult(Base):
    __tablename__ = "plagiarism_results"
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"))
    analysis_date = Column(DateTime, default=func.now())
    plagiarism_percentage_text = Column(Integer, nullable=True)
    plagiarism_details_text = Column(String, nullable=True)
    ai_detection_percentage = Column(Integer, nullable=True)
    ai_detection_details = Column(String, nullable=True)
    report_path = Column(String, nullable=True)
    
    document = relationship("Document", back_populates="analysis_results")

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    plan_name = Column(String)
    start_date = Column(DateTime, default=func.now())
    end_date = Column(DateTime)
    status = Column(String, default="active")
    
    user = relationship("User", back_populates="subscriptions")

# ==========================================
# 2. MODELOS DE VALIDACIÓN (Pydantic V2)
# ==========================================

# Definimos una configuración común para todos
shared_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

class UserBase(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    registration_date: datetime
    model_config = shared_config

class DocumentBase(BaseModel):
    id: int
    owner_id: int
    upload_date: datetime
    filename: str
    content: str
    model_config = shared_config

class PlagiarismResultBase(BaseModel):
    id: int
    document_id: int
    analysis_date: datetime
    plagiarism_percentage_text: Optional[int] = None
    plagiarism_details_text: Optional[str] = None
    ai_detection_percentage: Optional[int] = None
    ai_detection_details: Optional[str] = None
    report_path: Optional[str] = None
    model_config = shared_config

class SubscriptionBase(BaseModel):
    id: int
    user_id: int
    plan_name: str
    start_date: datetime
    end_date: datetime
    status: str
    model_config = shared_config

class TokenData(BaseModel):
    username: Optional[str] = None
    model_config = shared_config

# Crear tablas
Base.metadata.create_all(bind=engine)