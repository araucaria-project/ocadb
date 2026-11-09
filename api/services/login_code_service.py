import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from pymongo import ReturnDocument

from api import config
from api.services.database_connection import DatabaseConnection
from api.services.email import EmailMessage, EmailSender
from api.services.rate_limit import RateLimiter
from ocadb.models import UserInDB
from ocadb.models.login_code import LoginCode

log = logging.getLogger(__name__)


class LoginCodeService:
    env_settings = config.Settings()

    CODE_LENGTH = 6
    CODE_TTL_MINUTES = 10
    MAX_ATTEMPTS = 5

    # (limit, window in seconds)
    REQUESTS_PER_IDENTIFIER = (3, 15 * 60)
    REQUESTS_PER_IP = (20, 60 * 60)
    VERIFICATIONS_PER_IP = (30, 60 * 60)

    @staticmethod
    def _hash(username: str, code: str) -> str:
        # Keyed, so a leaked database does not let anyone brute-force 10^6 codes offline.
        key = LoginCodeService.env_settings.JWT_SECRET_KEY.encode()
        return hmac.new(key, f"{username}:{code}".encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _login_link(username: str, code: str, return_to: str | None) -> str:
        path = return_to if return_to and return_to.startswith("/") and not return_to.startswith("//") else "/"
        # Fragment, not query: it is never sent to the server hosting the frontend.
        fragment = urlencode({"login_id": username, "login_code": code})
        return f"{LoginCodeService.env_settings.FRONTEND_URL.rstrip('/')}{path}#{fragment}"

    @staticmethod
    def _message(user: UserInDB, code: str, return_to: str | None) -> EmailMessage:
        link = LoginCodeService._login_link(user.username, code, return_to)
        text = (
            f"Your OCADB login code is:\n\n"
            f"    {code}\n\n"
            f"It is valid for {LoginCodeService.CODE_TTL_MINUTES} minutes and can be used once.\n\n"
            f"Or open this link on the same device:\n{link}\n\n"
            f"Your Araucaria ID is: {user.username}\n"
            f"Prefer a password? You can set one in OCADB after logging in.\n\n"
            f"If you did not try to log in, ignore this email.\n"
        )
        return EmailMessage(to=user.email, subject=f"OCADB login code: {code}", text=text)

    @staticmethod
    async def request_code(identifier: str, ip: str, sender: EmailSender, return_to: str | None = None) -> None:
        """Send a login code if the identifier matches an active user with an email.

        Runs as a background task; whatever happens, the caller already answered 202.
        """
        identifier_key = identifier.strip().lower()
        allowed_identifier = await RateLimiter.hit("code_request:id", identifier_key, *LoginCodeService.REQUESTS_PER_IDENTIFIER)
        allowed_ip = await RateLimiter.hit("code_request:ip", ip, *LoginCodeService.REQUESTS_PER_IP)
        if not (allowed_identifier and allowed_ip):
            log.info("Login code request rate-limited (ip %s)", ip)
            return
        user = await DatabaseConnection.get_user_by_identifier(identifier)
        if user is None or user.disabled or not user.email:
            return
        code = f"{secrets.randbelow(10 ** LoginCodeService.CODE_LENGTH):0{LoginCodeService.CODE_LENGTH}d}"
        now = datetime.now(timezone.utc)
        # Only the newest code is valid.
        await LoginCode.find(LoginCode.username == user.username).delete()
        await LoginCode(
            username=user.username,
            code_hash=LoginCodeService._hash(user.username, code),
            issued_at=now,
            expires_at=now + timedelta(minutes=LoginCodeService.CODE_TTL_MINUTES),
        ).insert()
        await sender.send(LoginCodeService._message(user, code, return_to))

    @staticmethod
    async def ip_may_verify(ip: str) -> bool:
        return await RateLimiter.hit("code_verify:ip", ip, *LoginCodeService.VERIFICATIONS_PER_IP)

    @staticmethod
    async def verify_code(identifier: str, code: str) -> UserInDB | None:
        """Return the user if the code is right; consumes the code on success."""
        user = await DatabaseConnection.get_user_by_identifier(identifier)
        if user is None or user.disabled:
            return None
        now = datetime.now(timezone.utc)
        collection = LoginCode.get_motor_collection()
        # Counting the attempt and checking the limit in one update keeps
        # parallel guesses from exceeding MAX_ATTEMPTS.
        doc = await collection.find_one_and_update(
            {
                "username": user.username,
                "used": False,
                "expires_at": {"$gt": now},
                "attempts": {"$lt": LoginCodeService.MAX_ATTEMPTS},
            },
            {"$inc": {"attempts": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            return None
        if not hmac.compare_digest(doc["code_hash"], LoginCodeService._hash(user.username, code.strip())):
            return None
        result = await collection.update_one({"_id": doc["_id"], "used": False}, {"$set": {"used": True}})
        if result.modified_count != 1:
            return None
        return user
