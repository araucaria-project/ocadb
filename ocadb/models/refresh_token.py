import secrets
import hashlib
from datetime import datetime
from beanie import Document


class RefreshTokenDocument(Document):
    token_hash: str
    username: str
    issued_at: datetime
    expires_at: datetime
    revoked: bool = False

    class Settings:
        name = "refresh_tokens"
        indexes = ["token_hash", "username", "expires_at"]

    @staticmethod
    def generate() -> tuple[str, str]:
        """Returns (raw_token, token_hash). Give raw to client, store hash."""
        raw = secrets.token_urlsafe(48)
        h = hashlib.sha256(raw.encode()).hexdigest()
        return raw, h
