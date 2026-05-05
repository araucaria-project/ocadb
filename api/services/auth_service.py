import os
import logging
import hashlib
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError, ExpiredSignatureError
from datetime import datetime, timedelta, timezone

from api.services.crypto_service import CryptoService
from api.services.database_connection import DatabaseConnection
from api.schemas import TokenData
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
        if not user:
            return False
        if not CryptoService.verify_password(password, user.hashed_password):
            return False
        return user

    @staticmethod
    async def create_refresh_token(username: str, expire_days: int) -> str:
        raw, token_hash = RefreshTokenDocument.generate()
        now = datetime.now(timezone.utc)
        await RefreshTokenDocument(
            token_hash=token_hash,
            username=username,
            issued_at=now,
            expires_at=now + timedelta(days=expire_days),
        ).insert()
        return raw

    @staticmethod
    async def rotate_refresh_token(raw_token: str, expire_days: int) -> tuple[str, str]:
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        doc = await RefreshTokenDocument.find_one(RefreshTokenDocument.token_hash == token_hash)
        if doc is None or doc.revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked refresh token",
            )
        expires_at = doc.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired",
            )
        doc.revoked = True
        await doc.replace()
        access_token = AuthService.create_access_token(
            data={"sub": doc.username},
            expires_delta=timedelta(minutes=AuthService.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        new_refresh = await AuthService.create_refresh_token(doc.username, expire_days)
        return access_token, new_refresh

    @staticmethod
    async def validate_token(token: Annotated[str, Depends(oauth2_scheme)]):
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            # here is checked expiration date also
            payload = jwt.decode(token, AuthService._SECRET_KEY, algorithms=[AuthService._ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise credentials_exception
            expires = payload.get("exp")
            token_data = TokenData(username=username, expires=expires)
        except ExpiredSignatureError:
            raise credentials_exception
        except JWTError:
            raise credentials_exception
        return token
