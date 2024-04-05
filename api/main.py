# api/main.py
from functools import lru_cache

import uvicorn
from fastapi import FastAPI

from api.config import Settings
from api.routers import api_auth, sample_api

app = FastAPI()

# add endpoints from other files
app.include_router(api_auth.router)
app.include_router(sample_api.router)


# load settings.py
@lru_cache
def get_settings():
    return Settings()


@app.get("/metrics/statuses")
def health():
    return "OK"


def start():
    """Launched with `poetry run start` at root level"""
    uvicorn.run("api.main:app",
                host=get_settings().host,
                port=get_settings().port,
                reload=get_settings().reload,
                workers=get_settings().workers)
