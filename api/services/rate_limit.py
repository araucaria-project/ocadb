from datetime import datetime, timezone

from fastapi import Request
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ocadb.models.rate_limit import RateLimitCounter


class RateLimiter:
    """Fixed-window counters in Mongo; documents expire with their window."""

    @staticmethod
    async def hit(scope: str, key: str, limit: int, window_seconds: int) -> bool:
        """Count one request; return False once ``limit`` is exceeded in the current window."""
        now = datetime.now(timezone.utc)
        window_start = int(now.timestamp()) // window_seconds * window_seconds
        doc_key = f"{scope}:{key}:{window_start}"
        expires_at = datetime.fromtimestamp(window_start + window_seconds, timezone.utc)
        collection = RateLimitCounter.get_motor_collection()
        for _ in range(2):
            try:
                doc = await collection.find_one_and_update(
                    {"key": doc_key},
                    {"$inc": {"hits": 1}, "$setOnInsert": {"expires_at": expires_at}},
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )
                return doc["hits"] <= limit
            except DuplicateKeyError:
                # Two first hits raced on the upsert; the retry increments the winner's document.
                continue
        return False


def client_ip(request: Request) -> str:
    """Client address behind Cloudflare and/or Railway's proxy.

    Uses the header set by the closest proxy (the last X-Forwarded-For entry),
    since the leftmost entries can be supplied by the client.
    """
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"
