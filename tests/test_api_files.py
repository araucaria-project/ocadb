"""Integration tests for /api/v2/files endpoints."""
import pytest
from tests.conftest import make_fits_header, make_storage_status
from ocadb.models.file import StorageStatusType


def make_file_payload(filename: str = "test.fits", obs_name: str = "obs_file_001", **overrides):
    header = make_fits_header()
    base = {
        "filename": filename,
        "file_class": "raw",
        "obs_name": obs_name,
        "file_status": {
            "observatory": {"ready": False, "check_needed": False, "status": "not_stored"},
            "hub": {"ready": False, "check_needed": False, "status": "not_stored"},
            "cloud": {"ready": False, "check_needed": False, "status": "not_stored"},
        },
        "fits_header": header.model_dump(by_alias=True),
        "access_tags": [],
        "source_filenames": [],
    }
    base.update(overrides)
    return base


def make_obs_payload(obs_name: str = "obs_file_001"):
    header = make_fits_header()
    return {
        "obs_name": obs_name,
        "file_name": f"{obs_name}.fits",
        "fits_header": header.model_dump(by_alias=True),
        "obs_tags": [],
    }


# --- POST /api/v2/files/ ---

async def test_create_file_requires_auth(client, beanie):
    resp = await client.post("/api/v2/files/", json=make_file_payload())
    assert resp.status_code == 401


async def test_create_file_success_with_new_obs(client, auth_headers, regular_user):
    resp = await client.post("/api/v2/files/", json=make_file_payload(), headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["filename"] == "test.fits"


async def test_create_file_with_existing_obs(client, auth_headers, regular_user):
    await client.post("/api/v2/observations/", json=make_obs_payload(), headers=auth_headers)
    resp = await client.post("/api/v2/files/", json=make_file_payload(), headers=auth_headers)
    assert resp.status_code == 201


async def test_create_duplicate_file_returns_403(client, auth_headers, regular_user):
    await client.post("/api/v2/files/", json=make_file_payload(), headers=auth_headers)
    resp = await client.post("/api/v2/files/", json=make_file_payload(), headers=auth_headers)
    assert resp.status_code == 403


async def test_create_file_force_updates_existing(client, auth_headers, regular_user):
    await client.post("/api/v2/files/", json=make_file_payload(), headers=auth_headers)
    resp = await client.post("/api/v2/files/?force=true", json=make_file_payload(filesize=9999), headers=auth_headers)
    assert resp.status_code == 200 or resp.status_code == 201


# --- GET /api/v2/files/by-filename/{file_name}/ ---

async def test_get_file_by_name(client, auth_headers, regular_user):
    await client.post("/api/v2/files/", json=make_file_payload(), headers=auth_headers)
    resp = await client.get("/api/v2/files/by-filename/test.fits/", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["filename"] == "test.fits"


async def test_get_file_by_name_not_found(client, auth_headers, regular_user):
    resp = await client.get("/api/v2/files/by-filename/nonexistent.fits/", headers=auth_headers)
    assert resp.status_code == 404


# --- GET /api/v2/files/by-fileid/{file_id}/ ---

async def test_get_file_by_id(client, auth_headers, regular_user):
    create = await client.post("/api/v2/files/", json=make_file_payload(), headers=auth_headers)
    file_id = create.json()["_id"]
    resp = await client.get(f"/api/v2/files/by-fileid/{file_id}/", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["filename"] == "test.fits"


async def test_get_file_by_id_not_found(client, auth_headers, regular_user):
    resp = await client.get("/api/v2/files/by-fileid/000000000000000000000001/", headers=auth_headers)
    assert resp.status_code == 404


# --- GET /api/v2/files/by-observation-id/{observation_id}/ ---

async def test_get_files_for_observation(client, auth_headers, regular_user):
    create_obs = await client.post("/api/v2/observations/", json=make_obs_payload(obs_name="obs_with_files"), headers=auth_headers)
    obs_id = create_obs.json()["_id"]
    await client.post("/api/v2/files/", json=make_file_payload(filename="linked.fits", obs_name="obs_with_files"), headers=auth_headers)
    resp = await client.get(f"/api/v2/files/by-observation-id/{obs_id}/", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# --- GET /api/v2/files/file-status/{filename}/ ---

async def test_get_file_status(client, auth_headers, regular_user):
    await client.post("/api/v2/files/", json=make_file_payload(), headers=auth_headers)
    resp = await client.get("/api/v2/files/file-status/test.fits/", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "observatory" in body
    assert "hub" in body
    assert "cloud" in body


async def test_get_file_status_not_found(client, auth_headers, regular_user):
    resp = await client.get("/api/v2/files/file-status/missing.fits/", headers=auth_headers)
    assert resp.status_code == 404


# --- PUT /api/v2/files/file-status/{filename}/ ---

async def test_update_file_status(client, auth_headers, regular_user):
    await client.post("/api/v2/files/", json=make_file_payload(), headers=auth_headers)
    new_status = {
        "observatory": {"ready": False, "check_needed": False, "status": "not_stored"},
        "hub": {"ready": False, "check_needed": False, "status": "not_stored"},
        "cloud": {"ready": True, "check_needed": False, "status": "stored"},
    }
    resp = await client.put("/api/v2/files/file-status/test.fits/", json=new_status, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["file_status"]["cloud"]["status"] == "stored"


async def test_update_file_status_not_found(client, auth_headers, regular_user):
    new_status = {
        "observatory": {"ready": False, "check_needed": False, "status": "not_stored"},
        "hub": {"ready": False, "check_needed": False, "status": "not_stored"},
        "cloud": {"ready": False, "check_needed": False, "status": "not_stored"},
    }
    resp = await client.put("/api/v2/files/file-status/missing.fits/", json=new_status, headers=auth_headers)
    assert resp.status_code == 404


# --- metadata: stored only on Observation, never persisted on FITSFile ---

async def test_create_file_metadata_goes_only_to_observation(client, auth_headers, regular_user):
    resp = await client.post(
        "/api/v2/files/",
        json=make_file_payload(filename="meta_create.fits", obs_name="obs_meta_create",
                                metadata={"quality": "good"}),
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["metadata"] == {}

    obs_resp = await client.get("/api/v2/observations/by-observation-name/obs_meta_create/", headers=auth_headers)
    assert obs_resp.json()["metadata"] == {"quality": "good"}


async def test_upsert_insert_metadata_goes_only_to_observation(client, auth_headers, regular_user):
    resp = await client.post(
        "/api/v2/files/upsert",
        json=make_file_payload(filename="meta_upsert_insert.fits", obs_name="obs_meta_upsert_insert",
                                metadata={"quality": "good"}),
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201)

    file_resp = await client.get("/api/v2/files/by-filename/meta_upsert_insert.fits/", headers=auth_headers)
    assert file_resp.json()["metadata"] == {}

    obs_resp = await client.get("/api/v2/observations/by-observation-name/obs_meta_upsert_insert/", headers=auth_headers)
    assert obs_resp.json()["metadata"] == {"quality": "good"}


async def test_upsert_update_metadata_goes_only_to_observation(client, auth_headers, regular_user):
    await client.post(
        "/api/v2/files/upsert",
        json=make_file_payload(filename="meta_upsert_update.fits", obs_name="obs_meta_upsert_update"),
        headers=auth_headers,
    )
    resp = await client.post(
        "/api/v2/files/upsert",
        json=make_file_payload(filename="meta_upsert_update.fits", obs_name="obs_meta_upsert_update",
                                metadata={"quality": "good"}),
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201)

    file_resp = await client.get("/api/v2/files/by-filename/meta_upsert_update.fits/", headers=auth_headers)
    assert file_resp.json()["metadata"] == {}

    obs_resp = await client.get("/api/v2/observations/by-observation-name/obs_meta_upsert_update/", headers=auth_headers)
    assert obs_resp.json()["metadata"] == {"quality": "good"}


async def test_update_fitsfile_metadata_goes_only_to_observation(client, auth_headers, regular_user):
    create = await client.post(
        "/api/v2/files/",
        json=make_file_payload(filename="meta_update.fits", obs_name="obs_meta_update"),
        headers=auth_headers,
    )
    file_body = create.json()
    file_body["metadata"] = {"quality": "good"}
    resp = await client.put("/api/v2/files/", json=file_body, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["metadata"] == {}

    obs_resp = await client.get("/api/v2/observations/by-observation-name/obs_meta_update/", headers=auth_headers)
    assert obs_resp.json()["metadata"] == {"quality": "good"}


# --- POST /api/v2/files/upsert ---

async def test_upsert_creates_new_file(client, auth_headers, regular_user):
    resp = await client.post("/api/v2/files/upsert", json=make_file_payload(filename="upsert.fits"), headers=auth_headers)
    assert resp.status_code in (200, 201)
    assert resp.json()["filename"] == "upsert.fits"


async def test_upsert_updates_existing_file(client, auth_headers, regular_user):
    await client.post("/api/v2/files/upsert", json=make_file_payload(filename="upsert2.fits"), headers=auth_headers)
    resp = await client.post(
        "/api/v2/files/upsert",
        json=make_file_payload(filename="upsert2.fits", **{"filesize": 12345}),
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201)


# --- POST /api/v2/files/file-status/list ---

async def test_list_file_statuses(client, auth_headers, regular_user):
    await client.post("/api/v2/files/", json=make_file_payload(filename="status1.fits"), headers=auth_headers)
    await client.post("/api/v2/files/", json=make_file_payload(filename="status2.fits", obs_name="obs_file_002"), headers=auth_headers)
    resp = await client.post(
        "/api/v2/files/file-status/list",
        json=["status1.fits", "status2.fits", "missing.fits"],
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "status1.fits" in body
    assert "status2.fits" in body
    assert "missing.fits" not in body
