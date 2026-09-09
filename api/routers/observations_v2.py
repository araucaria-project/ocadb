import asyncio
import math
from pathlib import Path

from beanie.odm.operators.find.comparison import In
from beanie.odm.operators.find.geospatial import NearSphere, GeoWithin
from fastapi import APIRouter, HTTPException, status, Body, Depends
from fastapi.responses import Response
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
from ocadb.database import Connection
from ocadb.migrations.fits_header_migration import run_pass1, run_pass2
from ocadb.migrations.metadata_migration import run_pass1 as run_metadata_pass1, run_pass2 as run_metadata_pass2
from ocadb.migrations.storage_status_migration import run_pass1 as run_storage_status_pass1
from ocadb.migrations.source_filenames_migration import run_pass1 as run_source_filenames_pass1
from ocadb.migrations.source_files_number_migration import run_pass1 as run_source_files_number_pass1
from ocadb.models import Observation, FitsHeader, SkyCoord
from ocadb.models.file import FITSFile
from ocadb.models.search_object import SearchObject, SearchTag
from ocadb.models.geo import ArchDistance
from ocadb.models.s3_presigned_url import S3PresignedUrl, S3PresignedUrlBatchList
from api.services.auth_service import AuthService
from api.routers.api_auth import read_users_me
from api.services.s3_api_service import S3Connection
from api.schemas import DownloadScriptRequest
from pydantic import BaseModel

class SearchTagCreate(BaseModel):
    tag_name: str
    tag_description: Optional[str] = None
    tag_color: Optional[str] = None



import logging

from ocadb.models.search_object import SearchObject

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

    observations = await Observation.find_all().aggregate(AggregationQueryBuilder.aggregate(access_tags=user.access_tags, page=page, page_size=page_size, sort_expr={})).to_list()
    if not observations or not observations[0].get("data"):
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

@router.get("/{id}/file-lineage", response_description="Full source-file ancestry graph for an observation")
async def get_file_lineage(
        id: PydanticObjectId,
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Full transitive ancestry of this observation's files: every file linked to the
    observation, plus every source file they derive from (and those files' own sources,
    recursively — chains can be multi-level, e.g. RAW -> MASTER -> ZDF, and cross-observation
    since calibration frames are shared). See FITSFile.resolve_lineage for the walk itself.
    """
    observation = await Observation.get(id, fetch_links=True)
    if observation is None:
        raise HTTPException(status_code=404, detail=f"Observation {id} not found")

    nodes, edges = await FITSFile.resolve_lineage(observation.files)
    return {
        "roots": [f.filename for f in observation.files],
        "nodes": {
            name: {
                "file_class": f.file_class,
                "obs_name": f.obs_name,
                "cloud_status": f.file_status.cloud.status,
                "cloud_ready": f.file_status.cloud.ready,
                "image_type": f.image_type,
            }
            for name, f in nodes.items()
        },
        "edges": [{"from": child, "to": source} for child, source in edges],
    }

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
    observations = await Observation.find(Observation.canonized_object_name == name_canonizator(object_name)).aggregate(AggregationQueryBuilder.aggregate(access_tags=user.access_tags, page=page, page_size=page_size, sort_expr={})).to_list()

    if not observations or not observations[0].get("data"):
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

    observations = await Observation.find(Observation.fits_header.FILTER == filter_name).aggregate(AggregationQueryBuilder.aggregate(access_tags=user.access_tags, page=page, page_size=page_size, sort_expr={})).to_list()

    if not observations or not observations[0].get("data"):
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
        AggregationQueryBuilder.aggregate(access_tags=user.access_tags, page=page, page_size=page_size, sort_expr={}))).to_list()

    if not observations or not observations[0].get("data"):
        raise HTTPException(status_code=404, detail=f"No observations found")

    return observations[0]

@router.post('/search', response_description="Search Observations by multi parameter query", response_model=dict[str, Union[List[Observation], Any]])
async def search_multi(
        search_form: Annotated[MultiSearchForm, Body(...)],
        token: Annotated[str, Depends(AuthService.validate_token)],
        page: int = 1,
        page_size: int = 30
):
    user = await read_users_me(token)

    observations = Observation.find_all()
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
    if search_form.oca_jd_from is not None:
        observations = observations.find(Observation.oca_jd >= search_form.oca_jd_from)
    if search_form.oca_jd_to is not None:
        observations = observations.find(Observation.oca_jd <= search_form.oca_jd_to)
    if search_form.jd_from is not None:
        observations = observations.find(math.floor(Observation.fits_header.JD) >= search_form.jd_from)
    if search_form.jd_to is not None:
        observations = observations.find(math.floor(Observation.fits_header.JD) >= search_form.jd_to)
    if search_form.cone_search is not None:
        observations = observations.find(
        OcaWithin(Observation.telescope_coordinates.lon_lat, (search_form.cone_search.get_ref_lon(), search_form.cone_search.get_ref_lat()),
                  search_form.cone_search.rad_distance()))
    if search_form.tags is not None:
        observations = observations.find({"obs_tags": {"$all": list(search_form.tags)}})

    pipeline = AggregationQueryBuilder.aggregate(access_tags=user.access_tags, page=page, page_size=page_size, sort_expr=search_form.sort_expr)
    pipeline[-1]['$facet']['data'].append({"$addFields": {"files": []}})
    observations = await observations.find(fetch_links=False).aggregate(pipeline).to_list()

    if not observations or not observations[0].get("data"):
        raise HTTPException(status_code=404, detail=f"No observations found")

    return observations[0]

# values
@router.get("/values/telescop", response_description="Unique values for TELESCOP header field", response_model=List[str])
async def get_values_telescop(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    user = await read_users_me(token)
    values = await Observation.distinct("fits_header.TELESCOP")
    return sorted(v for v in values if v is not None)

@router.get("/values/imagetyp", response_description="Unique values for IMAGETYP header field", response_model=List[str])
async def get_values_imagetyp(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    values = await Observation.distinct("fits_header.IMAGETYP")
    return sorted(v for v in values if v is not None)

# /api/v1/observations/values/OBSTYPE
@router.get("/values/obstype", response_description="Unique values for OBSTYPE header field", response_model=List[str])
async def get_values_obstype(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    values = await Observation.distinct("fits_header.OBSTYPE")
    return sorted(v for v in values if v is not None)

# /api/v1/observations/values/PI
@router.get("/values/pi", response_description="Unique values for PI header field", response_model=List[str])
async def get_values_pi(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    values = await Observation.distinct("fits_header.PI")
    return sorted(v for v in values if v is not None)

@router.get('/values/search_object', response_description="Unique, sorted list of object following a pattern", response_model=List[SearchObject])
async def get_search_object(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    results = await SearchObject.find_all().sort(+SearchObject.canonized_name).to_list()
    return results

@router.get('/values/tags', response_description="List of available search tags", response_model=List[SearchTag])
async def get_search_tags(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    results = await SearchTag.find_all().sort(+SearchTag.tag_name).to_list()
    return results

@router.post('/values/tags', response_description="Create a new search tag", response_model=SearchTag, status_code=status.HTTP_201_CREATED)
async def create_search_tag(
        data: Annotated[SearchTagCreate, Body(...)],
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    tag = SearchTag(tag_name=data.tag_name, tag_description=data.tag_description, tag_color=data.tag_color)
    try:
        await tag.insert()
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=f"Tag '{data.tag_name}' already exists")
    return tag

@router.post('/{id}/obs-tags', response_description="Add a tag to an observation", status_code=200)
async def add_obs_tag(
        id: PydanticObjectId,
        tag_name: Annotated[str, Body(..., embed=True)],
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    obs = await Observation.get(id)
    if obs is None:
        raise HTTPException(status_code=404, detail=f"Observation {id} not found")
    await obs.update({"$addToSet": {"obs_tags": tag_name}})
    obs = await Observation.get(id)
    return {"obs_tags": list(obs.obs_tags or [])}

@router.put('/{id}/source-files-count', response_description="Correct an observation's denormalized source files count", status_code=200)
async def set_source_files_count(
        id: PydanticObjectId,
        count: Annotated[int, Body(..., embed=True, ge=0)],
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    """source_files_number is a cheap, approximate count kept on Observation purely to size
    loading placeholders before the real source-file list is fetched (see store_file). The
    frontend calls this once it has actually resolved the real list, to correct any drift.
    """
    obs = await Observation.get(id)
    if obs is None:
        raise HTTPException(status_code=404, detail=f"Observation {id} not found")
    if obs.source_files_number != count:
        await obs.update({"$set": {"source_files_number": count}})
    return {"source_files_number": count}


@router.post('/bulk-tag', response_description="Add and/or remove tags on multiple observations", status_code=200)
async def bulk_tag_observations(
        obs_ids: Annotated[List[str], Body(..., embed=True)],
        tags_to_add: Annotated[Optional[List[str]], Body(embed=True)] = None,
        tags_to_remove: Annotated[Optional[List[str]], Body(embed=True)] = None,
        token: Annotated[str, Depends(AuthService.validate_token)] = None
):
    ids = [PydanticObjectId(oid) for oid in obs_ids]
    update: dict = {}
    if tags_to_add:
        update["$addToSet"] = {"obs_tags": {"$each": tags_to_add}}
    if tags_to_add:
        await Observation.find(In(Observation.id, ids)).update_many({"$addToSet": {"obs_tags": {"$each": tags_to_add}}})
    if tags_to_remove:
        await Observation.find(In(Observation.id, ids)).update_many({"$pull": {"obs_tags": {"$in": tags_to_remove}}})
    return {"updated": len(ids), "tags_added": tags_to_add or [], "tags_removed": tags_to_remove or []}

@router.delete('/{id}/obs-tags', response_description="Remove a tag from an observation", status_code=200)
async def remove_obs_tag(
        id: PydanticObjectId,
        tag_name: Annotated[str, Body(..., embed=True)],
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    obs = await Observation.get(id)
    if obs is None:
        raise HTTPException(status_code=404, detail=f"Observation {id} not found")
    await obs.update({"$pull": {"obs_tags": tag_name}})
    obs = await Observation.get(id)
    return {"obs_tags": list(obs.obs_tags or [])}

@router.get("/values/sciprog", response_description="Unique values for OBJECT field", response_model=List[str])
async def get_values_object(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    values = await Observation.distinct("fits_header.SCIPROG")
    values = sorted(v for v in values if v is not None)
    return values


# /api/v1/observations/values/OBJECT
@router.get("/values/object", response_description="Unique values for OBJECT field", response_model=List[str])
async def get_values_object(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    values = await Observation.distinct("canonized_object_name")
    return sorted(v for v in values if v is not None)


# /api/v1/observations/values/FILTER  per TELESCOP
@router.get("/values/{telescope}/filter", response_description="Unique values for FILTER of TELESCOP header field", response_model=List[str])
async def get_values_telescope_filter(
        telescope: str,
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    if telescope == "all":
        values = await Observation.distinct("fits_header.FILTER")
    else:
        collection = Observation.get_motor_collection()
        values = await collection.distinct("fits_header.FILTER", {"fits_header.TELESCOP": telescope})
    return sorted(v for v in values if v is not None)




_migration_job: Dict[str, Any] = {"status": "idle"}

async def _run_migration() -> None:
    global _migration_job
    _migration_job = {
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
        "canonized_total": 0,
        "canonized_updated": 0,
        "canonized_errors": 0,
        "search_objects_created": 0,
        "search_objects_updated": 0,
        "search_objects_errors": 0,
        "obs_tags_total": 0,
        "obs_tags_updated": 0,
        "obs_tags_errors": 0,
        "total": 0,
    }
    try:
        # # Pass 1: backfill canonized_object_name for observations that are missing it
        # canon_total = await Observation.find(Observation.canonized_object_name == None).count()
        # _migration_job["canonized_total"] = canon_total
        # log.warning(f"Pass 1: backfilling canonized_object_name for {canon_total} observations...")
        #
        # canon_updated = 0
        # canon_errors = 0
        #
        # async for obs in Observation.find(Observation.canonized_object_name == None):
        #     try:
        #         if obs.fits_header is None:
        #             continue
        #         object_name = getattr(obs.fits_header, 'OBJECT', None)
        #         if not object_name:
        #             continue
        #         canonized = name_canonizator(object_name)
        #         if canonized:
        #             await obs.update({"$set": {"canonized_object_name": canonized}})
        #             canon_updated += 1
        #             _migration_job["canonized_updated"] = canon_updated
        #     except Exception as e:
        #         log.error(f"Canonize error for obs {obs.id}: {e}")
        #         canon_errors += 1
        #         _migration_job["canonized_errors"] = canon_errors
        #
        # log.warning(f"Pass 1 done. Updated: {canon_updated}, errors: {canon_errors}")

        # # Pass 2: populate search_objects collection
        # total = await Observation.find(Observation.canonized_object_name != None).count()
        # _migration_job["total"] = total
        # log.warning(f"Pass 2: populating search_objects from {total} observations with a canonized name...")
        #
        # so_created = 0
        # so_updated = 0
        # so_errors = 0
        #
        # async for obs in Observation.find(Observation.canonized_object_name != None):
        #     try:
        #         canonized = obs.canonized_object_name
        #         first_alias = obs.fits_header.OBJECT if obs.fits_header else None
        #         ra = getattr(obs.fits_header, 'RA', None) if obs.fits_header else None
        #         dec = getattr(obs.fits_header, 'DEC', None) if obs.fits_header else None
        #         ra = float(ra) if ra is not None else None
        #         dec = float(dec) if dec is not None else None
        #
        #         existing = await SearchObject.find_one(SearchObject.canonized_name == canonized)
        #         if existing is None:
        #             await SearchObject(canonized_name=canonized, first_alias=first_alias, ra=ra, dec=dec).insert()
        #             so_created += 1
        #             _migration_job["search_objects_created"] = so_created
        #             if so_created % 50 == 0:
        #                 log.info(f"  search_objects created: {so_created}")
        #         elif (existing.ra is None or existing.ra == 0.0) and ra is not None:
        #             await existing.update({"$set": {"ra": ra, "dec": dec}})
        #             so_updated += 1
        #             _migration_job["search_objects_updated"] = so_updated
        #     except DuplicateKeyError:
        #         pass  # pre-existing unique entry — safe to ignore
        #     except Exception as e:
        #         log.error(f"SearchObject error for obs {obs.id}: {e}")
        #         so_errors += 1
        #         _migration_job["search_objects_errors"] = so_errors

        # # Pass 3: populate obs_tags from filetypes + metadata (done)
        # tags_total = await Observation.count()
        # _migration_job["obs_tags_total"] = tags_total
        # log.warning(f"Pass 3: populating obs_tags for {tags_total} observations...")
        # tags_updated = 0
        # tags_errors = 0
        # async for obs in Observation.find_all():
        #     try:
        #         obs_tags: set[str] = {ft.value for ft in obs.filetypes}
        #         if obs.metadata:
        #             obs_tags.add("metadata")
        #         if obs_tags:
        #             await obs.update({"$set": {"obs_tags": list(obs_tags)}})
        #             tags_updated += 1
        #             _migration_job["obs_tags_updated"] = tags_updated
        #     except Exception as e:
        #         log.error(f"obs_tags error for obs {obs.id}: {e}")
        #         tags_errors += 1
        #         _migration_job["obs_tags_errors"] = tags_errors
        # log.warning(f"Pass 3 done. Updated: {tags_updated}, errors: {tags_errors}")

        # # Pass 4: create SearchTag documents for each known tag value (done)
        # known_tags = ['raw', 'zdf', 'master', 'source', 'tmp', 'test', 'metadata', 'cntac']
        # log.warning(f"Pass 4: creating SearchTag documents for {len(known_tags)} known tags...")
        # st_created = 0
        # st_errors = 0
        # for tag_name in known_tags:
        #     try:
        #         existing = await SearchTag.find_one(SearchTag.tag_name == tag_name)
        #         if existing is None:
        #             await SearchTag(tag_name=tag_name).insert()
        #             st_created += 1
        #     except DuplicateKeyError:
        #         pass
        #     except Exception as e:
        #         log.error(f"SearchTag error for tag '{tag_name}': {e}")
        #         st_errors += 1
        # log.warning(f"Pass 4 done. Created: {st_created}, errors: {st_errors}")

        tags_updated = 0
        tags_errors = 0

        # Pass 5: backfill tag_color on existing SearchTag documents
        known_colors = {
            'zdf':      'bg-emerald-900/40 text-emerald-300 border-emerald-600/50',
            'raw':      'bg-amber-900/30 text-amber-300 border-amber-600/50',
            'metadata': 'bg-violet-900/30 text-violet-300 border-violet-600/50',
            'master':   'bg-sky-900/40 text-sky-300 border-sky-600/50',
            'source':   'bg-cyan-900/40 text-cyan-300 border-cyan-600/50',
            'tmp':      'bg-orange-900/40 text-orange-300 border-orange-600/50',
            'test':     'bg-yellow-900/40 text-yellow-300 border-yellow-600/50',
        }
        tag_palette = [
            'bg-red-900/40 text-red-300 border-red-600/50',
            'bg-red-950/60 text-red-200 border-red-700/50',
            'bg-orange-900/40 text-orange-300 border-orange-600/50',
            'bg-orange-950/60 text-orange-200 border-orange-700/50',
            'bg-amber-900/30 text-amber-300 border-amber-600/50',
            'bg-amber-950/60 text-amber-200 border-amber-700/50',
            'bg-yellow-900/40 text-yellow-300 border-yellow-600/50',
            'bg-yellow-950/60 text-yellow-200 border-yellow-700/50',
            'bg-lime-900/40 text-lime-300 border-lime-600/50',
            'bg-lime-950/60 text-lime-200 border-lime-700/50',
            'bg-green-900/40 text-green-300 border-green-600/50',
            'bg-green-950/60 text-green-200 border-green-700/50',
            'bg-emerald-900/40 text-emerald-300 border-emerald-600/50',
            'bg-emerald-950/60 text-emerald-200 border-emerald-700/50',
            'bg-teal-900/40 text-teal-300 border-teal-600/50',
            'bg-teal-950/60 text-teal-200 border-teal-700/50',
            'bg-cyan-900/40 text-cyan-300 border-cyan-600/50',
            'bg-cyan-950/60 text-cyan-200 border-cyan-700/50',
            'bg-sky-900/40 text-sky-300 border-sky-600/50',
            'bg-sky-950/60 text-sky-200 border-sky-700/50',
            'bg-blue-900/40 text-blue-300 border-blue-600/50',
            'bg-blue-950/60 text-blue-200 border-blue-700/50',
            'bg-indigo-900/40 text-indigo-300 border-indigo-600/50',
            'bg-indigo-950/60 text-indigo-200 border-indigo-700/50',
            'bg-violet-900/30 text-violet-300 border-violet-600/50',
            'bg-violet-950/60 text-violet-200 border-violet-700/50',
            'bg-purple-900/40 text-purple-300 border-purple-600/50',
            'bg-purple-950/60 text-purple-200 border-purple-700/50',
            'bg-fuchsia-900/40 text-fuchsia-300 border-fuchsia-600/50',
            'bg-fuchsia-950/60 text-fuchsia-200 border-fuchsia-700/50',
            'bg-rose-900/40 text-rose-300 border-rose-600/50',
            'bg-rose-950/60 text-rose-200 border-rose-700/50',
        ]
        reserved_indices = {4, 6, 12, 16, 18, 24, 2}  # indices of known_colors in palette
        free_palette = [c for i, c in enumerate(tag_palette) if i not in reserved_indices]

        def _hash_color(name: str) -> str:
            h = 5381
            for ch in name:
                h = ((h * 33) ^ ord(ch)) & 0xFFFFFFFF
            return free_palette[h % len(free_palette)]

        log.warning("Pass 5: backfilling tag_color on SearchTag documents...")
        p5_updated = 0
        p5_errors = 0
        async for tag in SearchTag.find_all():
            if tag.tag_color:
                continue
            try:
                color = known_colors.get(tag.tag_name or '') or _hash_color(tag.tag_name or '')
                await tag.update({"$set": {"tag_color": color}})
                p5_updated += 1
            except Exception as e:
                log.error(f"Pass 5 error for tag '{tag.tag_name}': {e}")
                p5_errors += 1
        log.warning(f"Pass 5 done. Updated: {p5_updated}, errors: {p5_errors}")

        _migration_job.update({"status": "done", "finished_at": datetime.utcnow().isoformat()})
        log.warning(f"Done. obs_tags updated: {tags_updated}, errors: {tags_errors}")
    except Exception as e:
        _migration_job.update({"status": "failed", "error": str(e), "finished_at": datetime.utcnow().isoformat()})
        log.error(f"Migration failed: {e}")


@router.post("/migrate-api", response_description="Start migration job in the background", status_code=status.HTTP_202_ACCEPTED)
async def migrate_api(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    if _migration_job.get("status") == "running":
        raise HTTPException(status_code=409, detail="Migration already running")
    asyncio.create_task(_run_migration())
    return {"status": "accepted", "message": "Migration started. Poll /migrate-api/status for progress."}


@router.get("/migrate-api/status", response_description="Get migration job status")
async def migrate_api_status(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    return _migration_job


# --- fits_header -> Observation migration (see ocadb/migrations/fits_header_migration.py) ---
#
# Job state is persisted in a plain Mongo collection (not a Beanie document) rather than an
# in-process global: the previous migrate-api job lived only in memory, so a Railway
# redeploy/restart mid-run silently wiped its progress. Pass 2 here is destructive and
# not re-runnable, so losing track of how far it got is worse than for earlier migrations.

_FITS_HEADER_MIGRATION_JOB_ID = "fits_header_migration"


def _fits_header_migration_jobs():
    return Connection().database["migration_jobs"]


async def _run_fits_header_migration(apply: bool) -> None:
    jobs = _fits_header_migration_jobs()

    async def persist_progress(progress: dict) -> None:
        await jobs.update_one(
            {"_id": _FITS_HEADER_MIGRATION_JOB_ID},
            {"$set": {"status": "running", "progress": progress}},
        )

    try:
        pass1_result = await run_pass1(dry_run=not apply, on_progress=persist_progress)
        if not apply:
            await jobs.update_one(
                {"_id": _FITS_HEADER_MIGRATION_JOB_ID},
                {"$set": {
                    "status": "done", "apply": False,
                    "pass1": pass1_result, "pass2": None,
                    "finished_at": datetime.utcnow().isoformat(),
                }},
            )
            return

        pass2_result = await run_pass2(on_progress=persist_progress)
        await jobs.update_one(
            {"_id": _FITS_HEADER_MIGRATION_JOB_ID},
            {"$set": {
                "status": "done", "apply": True,
                "pass1": pass1_result, "pass2": pass2_result,
                "finished_at": datetime.utcnow().isoformat(),
            }},
        )
    except Exception as e:
        log.error(f"fits_header migration failed: {e}")
        await jobs.update_one(
            {"_id": _FITS_HEADER_MIGRATION_JOB_ID},
            {"$set": {"status": "failed", "error": str(e), "finished_at": datetime.utcnow().isoformat()}},
        )


@router.post("/migrate-fits-header", response_description="Start the fits_header migration in the background",
             status_code=status.HTTP_202_ACCEPTED)
async def migrate_fits_header(
        moderator: Annotated[str, Depends(AuthService.require_moderator)],
        apply: bool = False,
        force: bool = False,
):
    """Move fits_header from FITSFile documents onto their parent Observation (ZDF wins over
    RAW/other). Defaults to a dry run (Pass 1 only, no writes). Pass apply=true to also run
    Pass 2, which is destructive and strips fits_header from every FITSFile document.

    force=true bypasses the "already running" guard — needed if a previous run's process
    was killed/redeployed mid-flight and left a stale "running" status behind.
    """
    jobs = _fits_header_migration_jobs()
    existing = await jobs.find_one({"_id": _FITS_HEADER_MIGRATION_JOB_ID})
    if existing is not None and existing.get("status") == "running" and not force:
        raise HTTPException(status_code=409, detail="fits_header migration already running (pass force=true to override)")

    await jobs.update_one(
        {"_id": _FITS_HEADER_MIGRATION_JOB_ID},
        {"$set": {"status": "running", "apply": apply, "started_at": datetime.utcnow().isoformat(),
                  "started_by": moderator, "progress": None}},
        upsert=True,
    )
    asyncio.create_task(_run_fits_header_migration(apply))
    return {"status": "accepted", "apply": apply,
            "message": "Migration started. Poll /migrate-fits-header/status for progress."}


@router.get("/migrate-fits-header/status", response_description="Get fits_header migration job status")
async def migrate_fits_header_status(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    job = await _fits_header_migration_jobs().find_one({"_id": _FITS_HEADER_MIGRATION_JOB_ID})
    if job is None:
        return {"status": "idle"}
    return job


# --- metadata -> Observation migration (see ocadb/migrations/metadata_migration.py) ---
#
# Same shape/rationale as the fits_header migration above: Mongo-persisted job state
# (survives a Railway redeploy), moderator-gated trigger, dry-run by default.

_METADATA_MIGRATION_JOB_ID = "metadata_migration"


def _metadata_migration_jobs():
    return Connection().database["migration_jobs"]  # same collection, distinct _id


async def _run_metadata_migration(apply: bool) -> None:
    jobs = _metadata_migration_jobs()

    async def persist_progress(progress: dict) -> None:
        await jobs.update_one(
            {"_id": _METADATA_MIGRATION_JOB_ID},
            {"$set": {"status": "running", "progress": progress}},
        )

    try:
        pass1_result = await run_metadata_pass1(dry_run=not apply, on_progress=persist_progress)
        if not apply:
            await jobs.update_one(
                {"_id": _METADATA_MIGRATION_JOB_ID},
                {"$set": {
                    "status": "done", "apply": False,
                    "pass1": pass1_result, "pass2": None,
                    "finished_at": datetime.utcnow().isoformat(),
                }},
            )
            return

        pass2_result = await run_metadata_pass2(on_progress=persist_progress)
        await jobs.update_one(
            {"_id": _METADATA_MIGRATION_JOB_ID},
            {"$set": {
                "status": "done", "apply": True,
                "pass1": pass1_result, "pass2": pass2_result,
                "finished_at": datetime.utcnow().isoformat(),
            }},
        )
    except Exception as e:
        log.error(f"metadata migration failed: {e}")
        await jobs.update_one(
            {"_id": _METADATA_MIGRATION_JOB_ID},
            {"$set": {"status": "failed", "error": str(e), "finished_at": datetime.utcnow().isoformat()}},
        )


@router.post("/migrate-metadata", response_description="Start the metadata migration in the background",
             status_code=status.HTTP_202_ACCEPTED)
async def migrate_metadata(
        moderator: Annotated[str, Depends(AuthService.require_moderator)],
        apply: bool = False,
        force: bool = False,
):
    """Merge metadata from FITSFile documents onto their parent Observation (ZDF wins over
    RAW/other on key collision, mirroring fits_header's precedence). Defaults to a dry run
    (Pass 1 only, no writes). Pass apply=true to also run Pass 2, which clears metadata from
    every FITSFile document — unlike fits_header's Pass 2, this is freely re-runnable.

    force=true bypasses the "already running" guard — needed if a previous run's process
    was killed/redeployed mid-flight and left a stale "running" status behind.
    """
    jobs = _metadata_migration_jobs()
    existing = await jobs.find_one({"_id": _METADATA_MIGRATION_JOB_ID})
    if existing is not None and existing.get("status") == "running" and not force:
        raise HTTPException(status_code=409, detail="metadata migration already running (pass force=true to override)")

    await jobs.update_one(
        {"_id": _METADATA_MIGRATION_JOB_ID},
        {"$set": {"status": "running", "apply": apply, "started_at": datetime.utcnow().isoformat(),
                  "started_by": moderator, "progress": None}},
        upsert=True,
    )
    asyncio.create_task(_run_metadata_migration(apply))
    return {"status": "accepted", "apply": apply,
            "message": "Migration started. Poll /migrate-metadata/status for progress."}


@router.get("/migrate-metadata/status", response_description="Get metadata migration job status")
async def migrate_metadata_status(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    job = await _metadata_migration_jobs().find_one({"_id": _METADATA_MIGRATION_JOB_ID})
    if job is None:
        return {"status": "idle"}
    return job


# --- FITSFile storage status migration: scheduled -> on_demand (see
# ocadb/migrations/storage_status_migration.py) ---
#
# Same shape/rationale as the fits_header/metadata migrations above: Mongo-persisted
# job state (survives a Railway redeploy), moderator-gated trigger, dry-run by default.
# Single pass only — flipping a status field is not destructive, so there's no
# separate pass2 to strip anything afterwards.

_STORAGE_STATUS_MIGRATION_JOB_ID = "storage_status_migration"


def _storage_status_migration_jobs():
    return Connection().database["migration_jobs"]  # same collection, distinct _id


async def _run_storage_status_migration(apply: bool) -> None:
    jobs = _storage_status_migration_jobs()

    async def persist_progress(progress: dict) -> None:
        await jobs.update_one(
            {"_id": _STORAGE_STATUS_MIGRATION_JOB_ID},
            {"$set": {"status": "running", "progress": progress}},
        )

    try:
        pass1_result = await run_storage_status_pass1(dry_run=not apply, on_progress=persist_progress)
        await jobs.update_one(
            {"_id": _STORAGE_STATUS_MIGRATION_JOB_ID},
            {"$set": {
                "status": "done", "apply": apply,
                "pass1": pass1_result,
                "finished_at": datetime.utcnow().isoformat(),
            }},
        )
    except Exception as e:
        log.error(f"storage status migration failed: {e}")
        await jobs.update_one(
            {"_id": _STORAGE_STATUS_MIGRATION_JOB_ID},
            {"$set": {"status": "failed", "error": str(e), "finished_at": datetime.utcnow().isoformat()}},
        )


@router.post("/migrate-storage-status", response_description="Start the storage status migration in the background",
             status_code=status.HTTP_202_ACCEPTED)
async def migrate_storage_status(
        moderator: Annotated[str, Depends(AuthService.require_moderator)],
        apply: bool = False,
        force: bool = False,
):
    """Flip FITSFile storage status from SCHEDULED to ON_DEMAND across all three
    storage locations (observatory, hub, cloud). Defaults to a dry run (report only,
    no writes). Pass apply=true to actually write the changes — safe to re-run since
    files with no SCHEDULED location are skipped.

    force=true bypasses the "already running" guard — needed if a previous run's process
    was killed/redeployed mid-flight and left a stale "running" status behind.
    """
    jobs = _storage_status_migration_jobs()
    existing = await jobs.find_one({"_id": _STORAGE_STATUS_MIGRATION_JOB_ID})
    if existing is not None and existing.get("status") == "running" and not force:
        raise HTTPException(status_code=409, detail="storage status migration already running (pass force=true to override)")

    await jobs.update_one(
        {"_id": _STORAGE_STATUS_MIGRATION_JOB_ID},
        {"$set": {"status": "running", "apply": apply, "started_at": datetime.utcnow().isoformat(),
                  "started_by": moderator, "progress": None}},
        upsert=True,
    )
    asyncio.create_task(_run_storage_status_migration(apply))
    return {"status": "accepted", "apply": apply,
            "message": "Migration started. Poll /migrate-storage-status/status for progress."}


@router.get("/migrate-storage-status/status", response_description="Get storage status migration job status")
async def migrate_storage_status_status(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    job = await _storage_status_migration_jobs().find_one({"_id": _STORAGE_STATUS_MIGRATION_JOB_ID})
    if job is None:
        return {"status": "idle"}
    return job


# --- FITSFile source_filenames migration: clear source_filenames on RAW files (see
# ocadb/migrations/source_filenames_migration.py) ---
#
# Same shape/rationale as the migrations above: Mongo-persisted job state (survives
# a Railway redeploy), moderator-gated trigger, dry-run by default. Single pass only —
# clearing a list back to [] is not destructive, so there's no separate pass2.

_SOURCE_FILENAMES_MIGRATION_JOB_ID = "source_filenames_migration"


def _source_filenames_migration_jobs():
    return Connection().database["migration_jobs"]  # same collection, distinct _id


async def _run_source_filenames_migration(apply: bool) -> None:
    jobs = _source_filenames_migration_jobs()

    async def persist_progress(progress: dict) -> None:
        await jobs.update_one(
            {"_id": _SOURCE_FILENAMES_MIGRATION_JOB_ID},
            {"$set": {"status": "running", "progress": progress}},
        )

    try:
        pass1_result = await run_source_filenames_pass1(dry_run=not apply, on_progress=persist_progress)
        await jobs.update_one(
            {"_id": _SOURCE_FILENAMES_MIGRATION_JOB_ID},
            {"$set": {
                "status": "done", "apply": apply,
                "pass1": pass1_result,
                "finished_at": datetime.utcnow().isoformat(),
            }},
        )
    except Exception as e:
        log.error(f"source filenames migration failed: {e}")
        await jobs.update_one(
            {"_id": _SOURCE_FILENAMES_MIGRATION_JOB_ID},
            {"$set": {"status": "failed", "error": str(e), "finished_at": datetime.utcnow().isoformat()}},
        )


@router.post("/migrate-source-filenames", response_description="Start the source_filenames migration in the background",
             status_code=status.HTTP_202_ACCEPTED)
async def migrate_source_filenames(
        moderator: Annotated[str, Depends(AuthService.require_moderator)],
        apply: bool = False,
        force: bool = False,
):
    """Clear FITSFile.source_filenames back to [] for every file with file_class == RAW.
    A bug in source_files list generation left some RAW files with a non-empty
    source_filenames list; RAW files never have source files by definition. Defaults
    to a dry run (report only, no writes). Pass apply=true to actually write the
    changes — safe to re-run since files already at [] are skipped.

    force=true bypasses the "already running" guard — needed if a previous run's process
    was killed/redeployed mid-flight and left a stale "running" status behind.
    """
    jobs = _source_filenames_migration_jobs()
    existing = await jobs.find_one({"_id": _SOURCE_FILENAMES_MIGRATION_JOB_ID})
    if existing is not None and existing.get("status") == "running" and not force:
        raise HTTPException(status_code=409, detail="source filenames migration already running (pass force=true to override)")

    await jobs.update_one(
        {"_id": _SOURCE_FILENAMES_MIGRATION_JOB_ID},
        {"$set": {"status": "running", "apply": apply, "started_at": datetime.utcnow().isoformat(),
                  "started_by": moderator, "progress": None}},
        upsert=True,
    )
    asyncio.create_task(_run_source_filenames_migration(apply))
    return {"status": "accepted", "apply": apply,
            "message": "Migration started. Poll /migrate-source-filenames/status for progress."}


@router.get("/migrate-source-filenames/status", response_description="Get source_filenames migration job status")
async def migrate_source_filenames_status(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    job = await _source_filenames_migration_jobs().find_one({"_id": _SOURCE_FILENAMES_MIGRATION_JOB_ID})
    if job is None:
        return {"status": "idle"}
    return job


# --- Observation source_files_number backfill migration (see
# ocadb/migrations/source_files_number_migration.py) ---
#
# Same shape/rationale as the migrations above: Mongo-persisted job state, moderator-gated
# trigger, dry-run by default. Single pass only — backfilling a count from an existing
# array is not destructive, so there's no separate pass2.

_SOURCE_FILES_NUMBER_MIGRATION_JOB_ID = "source_files_number_migration"


def _source_files_number_migration_jobs():
    return Connection().database["migration_jobs"]  # same collection, distinct _id


async def _run_source_files_number_migration(apply: bool) -> None:
    jobs = _source_files_number_migration_jobs()

    async def persist_progress(progress: dict) -> None:
        await jobs.update_one(
            {"_id": _SOURCE_FILES_NUMBER_MIGRATION_JOB_ID},
            {"$set": {"status": "running", "progress": progress}},
        )

    try:
        pass1_result = await run_source_files_number_pass1(dry_run=not apply, on_progress=persist_progress)
        await jobs.update_one(
            {"_id": _SOURCE_FILES_NUMBER_MIGRATION_JOB_ID},
            {"$set": {
                "status": "done", "apply": apply,
                "pass1": pass1_result,
                "finished_at": datetime.utcnow().isoformat(),
            }},
        )
    except Exception as e:
        log.error(f"source files number migration failed: {e}")
        await jobs.update_one(
            {"_id": _SOURCE_FILES_NUMBER_MIGRATION_JOB_ID},
            {"$set": {"status": "failed", "error": str(e), "finished_at": datetime.utcnow().isoformat()}},
        )


@router.post("/migrate-source-files-number", response_description="Start the source_files_number backfill migration in the background",
             status_code=status.HTTP_202_ACCEPTED)
async def migrate_source_files_number(
        moderator: Annotated[str, Depends(AuthService.require_moderator)],
        apply: bool = False,
        force: bool = False,
):
    """Backfill Observation.source_files_number = len(old source_files array) for every
    document that still has the old array and hasn't been backfilled yet. Defaults to a
    dry run (report only, no writes). Pass apply=true to actually write the changes —
    safe to re-run since already-backfilled documents are skipped.

    force=true bypasses the "already running" guard — needed if a previous run's process
    was killed/redeployed mid-flight and left a stale "running" status behind.
    """
    jobs = _source_files_number_migration_jobs()
    existing = await jobs.find_one({"_id": _SOURCE_FILES_NUMBER_MIGRATION_JOB_ID})
    if existing is not None and existing.get("status") == "running" and not force:
        raise HTTPException(status_code=409, detail="source files number migration already running (pass force=true to override)")

    await jobs.update_one(
        {"_id": _SOURCE_FILES_NUMBER_MIGRATION_JOB_ID},
        {"$set": {"status": "running", "apply": apply, "started_at": datetime.utcnow().isoformat(),
                  "started_by": moderator, "progress": None}},
        upsert=True,
    )
    asyncio.create_task(_run_source_files_number_migration(apply))
    return {"status": "accepted", "apply": apply,
            "message": "Migration started. Poll /migrate-source-files-number/status for progress."}


@router.get("/migrate-source-files-number/status", response_description="Get source_files_number migration job status")
async def migrate_source_files_number_status(
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    job = await _source_files_number_migration_jobs().find_one({"_id": _SOURCE_FILES_NUMBER_MIGRATION_JOB_ID})
    if job is None:
        return {"status": "idle"}
    return job


@router.post("/download-script", response_description="Generate a POSIX shell download script for selected observations")
async def generate_download_script(
        request: Annotated[DownloadScriptRequest, Body(...)],
        token: Annotated[str, Depends(AuthService.validate_token)]
):
    """Generate a self-contained shell script that downloads FITS files for the given observations.

    File classes are filtered server-side; the script embeds the authenticated user's username
    and handles password acquisition and token refresh at runtime.
    """
    from ocafitsfiles import render_download_script, parse_filename

    user = await read_users_me(token)

    try:
        obs_ids = [PydanticObjectId(oid) for oid in request.obs_ids]
    except Exception:
        raise HTTPException(status_code=422, detail="One or more observation IDs are invalid")

    observations = await Observation.find(In(Observation.id, obs_ids)).to_list()

    if not observations:
        raise HTTPException(status_code=404, detail="No observations found for the given IDs")

    filenames: List[str] = []
    calib_seed: set = set()
    for obs in observations:
        await obs.fetch_all_links()
        for f in obs.files:
            filenames.append(f.filename)
            if request.include_calibration:
                calib_seed.update(f.source_filenames or [])

    if request.include_calibration:
        obs_name_set = set(filenames)
        collected: set = set()
        frontier = calib_seed - obs_name_set
        while frontier:
            new_names = frontier - collected
            if not new_names:
                break
            collected.update(new_names)
            db_files = await FITSFile.find({"filename": {"$in": list(new_names)}}).to_list()
            frontier = set()
            for f in db_files:
                frontier.update(f.source_filenames or [])
        filenames.extend(n for n in sorted(collected) if n not in obs_name_set)
    else:
        obs_name_set = set(filenames)

    if request.file_types is not None:
        allowed = set(request.file_types)
        def _ftype(name: str) -> str:
            _, suffix = parse_filename(name)
            return suffix if suffix else 'raw'
        filenames = [n for n in filenames if _ftype(n) in allowed]

    if not filenames:
        raise HTTPException(status_code=404, detail="No files found for the selected observations")

    await FITSFile.request_cloud_uploads(filenames, user.username)

    data_block = "\n".join(filenames)
    script_username = request.username or user.username
    script = render_download_script(data_block, username=script_username)

    return Response(
        content=script,
        media_type="text/x-shellscript",
        headers={"Content-Disposition": "attachment; filename=download.sh"}
    )
