from pydantic import BaseModel, Field, model_validator
from typing import Tuple, Literal, Optional, List
from datetime import datetime

from ocadb.models.geo import document_models


class S3PresignedUrl(BaseModel):
    type: Literal["Presigned_URL"] = "Presigned URL"
    description: str
    valid_until: str
    url: str

class S3PresignedUrlBatchList(BaseModel):
    filenames: List[str]

document_models = [S3PresignedUrl, S3PresignedUrlBatchList]