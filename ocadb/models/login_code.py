from datetime import datetime
from beanie import Document
import pymongo
from pymongo import IndexModel


class LoginCode(Document):
    """One-time login code sent by email. Only the HMAC of the code is stored."""
    username: str
    code_hash: str
    issued_at: datetime
    expires_at: datetime
    attempts: int = 0
    used: bool = False

    class Settings:
        name = "login_codes"
        indexes = [
            "username",
            IndexModel([("expires_at", pymongo.ASCENDING)], expireAfterSeconds=0),
        ]


document_models = [LoginCode]
