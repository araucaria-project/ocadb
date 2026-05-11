import array

import pymongo
from astropy.units.quantity_helper.function_helpers import unique
from attr.filters import exclude
from beanie import Document, Indexed, PydanticObjectId, Link, after_event, Replace, Update, Insert
from pyaraucaria.fits import fits_header
from pydantic import BaseModel, Field, model_validator, PrivateAttr
from typing import Optional, Dict, Any, Annotated, List, Set
from datetime import datetime
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema
from pymongo import IndexModel
from dateutil import parser
from pyaraucaria.lookup_objects import name_canonizator

from ocadb.models.file import FitsHeader, FITSFile, FileClassification
from ocadb.models.geo import SkyCoord, Point2D
from ocadb.models.search_object import SearchObject


class Observation(Document):
    """Astronomical observation with FITS header and metadata"""

    def __init__(self, *args: Any, **kwargs):
        super().__init__(*args, **kwargs)
        self.obs_name= kwargs.get("obs_name")
        self.file_name= kwargs.get("file_name")
        self.fits_header = kwargs.get("fits_header")


    # Core identification
    obs_name: str = Field(..., description="Observation name", unique=True)
    # filename: str = Field(..., description="FITS filename", unique=True)
    file_name: Optional[str] = Field(None, description="FITS filename", unique=True)
    object_id: Optional[str] = Field(None, description="Reference to observed Object document")
    canonized_object_name: Optional[str] = Field(str, description="Canonized astronomical object name")

    # files support
    files: List[Link[FITSFile]] = []
    filetypes: Set[FileClassification] = set()
    source_files: Set[str] = set()

    # async def update_source_files(self, new_file:FITSFile):
    #     if new_file.filename not in self.source_files:
    #         self.source_files.add(new_file.filename)
    #         for file in new_file.source_filenames:
    #             fits_file = await FITSFile.find_one(FITSFile.filename == file)
    #             await self.update_source_files(fits_file)

    async def store_file(self, fits_file: FITSFile):
        self.files.append(fits_file)
        self.filetypes.add(fits_file.file_class)
        self.source_files.update(fits_file.source_filenames)

    def store_metadata(self, metadata: dict):
        self.metadata = metadata

    def get_id(self):
        return self.id

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
    oca_jd: Optional[int] = Field(None, description="OCM representation of observation date")

    def store_fits_header(self, fits_header):
        self.fits_header = fits_header



    @model_validator(mode='after')
    def store_skycoord(self):
        # workaround - pydantic bug?? similar to https://github.com/google/adk-python/issues/3633
        if isinstance(self.fits_header, dict):
            self.fits_header = FitsHeader.model_validate(self.fits_header)
        if not self.fits_header.RA or not self.fits_header.DEC:
            self.telescope_coordinates = SkyCoord(radec=(self.fits_header.RA_TEL, self.fits_header.DEC_TEL))
        else:
            self.telescope_coordinates = SkyCoord(radec=(self.fits_header.RA, self.fits_header.DEC))

        return self

    @model_validator(mode='after')
    def store_canonical_object(self):
        if isinstance(self.fits_header, dict):
            self.fits_header = FitsHeader.model_validate(self.fits_header)
        self.canonized_object_name = name_canonizator(self.fits_header.OBJECT)

        return self

    @model_validator(mode='after')
    def store_obs_date(self):
        # workaround - pydantic bug?? similar to https://github.com/google/adk-python/issues/3633
        if isinstance(self.fits_header, dict):
            self.fits_header = FitsHeader.model_validate(self.fits_header)
        self.date_obs = parser.parse(self.fits_header.DATE_OBS)
        return self

    @model_validator(mode='after')
    def store_tags(self):
        # workaround - pydantic bug?? similar to https://github.com/google/adk-python/issues/3633
        if isinstance(self.fits_header, dict):
            self.fits_header = FitsHeader.model_validate(self.fits_header)

        self.access_tags = []

        if hasattr(self.fits_header, 'INSTRUME') and self.fits_header.INSTRUME is not None:
            self.access_tags.append(self.fits_header.INSTRUME)
        if hasattr(self.fits_header, 'ORIGIN') and self.fits_header.ORIGIN is not None:
            self.access_tags.append(self.fits_header.ORIGIN)
        if hasattr(self.fits_header, 'PI') and self.fits_header.PI:
            self.access_tags.append(self.fits_header.PI)
        if hasattr(self.fits_header, 'OBSTYPE'):
            if self.fits_header.OBSTYPE == 'calib':
                self.access_tags.append((self.fits_header.OBSTYPE))

        return self

    @model_validator(mode='after')
    def store_oca_jd(self):
        if self.fits_header.JD is not None:
            self.oca_jd = int(self.fits_header.JD) % 10000
        return self

    @after_event(Insert, Replace, Update)
    async def propagate_values(self):
        """Propagate access_tags to all linked FITSFile documents after any write."""
        if not self.files:
            return
        file_ids = [
            f.id if isinstance(f, FITSFile) else f.ref.id
            for f in self.files
        ]
        await FITSFile.find({"_id": {"$in": file_ids}}).update_many(
            {"$set": {"access_tags": self.access_tags}}
        )

        if self.canonized_object_name:
            search_object = await SearchObject.find_one(SearchObject.canonized_name == self.canonized_object_name,
                                                        projection_model=SearchObject)

            if search_object is None:
                search_object = SearchObject(canonized_name=self.canonized_object_name, first_alias=self.fits_header.OBJECT)
                await search_object.insert()

        # if self.canonized_object_name:
        #     alias = await SearchObjectAlias.find_one(SearchObjectAlias.alias == self.fits_header.OBJECT, projection_model=SearchObjectAlias)
        #
        #     if alias is None:
        #         search_object = await SearchObject.find_one(SearchObject.canonized_name == self.canonized_object_name, projection_model=SearchObject)
        #         if search_object is None:
        #             search_object = SearchObject(canonized_name=self.canonized_object_name)
        #             await search_object.insert()
        #
        #         alias = SearchObjectAlias(alias=self.fits_header.OBJECT, search_object=search_object)
        #         await alias.insert()

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
            "canonized_object_name",
            "date_obs",
            "fits_header.DATE_OBS",
            "fits_header.OBJECT",
            "fits_header.FILTER",
            "fits_header.TELESCOP",
            "fits_header.JD",
            "fits_header.IMAGETYP",
            "fits_header.OBSTYPE",
            "fits_header.PI",
            "fits_header.SCIPROG",
            "fits_header.AIRMASS",
            "fits_header.EXPTIME",
            "oca_jd",
            "access_tags",
            IndexModel([("telescope_coordinates.lon_lat", pymongo.GEOSPHERE)], name="skycoord_spatial_index"), # geospatial index
        ]
        validate_assignment = True


# Document models for Beanie registration
document_models = [Observation]