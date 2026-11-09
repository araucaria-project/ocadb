"""Emailed login codes, rate limits, password-less accounts and password changes."""
import hashlib
import re
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from api.main import app
from api.services.crypto_service import CryptoService
from api.services.database_connection import DatabaseConnection
from api.services.email import get_email_sender
from api.services.email.console import ConsoleEmailSender
from api.services.login_code_service import LoginCodeService
from ocadb.models import UserInDB
from ocadb.models.login_code import LoginCode
from ocadb.models.refresh_token import RefreshTokenDocument


@pytest_asyncio.fixture(loop_scope="session")
async def outbox(beanie):
    sender = ConsoleEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    yield sender.outbox
    app.dependency_overrides.pop(get_email_sender, None)


@pytest_asyncio.fixture(loop_scope="session")
async def codeonly_user(beanie):
    user = UserInDB(username="codeonly", email="code.only@example.com", full_name="Code Only",
                    access_tags=["AKOND"])
    await user.insert()
    return user


def _code(message) -> str:
    return re.search(r"^\s+(\d{6})$", message.text, re.MULTILINE).group(1)


async def _request(client, identifier, **extra):
    resp = await client.post("/api/v1/auth/code/request/", json={"identifier": identifier, **extra})
    assert resp.status_code == 202
    return resp


async def _verify(client, identifier, code, **extra):
    return await client.post("/api/v1/auth/code/verify/", json={"identifier": identifier, "code": code, **extra})


async def _login(client, username, password):
    return await client.post(
        "/api/v1/auth/token/",
        data={"username": username, "password": password, "grant_type": "password"},
    )


# --- request + verify ---

async def test_code_login_by_username(client, regular_user, outbox):
    await _request(client, "testuser")
    assert len(outbox) == 1
    assert outbox[0].to == "test@example.com"
    resp = await _verify(client, "testuser", _code(outbox[0]))
    assert resp.status_code == 200
    assert {"access_token", "refresh_token"} <= resp.json().keys()


async def test_code_login_by_email_any_case(client, regular_user, outbox):
    await _request(client, "  Test@Example.COM ")
    assert len(outbox) == 1
    resp = await _verify(client, "TEST@example.com", _code(outbox[0]))
    assert resp.status_code == 200


async def test_code_hash_is_not_plain_sha256(regular_user, outbox, client):
    await _request(client, "testuser")
    doc = await LoginCode.find_one(LoginCode.username == "testuser")
    assert doc.code_hash != hashlib.sha256(_code(outbox[0]).encode()).hexdigest()


@pytest.mark.parametrize("identifier", ["nobody", "nobody@example.com"])
async def test_unknown_identifier_sends_nothing(client, beanie, outbox, identifier):
    resp = await _request(client, identifier)
    assert len(outbox) == 0
    assert "detail" in resp.json()


async def test_disabled_user_gets_no_code(client, regular_user, outbox):
    regular_user.disabled = True
    await regular_user.replace()
    await _request(client, "testuser")
    assert outbox == []


async def test_user_without_email_gets_no_code(client, beanie, outbox):
    await UserInDB(username="noemail", full_name="No Email", hashed_password=None).insert()
    await _request(client, "noemail")
    assert outbox == []


async def test_verify_unknown_user_returns_401(client, beanie):
    resp = await _verify(client, "nobody", "123456")
    assert resp.status_code == 401


async def test_wrong_code_then_right_code(client, regular_user, outbox):
    await _request(client, "testuser")
    code = _code(outbox[0])
    wrong = "000000" if code != "000000" else "111111"
    assert (await _verify(client, "testuser", wrong)).status_code == 401
    assert (await _verify(client, "testuser", code)).status_code == 200


async def test_attempts_exhausted(client, regular_user, outbox):
    await _request(client, "testuser")
    code = _code(outbox[0])
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(LoginCodeService.MAX_ATTEMPTS):
        assert (await _verify(client, "testuser", wrong)).status_code == 401
    assert (await _verify(client, "testuser", code)).status_code == 401


async def test_code_is_single_use(client, regular_user, outbox):
    await _request(client, "testuser")
    code = _code(outbox[0])
    assert (await _verify(client, "testuser", code)).status_code == 200
    assert (await _verify(client, "testuser", code)).status_code == 401


async def test_expired_code_rejected(client, regular_user, outbox):
    await _request(client, "testuser")
    doc = await LoginCode.find_one(LoginCode.username == "testuser")
    doc.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await doc.replace()
    assert (await _verify(client, "testuser", _code(outbox[0]))).status_code == 401


async def test_new_code_replaces_old(client, regular_user, outbox):
    await _request(client, "testuser")
    await _request(client, "testuser")
    first, second = _code(outbox[0]), _code(outbox[1])
    if first != second:
        assert (await _verify(client, "testuser", first)).status_code == 401
    assert (await _verify(client, "testuser", second)).status_code == 200


async def test_code_login_remember_device(client, regular_user, outbox):
    await _request(client, "testuser")
    resp = await _verify(client, "testuser", _code(outbox[0]), remember=True)
    h = hashlib.sha256(resp.json()["refresh_token"].encode()).hexdigest()
    doc = await RefreshTokenDocument.find_one(RefreshTokenDocument.token_hash == h)
    assert doc.lifetime_days == 90


# --- emailed link ---

async def test_email_link_keeps_return_path(client, regular_user, outbox):
    await _request(client, "testuser", return_to="/?object=tzfor&filter=V")
    assert "/?object=tzfor&filter=V#login_id=testuser&login_code=" in outbox[0].text


@pytest.mark.parametrize("return_to", ["//evil.example/x", "https://evil.example/x"])
async def test_email_link_ignores_foreign_return_to(client, regular_user, outbox, return_to):
    await _request(client, "testuser", return_to=return_to)
    assert "evil.example" not in outbox[0].text


# --- rate limits ---

async def test_requests_per_identifier_limited(client, regular_user, outbox):
    limit, _ = LoginCodeService.REQUESTS_PER_IDENTIFIER
    for _ in range(limit + 2):
        await _request(client, "testuser")
    assert len(outbox) == limit


async def test_verifications_per_ip_limited(client, regular_user):
    limit, _ = LoginCodeService.VERIFICATIONS_PER_IP
    for _ in range(limit):
        assert (await _verify(client, "testuser", "000000")).status_code == 401
    assert (await _verify(client, "testuser", "000000")).status_code == 429


# --- password-less accounts ---

async def test_codeonly_user_cannot_log_in_with_password(client, codeonly_user):
    assert (await _login(client, "codeonly", "")).status_code in (401, 422)
    assert (await _login(client, "codeonly", "anything")).status_code == 401


async def test_register_without_password(client, moderator_user, mod_headers):
    payload = {"username": "nopass", "email": "NoPass@Example.com", "full_name": "No Pass", "access_tags": []}
    resp = await client.post("/api/v1/auth/register/", json=payload, headers=mod_headers)
    assert resp.status_code == 200
    user = await DatabaseConnection.get_user("nopass")
    assert user.hashed_password is None
    assert user.email == "nopass@example.com"


async def test_register_duplicate_email_returns_400(client, moderator_user, mod_headers, regular_user):
    payload = {"username": "other", "email": "TEST@example.com", "full_name": "Other", "access_tags": []}
    resp = await client.post("/api/v1/auth/register/", json=payload, headers=mod_headers)
    assert resp.status_code == 400


async def test_update_to_duplicate_email_returns_400(client, moderator_user, mod_headers, regular_user):
    resp = await client.put("/api/v1/auth/user/testuser/", json={"email": "mod@example.com"}, headers=mod_headers)
    assert resp.status_code == 400


async def test_users_without_email_do_not_collide(beanie):
    await UserInDB(username="a", hashed_password=None).insert()
    await UserInDB(username="b", email="", hashed_password=None).insert()


async def test_identifier_lookup_matches_unnormalized_stored_email(beanie):
    await UserInDB.get_motor_collection().insert_one({"username": "legacy", "email": "Jan.Kowalski@CAMK.edu.pl"})
    user = await DatabaseConnection.get_user_by_identifier("jan.kowalski@camk.edu.pl")
    assert user is not None and user.username == "legacy"


# --- POST /auth/password/ ---

async def _code_session(client, outbox, username):
    await _request(client, username)
    resp = await _verify(client, username, _code(outbox[-1]))
    tokens = resp.json()
    return tokens, {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_codeonly_user_sets_password(client, codeonly_user, outbox):
    _, headers = await _code_session(client, outbox, "codeonly")
    resp = await client.post("/api/v1/auth/password/", json={"new_password": "brand-new-pass"}, headers=headers)
    assert resp.status_code == 204
    assert (await _login(client, "codeonly", "brand-new-pass")).status_code == 200


async def test_change_password_requires_current(client, regular_user, auth_headers):
    resp = await client.post("/api/v1/auth/password/", json={"new_password": "another-pass"}, headers=auth_headers)
    assert resp.status_code == 403
    resp = await client.post("/api/v1/auth/password/",
                             json={"current_password": "wrong", "new_password": "another-pass"}, headers=auth_headers)
    assert resp.status_code == 403


async def test_change_password_too_short(client, regular_user, auth_headers):
    resp = await client.post("/api/v1/auth/password/",
                             json={"current_password": "testpass123", "new_password": "short"}, headers=auth_headers)
    assert resp.status_code == 422


async def test_change_password_logs_out_other_sessions(client, regular_user):
    this = (await _login(client, "testuser", "testpass123")).json()
    other = (await _login(client, "testuser", "testpass123")).json()
    resp = await client.post(
        "/api/v1/auth/password/",
        json={"current_password": "testpass123", "new_password": "another-pass",
              "keep_refresh_token": this["refresh_token"]},
        headers={"Authorization": f"Bearer {this['access_token']}"},
    )
    assert resp.status_code == 204
    assert (await client.post("/api/v1/auth/refresh/", json={"refresh_token": other["refresh_token"]})).status_code == 401
    assert (await client.post("/api/v1/auth/refresh/", json={"refresh_token": this["refresh_token"]})).status_code == 200
    assert (await _login(client, "testuser", "testpass123")).status_code == 401
    assert (await _login(client, "testuser", "another-pass")).status_code == 200
