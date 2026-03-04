import math

from beanie.odm.operators.find.comparison import In
from beanie.odm.operators.find.geospatial import NearSphere, GeoWithin
from fastapi import APIRouter, HTTPException, status, Body, Depends
from beanie import PydanticObjectId, exceptions
from typing import List, Annotated, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
from dateutil import parser

from pymongo.errors import DuplicateKeyError

from api.routers.observations import get_observation, create_observation, get_observation_by_obs_name
from api.services.oca_geospatial_query import OcaWithin
from api.services.query_builder import MultiSearchForm
from ocadb.models import Observation, FitsHeader, SkyCoord
from ocadb.models.file import FITSFile, StorageStatus
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
async def create_file(
    file_data: Annotated[FITSFile, Body(...)],
    token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Create a new observation record"""
    try:
        await file_data.insert()
        if file_data.obs_name is not None:
            observation = None
            try:
                observations = await get_observation_by_obs_name(file_data.obs_name, token=token)
                observation = observations[0] # change it laterrr
            except (ValueError, exceptions.DocumentNotFound):
                observation = await create_observation(observation_data=Observation(obs_name=file_data.obs_name, file_name=file_data.filename, fits_header=file_data.fits_header), token=token)

            observation.store_file(file_data)
            await observation.replace()
    except DuplicateKeyError as e:
        raise HTTPException(status_code=403, detail=f"Observation with filename {file_data.filename} already exists.")
    return file_data

@router.put("/", response_description="Update a FITSFile", response_model=FITSFile)
async def update_fitsfile(
        fitsfile_data: Annotated[FITSFile, Body(...)],
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    fitsfile_data.updated_at = datetime.utcnow()
    try:
        await fitsfile_data.replace()
    except (ValueError, exceptions.DocumentNotFound):
        raise HTTPException(status_code=404, detail=f"File with ID {fitsfile_data._id} not found")

    return fitsfile_data

@router.put("/file-status/{fitsfile_name}/", response_description="Update file status", response_model=FITSFile)
async def update_file_status(
        fitsfile_name: str,
        filestatus: Annotated[StorageStatus, Body(...)],
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    try:
        fitsfile = await FITSFile.find_one(FITSFile.file_name == fitsfile_name)
        fitsfile.file_status = filestatus
        fitsfile.replace()

        return fitsfile
    except (ValueError, exceptions.DocumentNotFound):
        raise HTTPException(status_code=404, detail=f"FITS file with name {fitsfile_name} not found")

@router.delete("/{fitsfile_id}/", response_description="Delete a FITSFile")
async def delete_fitsfile(
    fitsfile_id: PydanticObjectId,
    token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Delete a fits file record"""
    fitsfile = await FITSFile.find_one(FITSFile.id == fitsfile_id)
    observation = await get_observation(token, fitsfile.observation_id)

    try:
        observation.files.remove(fitsfile_id)
        await fitsfile.delete()
        await observation.replace()
    except (ValueError, exceptions.DocumentNotFound):
        raise HTTPException(status_code=404, detail=f"FITS file with ID {fitsfile_id}, or linked observation not found")

    return {"message": "FITS file deleted successfully"}

@router.get("/by-file-id/{file_id}/", response_description="Get a FITSFile", response_model=FITSFile)
async def get_fitsfile(
        file_id: PydanticObjectId,
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    file = await FITSFile.find_one({"_id": file_id})
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return file

@router.get("/by-file-name/{file_name}/", response_description="Get a FITSFile by name", response_model=FITSFile)
async def get_fitsfile_by_name(
        file_name: str,
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    try:
        file = await FITSFile.find_one({"file_name": file_name})
        return file
    except (ValueError, exceptions.DocumentNotFound):
        raise HTTPException(status_code=404, detail="File not found")

@router.get("/by-observation-id/{observation_id}/", response_description="Get files for observation id", response_model=List[FITSFile])
async def get_fitsfiles_for_observation(
        observation_id: PydanticObjectId,
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    observation = await get_observation(token, observation_id)
    if observation is None:
        raise HTTPException(status_code=404, detail="Observation not found")

    # return await FITSFile.find({"_id": {"$in": observation.files}}).to_list()
    await observation.fetch_all_links()
    return observation.files