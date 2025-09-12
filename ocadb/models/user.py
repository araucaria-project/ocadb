from beanie import Document
from pydantic import BaseModel
from typing import Optional


class User(BaseModel):
    """Base user model for API responses (without password)"""
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None


class UserInDB(Document, User):
    """User document stored in MongoDB (includes hashed password)"""
    hashed_password: str

    class Settings:
        name = "users"