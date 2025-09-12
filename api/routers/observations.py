from fastapi import APIRouter, HTTPException, status, Body, Depends
from beanie import PydanticObjectId
from typing import List, Annotated, Dict, Any

from ocadb.models import Observation, FitsHeader
from api.services.auth_service import AuthService

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


@router.get("/{id}", response_description="Get a single Observation", response_model=Observation)
async def get_observation(id: PydanticObjectId):
    """Get observation by ID"""
    observation = await Observation.get(id)
    if observation is None:
        raise HTTPException(status_code=404, detail=f"Observation with ID {id} not found")
    return observation


@router.get("/", response_description="List Observations", response_model=List[Observation])
async def list_observations():
    """List all observations"""
    observations = await Observation.find_all().to_list()
    return observations


@router.get("/by-filename/{filename}", response_description="Get Observation by filename", response_model=Observation)
async def get_observation_by_filename(filename: str):
    """Get observation by FITS filename"""
    observation = await Observation.find_one(Observation.filename == filename)
    if observation is None:
        raise HTTPException(status_code=404, detail=f"Observation with filename {filename} not found")
    return observation


@router.get("/by-object/{object_name}", response_description="List Observations by object name", response_model=List[Observation])
async def list_observations_by_object(object_name: str):
    """List observations of a specific object"""
    observations = await Observation.find(Observation.fits_header.OBJECT == object_name).to_list()
    return observations


@router.get("/by-filter/{filter_name}", response_description="List Observations by filter", response_model=List[Observation])
async def list_observations_by_filter(filter_name: str):
    """List observations using a specific filter"""
    observations = await Observation.find(Observation.fits_header.FILTER == filter_name).to_list()
    return observations


# @router.put("/{id}/metadata", response_description="Update observation metadata")
# async def update_observation_metadata(
#     id: PydanticObjectId,
#     metadata: Annotated[Dict[str, Any], Body(...)],
#     token: Annotated[str, Depends(AuthService.validate_token)]
# ):
#     """Update observation metadata (quality checks, processing info, etc.)"""
#     observation = await Observation.get(id)
#     if observation is None:
#         raise HTTPException(status_code=404, detail=f"Observation with ID {id} not found")
#
#     # Update metadata while preserving existing data
#     observation.metadata.update(metadata)
#     await observation.save()
#
#     return {"message": "Metadata updated successfully", "observation_id": str(id)}


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