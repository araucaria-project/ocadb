# api/main.py
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import objects
from ocadb import database



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    mongo_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    database_name = os.getenv("MONGODB_DATABASE", "ocadb")
    await database.Connection().ensure_connection(mongo_url, database_name)
    yield
    # Shutdown (if needed)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://([a-z0-9-]+\.)*ocadb\.space$|^https://.*\.app\.github\.dev$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(objects.router, prefix='/api/v1')


@app.get("/")
async def read_root():
    return {"Hello": "OCA"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ocadb-api"}

def start_development_server():
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", reload=True)
