from datetime import datetime
from typing import List

from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenData(BaseModel):
    username: str | None = None
    expires: datetime | None = None


class DownloadScriptRequest(BaseModel):
    obs_ids: List[str]
    username: str | None = None
