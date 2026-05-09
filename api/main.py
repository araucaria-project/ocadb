# api/main.py
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import api_auth, sample_api, objects, observations, observations_v2, files, files_v2
from ocadb import database
from api.config import Settings

log = logging.getLogger(__name__.rsplit('.')[-1])


async def _seed_dev_database() -> None:
    """Seed a fresh database with a dev user and sample observations.

    Runs on startup only when the users collection is empty, so it
    never touches production databases.  Gives new developers a
    working login and data to search right after ``docker compose up``.
    """
    import json
    from pathlib import Path
    from ocadb.models import UserInDB, Observation
    from api.services.crypto_service import CryptoService

    if await UserInDB.count() > 0:
        return

    log.info("Empty database detected — seeding dev user (dev / dev) and sample observations")
    user = UserInDB(
        username="dev",
        email="dev@localhost",
        full_name="Developer",
        hashed_password=CryptoService.get_password_hash("dev"),
        moderator=True,
        access_tags=["CAMK PAN"],
    )
    await user.insert()

    seed_file = Path(__file__).resolve().parent.parent / "dev" / "seed_observations.json"
    if seed_file.exists():
        raw = json.loads(seed_file.read_text())
        for entry in raw:
            try:
                obs = Observation(**entry)
                await obs.insert()
            except Exception as e:
                log.warning("Seed observation %s skipped: %s", entry.get("obs_name"), e)
        log.info("Seeded %d sample observations", len(raw))
    else:
        log.info("No seed file found at %s, skipping observation seed", seed_file)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    env_settings = Settings()
    mongo_url = env_settings.MONGODB_URL
    database_name = env_settings.MONGODB_DATABASE

    await database.Connection().ensure_connection(mongo_url, database_name)
    await _seed_dev_database()
    yield
    # Shutdown (if needed)


app = FastAPI(lifespan=lifespan,
              docs_url='/swagger',
              openapi_url='/api/v1/openapi.json')

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https?://192\.168\.\d+\.\d+(:\d+)?$|^https?://10\.\d+\.\d+\.\d+(:\d+)?$|^https://([a-z0-9-]+\.)*ocadb\.space$|^https://.*\.app\.github\.dev$|^https://.*\.workers\.dev$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers with consistent /api/v1 prefix
app.include_router(objects.router, prefix='/api/v1')
app.include_router(observations.router, prefix='/api/v1')
app.include_router(observations_v2.router, prefix='/api/v2')
app.include_router(api_auth.router, prefix='/api/v1')
app.include_router(sample_api.router, prefix='/api/v1')
app.include_router(files.router, prefix='/api/v1')
app.include_router(files_v2.router, prefix='/api/v2')


@app.get("/")
async def read_root():
    return {"Hello": "OCA"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ocadb-api"}

def start_development_server():
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", reload=True)
