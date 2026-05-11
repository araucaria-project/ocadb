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


# Document models for Beanie registration
document_models = [SearchObject]