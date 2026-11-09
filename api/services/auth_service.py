import os
import logging
import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError, ExpiredSignatureError
from datetime import datetime, timedelta, timezone

from api.services.crypto_service import CryptoService
from api.services.database_connection import DatabaseConnection
from ocadb.models import UserInDB
from ocadb.models.refresh_token import RefreshTokenDocument

from api import config

log = logging.getLogger(__name__)

class AuthService:
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token")
    env_settings = config.Settings()

    # load settings from environment file
    _SECRET_KEY = env_settings.JWT_SECRET_KEY
    _ALGORITHM = env_settings.ALGORITHM
    ACCESS_TOKEN_EXPIRE_MINUTES = int(env_settings.ACCESS_TOKEN_EXPIRE_MINUTES) # int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    # Checked against when the user does not exist, so a failed login costs one
    # bcrypt verification either way and response time does not reveal accounts.
    _DUMMY_PASSWORD_HASH = CryptoService.get_password_hash(secrets.token_urlsafe(16))

    # A rotated refresh token presented again within this window is treated as a
    # benign race (two tabs refreshing at once), not as theft.
    REFRESH_REUSE_GRACE_SECONDS = 30

    @staticmethod
    def create_access_token(data: dict, expires_delta: timedelta | None = None):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, AuthService._SECRET_KEY, algorithm=AuthService._ALGORITHM)

        return encoded_jwt

    @staticmethod
    async def authenticate_user(username: str, password: str):
        user = await DatabaseConnection.get_user(username)
        has_password = bool(user and user.hashed_password)
        hashed_password = user.hashed_password if has_password else AuthService._DUMMY_PASSWORD_HASH
        password_ok = CryptoService.verify_password(password, hashed_password)
        if not has_password or not password_ok or user.disabled:
            return False
        return user

    @staticmethod
    async def create_refresh_token(username: str, expire_days: int, family_id: str | None = None) -> str:
        raw, token_hash = RefreshTokenDocument.generate()
        now = datetime.now(timezone.utc)
        await RefreshTokenDocument(
            token_hash=token_hash,
            username=username,
            issued_at=now,
            expires_at=now + timedelta(days=expire_days),
            family_id=family_id or secrets.token_hex(16),
            lifetime_days=expire_days,
        ).insert()
        return raw

    @staticmethod
    async def _revoke_family(family_id: str, now: datetime) -> None:
        await RefreshTokenDocument.get_motor_collection().update_many(
            {"family_id": family_id, "revoked": False},
            {"$set": {"revoked": True, "revoked_at": now}},
        )

    @staticmethod
    async def rotate_refresh_token(raw_token: str, expire_days: int) -> tuple[str, str]:
        """Exchange a refresh token for a new access + refresh token pair.

        ``expire_days`` applies only to legacy tokens; newer tokens keep the
        lifetime they were issued with (7 days, or longer for remembered devices).
        """
        invalid = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked refresh token",
        )
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        now = datetime.now(timezone.utc)
        # Claim the token atomically, so two concurrent requests cannot both rotate it.
        doc = await RefreshTokenDocument.get_motor_collection().find_one_and_update(
            {"token_hash": token_hash, "revoked": False},
            {"$set": {"revoked": True, "revoked_at": now}},
        )
        if doc is None:
            await AuthService._handle_reused_refresh_token(token_hash, now)
            raise invalid
        expires_at = doc["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired",
            )
        user = await DatabaseConnection.get_user(doc["username"])
        if user is None or user.disabled:
            raise invalid
        access_token = AuthService.create_access_token(
            data={"sub": user.username},
            expires_delta=timedelta(minutes=AuthService.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        new_refresh = await AuthService.create_refresh_token(
            user.username,
            doc.get("lifetime_days") or expire_days,
            family_id=doc.get("family_id"),
        )
        return access_token, new_refresh

    @staticmethod
    async def _handle_reused_refresh_token(token_hash: str, now: datetime) -> None:
        """A revoked token came back. Outside the grace window that means it was
        copied, so every token of its login is revoked."""
        doc = await RefreshTokenDocument.find_one(RefreshTokenDocument.token_hash == token_hash)
        if doc is None or doc.family_id is None:
            return
        revoked_at = doc.revoked_at
        if revoked_at is not None:
            if revoked_at.tzinfo is None:
                revoked_at = revoked_at.replace(tzinfo=timezone.utc)
            if now - revoked_at < timedelta(seconds=AuthService.REFRESH_REUSE_GRACE_SECONDS):
                return
        log.warning("Reuse of revoked refresh token for user %s; revoking its token family", doc.username)
        await AuthService._revoke_family(doc.family_id, now)

    @staticmethod
    async def revoke_refresh_token(raw_token: str) -> None:
        """Log out: revoke the token and every other token of the same login."""
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        doc = await RefreshTokenDocument.find_one(RefreshTokenDocument.token_hash == token_hash)
        if doc is None:
            return
        now = datetime.now(timezone.utc)
        if doc.family_id:
            await AuthService._revoke_family(doc.family_id, now)
        elif not doc.revoked:
            doc.revoked = True
            doc.revoked_at = now
            await doc.replace()

    @staticmethod
    async def revoke_user_refresh_tokens(username: str, keep_refresh_token: str | None = None) -> None:
        """Log the user out everywhere, except the login that ``keep_refresh_token`` belongs to."""
        query: dict = {"username": username, "revoked": False}
        if keep_refresh_token:
            token_hash = hashlib.sha256(keep_refresh_token.encode()).hexdigest()
            keep = await RefreshTokenDocument.find_one(RefreshTokenDocument.token_hash == token_hash)
            if keep is not None and keep.username == username and keep.family_id:
                query["family_id"] = {"$ne": keep.family_id}
        await RefreshTokenDocument.get_motor_collection().update_many(
            query, {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc)}},
        )

    @staticmethod
    async def user_from_token(token: str) -> UserInDB:
        """Decode an access token and return its user, rejecting unknown and disabled users."""
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            # here is checked expiration date also
            payload = jwt.decode(token, AuthService._SECRET_KEY, algorithms=[AuthService._ALGORITHM])
        except (ExpiredSignatureError, JWTError):
            raise credentials_exception
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
        user = await DatabaseConnection.get_user(username)
        if user is None or user.disabled:
            raise credentials_exception
        return user

    @staticmethod
    async def validate_token(token: Annotated[str, Depends(oauth2_scheme)]) -> str:
        """Dependency returning the raw token, for endpoints that still take it.
        Prefer ``current_user`` in new code."""
        await AuthService.user_from_token(token)
        return token

    @staticmethod
    async def current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> UserInDB:
        return await AuthService.user_from_token(token)

    @staticmethod
    async def current_moderator(token: Annotated[str, Depends(oauth2_scheme)]) -> UserInDB:
        user = await AuthService.user_from_token(token)
        if not user.moderator:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    @staticmethod
    async def require_moderator(token: Annotated[str, Depends(oauth2_scheme)]) -> str:
        """Like current_moderator, but returns the username."""
        user = await AuthService.current_moderator(token)
        return user.username
