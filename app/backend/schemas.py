from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime

class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    is_active: bool
    registration_date: datetime
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True,orm_mode=True)
class Token(BaseModel):
    access_token: str
    token_type: str
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True,orm_mode =True)

   
class DocumentBase(BaseModel):
    filename: str

class Document(DocumentBase):
    id: int
    owner_id: int
    upload_date: datetime
    content: str
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True,orm_mode=True)

class PlagiarismResultBase(BaseModel):
    plagiarism_percentage_text: Optional[int]
    plagiarism_details_text: Optional[Dict[str, Any]]  # Usar Dict[str, Any]
    ai_detection_percentage: Optional[int]
    ai_detection_details: Optional[Dict[str, Any]] # Usar Dict[str, Any]
    report_path: Optional[str]
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True,orm_mode=True)
class PlagiarismResult(PlagiarismResultBase):
    id: int
    document_id: int
    analysis_date: datetime
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True,orm_mode=True)

