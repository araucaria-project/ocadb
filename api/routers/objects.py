

from fastapi import APIRouter, HTTPException, status, Body
from beanie import PydanticObjectId
from typing import List

from ocadb.models import Object  # Załóżmy, że tutaj są zdefiniowane modele Beanie

router = APIRouter(prefix="/objects",
                   tags=["objects"],
                   dependencies=[],
                   responses={404: {"description": "Not found"}}
                   )

@router.post("/", response_description="Add new Object", response_model=Object, status_code=status.HTTP_201_CREATED)
async def create_object(object_data: Object = Body(...)):
    await object_data.insert()
    return object_data

@router.get("/{id}", response_description="Get a single Object", response_model=Object)
async def get_object(id: PydanticObjectId):
    object = await Object.get(id)
    if object is None:
        raise HTTPException(status_code=404, detail=f"Object with ID {id} not found")
    return object

@router.get("/", response_description="List Objects", response_model=List[Object])
async def list_objects():
    objects = await Object.find_all().to_list()
    return objects

@router.put("/{id}", response_description="Update an Object", response_model=Object)
async def update_object(id: PydanticObjectId, object_update: Object = Body(...)):
    object = await Object.get(id)
    if object is None:
        raise HTTPException(status_code=404, detail=f"Object with ID {id} not found")

    object_update_dict = object_update.dict(exclude_unset=True)
    await object.set(object_update_dict).save()
    return object

@router.delete("/{id}", response_description="Delete an Object")
async def delete_object(id: PydanticObjectId):
    delete_result = await Object.find_one(Object.id == id).delete()
    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Object with ID {id} not found")
    return {"message": "Object deleted successfully"}

# Nie zapomnij zarejestrować router w głównej aplikacji FastAPI: app.include_router(router)