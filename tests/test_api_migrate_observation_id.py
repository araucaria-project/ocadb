"""Integration tests for the /api/v2/observations/migrate-observation-id endpoints.

The migration reads/writes the raw "fits_files"/"observations" collections directly
(via Connection().database) rather than through the Beanie models, mirroring
test_api_migrate_source_files_number.py's approach — the bug being backfilled is
precisely that FITSFile.observation_id can be null in the DB while Observation.files
still correctly references the file, so seeding raw documents lets us set up that
exact (otherwise unreachable through the models) inconsistent state directly.
"""
import asyncio

from bson import ObjectId
from bson.dbref import DBRef

from ocadb.database import Connection

STATUS_URL = "/api/v2/observations/migrate-observation-id/status"
MIGRATE_URL = "/api/v2/observations/migrate-observation-id"


def _fits_files():
    return Connection().database["fits_files"]


def _observations():
    return Connection().database["observations"]


async def seed_file(filename: str, observation_id=None) -> ObjectId:
    file_id = ObjectId()
    await _fits_files().insert_one({"_id": file_id, "filename": filename, "observation_id": observation_id})
    return file_id


async def seed_observation(obs_name: str, file_ids: list[ObjectId]) -> ObjectId:
    obs_id = ObjectId()
    await _observations().insert_one({
        "_id": obs_id, "obs_name": obs_name,
        "files": [DBRef("fits_files", fid) for fid in file_ids],
    })
    return obs_id


async def wait_for_job_done(client, headers, timeout=5.0):
    for _ in range(int(timeout / 0.1)):
        resp = await client.get(STATUS_URL, headers=headers)
        job = resp.json()
        if job.get("status") in ("done", "failed"):
            return job
        await asyncio.sleep(0.1)
    raise AssertionError("migration job did not finish in time")


# --- auth gating ---

async def test_migrate_requires_auth(client, beanie):
    resp = await client.post(MIGRATE_URL)
    assert resp.status_code == 401


async def test_migrate_rejects_non_moderator(client, auth_headers, regular_user):
    resp = await client.post(MIGRATE_URL, headers=auth_headers)
    assert resp.status_code == 403


async def test_status_allows_non_moderator(client, auth_headers, regular_user):
    resp = await client.get(STATUS_URL, headers=auth_headers)
    assert resp.status_code == 200


# --- dry run ---

async def test_dry_run_does_not_modify_documents(client, mod_headers, moderator_user):
    file_id = await seed_file("obsid_dry.fits")
    obs_id = await seed_observation("obsid_dry", [file_id])

    resp = await client.post(MIGRATE_URL, headers=mod_headers)
    assert resp.status_code == 202
    assert resp.json()["apply"] is False

    job = await wait_for_job_done(client, mod_headers)
    assert job["status"] == "done"
    assert job["pass1"]["updated"] == 1

    doc = await _fits_files().find_one({"_id": file_id})
    assert doc["observation_id"] is None  # untouched by dry run


# --- apply ---

async def test_apply_backfills_from_observation_back_reference(client, mod_headers, moderator_user):
    file_id = await seed_file("obsid_apply.fits")
    obs_id = await seed_observation("obsid_apply", [file_id])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["status"] == "done"
    assert job["pass1"]["updated"] == 1

    doc = await _fits_files().find_one({"_id": file_id})
    assert doc["observation_id"] == obs_id


async def test_apply_skips_files_that_already_have_observation_id(client, mod_headers, moderator_user):
    existing_obs_id = ObjectId()
    file_id = await seed_file("obsid_already.fits", observation_id=existing_obs_id)
    await seed_observation("obsid_already", [file_id])  # would map to a different id, but query excludes this doc

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["total"] == 0

    doc = await _fits_files().find_one({"_id": file_id})
    assert doc["observation_id"] == existing_obs_id  # left exactly as it was


async def test_apply_counts_orphan_file_as_error_not_success(client, mod_headers, moderator_user):
    file_id = await seed_file("obsid_orphan.fits")  # no Observation references this file at all

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["errors"] == 1
    assert job["pass1"]["updated"] == 0

    doc = await _fits_files().find_one({"_id": file_id})
    assert doc["observation_id"] is None  # never fabricated


# --- concurrency guard ---

async def test_second_trigger_without_force_returns_409_while_running(client, mod_headers, moderator_user):
    jobs = Connection().database["migration_jobs"]
    await jobs.update_one(
        {"_id": "observation_id_migration"},
        {"$set": {"status": "running"}},
        upsert=True,
    )

    resp = await client.post(MIGRATE_URL, headers=mod_headers)
    assert resp.status_code == 409

    resp = await client.post(f"{MIGRATE_URL}?force=true", headers=mod_headers)
    assert resp.status_code == 202
    await wait_for_job_done(client, mod_headers)


# --- re-run safety ---

async def test_rerun_after_apply_is_a_noop(client, mod_headers, moderator_user):
    file_id = await seed_file("obsid_rerun.fits")
    obs_id = await seed_observation("obsid_rerun", [file_id])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["updated"] == 1

    resp = await client.post(f"{MIGRATE_URL}?apply=true&force=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["total"] == 0  # already backfilled, excluded by the query entirely

    doc = await _fits_files().find_one({"_id": file_id})
    assert doc["observation_id"] == obs_id
