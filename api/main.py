# api/main.py
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import api_auth, sample_api, objects, observations, observations_v2, files, files_v2
from ocadb import database
from api.config import Settings

log = logging.getLogger(__name__.rsplit('.')[-1])

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    env_settings = Settings()
    mongo_url = env_settings.MONGODB_URL
    database_name = env_settings.MONGODB_DATABASE

    await database.Connection().ensure_connection(mongo_url, database_name)
    yield
    # Shutdown (if needed)


app = FastAPI(lifespan=lifespan,
              docs_url='/swagger',
              openapi_url='/api/v1/openapi.json')

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://([a-z0-9-]+\.)*ocadb\.space$|^https://.*\.app\.github\.dev$",
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
