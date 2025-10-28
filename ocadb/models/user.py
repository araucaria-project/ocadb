from beanie import Document
from pydantic import BaseModel
from typing import Optional


class User(BaseModel):
    """Base user model for API responses (without password)"""
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    access_tags: Optional[list[str]] = None


class UserInDB(Document, User):
    """User document stored in MongoDB (includes hashed password)"""
    hashed_password: str

    def __str__(self):
        return "> username: " + self.username + "\n" + "> full name: " + self.full_name + "\n" + "> email: " + self.email + "\n" + "> access tags: " + str(
            self.access_tags)

    class Settings:
        name = "users"