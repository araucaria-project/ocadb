from datetime import datetime, timedelta
from typing import List, Optional

import pymongo
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
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
    "UploadRequest", "FITSFile", "document_models",
]

# Statuses that mean "not sitting in cloud storage yet" — a download request
# against a file in one of these states is a signal an operator needs to act on.
_CLOUD_UPLOAD_PENDING_STATUSES = [
    StorageStatusType.NOT_STORED.value,
    StorageStatusType.DELETED.value,
    StorageStatusType.CORRUPTED.value,
]
_CLOUD_UPLOAD_ALREADY_FLAGGED_STATUSES = _CLOUD_UPLOAD_PENDING_STATUSES + [StorageStatusType.REQUESTED.value]


class UploadRequest(BaseModel):
    """OcaDB-local record of who asked for a file that isn't in cloud storage yet.

    Deliberately not part of the shared `datamodels` contract: it's an
    operator-review concern specific to OcaDB, not something the file
    producer side needs to know about.
    """
    requested_by: str
    requested_at: datetime


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

    # Operator review queue — who has asked to download this file while it wasn't in cloud storage
    upload_requests: List[UploadRequest] = Field(default_factory=list)

    # Small derived scalar kept from fits_header (e.g. "zero", "dark", "science") even
    # though the full header itself is no longer persisted here — see fits_header below.
    image_type: Optional[str] = Field(
        None, description="FITS header IMAGETYP, copied at write time (header itself is not persisted)"
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

    @classmethod
    async def request_cloud_uploads(cls, filenames: List[str], username: str) -> None:
        """Flag files that aren't in cloud storage as REQUESTED and log the requester.

        Called when a user asks to download files (e.g. via the download-script
        endpoint). Files already stored/scheduled/queued/storing in cloud are left
        untouched — this is purely a signal for an operator to review and decide
        whether/when to actually run the upload.
        """
        if not filenames:
            return

        now = datetime.utcnow()
        entry = {"requested_by": username, "requested_at": now}

        # Log the request against anything still pending an upload decision,
        # even if it was already flagged REQUESTED by an earlier request.
        await cls.find({
            "filename": {"$in": filenames},
            "file_status.cloud.status": {"$in": _CLOUD_UPLOAD_ALREADY_FLAGGED_STATUSES},
        }).update({
            "$push": {"upload_requests": entry},
            "$set": {"updated_at": now},
        })

        # Only flip the status the first time — don't stomp on an in-flight upload.
        await cls.find({
            "filename": {"$in": filenames},
            "file_status.cloud.status": {"$in": _CLOUD_UPLOAD_PENDING_STATUSES},
        }).update({
            "$set": {
                "file_status.cloud.status": StorageStatusType.REQUESTED.value,
                "file_status.cloud.check_needed": True,
            },
        })

    def pop_fits_header(self) -> Optional[FitsHeader]:
        """Detach fits_header (deriving image_type from it first) before this object
        is persisted — the full header must never be written to FITSFile storage,
        only to the parent Observation. Returns the detached header for the caller
        to hand to Observation.store_file/adopt_header_if_precedent.
        """
        header = self.fits_header
        self.image_type = header.IMAGETYP if header is not None else None
        self.fits_header = None
        return header

    def pop_metadata(self) -> dict:
        """Detach metadata before this object is persisted — metadata must never be
        written to FITSFile storage, only to the parent Observation. Unlike
        pop_fits_header, metadata is a non-Optional dict, so it resets to {} not None.
        """
        metadata = self.metadata
        self.metadata = {}
        return metadata

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
