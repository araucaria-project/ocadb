from beanie.odm.operators.find.geospatial import NearSphere, GeoWithin
from fastapi import APIRouter, HTTPException, status, Body, Depends
from beanie import PydanticObjectId, exceptions
from typing import List, Annotated, Dict, Any, Tuple
from datetime import datetime, timedelta

from api.services.oca_geospatial_query import OcaWithin
from ocadb.models import Observation, FitsHeader, SkyCoord
from ocadb.models.geo import ArchDistance
from ocadb.models.s3_presigned_url import S3PresignedUrl
from api.services.auth_service import AuthService
from api.routers.api_auth import read_users_me
from api.services.s3_api_service import S3Connection



import logging

log = logging.getLogger(__name__)

router = APIRouter(prefix="/observations",
                   tags=["observations"],
                   dependencies=[],
                   responses={404: {"description": "Not found"}}
                   )


@router.post("/", response_description="Add new Observation", response_model=Observation, status_code=status.HTTP_201_CREATED)
async def create_observation(
    observation_data: Annotated[Observation, Body(...)],
    token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Create a new observation record"""
    await observation_data.insert()
    return observation_data

@router.put("/", response_description="Update observation")
async def update_observation(
        observation_data: Annotated[Observation, Body(...)],
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Update observation"""
    observation_data.updated_at = datetime.utcnow()
    try:
        await observation_data.replace()
    except (ValueError, exceptions.DocumentNotFound):
        raise HTTPException(status_code=404, detail=f"Observation with ID {observation_data._id} not found")

    return observation_data

@router.get("/{id}", response_description="Get a single Observation", response_model=Observation)
async def get_observation(
        token: Annotated[str, Depends(AuthService.validate_token)],
        id: PydanticObjectId):

    """Get observation by ID"""
    observation = await Observation.get(id)
    if observation is None:
        raise HTTPException(status_code=404, detail=f"Observation with ID {id} not found")
    return observation

@router.get("/{id}/url", response_description="Get a presigned URL for a single Observation", response_model=S3PresignedUrl)
async def get_observation_url(
        token: Annotated[str, Depends(AuthService.validate_token)],
        id: PydanticObjectId,
        expires_in: int = 3600):
    """Get observation by ID"""
    observation = await Observation.get(id)
    if observation is None:
        raise HTTPException(status_code=404, detail=f"Observation with ID {id} not found")

    s3_con = S3Connection()
    presigned_url = await s3_con.get_presigned_url(params={'Bucket': 'tests-private', 'Key': observation.filename}, expires_in=expires_in)
    s3_presigned_url_response = S3PresignedUrl(description=observation.filename, url=presigned_url, valid_until=(datetime.utcnow()+timedelta(seconds=expires_in)).strftime('%Y%m%dT%H%M%SZ'))
    return s3_presigned_url_response


@router.get("/", response_description="List Observations", response_model=List[Observation])
async def list_observations(
    token: Annotated[str, Depends(AuthService.validate_token)]):

    """List all observations"""
    user = await read_users_me(token)

    observations = await Observation.find_all().to_list()
    # observations = await Observation.find_all().aggregate(
    #         [OcaWithin.redact_with_access_tags(access_tags=user.access_tags)], projection_model=Observation).to_list()
    return observations


@router.get("/by-filename/{filename}", response_description="Get Observation by filename", response_model=List[Observation])
async def get_observation_by_filename(
        filename: str,
        token: Annotated[str, Depends(AuthService.validate_token)]):
    """Get observation by FITS filename"""
    user = await read_users_me(token)

    observations = await Observation.find(Observation.filename == filename).aggregate(
        [OcaWithin.redact_with_access_tags(access_tags=user.access_tags)], projection_model=Observation).to_list()

    if not observations:
        raise HTTPException(status_code=404, detail=f"Observation with filename {filename} not found")
    return observations


@router.get("/by-object/{object_name}", response_description="List Observations by object name", response_model=List[Observation])
async def list_observations_by_object(
        object_name: str,
        token: Annotated[str, Depends(AuthService.validate_token)]):
    """List observations of a specific object"""
    user = await read_users_me(token)
    access_tags = user.access_tags

    observations = await Observation.find(Observation.fits_header.OBJECT == object_name).aggregate(
        [OcaWithin.redact_with_access_tags(access_tags=user.access_tags)], projection_model=Observation).to_list()
    return observations


@router.get("/by-filter/{filter_name}", response_description="List Observations by filter", response_model=List[Observation])
async def list_observations_by_filter(
        filter_name: str,
        token: Annotated[str, Depends(AuthService.validate_token)]):
    """List observations using a specific filter"""
    user = await read_users_me(token)

    observations = await Observation.find(Observation.fits_header.FILTER == filter_name).aggregate(
        [OcaWithin.redact_with_access_tags(access_tags=user.access_tags)], projection_model=Observation).to_list()


    return observations

@router.get("/coordinates/", response_description="List Observations by geospatial coordinates", response_model=List[Observation])
async def list_observations_by_geo(
    sky_area: Annotated[ArchDistance, Body(...)],
    token: Annotated[str, Depends(AuthService.validate_token)]
):
    user = await read_users_me(token)

    observations = await Observation.find(
        OcaWithin(Observation.telescope_coordinates.lon_lat, (sky_area.get_ref_lon(), sky_area.get_ref_lat()),
                  sky_area.rad_distance())).aggregate(
        [OcaWithin.redact_with_access_tags(access_tags=user.access_tags)], projection_model=Observation).to_list()

    return observations

@router.put("/{id}/metadata", response_description="Update observation metadata")
async def update_observation_metadata(
    id: PydanticObjectId,
    metadata: Annotated[Dict[str, Any], Body(...)],
    token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Update observation metadata (quality checks, processing info, etc.)"""
    observation = await Observation.get(id)
    if observation is None:
        raise HTTPException(status_code=404, detail=f"Observation with ID {id} not found")

    # Update metadata while preserving existing data
    observation.metadata.update(metadata)
    await observation.save()

    return {"message": "Metadata updated successfully", "observation_id": str(id)}


@router.delete("/{id}", response_description="Delete an Observation")
async def delete_observation(
    id: PydanticObjectId,
    token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Delete an observation record"""
    delete_result = await Observation.find_one(Observation.id == id).delete()
    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Observation with ID {id} not found")
    return {"message": "Observation deleted successfully"}