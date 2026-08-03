from datetime import datetime, timedelta
from typing import List, Optional

import pymongo
from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

from api.services.s3_api_service import S3Connection
from datamodels.ocadb.fits import (
    DigestStr,
    FileClassification,
    FITSFile as FITSFileBase,
    FitsHeader,
    StorageLocationStatus,
    StorageStatus,
    StorageStatusType,
)
from ocadb.models.s3_presigned_url import S3PresignedUrl

__all__ = [
    "DigestStr", "FileClassification", "FitsHeader",
    "StorageLocationStatus", "StorageStatus", "StorageStatusType",
    "FITSFile", "document_models",
]


class FITSFile(FITSFileBase, Document):
    """FITS file document — extends the shared plain FITSFile contract
    (see datamodels.ocadb.fits) with ocadb's persistence-layer concerns: Beanie
    indexes/settings, Mongo-typed relations, and DB-only fields."""

    # Override: Mongo reference type instead of the shared plain-str contract
    observation_id: Optional[PydanticObjectId] = Field(None, description="Parent observation reference")

    # Access control — denormalized from parent Observation for aggregation filtering
    access_tags: List[str] = Field(
        default_factory=list,
        description="Access control tags inherited from parent observation (INSTRUME, ORIGIN, PI)"
    )

    class Settings:
        name = "fits_files"
        indexes = [
            IndexModel([("filename", pymongo.ASCENDING)], unique=True),
            IndexModel([("file_class", pymongo.ASCENDING)]),
            IndexModel([("file_status.cloud.check_needed", pymongo.ASCENDING)]),
            IndexModel([("file_status.cloud.ready", pymongo.ASCENDING)]),
            IndexModel([("file_status.cloud.status", pymongo.ASCENDING)]),
            IndexModel([("access_tags", pymongo.ASCENDING)]),
            IndexModel([("created_at", pymongo.DESCENDING)]),
        ]
        validate_assignment = True

    async def resolve_source_files(self) -> List["FITSFile"]:
        """Resolve source file references to actual documents.

        Returns:
            List of FITSFile documents that exist in the database.
            Empty list if no source files exist yet.
        """
        if not self.source_filenames:
            return []
        return await FITSFile.find({"filename": {"$in": self.source_filenames}}).to_list()

    async def get_presigned_url(self, expires_in):
        s3_con = S3Connection()
        presigned_url = await s3_con.get_presigned_url(
            params={'Bucket': s3_con.bucket_name, 'Key': self.filename}, expires_in=expires_in)
        s3_presigned_url_response = S3PresignedUrl(
            description=self.filename, observation_name=str(self.obs_name), url=presigned_url,
            valid_until=(datetime.utcnow() + timedelta(seconds=expires_in)).strftime('%Y%m%dT%H%M%SZ'))
        return s3_presigned_url_response

    async def get_plain_presigned_url(self, expires_in):
        s3_con = S3Connection()
        presigned_url = await s3_con.get_presigned_url(
            params={'Bucket': s3_con.bucket_name, 'Key': self.filename}, expires_in=expires_in)
        return presigned_url


# Document models for Beanie registration
document_models = [FITSFile]
