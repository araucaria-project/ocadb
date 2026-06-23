"""Integration tests for /api/v1/auth/* endpoints."""
import pytest
from httpx import AsyncClient

from ocadb.models import UserInDB
from api.services.crypto_service import CryptoService
from api.services.auth_service import AuthService
from datetime import timedelta


# --- POST /api/v1/auth/token/ ---

async def test_login_returns_token_pair(client, regular_user):
    resp = await client.post(
        "/api/v1/auth/token/",
        data={"username": "testuser", "password": "testpass123", "grant_type": "password"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_password_returns_401(client, regular_user):
    resp = await client.post(
        "/api/v1/auth/token/",
        data={"username": "testuser", "password": "wrongpass", "grant_type": "password"},
    )
    assert resp.status_code == 401


async def test_login_nonexistent_user_returns_401(client, beanie):
    resp = await client.post(
        "/api/v1/auth/token/",
        data={"username": "nobody", "password": "pass", "grant_type": "password"},
    )
    assert resp.status_code == 401


# --- POST /api/v1/auth/plaintoken/ ---

async def test_plaintoken_returns_string(client, regular_user):
    resp = await client.post(
        "/api/v1/auth/plaintoken/",
        data={"username": "testuser", "password": "testpass123", "grant_type": "password"},
    )
    assert resp.status_code == 200
    token = resp.text
    assert len(token) > 0
    assert "." in token


async def test_plaintoken_wrong_password_returns_401(client, regular_user):
    resp = await client.post(
        "/api/v1/auth/plaintoken/",
        data={"username": "testuser", "password": "wrong", "grant_type": "password"},
    )
    assert resp.status_code == 401


# --- POST /api/v1/auth/refresh/ ---

async def test_refresh_token_returns_new_pair(client, regular_user):
    login = await client.post(
        "/api/v1/auth/token/",
        data={"username": "testuser", "password": "testpass123", "grant_type": "password"},
    )
    refresh_token = login.json()["refresh_token"]
    resp = await client.post("/api/v1/auth/refresh/", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["refresh_token"] != refresh_token


async def test_refresh_token_old_token_revoked(client, regular_user):
    login = await client.post(
        "/api/v1/auth/token/",
        data={"username": "testuser", "password": "testpass123", "grant_type": "password"},
    )
    refresh_token = login.json()["refresh_token"]
    await client.post("/api/v1/auth/refresh/", json={"refresh_token": refresh_token})
    resp = await client.post("/api/v1/auth/refresh/", json={"refresh_token": refresh_token})
    assert resp.status_code == 401


async def test_refresh_invalid_token_returns_401(client, beanie):
    resp = await client.post("/api/v1/auth/refresh/", json={"refresh_token": "invalid-token"})
    assert resp.status_code == 401


# --- GET /api/v1/auth/me/ ---

async def test_me_returns_current_user(client, regular_user, auth_headers):
    resp = await client.get("/api/v1/auth/me/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "testuser"
    assert body["email"] == "test@example.com"


async def test_me_no_token_returns_401(client, beanie):
    resp = await client.get("/api/v1/auth/me/")
    assert resp.status_code == 401


async def test_me_does_not_return_password(client, regular_user, auth_headers):
    resp = await client.get("/api/v1/auth/me/", headers=auth_headers)
    body = resp.json()
    assert "hashed_password" not in body
    assert "password" not in body


# --- POST /api/v1/auth/register/ ---

async def test_register_user_as_moderator(client, moderator_user, mod_headers):
    payload = {
        "username": "newuser",
        "email": "new@example.com",
        "full_name": "New User",
        "password": "newpass123",
        "access_tags": ["AKOND"],
    }
    resp = await client.post("/api/v1/auth/register/", json=payload, headers=mod_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "newuser"


async def test_register_duplicate_user_returns_400(client, moderator_user, mod_headers, regular_user):
    payload = {
        "username": "testuser",
        "email": "dup@example.com",
        "full_name": "Dup User",
        "password": "pass",
        "access_tags": [],
    }
    resp = await client.post("/api/v1/auth/register/", json=payload, headers=mod_headers)
    assert resp.status_code == 400


async def test_register_as_non_moderator_returns_403(client, regular_user, auth_headers):
    payload = {
        "username": "anotheruser",
        "email": "another@example.com",
        "full_name": "Another",
        "password": "pass",
        "access_tags": [],
    }
    resp = await client.post("/api/v1/auth/register/", json=payload, headers=auth_headers)
    assert resp.status_code == 403


# --- GET/PUT /api/v1/auth/user/viewer_conf ---

async def test_get_viewer_conf_empty(client, regular_user, auth_headers):
    resp = await client.get("/api/v1/auth/user/viewer_conf", headers=auth_headers)
    assert resp.status_code == 200


async def test_put_viewer_conf_persists(client, regular_user, auth_headers):
    conf = {"theme": "dark", "columns": ["date", "object"]}
    resp = await client.put("/api/v1/auth/user/viewer_conf", json=conf, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["theme"] == "dark"


# --- GET /api/v1/auth/user/{username}/ ---

async def test_get_user_by_username_as_moderator(client, moderator_user, mod_headers, regular_user):
    resp = await client.get("/api/v1/auth/user/testuser/", headers=mod_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "testuser"


async def test_get_user_by_username_as_non_mod_returns_403(client, regular_user, auth_headers, moderator_user):
    resp = await client.get("/api/v1/auth/user/moduser/", headers=auth_headers)
    assert resp.status_code == 403
