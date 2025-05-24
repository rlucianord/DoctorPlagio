import sys
from pathlib import Path
sys.path[0] = str(Path(sys.path[0]).parent)
print(sys.path[1])
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime, func
from sqlalchemy.orm import relationship
from backend import database
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime 
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker 
from sqlalchemy.ext.declarative import declarative_base

from backend.config import DATABASE_URL
# Database URL (replace with your actual database URL)

# Create the database engine
engine = create_engine(DATABASE_URL)
Base=database.Base
# Create tables if they do not exist


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
    class Config:
        arbitrary_types_allowed = True
        from_attributes = True
        orm_mode = True

class Document(Base):
    __tablename__ = "documents"
   
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    upload_date = Column(DateTime, default=func.now())
    filename = Column(String)
    content = Column(String) # O podrías guardar la ruta al archivo en un sistema de almacenamiento
    analysis_results = relationship("PlagiarismResult", back_populates="document")
    owner = relationship("User", back_populates="documents")
    class Config:
        arbitrary_types_allowed = True
        from_attributes = True
        orm_mode = True

class PlagiarismResult(Base):
    __tablename__ = "plagiarism_results"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"))
    analysis_date = Column(DateTime, default=func.now())
    plagiarism_percentage_text = Column(Integer, nullable=True)
    plagiarism_details_text = Column(String, nullable=True) # JSON con detalles
    ai_detection_percentage = Column(Integer, nullable=True)
    ai_detection_details = Column(String, nullable=True) # JSON con detalles
    report_path = Column(String, nullable=True)
    document = relationship("Document", back_populates="analysis_results")
    class Config:
        arbitrary_types_allowed = True
        from_attributes = True
        orm_mode = True
# from_attributes = True
# Pydantic models for FastAPI response
class UserBase(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    registration_date: datetime
    class Config:
        orm_mode = True
        from_attributes = True
        arbitrary_types_allowed = True
         

   
class DocumentBase(BaseModel):
    id: int
    owner_id: int
    upload_date: datetime
    filename: str
    content: str
    class Config:
        orm_mode = True
        from_attributes = True
        arbitrary_types_allowed = True

class PlagiarismResultBase(BaseModel):
    id: int
    document_id: int
    analysis_date: datetime
    plagiarism_percentage_text: Optional[int]
    plagiarism_details_text: Optional[str]
    ai_detection_percentage: Optional[int]
    ai_detection_details: Optional[str]
    report_path: Optional[str]
    class Config:
        from_attributes = True
        arbitrary_types_allowed = True
        orm_mode = True

class SubscriptionBase(BaseModel):
    id: int
    user_id: int
    plan_name: str
    start_date: datetime
    end_date: datetime
    status: str
    class Config:
        from_attributes = True
        arbitrary_types_allowed = True
        orm_mode = True
class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    plan_name = Column(String)
    start_date = Column(DateTime, default=func.now())
    end_date = Column(DateTime)
    status = Column(String, default="active")
    user = relationship("User", back_populates="subscriptions")
    class Config:
        from_attributes = True
        arbitrary_types_allowed = True
        orm_mode = True

class TokenData(BaseModel):
    username: Optional[str] = None
    class Config:
            arbitrary_types_allowed = True
            from_attributes = True    
    # class Config:
    #     arbitrary_types_allowed = True
    #     from_attributes = True


Base.metadata.create_all(bind=engine, checkfirst=True, tables=[User.__table__, Document.__table__, PlagiarismResult.__table__, Subscription.__table__])        