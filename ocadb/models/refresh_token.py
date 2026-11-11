import secrets
import hashlib
from datetime import datetime
from typing import Optional
from beanie import Document
import pymongo
from pymongo import IndexModel


class RefreshTokenDocument(Document):
    token_hash: str
    username: str
    issued_at: datetime
    expires_at: datetime
    revoked: bool = False
    revoked_at: Optional[datetime] = None
    # All tokens descended from one login share a family; reuse of a rotated
    # token revokes the whole family. None for tokens issued before families.
    family_id: Optional[str] = None
    # Lifetime carried over on rotation, so a "remember this device" login
    # stays long-lived. None for legacy tokens (caller's default applies).
    lifetime_days: Optional[int] = None

    class Settings:
        name = "refresh_tokens"
        indexes = [
            "token_hash",
            "username",
            "family_id",
            IndexModel([("expires_at", pymongo.ASCENDING)], expireAfterSeconds=0),
        ]

    @staticmethod
    def generate() -> tuple[str, str]:
        """Returns (raw_token, token_hash). Give raw to client, store hash."""
        raw = secrets.token_urlsafe(48)
        h = hashlib.sha256(raw.encode()).hexdigest()
        return raw, h
