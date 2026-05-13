from typing import Optional, Any

import pymongo
from beanie import Document, Link
from pydantic import BaseModel
from pymongo import IndexModel


class SearchObject(Document):
    canonized_name: Optional[str] = None
    first_alias: Optional[str] = None
    ra: Optional[float] = 0.0
    dec: Optional[float] = 0.0

    def __init__(self, *args: Any, **kwargs):
        super().__init__(*args, **kwargs)
        self.canonized_name = kwargs.get("canonized_name")
        self.first_alias = kwargs.get("first_alias")
        self.ra = kwargs.get("ra")
        self.dec = kwargs.get("dec")

    class Settings:
        name = "search_objects"
        indexes = [
            IndexModel([("canonized_name", pymongo.ASCENDING)], unique=True),
        ]

class SearchTag(Document):
    tag_name: Optional[str] = None
    tag_description: Optional[str] = None
    tag_color: Optional[str] = None

    def __init__(self, *args: Any, **kwargs):
        super().__init__(*args, **kwargs)
        self.tag_name = kwargs.get("tag_name")
        self.tag_description = kwargs.get("tag_description")
        self.tag_color = kwargs.get("tag_color")

    class Settings:
        name = "search_tags"
        indexes = [
            IndexModel([("tag_name", pymongo.ASCENDING)], unique=True),
        ]

# Document models for Beanie registration
document_models = [SearchObject, SearchTag]