import beanie.exceptions
import pymongo.errors

from fastapi import APIRouter, HTTPException, status, Body, Depends
from beanie import PydanticObjectId, exceptions
from typing import List, Annotated, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta

from pymongo.errors import DuplicateKeyError

from api.routers.observations_v2 import get_observation, create_observation, get_observation_by_obs_name, \
    get_observation_by_filename
from ocadb.models import Observation, FitsHeader, SkyCoord
from ocadb.models.file import FITSFile, StorageStatus
from api.services.auth_service import AuthService



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
    """Create a new FITSfile record"""
    try:
        if file_data.obs_name is not None:
            try:
                observation = await get_observation_by_obs_name(file_data.obs_name, token=token)
                observation.updated_at = datetime.utcnow()

            except HTTPException as exc:
                try:
                    if exc.status_code == 404:
                        observation = await create_observation(observation_data=Observation(obs_name=file_data.obs_name, file_name=file_data.filename, fits_header=file_data.fits_header), token=token)
                    else:
                        raise
                except HTTPException as e:
                    raise HTTPException(status_code=e.status_code, detail="Cannot create observation object.")

            file_data.observation_id = observation.get_id()
            await file_data.insert()

            observation.store_file(file_data)

            if file_data.metadata:
                observation.store_metadata(file_data.metadata)

            await observation.replace()
    except DuplicateKeyError as e:
        raise HTTPException(status_code=403, detail=f"FITSFile with filename {file_data.filename} already exists.")
    return file_data

@router.put("/", response_description="Update a FITSFile", response_model=FITSFile)
async def update_fitsfile(
        file_data: Annotated[FITSFile, Body(...)],
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Update an existing FITSfile record"""

    file_data.updated_at = datetime.utcnow()

    try:
        await file_data.replace()
    except:
        raise HTTPException(status_code=404, detail=f"Cannot update observation with id {file_data._id}")

    observation = await get_observation_by_obs_name(file_data.obs_name, token=token)

    if observation is None:
        raise HTTPException(status_code=404, detail=f"Observation with name {file_data.obs_name} not found")

    observation.store_metadata(file_data.metadata)
    await observation.replace()




    return file_data

@router.delete("/{fitsfile_id}/", response_description="Delete a FITSFile")
async def delete_fitsfile(
    fitsfile_id: PydanticObjectId,
    token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Delete a FITSfile record"""
    fitsfile = await FITSFile.find_one(FITSFile.id == fitsfile_id)
    observation = await get_observation(token, fitsfile.observation_id)

    if fitsfile is None or observation is None:
        raise HTTPException(status_code=404, detail=f"FITS file with ID {fitsfile_id}, or linked observation not found")

    observation.files.remove(fitsfile_id)
    await fitsfile.delete()
    await observation.replace()

    return {"message": "FITS file deleted successfully"}

@router.get("/by-fileid/{file_id}/", response_description="Get a FITSFile", response_model=FITSFile)
async def get_fitsfile_by_id(
        file_id: PydanticObjectId,
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Get a FITSfile record by file_id"""
    file = await FITSFile.find_one({"_id": file_id})
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")

    return file

@router.get("/by-filename/{file_name}/", response_description="Get a FITSFile by name", response_model=FITSFile)
async def get_fitsfile_by_name(
        file_name: str,
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Get a FITSfile record by its filename"""
    file = await FITSFile.find_one(FITSFile.filename == file_name)
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return file


@router.get('/by-filename/{file_name}/plainurl', response_description="Get plain presigned url for FITSFile by its name", response_model=str)
async def get_fitsfile_by_name_plainurl(
        token: Annotated[str, Depends(AuthService.validate_token)],
        file_name: str,
        expires_in: int = 3600
):
    """Get a FITSfile record presigned S3 URL"""
    file = await FITSFile.find_one(FITSFile.filename == file_name)
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return await file.get_plain_presigned_url(expires_in)

@router.get("/by-observation-id/{observation_id}/", response_description="Get files for observation id", response_model=List[FITSFile])
async def get_fitsfiles_for_observation(
        observation_id: PydanticObjectId,
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Get a FITSfile records by its connected observation_id"""
    observation = await get_observation(token, observation_id)
    if observation is None:
        raise HTTPException(status_code=404, detail="Observation not found")

    # return await FITSFile.find({"_id": {"$in": observation.files}}).to_list()
    await observation.fetch_all_links()
    return observation.files

@router.get("/file-status/{fitsfile_name}/", response_description="Get file status", response_model=StorageStatus)
async def get_file_status(
        fitsfile_name: str,
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Get a FITSfile record status by its filename"""

    fitsfile = await FITSFile.find_one(FITSFile.filename == fitsfile_name)
    if fitsfile is None:
        raise HTTPException(status_code=404, detail=f"FITS file with name {fitsfile_name} not found.")

    return fitsfile.file_status


@router.put("/file-status/{fitsfile_name}/", response_description="Update file status", response_model=FITSFile)
async def update_file_status(
        fitsfile_name: str,
        filestatus: Annotated[StorageStatus, Body(...)],
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Update a FITSfile record status by its filename"""

    fitsfile = await FITSFile.find_one(FITSFile.filename == fitsfile_name)
    if fitsfile is None:
        raise HTTPException(status_code=404, detail=f"FITS file with name {fitsfile_name} not found")

    fitsfile.file_status = filestatus
    fitsfile.replace()

    return fitsfile