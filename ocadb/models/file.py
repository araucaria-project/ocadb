from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

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
    StorageStatusType.ON_DEMAND.value,
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

    # Set when a moderator approves this file for upload (REQUESTED -> QUEUED) via
    # approve_uploads() below — an audit trail in the same spirit as upload_requests.
    approved_by: Optional[str] = Field(None, description="Moderator who last approved this file for upload")
    approved_at: Optional[datetime] = Field(None, description="When this file was last approved for upload")

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
            IndexModel([("observation_id", pymongo.ASCENDING)]),
        ]
        validate_assignment = True

    @classmethod
    async def request_cloud_uploads(cls, filenames: List[str], username: str) -> None:
        """Flag files that aren't in cloud storage as REQUESTED and log the requester.

        Called when a user asks to download files (e.g. via the download-script
        endpoint). Files already stored/scheduled/queued/storing in cloud are left
        untouched — this is purely a signal for an operator to review and decide
        whether/when to actually run the upload. ON_DEMAND files (available at the
        producer but not proactively uploaded) are flipped to REQUESTED just like
        NOT_STORED/DELETED/CORRUPTED, since a download request is exactly the signal
        they were waiting for.
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

    @classmethod
    async def approve_uploads(cls, obs_ids: List[PydanticObjectId], username: str) -> int:
        """Moderator approval step: flips every REQUESTED file belonging to the given
        observations to QUEUED, the signal `sroca` polls for to actually perform the
        S3 upload. Returns the number of files flipped.
        """
        if not obs_ids:
            return 0

        now = datetime.utcnow()
        result = await cls.find({
            "observation_id": {"$in": obs_ids},
            "file_status.cloud.status": StorageStatusType.REQUESTED.value,
        }).update({
            "$set": {
                "file_status.cloud.status": StorageStatusType.QUEUED.value,
                "file_status.cloud.check_needed": True,
                "approved_by": username,
                "approved_at": now,
                "updated_at": now,
            },
        })
        return result.modified_count if result is not None else 0

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

    @classmethod
    async def resolve_lineage(
        cls, root_files: List["FITSFile"]
    ) -> Tuple[Dict[str, "FITSFile"], List[Tuple[str, str]]]:
        """Walk the full transitive closure of source_filenames starting from root_files.

        Same frontier/collected BFS shape as generate_download_script's calibration walk
        (api/routers/observations_v2.py) — source files can be multi-level (RAW -> MASTER
        -> ZDF chains) and are looked up purely by filename, not scoped to any one
        observation, matching how the producer assigns them. Unlike that endpoint, this
        also keeps the (child_filename, source_filename) edges, not just the flat
        filename set, since callers need the actual ancestry graph.

        Returns (nodes: filename -> FITSFile, edges: list of (child_filename, source_filename)).
        """
        nodes: Dict[str, "FITSFile"] = {f.filename: f for f in root_files}
        edges: List[Tuple[str, str]] = []

        frontier = {f.filename for f in root_files}
        while frontier:
            batch = [nodes[name] for name in frontier]
            frontier = set()
            for f in batch:
                for source_name in (f.source_filenames or []):
                    edges.append((f.filename, source_name))
                    if source_name not in nodes:
                        frontier.add(source_name)

            if not frontier:
                break
            new_files = await cls.find({"filename": {"$in": list(frontier)}}).to_list()
            for nf in new_files:
                nodes[nf.filename] = nf
            # Filenames with no matching FITSFile document (e.g. not yet ingested) stay
            # out of `nodes` but remain referenced by an edge — drop them from the next
            # frontier since there's nothing further to walk from them.
            frontier = {name for name in frontier if name in nodes}

        return nodes, edges

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
