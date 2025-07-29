# api/main.py
from fastapi import FastAPI
from .routers import objects
from ocadb import database

app = FastAPI()

app.include_router(objects.router, prefix='/api/v1')

@app.on_event("startup")
async def startup_event():
    await database.Connection().ensure_connection()


@app.get("/")
async def read_root():
    return {"Hello": "OCA"}

def start_development_server():
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", reload=True)
