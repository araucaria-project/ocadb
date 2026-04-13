import math
from pathlib import Path

from beanie.odm.operators.find.comparison import In
from beanie.odm.operators.find.geospatial import NearSphere, GeoWithin
from fastapi import APIRouter, HTTPException, status, Body, Depends
from beanie import PydanticObjectId, exceptions
from typing import List, Annotated, Dict, Any, Tuple, Optional, Union
from datetime import datetime, timedelta
from dateutil import parser
from pyaraucaria.fits import fits_header
from pyaraucaria.lookup_objects import name_canonizator

from pymongo.errors import DuplicateKeyError

from api.services.aggregation_query_builder import AggregationQueryBuilder
from api.services.oca_geospatial_query import OcaWithin
from api.services.query_builder import MultiSearchForm
from ocadb.models import Observation, FitsHeader, SkyCoord
from ocadb.models.geo import ArchDistance
from ocadb.models.s3_presigned_url import S3PresignedUrl, S3PresignedUrlBatchList
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

@router.get("/", response_description="List Observations", response_model=dict[str, Union[List[Observation], Any]])
async def list_observations(
    token: Annotated[str, Depends(AuthService.validate_token)],
    page: int = 1,
    page_size: int = 50
):

    """List all observations"""
    user = await read_users_me(token)

    observations = await Observation.find_all().aggregate(AggregationQueryBuilder.aggregate(match_query={}, access_tags=user.access_tags, page=page, page_size=page_size)).to_list()
    if len(observations) == 0:
        raise HTTPException(status_code=404, detail="No observations found")

    return observations[0]

@router.post("/", response_description="Add new Observation", response_model=Observation, status_code=status.HTTP_201_CREATED)
async def create_observation(
    observation_data: Annotated[Observation, Body(...)],
    token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Create a new observation record"""
    try:
        await observation_data.insert()
    except DuplicateKeyError as e:
        raise HTTPException(status_code=403, detail=f"Observation with filename {observation_data.file_name} already exists.")
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
    except:
        raise HTTPException(status_code=404, detail=f"Observation with ID {observation_data._id} not found or cannot be updated")

    return observation_data

@router.delete("/{id}/", response_description="Delete an Observation")
async def delete_observation(
    id: PydanticObjectId,
    token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Delete an observation record"""
    delete_result = await Observation.find_one(Observation.id == id).delete()
    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Observation with ID {id} not found")
    return {"message": "Observation deleted successfully"}

@router.get("/{id}/", response_description="Get a single Observation", response_model=Observation)
async def get_observation(
        token: Annotated[str, Depends(AuthService.validate_token)],
        id: PydanticObjectId):

    """Get observation by ID - full version"""
    observation = await Observation.get(id, fetch_links=True)
    if observation is None:
        raise HTTPException(status_code=404, detail=f"Observation with ID {id} not found")
    return observation

@router.get("/{id}/short", response_description="Get a single Observation", response_model=Observation)
async def get_observation_short(
        token: Annotated[str, Depends(AuthService.validate_token)],
        id: PydanticObjectId):

    """Get observation by ID - short version"""
    observation = await Observation.get(id)
    if observation is None:
        raise HTTPException(status_code=404, detail=f"Observation with ID {id} not found")
    return observation

@router.put("/{id}/metadata", response_description="Update observation metadata", status_code=200)
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

# @router.get("/{obs_name}/calib", response_description="Get list of calibration files", response_model=List[str])
# async def get_calibration_files(
#         obs_name: str,
#         token: Annotated[str, Depends(AuthService.validate_token)]
# ):
#     user = await read_users_me(token)
#
#     return []

# searches

@router.get("/by-filename/{filename}/", response_description="Get Observation by one of its files filename", response_model=Observation)
async def get_observation_by_filename(
        filename: str,
        token: Annotated[str, Depends(AuthService.validate_token)]):
    """Get observation by conencted FITS filename - full output version"""
    user = await read_users_me(token)

    observations = await Observation.find(Observation.files.filename == filename, fetch_links=True).aggregate(
        [OcaWithin.redact_with_access_tags(access_tags=user.access_tags)], projection_model=Observation).to_list()

    if not observations:
        raise HTTPException(status_code=404, detail=f"Observation with filename {filename} not found")
    return observations[0]

@router.get("/by-observation-name/{observation_name}/", response_description="Get Observation by its observation name", response_model=Observation)
async def get_observation_by_obs_name(
        observation_name: str,
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Get observation by Observation name"""
    user = await read_users_me(token)

    observations = await Observation.find(Observation.obs_name == observation_name).aggregate(
     [OcaWithin.redact_with_access_tags(access_tags=user.access_tags)], projection_model=Observation).to_list()

    if not observations:
        raise HTTPException(status_code=404, detail=f"Observation with name {observation_name} not found")
    return observations[0]

@router.get("/by-object/{object_name}/", response_description="List Observations by object name", response_model=dict[str, Union[List[Observation], Any]])
async def list_observations_by_object(
        object_name: str,
        token: Annotated[str, Depends(AuthService.validate_token)],
        page: int = 1,
        page_size: int = 50
):
    """List observations of a specific object"""
    user = await read_users_me(token)
    observations = await Observation.find(Observation.canonized_object_name == name_canonizator(object_name)).aggregate(AggregationQueryBuilder.aggregate(match_query={}, access_tags=user.access_tags, page=page, page_size=page_size)).to_list()

    if not observations:
        raise HTTPException(status_code=404, detail=f"Observation for object {object_name} not found")

    return observations[0]


@router.get("/by-filter/{filter_name}/", response_description="List Observations by filter", response_model=dict[str, Union[List[Observation], Any]])
async def list_observations_by_filter(
        filter_name: str,
        token: Annotated[str, Depends(AuthService.validate_token)],
        page: int = 1,
        page_size: int = 50
):
    """List observations using a specific filter"""
    user = await read_users_me(token)

    observations = await Observation.find(Observation.fits_header.FILTER == filter_name).aggregate(AggregationQueryBuilder.aggregate(match_query={}, access_tags=user.access_tags, page=page, page_size=page_size)).to_list()

    if not observations:
        raise HTTPException(status_code=404, detail=f"No observations found")

    return observations[0]

@router.get("/by-coordinates", response_description="List Observations by geospatial coordinates", response_model=dict[str, Union[List[Observation], Any]])
async def list_observations_by_geo(
    sky_area: Annotated[ArchDistance, Body(...)],
    token: Annotated[str, Depends(AuthService.validate_token)],
    page: int = 1,
    page_size: int = 50
):
    user = await read_users_me(token)

    observations = await (Observation.find(
        OcaWithin(Observation.telescope_coordinates.lon_lat, (sky_area.get_ref_lon(), sky_area.get_ref_lat()),
                  sky_area.rad_distance())).aggregate(
        AggregationQueryBuilder.aggregate(match_query={}, access_tags=user.access_tags, page=page, page_size=page_size))).to_list()

    if not observations:
        raise HTTPException(status_code=404, detail=f"No observations found")

    return observations[0]

@router.post('/search', response_description="Search Observations by multi parameter query", response_model=dict[str, Union[List[Observation], Any]])
async def search_multi(
        search_form: Annotated[MultiSearchForm, Body(...)],
        token: Annotated[str, Depends(AuthService.validate_token)],
        page: int = 1,
        page_size: int = 50
):
    user = await read_users_me(token)

    observations = Observation.find()
    if search_form.telescop is not None:
        observations = observations.find(Observation.fits_header.TELESCOP == search_form.telescop)
    if search_form.imagetyp is not None:
        observations = observations.find(Observation.fits_header.IMAGETYP == search_form.imagetyp)
    if search_form.obstype is not None:
        observations = observations.find(Observation.fits_header.OBSTYPE == search_form.obstype)
    if search_form.object is not None:
        observations = observations.find(Observation.canonized_object_name == name_canonizator(search_form.object))
    if search_form.sciprog is not None:
        observations = observations.find(Observation.fits_header.SCIPROG == search_form.sciprog)
    if search_form.filter is not None:
        observations = observations.find(In(Observation.fits_header.FILTER, search_form.filter))
    if search_form.pi is not None:
        observations = observations.find(Observation.fits_header.PI == search_form.pi)
    if search_form.date_obs_from is not None:
        observations = observations.find(Observation.date_obs >= parser.parse(search_form.date_obs_from))
    if search_form.date_obs_to is not None:
        observations = observations.find(Observation.date_obs <= parser.parse(search_form.date_obs_to))
    if search_form.jd_from is not None:
        observations = observations.find(math.floor(Observation.fits_header.JD) >= search_form.jd_from)
    if search_form.jd_to is not None:
        observations = observations.find(math.floor(Observation.fits_header.JD) >= search_form.jd_to)

    observations = await observations.find(fetch_links=True).aggregate(AggregationQueryBuilder.aggregate(match_query={}, access_tags=user.access_tags, page=page, page_size=page_size)).to_list()

    if not observations:
        raise HTTPException(status_code=404, detail=f"No observations found")

    return observations[0]

# values
@router.get("/values/telescop", response_description="Unique values for TELESCOP header field", response_model=List[str])
async def get_values_telescop(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    user = await read_users_me(token)
    values = await Observation.distinct("fits_header.TELESCOP")
    return values

@router.get("/values/imagetyp", response_description="Unique values for IMAGETYP header field", response_model=List[str])
async def get_values_imagetyp(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    values = await Observation.distinct("fits_header.IMAGETYP")
    return values

# /api/v1/observations/values/OBSTYPE
@router.get("/values/obstype", response_description="Unique values for OBSTYPE header field", response_model=List[str])
async def get_values_obstype(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    values = await Observation.distinct("fits_header.OBSTYPE")
    return values

# /api/v1/observations/values/PI
@router.get("/values/pi", response_description="Unique values for PI header field", response_model=List[str])
async def get_values_pi(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    values = await Observation.distinct("fits_header.PI")
    return values

# /api/v1/observations/values/OBJECT
@router.get("/values/object", response_description="Unique values for OBJECT field", response_model=List[str])
async def get_values_object(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    values = await Observation.distinct("canonized_object_name")
    return values

# /api/v1/observations/values/FILTER  per TELESCOP
@router.get("/values/{telescope}/filter", response_description="Unique values for FILTER of TELESCOP header field", response_model=List[str])
async def get_values_telescope_filter(
        telescope: str,
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    # values = Observation.find(Observation.fits_header.TELESCOP == telescope).distinct("fits_header.FILTER")
    values = Observation.distinct("fits_header.FILTER")
    return values
