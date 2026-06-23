"""Tests for AuthService: token creation, validation, refresh rotation."""
import pytest
from datetime import timedelta, datetime, timezone

from jose import jwt
from api.services.auth_service import AuthService
from api.services.crypto_service import CryptoService
from ocadb.models import UserInDB


# --- create_access_token ---

def test_create_access_token_returns_string():
    token = AuthService.create_access_token(data={"sub": "alice"})
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_access_token_contains_sub():
    token = AuthService.create_access_token(data={"sub": "alice"})
    payload = jwt.decode(token, AuthService._SECRET_KEY, algorithms=[AuthService._ALGORITHM])
    assert payload["sub"] == "alice"


def test_create_access_token_contains_expiry():
    token = AuthService.create_access_token(data={"sub": "alice"})
    payload = jwt.decode(token, AuthService._SECRET_KEY, algorithms=[AuthService._ALGORITHM])
    assert "exp" in payload


def test_create_access_token_custom_expiry():
    expires = timedelta(hours=2)
    before = datetime.now(timezone.utc)
    token = AuthService.create_access_token(data={"sub": "alice"}, expires_delta=expires)
    payload = jwt.decode(token, AuthService._SECRET_KEY, algorithms=[AuthService._ALGORITHM])
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    assert exp > before + timedelta(hours=1, minutes=55)


def test_create_access_token_default_expiry_is_15min():
    before = datetime.now(timezone.utc)
    token = AuthService.create_access_token(data={"sub": "alice"})
    payload = jwt.decode(token, AuthService._SECRET_KEY, algorithms=[AuthService._ALGORITHM])
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    assert exp < before + timedelta(minutes=16)
    assert exp > before + timedelta(minutes=14)


# --- validate_token ---

async def test_validate_token_valid(beanie):
    token = AuthService.create_access_token(
        data={"sub": "testuser"}, expires_delta=timedelta(minutes=30)
    )
    result = await AuthService.validate_token(token)
    assert result == token


async def test_validate_token_expired(beanie):
    from fastapi import HTTPException
    token = AuthService.create_access_token(
        data={"sub": "testuser"}, expires_delta=timedelta(seconds=-1)
    )
    with pytest.raises(HTTPException) as exc:
        await AuthService.validate_token(token)
    assert exc.value.status_code == 401


async def test_validate_token_garbage(beanie):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await AuthService.validate_token("not.a.jwt")
    assert exc.value.status_code == 401


# --- authenticate_user ---

async def test_authenticate_user_correct_credentials(beanie):
    user = UserInDB(
        username="loginuser",
        email="login@test.com",
        full_name="Login User",
        hashed_password=CryptoService.get_password_hash("secret123"),
        moderator=False,
        access_tags=[],
    )
    await user.insert()
    result = await AuthService.authenticate_user("loginuser", "secret123")
    assert result is not False
    assert result.username == "loginuser"


async def test_authenticate_user_wrong_password(beanie):
    user = UserInDB(
        username="loginuser2",
        email="login2@test.com",
        full_name="Login User2",
        hashed_password=CryptoService.get_password_hash("correct"),
        moderator=False,
        access_tags=[],
    )
    await user.insert()
    result = await AuthService.authenticate_user("loginuser2", "wrong")
    assert result is False


async def test_authenticate_user_nonexistent(beanie):
    result = await AuthService.authenticate_user("nobody", "pass")
    assert result is False


# --- create_refresh_token + rotate_refresh_token ---

async def test_create_refresh_token_returns_string(beanie):
    token = await AuthService.create_refresh_token("alice", expire_days=7)
    assert isinstance(token, str)
    assert len(token) > 0


async def test_rotate_refresh_token_returns_new_pair(beanie):
    raw = await AuthService.create_refresh_token("alice", expire_days=7)
    access, new_refresh = await AuthService.rotate_refresh_token(raw, expire_days=7)
    assert isinstance(access, str)
    assert isinstance(new_refresh, str)
    assert new_refresh != raw


async def test_rotate_refresh_token_revokes_old(beanie):
    from fastapi import HTTPException
    raw = await AuthService.create_refresh_token("alice", expire_days=7)
    await AuthService.rotate_refresh_token(raw, expire_days=7)
    with pytest.raises(HTTPException) as exc:
        await AuthService.rotate_refresh_token(raw, expire_days=7)
    assert exc.value.status_code == 401


async def test_rotate_refresh_token_invalid_raises(beanie):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await AuthService.rotate_refresh_token("invalid-token", expire_days=7)
    assert exc.value.status_code == 401


async def test_rotate_refresh_token_expired_raises(beanie):
    from fastapi import HTTPException
    from ocadb.models.refresh_token import RefreshTokenDocument
    import hashlib
    import secrets
    raw = secrets.token_urlsafe(48)
    h = hashlib.sha256(raw.encode()).hexdigest()
    past = datetime.now(timezone.utc) - timedelta(days=1)
    await RefreshTokenDocument(
        token_hash=h,
        username="alice",
        issued_at=past - timedelta(days=8),
        expires_at=past,
    ).insert()
    with pytest.raises(HTTPException) as exc:
        await AuthService.rotate_refresh_token(raw, expire_days=7)
    assert exc.value.status_code == 401
