import array

import pymongo
from astropy.units.quantity_helper.function_helpers import unique
from attr.filters import exclude
from beanie import Document, Indexed, PydanticObjectId, Link
from pydantic import BaseModel, Field, model_validator, PrivateAttr
from typing import Optional, Dict, Any, Annotated, List
from datetime import datetime
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema
from pymongo import IndexModel
from dateutil import parser

from ocadb.models.file import FitsHeader, FITSFile
from ocadb.models.geo import SkyCoord, Point2D


class Observation(Document):
    """Astronomical observation with FITS header and metadata"""
    
    # Core identification
    obs_name: str = Field(..., description="Observation name", unique=True)
    # filename: str = Field(..., description="FITS filename", unique=True)
    file_name: Optional[str] = Field(None, description="FITS filename", unique=True)
    object_id: Optional[str] = Field(None, description="Reference to observed Object document")

    # files support
    # files: List[PydanticObjectId] = Field([])
    files: List[Link[FITSFile]] = []

    def store_file(self, fits_file: FITSFile):
        self.files.append(fits_file)
    
    # Raw FITS header (flat structure, exact field names)
    fits_header: FitsHeader = Field(..., description="Complete FITS header")
    
    # Flexible metadata container (quality checks, processing info, etc.)
    metadata: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Observation metadata (quality checks, processing info, etc.)"
    )

    # Coordinates
    telescope_coordinates: SkyCoord = Field(SkyCoord, description="telescope direction coordinates", exclude=True) # exclude field from json dump

    # Access control
    access_tags: Optional[list[str]] = Field(list[str], description="tags for document access control", exclude=True) # exclude field from json dump

    # observation date
    date_obs: datetime = Field(datetime, description="internal ISO Date to datetime conversion", exclude=True) # exclude field from json dump

    @model_validator(mode='after')
    def store_skycoord(self):
        self.telescope_coordinates = SkyCoord(radec=(self.fits_header.RA_TEL, self.fits_header.DEC_TEL))
        return self

    @model_validator(mode='after')
    def store_obs_date(self):
        self.date_obs = parser.parse(self.fits_header.DATE_OBS)
        return self

    @model_validator(mode='after')
    def store_tags(self):
        self.access_tags = []

        if hasattr(self.fits_header, 'INSTRUME'):
            self.access_tags.append(self.fits_header.INSTRUME)
        if hasattr(self.fits_header, 'ORIGIN'):
            self.access_tags.append(self.fits_header.ORIGIN)
        if hasattr(self.fits_header, 'PI'):
            self.access_tags.append(self.fits_header.PI)

        return self

    # Processing timestamps
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow, description="Record creation time")
    updated_at: Optional[datetime] = Field(None, description="Last update time")

    class Settings:
        name = "observations"
        indexes = [
            # filename needs 2 indexes, read: https://www.mongodb.com/community/forums/t/e11000-duplicate-key-error-collection-with-period-in-the-text/293708/11
            IndexModel([("obs_name", pymongo.TEXT)], unique=False),
            IndexModel([("obs_name")], unique=True),
            "object_id", 
            "fits_header.DATE_OBS",
            "fits_header.OBJECT",
            "fits_header.FILTER",
            "fits_header.TELESCOP",
            "fits_header.JD",
            IndexModel([("telescope_coordinates.lon_lat", pymongo.GEOSPHERE)], name="skycoord_spatial_index"), # geospatial index
        ]


# Document models for Beanie registration
document_models = [Observation]