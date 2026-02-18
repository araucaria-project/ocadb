import math

from beanie.odm.operators.find.comparison import In
from beanie.odm.operators.find.geospatial import NearSphere, GeoWithin
from fastapi import APIRouter, HTTPException, status, Body, Depends
from beanie import PydanticObjectId, exceptions
from typing import List, Annotated, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
from dateutil import parser

from pymongo.errors import DuplicateKeyError

from api.routers.observations import get_observation
from api.services.oca_geospatial_query import OcaWithin
from api.services.query_builder import MultiSearchForm
from ocadb.models import Observation, FitsHeader, SkyCoord
from ocadb.models.file import FITSFile
from ocadb.models.geo import ArchDistance
from ocadb.models.s3_presigned_url import S3PresignedUrl, S3PresignedUrlBatchList
from api.services.auth_service import AuthService
from api.routers.api_auth import read_users_me
from api.services.s3_api_service import S3Connection



import logging

log = logging.getLogger(__name__)

router = APIRouter(prefix="/files",
                   tags=["files"],
                   dependencies=[],
                   responses={404: {"description": "Not found"}}
                   )

@router.post("/", response_description="Add new File", response_model=FITSFile, status_code=status.HTTP_201_CREATED)
async def create_observation(
    file_data: Annotated[FITSFile, Body(...)],
    token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Create a new observation record"""
    try:
        await file_data.insert()
        if file_data.observation_id is not None:
            observation = await get_observation(token, file_data.observation_id)
            if observation is None:
                raise HTTPException(status_code=404, detail=f"Observation with ID {id} not found")
            observation.store_file(file_data.id)
            await observation.replace()
    except DuplicateKeyError as e:
        raise HTTPException(status_code=403, detail=f"Observation with filename {file_data.filename} already exists.")
    return file_data