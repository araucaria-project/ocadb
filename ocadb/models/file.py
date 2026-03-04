from pathlib import PosixPath

from beanie import Document, PydanticObjectId
from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Annotated
from datetime import datetime, timezone, timedelta
from enum import Enum

import pymongo
from pymongo import IndexModel

from api.services.s3_api_service import S3Connection
from ocadb.models.s3_presigned_url import S3PresignedUrl


# Enums for better type safety and readability
class StorageStatusType(str, Enum):
    """Status types for file storage operations."""
    NOT_STORED = "not_stored"
    DELETED = "deleted"
    STORED = "stored"
    CORRUPTED = "corrupted"
    REQUESTED = "requested"
    SCHEDULED = "scheduled"
    QUEUED = "queued"
    STORING = "storing"


class FileClassification(str, Enum):
    """FITS file classification types."""
    RAW = "raw"
    ZDF = "zdf"
    MASTER = "master"
    SOURCE = "source"
    TMP = "tmp"
    TEST = "test"


DigestStr = Annotated[
    str,
    Field(
        pattern=r"^(sha-256|sha-512|md5)=[A-Za-z0-9+/]+={0,2}$",
        description="Content digest per RFC 3230/8240 (e.g., 'sha-256=<base64>')",
    ),
]


class FitsHeader(BaseModel):
    """Direct mapping of FITS header keywords (exact field names)"""
    SIMPLE: Optional[bool] = None
    BITPIX: Optional[int] = None
    NAXIS: Optional[int] = None
    NAXIS1: Optional[int] = None
    NAXIS2: Optional[int] = None
    OCASTD: Optional[str] = None
    OBSERVAT: Optional[str] = None
    OBS_LAT: Optional[float] = Field(None, alias="OBS-LAT")
    OBS_LONG: Optional[float] = Field(None, alias="OBS-LONG")
    OBS_ELEV: Optional[int] = Field(None, alias="OBS-ELEV")
    ORIGIN: Optional[str] = None
    TELESCOP: Optional[str] = None
    DATE_OBS: Optional[str] = Field(None, alias="DATE-OBS")
    JD: Optional[float] = None
    RA: Optional[float] = None
    DEC: Optional[float] = None
    EQUINOX: Optional[str] = None
    RA_OBJ: Optional[str] = None
    DEC_OBJ: Optional[str] = None
    RA_TEL: Optional[float] = None
    DEC_TEL: Optional[float] = None
    ALT_TEL: Optional[float] = None
    AZ_TEL: Optional[float] = None
    AIRMASS: Optional[float] = None
    OBSMODE: Optional[str] = None
    FOCUS: Optional[int] = None
    ROTATOR: Optional[float] = None
    OBSERVER: Optional[str] = None
    IMAGETYP: Optional[str] = None
    OBSTYPE: Optional[str] = None
    OBJECT: Optional[str] = None
    OBS_PROG: Optional[str] = Field(None, alias="OBS-PROG")
    NLOOPS: Optional[int] = None
    LOOP: Optional[int] = None
    FILTER: Optional[str] = None
    EXPTIME: Optional[float] = None
    INSTRUME: Optional[str] = None
    CCD_TEMP: Optional[float] = Field(None, alias="CCD-TEMP")
    SET_TEMP: Optional[str] = Field(None, alias="SET-TEMP")
    XBINNING: Optional[int] = None
    YBINNING: Optional[int] = None
    READ_MOD: Optional[int] = Field(None, alias="READ-MOD")
    GAIN_MOD: Optional[int] = Field(None, alias="GAIN-MOD")
    GAIN: Optional[float] = None
    RON: Optional[float] = None
    SUBRASTR: Optional[str] = None
    SCALE: Optional[float] = None
    SATURATE: Optional[str] = None
    PIERSIDE: Optional[int] = None
    FLAT_ERA: Optional[int] = None
    ZERO_ERA: Optional[int] = None
    DARK_ERA: Optional[int] = None
    TEST: Optional[int] = None
    CCD_BLCL: Optional[str] = Field(None, alias="CCD-BLCL")
    CCD_SCMP: Optional[str] = Field(None, alias="CCD-SCMP")
    CCD_PORT: Optional[str] = Field(None, alias="CCD-PORT")
    CCD_VSSP: Optional[str] = Field(None, alias="CCD-VSSP")
    BZERO: Optional[int] = None

    # Allow additional FITS header fields not explicitly defined
    model_config = {"extra": "allow"}

    def __init__(self, dictionary):
        super().__init__()
        for key, value in dictionary.items():
            setattr(self, key, value)

class StorageLocationStatus(BaseModel):
    """Storage status at a specific location (observatory, hub, or cloud)."""
    ready: bool = Field(..., description="Whether the file exists at this location")
    check_needed: bool = Field(..., description="Whether file existence needs verification")
    status: StorageStatusType = Field(..., description="Current storage status")
    expected_time: Optional[datetime] = Field(None, description="Expected completion time for pending operations")


class StorageStatus(BaseModel):
    """Aggregated storage status across all storage locations."""
    observatory: StorageLocationStatus = Field(..., description="Observatory storage status")
    hub: StorageLocationStatus = Field(..., description="Hub storage status")
    cloud: StorageLocationStatus = Field(..., description="Cloud storage status")


class FITSFile(Document):
    """FITS file document with header metadata, storage status, and relations."""

    # Core identification
    filename: str = Field(..., description="FITS filename")
    file_class: FileClassification = Field(..., description="File classification type")
    path: Optional[PosixPath] = Field(None, description="PosixPath to the file")

    # File metadata
    filesize: Optional[int] = Field(None, description="File size in bytes")
    mtime: Optional[datetime] = Field(None, description="Source file modification time (UTC preferred)")
    digest: Optional[DigestStr] = None

    # Relations
    observation_id: Optional[PydanticObjectId] = Field(None, description="Parent observation reference")
    obs_name: str = Field(..., description="Parent observation name")

    source_filenames: List[str] = Field(
        default_factory=list,
        description="Source file references (by filename)"
    )

    # FITS metadata
    fits_header: Optional[FitsHeader] = Field(None, description="Complete FITS header")

    # Storage tracking
    file_status: StorageStatus = Field(..., description="Storage status across all locations")

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Record creation time"
    )
    updated_at: Optional[datetime] = Field(None, description="Last update time")

    # @model_validator(mode='after')
    # async def store_observation(self):
    #     if self.observation_id is not None:
    #         observation = await Observation.get(id)
    #         if observation is None:
    #             raise HTTPException(status_code=404, detail=f"Observation with ID {id} not found")
    #         observation.store_file(self.observation_id)

    class Settings:
        name = "fits_files"
        indexes = [
            IndexModel([("filename", pymongo.ASCENDING)], unique=True),
            # IndexModel([("observation_id", pymongo.ASCENDING)]),
            IndexModel([("file_class", pymongo.ASCENDING)]),
            IndexModel([("file_status.cloud.check_needed", pymongo.ASCENDING)]),
            IndexModel([("file_status.cloud.ready", pymongo.ASCENDING)]),
            IndexModel([("file_status.cloud.status", pymongo.ASCENDING)]),
            IndexModel([("created_at", pymongo.DESCENDING)]),
        ]

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
        s3_presigned_url_response = S3PresignedUrl(description=self.filename, observation_name=str(self.obs_name), url=presigned_url, valid_until=(
                    datetime.utcnow() + timedelta(seconds=expires_in)).strftime('%Y%m%dT%H%M%SZ'))
        return s3_presigned_url_response

# Document models for Beanie registration
document_models = [FITSFile]