from datetime import datetime
from beanie import Document
import pymongo
from pymongo import IndexModel


class RateLimitCounter(Document):
    """Request count for one fixed time window, e.g. key "code_request:ip:1.2.3.4:1762700400"."""
    key: str
    hits: int = 0
    expires_at: datetime

    class Settings:
        name = "rate_limits"
        indexes = [
            IndexModel([("key", pymongo.ASCENDING)], unique=True),
            IndexModel([("expires_at", pymongo.ASCENDING)], expireAfterSeconds=0),
        ]


document_models = [RateLimitCounter]
