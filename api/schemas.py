from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class RefreshRequest(BaseModel):
    refresh_token: str


class CodeRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=254, description="Araucaria ID or email")
    return_to: str | None = Field(None, max_length=2048, description="Frontend path the emailed link should open")


class CodeVerifyRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)
    code: str = Field(min_length=1, max_length=16)
    remember: bool = False


class PasswordChangeRequest(BaseModel):
    current_password: str | None = Field(None, description="Required if the account already has a password")
    new_password: str = Field(min_length=8, max_length=128)
    keep_refresh_token: str | None = Field(None, description="Refresh token of this session, which stays logged in")


class TokenData(BaseModel):
    username: str | None = None
    expires: datetime | None = None


class DownloadScriptRequest(BaseModel):
    obs_ids: List[str]
    username: str | None = None
    include_calibration: bool = False
    file_types: List[str] | None = None  # None = all types


class TabularExportRequest(BaseModel):
    obs_ids: List[str]
    format: str = 'ecsv'  # 'ecsv' or 'fixed_width'
    coord_format: str = 'deg'  # 'deg' or 'sexagesimal' — matches the frontend's RA/Dec unit toggle


class RequestFilesRequest(BaseModel):
    obs_ids: List[str]
    include_calibration: bool = False
    file_types: List[str] | None = None  # None = all types
