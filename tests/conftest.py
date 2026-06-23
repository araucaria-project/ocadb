import pytest
import pytest_asyncio
from datetime import timedelta
from httpx import AsyncClient, ASGITransport

from ocadb.database import Connection
from ocadb.models import UserInDB, Observation, FitsHeader
from ocadb.models.file import FITSFile, FileClassification, StorageStatus, StorageLocationStatus, StorageStatusType
from ocadb.models.search_object import SearchObject, SearchTag
from api.services.crypto_service import CryptoService
from api.services.auth_service import AuthService
from api.main import app

TEST_DB = "mongodb://localhost:27017"
TEST_DB_NAME = "ocadb_test"

_COLLECTIONS = [
    "observations", "fits_files", "users", "refresh_tokens",
    "search_objects", "search_tags", "Object",
]


def make_storage_status(status: StorageStatusType = StorageStatusType.NOT_STORED) -> StorageStatus:
    loc = StorageLocationStatus(ready=False, check_needed=False, status=status)
    return StorageStatus(observatory=loc, hub=loc, cloud=loc)


def make_fits_header(**overrides) -> FitsHeader:
    base = {
        "DATE-OBS": "2024-01-15T20:30:00",
        "RA": 180.0,
        "DEC": -30.0,
        "OBJECT": "TZ For",
        "TELESCOP": "TEST-1m",
        "INSTRUME": "TEST-CAM",
        "ORIGIN": "AKOND",
        "FILTER": "V",
        "EXPTIME": 120.0,
        "IMAGETYP": "object",
        "OBSTYPE": "science",
        "JD": 2460320.5,
        "PI": "testpi",
    }
    base.update(overrides)
    return FitsHeader.model_validate(base)


# ── session-level DB connection ───────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def beanie():
    """One motor connection for the whole session (session loop scope avoids cross-loop errors)."""
    conn = Connection()
    conn.client = None
    await conn.ensure_connection(
        connection_string=f"{TEST_DB}/{TEST_DB_NAME}",
        database_name=TEST_DB_NAME,
    )
    return conn.client


# ── per-test DB cleanup using the session event loop ─────────────────────────

@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def cleanup_db(beanie):
    """Wipes all test collections before each test. autouse so every test starts clean."""
    db = beanie[TEST_DB_NAME]
    for col in _COLLECTIONS:
        await db[col].delete_many({})
    yield


# ── API client ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(loop_scope="session")
async def client(beanie):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ── user fixtures ─────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(loop_scope="session")
async def regular_user(beanie):
    user = UserInDB(
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        hashed_password=CryptoService.get_password_hash("testpass123"),
        moderator=False,
        access_tags=["TEST-CAM", "AKOND", "testpi"],
    )
    await user.insert()
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def moderator_user(beanie):
    user = UserInDB(
        username="moduser",
        email="mod@example.com",
        full_name="Moderator User",
        hashed_password=CryptoService.get_password_hash("modpass123"),
        moderator=True,
        access_tags=["TEST-CAM", "AKOND", "testpi", "mod"],
    )
    await user.insert()
    return user


# ── token / header fixtures ───────────────────────────────────────────────────

@pytest_asyncio.fixture(loop_scope="session")
async def user_token(regular_user):
    return AuthService.create_access_token(
        data={"sub": regular_user.username},
        expires_delta=timedelta(minutes=30),
    )


@pytest_asyncio.fixture(loop_scope="session")
async def mod_token(moderator_user):
    return AuthService.create_access_token(
        data={"sub": moderator_user.username},
        expires_delta=timedelta(minutes=30),
    )


@pytest_asyncio.fixture(loop_scope="session")
async def auth_headers(user_token):
    return {"Authorization": f"Bearer {user_token}"}


@pytest_asyncio.fixture(loop_scope="session")
async def mod_headers(mod_token):
    return {"Authorization": f"Bearer {mod_token}"}


# ── sample data fixtures ──────────────────────────────────────────────────────

@pytest_asyncio.fixture(loop_scope="session")
async def sample_observation(beanie):
    obs = Observation(
        obs_name="test_obs_001",
        file_name="test_001.fits",
        fits_header=make_fits_header(),
    )
    await obs.insert()
    return obs


@pytest_asyncio.fixture(loop_scope="session")
async def sample_fits_file(beanie, sample_observation):
    f = FITSFile(
        filename="test_001.fits",
        file_class=FileClassification.RAW,
        obs_name="test_obs_001",
        observation_id=sample_observation.id,
        file_status=make_storage_status(),
    )
    await f.insert()
    return f
