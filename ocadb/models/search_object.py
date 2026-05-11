from typing import Optional, Any

import pymongo
from beanie import Document, Link
from pydantic import BaseModel
from pymongo import IndexModel


class SearchObject(Document):
    canonized_name: Optional[str] = None
    first_alias: Optional[str] = None

    def __init__(self, *args: Any, **kwargs):
        super().__init__(*args, **kwargs)
        self.canonized_name = kwargs.get("canonized_name")
        self.first_alias = kwargs.get("first_alias")

    class Settings:
        name = "search_objects"
        indexes = [
            IndexModel([("canonized_name", pymongo.ASCENDING)], unique=True),
        ]

class SearchObjectShort(BaseModel):
    alias: str
    canonized: Link[SearchObject]


class SearchObjectAlias(Document):
    search_object: Link[SearchObject]
    alias: Optional[str] = None

    def __init__(self, *args: Any, **kwargs):
        super().__init__(*args, **kwargs)
        self.alias = kwargs.get("alias")

    class Settings:
        name = "search_object_aliases"
        indexes = [
            IndexModel([("alias", pymongo.ASCENDING)], unique=False),
        ]

# Document models for Beanie registration
document_models = [SearchObject, SearchObjectAlias]