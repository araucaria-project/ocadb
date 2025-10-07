from pydantic import BaseModel, Field, model_validator
from typing import Tuple, Literal, Optional

from ocadb.models.geo import document_models


class S3PresignedUrl(BaseModel):
    type: Literal["Presigned_URL"] = "Presigned_URL"
    filename: str
    expires_in: int
    url: str

document_models = [S3PresignedUrl]