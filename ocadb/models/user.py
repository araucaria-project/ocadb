from beanie import Document
from pydantic import BaseModel, field_validator
from pymongo import ASCENDING, IndexModel
from typing import Optional


def normalize_email(email: Optional[str]) -> Optional[str]:
    """Lowercase and strip an email; empty becomes None."""
    if email is None:
        return None
    email = email.strip().lower()
    return email or None


class User(BaseModel):
    """Base user model for API responses (without password)"""
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    moderator: Optional[bool] = None
    access_tags: Optional[list[str]] = None
    viewer_conf: Optional[dict] = {}

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: Optional[str]) -> Optional[str]:
        return normalize_email(v)


class UserInDB(Document, User):
    """User document stored in MongoDB (includes hashed password)"""
    # None for accounts that log in with emailed codes only
    hashed_password: Optional[str] = None

    def __str__(self):
        return (f"> username: {self.username}\n> full name: {self.full_name}\n"
                f"> email: {self.email}\n> access tags: {self.access_tags}")

    class Settings:
        name = "users"
        indexes = [
            # Unique among users that have an email; users without one are not indexed.
            IndexModel([("email", ASCENDING)], name="email_unique", unique=True,
                       partialFilterExpression={"email": {"$gt": ""}}),
        ]
