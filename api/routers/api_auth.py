from datetime import timedelta
from typing import Annotated, Dict, Any, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Body, Form, Request, Response
from fastapi.responses import PlainTextResponse
from fastapi.security import OAuth2PasswordRequestFormStrict
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError
from starlette.responses import JSONResponse

from api.services.auth_service import AuthService
from api.schemas import Token, TokenPair, RefreshRequest, CodeRequest, CodeVerifyRequest, PasswordChangeRequest
from api import config
from ocadb.models import User, UserInDB
from api.services.database_connection import DatabaseConnection
from api.services.crypto_service import CryptoService
from api.services.email import EmailSender, get_email_sender
from api.services.login_code_service import LoginCodeService
from api.services.rate_limit import client_ip
from ocadb.models.user import normalize_email

router = APIRouter(prefix="/auth", tags=["authentication"])

_REFRESH_EXPIRE_DAYS = int(config.Settings().REFRESH_TOKEN_EXPIRE_DAYS)
_REMEMBER_DEVICE_REFRESH_EXPIRE_DAYS = int(config.Settings().REMEMBER_DEVICE_REFRESH_TOKEN_EXPIRE_DAYS)


class UserCreate(BaseModel):
    username: str
    email: str
    full_name: str
    password: Optional[str] = None  # None: the user logs in with emailed codes
    access_tags: list[str]

@router.post("/plaintoken/", response_class=PlainTextResponse)
async def login_for_plain_access_token(
        form_data: Annotated[OAuth2PasswordRequestFormStrict, Depends()]
) -> PlainTextResponse:
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

    return PlainTextResponse(content=access_token)

@router.post("/token/")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestFormStrict, Depends()],
    remember: Annotated[bool, Form(description="Remember this device: long-lived refresh token")] = False,
) -> TokenPair:
    user = await AuthService.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await _issue_token_pair(user.username, remember)


async def _issue_token_pair(username: str, remember: bool) -> TokenPair:
    access_token_expires = timedelta(minutes=AuthService.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = AuthService.create_access_token(
        data={"sub": username}, expires_delta=access_token_expires
    )
    refresh_days = _REMEMBER_DEVICE_REFRESH_EXPIRE_DAYS if remember else _REFRESH_EXPIRE_DAYS
    refresh_token = await AuthService.create_refresh_token(username, refresh_days)
    return TokenPair(access_token=access_token, refresh_token=refresh_token, token_type="bearer")


@router.post("/refresh/")
async def refresh_access_token(body: RefreshRequest) -> TokenPair:
    new_access, new_refresh = await AuthService.rotate_refresh_token(body.refresh_token, _REFRESH_EXPIRE_DAYS)
    return TokenPair(access_token=new_access, refresh_token=new_refresh, token_type="bearer")


@router.post("/logout/", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest) -> Response:
    """Revoke the refresh token and all tokens of the same login. Always 204."""
    await AuthService.revoke_refresh_token(body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/code/request/", status_code=status.HTTP_202_ACCEPTED)
async def request_login_code(body: CodeRequest,
                             request: Request,
                             background_tasks: BackgroundTasks,
                             sender: Annotated[EmailSender, Depends(get_email_sender)]):
    """Email a one-time login code. Always 202, whether or not the account exists."""
    background_tasks.add_task(LoginCodeService.request_code, body.identifier, client_ip(request), sender, body.return_to)
    return {"detail": "If this account exists and has an email address, a login code has been sent."}


@router.post("/code/verify/")
async def verify_login_code(body: CodeVerifyRequest, request: Request) -> TokenPair:
    if not await LoginCodeService.ip_may_verify(client_ip(request)):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts, try again later")
    user = await LoginCodeService.verify_code(body.identifier, body.code)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired code")
    return await _issue_token_pair(user.username, body.remember)


@router.post("/password/", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: PasswordChangeRequest,
                          user: Annotated[UserInDB, Depends(AuthService.current_user)]) -> Response:
    """Set or change the password; logs out all other sessions."""
    if user.hashed_password and not (
            body.current_password and CryptoService.verify_password(body.current_password, user.hashed_password)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Current password is incorrect")
    await user.set({UserInDB.hashed_password: CryptoService.get_password_hash(body.new_password)})
    await AuthService.revoke_user_refresh_tokens(user.username, keep_refresh_token=body.keep_refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _email_in_use() -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already in use")


def _public_user(user: UserInDB) -> User:
    return User(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        disabled=user.disabled,
        moderator=user.moderator,
        access_tags=user.access_tags
    )


@router.post("/register/", response_model=User)
async def register_user(user_data: UserCreate,
                        mod_user: Annotated[UserInDB, Depends(AuthService.current_moderator)]):
    """Register a new user"""
    # Check if user already exists
    existing_user = await DatabaseConnection.get_user(user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )

    # Hash password and create user
    hashed_password = CryptoService.get_password_hash(user_data.password) if user_data.password else None
    try:
        user = await DatabaseConnection.create_user(
            username=user_data.username,
            email=user_data.email,
            full_name=user_data.full_name,
            hashed_password=hashed_password,
            access_tags=user_data.access_tags
        )
    except DuplicateKeyError:
        raise _email_in_use()

    # Return user without password
    return User(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        disabled=user.disabled,
        access_tags=user_data.access_tags
    )

@router.get("/me/", response_model=User)
async def read_users_me(token: Annotated[str, Depends(AuthService.oauth2_scheme)]):
    """Get current user info.

    Also called directly as ``read_users_me(token)`` by other routers.
    """
    user = await AuthService.user_from_token(token)
    return _public_user(user)

@router.get("/user/{username}/", response_model=User)
async def read_users_username(mod_user: Annotated[UserInDB, Depends(AuthService.current_moderator)],
                              username: str):
    user = await DatabaseConnection.get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _public_user(user)

@router.get("/user/viewer_conf", response_class=JSONResponse)
async def get_viewer_conf(
        user: Annotated[UserInDB, Depends(AuthService.current_user)]
):
    return user.viewer_conf

@router.put("/user/viewer_conf", status_code=200, response_class=JSONResponse)
async def put_viewer_conf(
        viewer_conf: dict,
        user: Annotated[UserInDB, Depends(AuthService.current_user)]
):
    await user.update({"$set": {"viewer_conf": viewer_conf}})
    return viewer_conf

@router.put("/user/{username}/", response_model=User)
async def update_users_username(mod_user: Annotated[UserInDB, Depends(AuthService.current_moderator)],
                                upd_user: Annotated[Dict[str, Any], Body(...)],
                                username: str):
    user = await DatabaseConnection.get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if "email" in upd_user:
        user.email = normalize_email(upd_user["email"])
    if "full_name" in upd_user:
        user.full_name = upd_user["full_name"]
    if "access_tags" in upd_user:
        user.access_tags = upd_user["access_tags"]
    if "disabled" in upd_user:
        user.disabled = upd_user["disabled"]

    try:
        await user.replace()
    except DuplicateKeyError:
        raise _email_in_use()

    return user
