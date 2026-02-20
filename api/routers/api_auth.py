from datetime import timedelta
from typing import Annotated, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordRequestFormStrict
from pydantic import BaseModel

from api.services.auth_service import AuthService
from api.schemas import Token
from ocadb.models import User, UserInDB
from api.services.database_connection import DatabaseConnection
from api.services.crypto_service import CryptoService

router = APIRouter(prefix="/auth", tags=["authentication"])


class UserCreate(BaseModel):
    username: str
    email: str
    full_name: str
    password: str
    access_tags: list[str]


@router.post("/token/")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestFormStrict, Depends()]
) -> Token:
    user = await AuthService.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=AuthService.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = AuthService.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


@router.post("/register/", response_model=User)
async def register_user(user_data: UserCreate,
                        token: Annotated[str, Depends(AuthService.validate_token)]):
    # Extract username from token
    from jose import jwt
    payload = jwt.decode(token, AuthService._SECRET_KEY, algorithms=[AuthService._ALGORITHM])
    moduser = payload.get("sub")

    mod_user = await DatabaseConnection.get_user(moduser)

    if mod_user.moderator == True:
        """Register a new user"""
        # Check if user already exists
        existing_user = await DatabaseConnection.get_user(user_data.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered"
            )

        # Hash password and create user
        hashed_password = CryptoService.get_password_hash(user_data.password)
        user = await DatabaseConnection.create_user(
            username=user_data.username,
            email=user_data.email,
            full_name=user_data.full_name,
            hashed_password=hashed_password,
            access_tags=user_data.access_tags
        )

        # Return user without password
        return User(
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            disabled=user.disabled,
            access_tags=user_data.access_tags
        )
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions to register users")

@router.get("/me/", response_model=User)
async def read_users_me(token: Annotated[str, Depends(AuthService.validate_token)]):
    """Get current user info"""
    # Extract username from token
    from jose import jwt
    payload = jwt.decode(token, AuthService._SECRET_KEY, algorithms=[AuthService._ALGORITHM])
    username = payload.get("sub")
    
    user = await DatabaseConnection.get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return User(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        disabled=user.disabled,
        access_tags=user.access_tags
    )

@router.get("/user/{username}/", response_model=User)
async def read_users_username(token: Annotated[str, Depends(AuthService.validate_token)],
                              username: str):
    # Extract username from token
    from jose import jwt
    payload = jwt.decode(token, AuthService._SECRET_KEY, algorithms=[AuthService._ALGORITHM])
    moduser = payload.get("sub")

    mod_user = await DatabaseConnection.get_user(moduser)

    if mod_user.moderator == True:
        user = await DatabaseConnection.get_user(username)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        else:
            return User(
                username=user.username,
                email=user.email,
                full_name=user.full_name,
                disabled=user.disabled,
                access_tags=user.access_tags
            )
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions to read user")

@router.put("/user/{username}/", response_model=User)
async def update_users_username(token: Annotated[str, Depends(AuthService.validate_token)],
                              upd_user: Annotated[Dict[str, Any], Body(...)],
                              username: str):
    # Extract username from token
    from jose import jwt
    payload = jwt.decode(token, AuthService._SECRET_KEY, algorithms=[AuthService._ALGORITHM])
    moduser = payload.get("sub")

    mod_user = await DatabaseConnection.get_user(moduser)

    if mod_user.moderator == True:
        user = await DatabaseConnection.get_user(username)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        else:
            if "email" in upd_user:
                user.email = upd_user["email"]
            if "full_name" in upd_user:
                user.full_name = upd_user["full_name"]
            if "access_tags" in upd_user:
                user.access_tags = upd_user["access_tags"]
            if "disabled" in upd_user:
                user.disabled = upd_user["disabled"]

            await user.replace()

            return user
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions to update user")