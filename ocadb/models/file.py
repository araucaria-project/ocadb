import pymongo
from attr.filters import exclude
from beanie import Document, Indexed
from pyaraucaria.fits import fits_header
from pydantic import BaseModel, Field, model_validator, PrivateAttr
from typing import Optional, Dict, Any, Annotated
from datetime import datetime

from pymongo import IndexModel

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
    PIERSIDE: Optional[str] = None
    FLAT_ERA: Optional[int] = None
    ZERO_ERA: Optional[int] = None
    DARK_ERA: Optional[int] = None
    TEST: Optional[int] = None
    CCD_BLCL: Optional[str] = Field(None, alias="CCD-BLCL")
    CCD_SCMP: Optional[str] = Field(None, alias="CCD-SCMP")
    CCD_PORT: Optional[str] = Field(None, alias="CCD-PORT")
    CCD_VSSP: Optional[str] = Field(None, alias="CCD-VSSP")
    BZERO: Optional[int] = None

    model_config = {"extra": "allow"} # model_config = ConfigDict(extra='allow')

class FITSFile(Document):
    filename: str = Field(..., description="FITS filename", unique=True)
    file_class: str = Field(...)
    file_status: str = Field(...)
    # Raw FITS header (flat structure, exact field names)
    fits_header: FitsHeader = Field(..., description="Complete FITS header")

    class Settings:
        name = "fits_files",
        indexes = [
            IndexModel([("filename", pymongo.TEXT)], unique=False),
            IndexModel(["filename"], unique=True)
        ]

# Document models for Beanie registration
document_models = [FITSFile]