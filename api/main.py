# api/main.py
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
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
