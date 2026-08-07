import beanie.exceptions
import pymongo.errors
from pymongo import ReturnDocument

from fastapi import APIRouter, HTTPException, status, Body, Depends
from beanie import PydanticObjectId, exceptions
from typing import List, Annotated, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
from fastapi import Response

from pymongo.errors import DuplicateKeyError
from pymongo.results import UpdateResult

from api.routers.observations_v2 import get_observation, create_observation, get_observation_by_obs_name, \
    get_observation_by_filename
from ocadb.models import Observation, FitsHeader, SkyCoord
from ocadb.models.file import FITSFile, StorageStatus, StorageLocationStatus, StorageStatusType
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
    token: Annotated[str, Depends(AuthService.validate_token)],
    force: bool = False
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
            header = file_data.pop_fits_header()
            await file_data.insert()

            await observation.store_file(file_data, fits_header=header)

            if file_data.metadata:
                observation.store_metadata(file_data.metadata)

            await observation.replace()
    except DuplicateKeyError as e:
        if not force:
            raise HTTPException(status_code=403, detail=f"FITSFile with filename {file_data.filename} already exists.")
        else:
            file_data.id = (await get_fitsfile_by_name(file_data.filename, token=token)).id
            return await update_fitsfile(file_data=file_data, token=token)
    return file_data

@router.post("/upsert", response_description="Insert or update an existing FITSFile record", response_model=FITSFile)
async def upsert_fitsfile(
        file_data: Annotated[FITSFile, Body(...)],
        response: Response,
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    result = await FITSFile.find_one(
        FITSFile.filename == file_data.filename
    ).update(
        {
            "$set": {
                "obs_name": file_data.obs_name,
                "file_class": file_data.file_class,
                "filesize": file_data.filesize,
                "mtime": file_data.mtime,
                "digest": file_data.digest,
                "observation_id": file_data.observation_id,
                "source_filenames": file_data.source_filenames,
                "image_type": file_data.fits_header.IMAGETYP if file_data.fits_header else None,
                "file_status": file_data.file_status,
                "metadata": file_data.metadata,
                "access_tags": file_data.access_tags,
                "updated_at": datetime.utcnow(),
            },
            "$setOnInsert": {
                "filename": file_data.filename,
                "created_at": datetime.utcnow(),
            },
        },
        upsert=True,
    )

    response.status_code = 201 if result.upserted_id else 200

    if result.upserted_id:
        file_data.id = result.upserted_id

        if file_data.obs_name is not None:
            try:
                observation = await get_observation_by_obs_name(file_data.obs_name, token=token)
                observation.updated_at = datetime.utcnow()

            except HTTPException as exc:
                try:
                    if exc.status_code == 404:
                        observation = await create_observation(
                            observation_data=Observation(obs_name=file_data.obs_name, file_name=file_data.filename,
                                                         fits_header=file_data.fits_header), token=token)
                    else:
                        raise
                except HTTPException as e:
                    raise HTTPException(status_code=e.status_code, detail="Cannot create observation object.")

            await observation.store_file(file_data)

            if file_data.metadata:
                observation.store_metadata(file_data.metadata)

            await observation.replace()
    else: # update and we want the id
        updated_doc = await FITSFile.find_one(
            FITSFile.filename == file_data.filename
        )

        if file_data.fits_header is not None and file_data.obs_name is not None:
            try:
                observation = await get_observation_by_obs_name(file_data.obs_name, token=token)
                if observation.adopt_header_if_precedent(file_data.file_class, file_data.fits_header):
                    await observation.replace()
            except HTTPException:
                log.warning("upsert_fitsfile: could not adopt header — observation '%s' not found", file_data.obs_name)

        file_data = updated_doc

    return file_data

@router.put("/", response_description="Update a FITSFile", response_model=FITSFile)
async def update_fitsfile(
        file_data: Annotated[FITSFile, Body(...)],
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Update an existing FITSfile record"""

    file_data.updated_at = datetime.utcnow()
    header = file_data.pop_fits_header()

    try:
        await file_data.replace()
    except Exception as e:
        raise HTTPException(status_code=403, detail=f"Cannot update file with id {file_data._id}, {e}")

    observation = await get_observation_by_obs_name(file_data.obs_name, token=token)

    if observation is None:
        raise HTTPException(status_code=404, detail=f"Observation with name {file_data.obs_name} not found")

    observation.store_metadata(file_data.metadata)
    observation.adopt_header_if_precedent(file_data.file_class, header)
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

@router.post("/file-status/list", response_description="Get a list of file statuses", response_model=dict[str, StorageStatus])
async def list_files_status(
        filenames_data: Annotated[List[str], Body(...)],
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    """List file statuses for filenames in input"""
    async def get_aiter(sync_list):
        for i in sync_list:
            yield i

    response = {}

    async for filename in get_aiter(filenames_data):
        file = await FITSFile.find_one(FITSFile.filename == filename)
        if file:
            response[file.filename] = file.file_status

    return response

@router.get("/upload-requests", response_description="List files requested for download that aren't in cloud storage yet", response_model=List[FITSFile])
async def list_pending_upload_requests(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Operator review queue: files someone tried to download while file_status.cloud
    wasn't STORED, together with who asked and when (FITSFile.upload_requests)."""
    return await FITSFile.find(
        {"file_status.cloud.status": StorageStatusType.REQUESTED.value}
    ).sort("-updated_at").to_list()

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

@router.put("/file-status/{fitsfile_name}/{storage_stage_name}/", response_description="Update file status", response_model=FITSFile)
async def update_file_status_by_stage(
        fitsfile_name: str,
        storage_stage_name: str,
        token: Annotated[str, Depends(AuthService.validate_token)],
        file_location_status: StorageLocationStatus = Annotated[StorageLocationStatus, Body(...)]
):
    """Update a FITSfile record status by its filename and storage stage name"""
    if storage_stage_name not in ["observatory", "hub", "cloud"]:
        raise HTTPException(status_code=403, detail="Unexpected storage stage name")

    file = await FITSFile.find_one(FITSFile.filename == fitsfile_name)

    if file is None:
        raise HTTPException(status_code=404, detail="File not found")

    file.file_status = file.file_status.model_copy(update={storage_stage_name: file_location_status})
    file.updated_at = datetime.utcnow()
    await file.replace()

    return file