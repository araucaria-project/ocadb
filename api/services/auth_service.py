import os
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError, ExpiredSignatureError
from datetime import datetime, timedelta, timezone

from api.services.crypto_service import CryptoService
from api.services.database_connection import DatabaseConnection
from api.schemas import TokenData


class AuthService:

    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token")

    _SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback-secret-key-for-development-only")
    _ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

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
