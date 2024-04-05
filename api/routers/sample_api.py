from typing import Annotated
from fastapi import APIRouter, Depends
from api.src.auth_service import AuthService

router = APIRouter()


@router.get("/test/free")
async def read_root():
    return "ok, I'm free"


# endpoint blocked by authorization
@router.get("/test/protected/")
async def read_users_me(token: Annotated[str, Depends(AuthService.validate_token)]):
    return "ok, I'm alive"
