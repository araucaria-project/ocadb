"""Tests for FITSFile model."""
import pytest
from datetime import datetime, timezone

from ocadb.models.file import (
    FITSFile, FileClassification, StorageStatus, StorageLocationStatus, StorageStatusType, FitsHeader,
)
from tests.conftest import make_fits_header, make_storage_status


# --- Construction ---

def test_fitsfile_construction():
    f = FITSFile(
        filename="foo.fits",
        file_class=FileClassification.RAW,
        obs_name="obs001",
        file_status=make_storage_status(),
    )
    assert f.filename == "foo.fits"
    assert f.file_class == FileClassification.RAW
    assert f.obs_name == "obs001"


def test_fitsfile_default_access_tags_empty():
    f = FITSFile(
        filename="foo.fits",
        file_class=FileClassification.ZDF,
        obs_name="obs001",
        file_status=make_storage_status(),
    )
    assert f.access_tags == []


def test_fitsfile_digest_valid_sha256():
    import base64
    digest_val = "sha-256=" + base64.b64encode(b"x" * 32).decode()
    f = FITSFile(
        filename="foo.fits",
        file_class=FileClassification.RAW,
        obs_name="obs001",
        file_status=make_storage_status(),
        digest=digest_val,
    )
    assert f.digest == digest_val


def test_fitsfile_digest_invalid_format():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        FITSFile(
            filename="foo.fits",
            file_class=FileClassification.RAW,
            obs_name="obs001",
            file_status=make_storage_status(),
            digest="not-a-valid-digest",
        )


def test_fitsfile_all_file_classifications():
    for cls in FileClassification:
        f = FITSFile(
            filename=f"test_{cls.value}.fits",
            file_class=cls,
            obs_name="obs001",
            file_status=make_storage_status(),
        )
        assert f.file_class == cls


# --- pop_fits_header / pop_metadata ---

def test_pop_fits_header_detaches_and_derives_image_type():
    header = make_fits_header(IMAGETYP="dark")
    f = FITSFile(
        filename="foo.fits",
        file_class=FileClassification.RAW,
        obs_name="obs001",
        file_status=make_storage_status(),
        fits_header=header,
    )
    popped = f.pop_fits_header()
    assert popped == header
    assert f.fits_header is None
    assert f.image_type == "dark"


def test_pop_metadata_detaches_and_resets_to_empty_dict():
    f = FITSFile(
        filename="foo.fits",
        file_class=FileClassification.RAW,
        obs_name="obs001",
        file_status=make_storage_status(),
        metadata={"quality": "good"},
    )
    popped = f.pop_metadata()
    assert popped == {"quality": "good"}
    assert f.metadata == {}  # reset to {}, not None — metadata is never Optional


# --- StorageStatus ---

def test_storage_status_all_not_stored():
    s = make_storage_status(StorageStatusType.NOT_STORED)
    assert s.observatory.status == StorageStatusType.NOT_STORED
    assert s.hub.status == StorageStatusType.NOT_STORED
    assert s.cloud.status == StorageStatusType.NOT_STORED


def test_storage_status_partial():
    obs_loc = StorageLocationStatus(ready=True, check_needed=False, status=StorageStatusType.STORED)
    hub_loc = StorageLocationStatus(ready=False, check_needed=True, status=StorageStatusType.STORING)
    cloud_loc = StorageLocationStatus(ready=False, check_needed=False, status=StorageStatusType.NOT_STORED)
    s = StorageStatus(observatory=obs_loc, hub=hub_loc, cloud=cloud_loc)
    assert s.observatory.ready is True
    assert s.hub.status == StorageStatusType.STORING
    assert s.cloud.ready is False


def test_storage_status_all_types():
    for status_type in StorageStatusType:
        loc = StorageLocationStatus(ready=False, check_needed=False, status=status_type)
        assert loc.status == status_type


# --- resolve_source_files ---

async def test_resolve_source_files_empty(beanie):
    f = FITSFile(
        filename="master.fits",
        file_class=FileClassification.MASTER,
        obs_name="obs001",
        file_status=make_storage_status(),
        source_filenames=[],
    )
    await f.insert()
    result = await f.resolve_source_files()
    assert result == []


async def test_resolve_source_files_with_existing(beanie):
    raw1 = FITSFile(
        filename="raw1.fits",
        file_class=FileClassification.RAW,
        obs_name="obs001",
        file_status=make_storage_status(),
    )
    raw2 = FITSFile(
        filename="raw2.fits",
        file_class=FileClassification.RAW,
        obs_name="obs001",
        file_status=make_storage_status(),
    )
    await raw1.insert()
    await raw2.insert()

    master = FITSFile(
        filename="master.fits",
        file_class=FileClassification.MASTER,
        obs_name="obs001",
        file_status=make_storage_status(),
        source_filenames=["raw1.fits", "raw2.fits"],
    )
    await master.insert()

    sources = await master.resolve_source_files()
    filenames = {s.filename for s in sources}
    assert "raw1.fits" in filenames
    assert "raw2.fits" in filenames


async def test_resolve_source_files_missing_refs(beanie):
    f = FITSFile(
        filename="orphan.fits",
        file_class=FileClassification.ZDF,
        obs_name="obs001",
        file_status=make_storage_status(),
        source_filenames=["nonexistent1.fits", "nonexistent2.fits"],
    )
    await f.insert()
    result = await f.resolve_source_files()
    assert result == []


# --- DB persistence ---

async def test_fitsfile_insert_and_find(beanie):
    f = FITSFile(
        filename="findme.fits",
        file_class=FileClassification.RAW,
        obs_name="obs001",
        file_status=make_storage_status(),
    )
    await f.insert()
    found = await FITSFile.find_one(FITSFile.filename == "findme.fits")
    assert found is not None
    assert found.filename == "findme.fits"


async def test_fitsfile_unique_filename(beanie):
    from pymongo.errors import DuplicateKeyError
    f1 = FITSFile(
        filename="dup.fits",
        file_class=FileClassification.RAW,
        obs_name="obs001",
        file_status=make_storage_status(),
    )
    await f1.insert()
    f2 = FITSFile(
        filename="dup.fits",
        file_class=FileClassification.RAW,
        obs_name="obs002",
        file_status=make_storage_status(),
    )
    with pytest.raises(DuplicateKeyError):
        await f2.insert()


async def test_fitsfile_access_tags_persisted(beanie):
    f = FITSFile(
        filename="tagged.fits",
        file_class=FileClassification.RAW,
        obs_name="obs001",
        file_status=make_storage_status(),
        access_tags=["AKOND", "TEST-CAM"],
    )
    await f.insert()
    found = await FITSFile.find_one(FITSFile.filename == "tagged.fits")
    assert "AKOND" in found.access_tags
    assert "TEST-CAM" in found.access_tags


async def test_fitsfile_created_at_set_automatically(beanie):
    f = FITSFile(
        filename="timestamped.fits",
        file_class=FileClassification.RAW,
        obs_name="obs001",
        file_status=make_storage_status(),
    )
    await f.insert()
    assert isinstance(f.created_at, datetime)
