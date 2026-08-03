from typing import Any, List

import pymongo
from beanie import Document, Link, after_event, Replace, Update, Insert
from pydantic import Field, model_validator
from pymongo import IndexModel
from dateutil import parser
from pyaraucaria.lookup_objects import name_canonizator

from datamodels.ocadb.observation import ObservationBase
from ocadb.models.file import FitsHeader, FITSFile, FileClassification
from ocadb.models.geo import SkyCoord, Point2D
from ocadb.models.search_object import SearchObject

__all__ = ["ObservationBase", "Observation", "document_models"]


class Observation(ObservationBase, Document):
    """Astronomical observation document — extends the shared plain
    Observation contract (see datamodels.ocadb.observation) with ocadb's
    persistence-layer concerns: Beanie indexes/settings, linked FITSFile
    documents, and DB-only event hooks."""

    def __init__(self, *args: Any, **kwargs):
        super().__init__(*args, **kwargs)
        self.obs_name = kwargs.get("obs_name")
        self.file_name = kwargs.get("file_name")
        self.fits_header = kwargs.get("fits_header")

    # files support — link to FITSFile documents (DB-only relation)
    files: List[Link[FITSFile]] = []

    # Coordinates — DB-only, not part of the shared plain contract
    telescope_coordinates: SkyCoord = Field(SkyCoord, description="telescope direction coordinates", exclude=True)  # exclude field from json dump

    async def store_file(self, fits_file: FITSFile):
        self.files.append(fits_file)
        self.filetypes.add(fits_file.file_class)

        self.obs_tags.add(fits_file.file_class)

        self.source_files.update(fits_file.source_filenames)

    def get_id(self):
        return self.id

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
                search_object = SearchObject(canonized_name=self.canonized_object_name, first_alias=self.fits_header.OBJECT, ra=self.fits_header.RA, dec=self.fits_header.DEC)
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
            "obs_tags",
            IndexModel([("telescope_coordinates.lon_lat", pymongo.GEOSPHERE)], name="skycoord_spatial_index"), # geospatial index
        ]
        validate_assignment = True


# Document models for Beanie registration
document_models = [Observation]
