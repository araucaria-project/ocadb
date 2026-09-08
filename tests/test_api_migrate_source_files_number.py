"""Integration tests for the /api/v2/observations/migrate-source-files-number endpoints.

The migration reads/writes the raw "observations" collection directly (via
Connection().database), not the Observation model — the old source_files array
field no longer exists on the model, so documents are seeded/inspected as plain
dicts here rather than through Observation.
"""
import asyncio

from bson import ObjectId

from ocadb.database import Connection

STATUS_URL = "/api/v2/observations/migrate-source-files-number/status"
MIGRATE_URL = "/api/v2/observations/migrate-source-files-number"


def _collection():
    return Connection().database["observations"]


async def seed_doc(obs_name: str, source_files: list[str], source_files_number=None) -> str:
    doc = {"_id": ObjectId(), "obs_name": obs_name, "source_files": source_files}
    if source_files_number is not None:
        doc["source_files_number"] = source_files_number
    await _collection().insert_one(doc)
    return str(doc["_id"])


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
    obs_id = await seed_doc("sfn_dry", ["a.fits", "b.fits"])

    resp = await client.post(MIGRATE_URL, headers=mod_headers)
    assert resp.status_code == 202
    assert resp.json()["apply"] is False

    job = await wait_for_job_done(client, mod_headers)
    assert job["status"] == "done"
    assert job["pass1"]["updated"] == 1

    doc = await _collection().find_one({"_id": ObjectId(obs_id)})
    assert "source_files_number" not in doc  # untouched by dry run


# --- apply ---

async def test_apply_backfills_count_from_array_length(client, mod_headers, moderator_user):
    obs_id = await seed_doc("sfn_apply", ["a.fits", "b.fits", "c.fits"])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["status"] == "done"
    assert job["pass1"]["updated"] == 1

    doc = await _collection().find_one({"_id": ObjectId(obs_id)})
    assert doc["source_files_number"] == 3


async def test_apply_skips_already_backfilled(client, mod_headers, moderator_user):
    await seed_doc("sfn_already", ["a.fits"], source_files_number=1)

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["skipped"] >= 1
    assert job["pass1"]["updated"] == 0


async def test_apply_skips_documents_without_source_files_field(client, mod_headers, moderator_user):
    # never had the old field at all (e.g. created after the model change)
    await _collection().insert_one({"_id": ObjectId(), "obs_name": "sfn_no_field"})

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["total"] == 0


# --- concurrency guard ---

async def test_second_trigger_without_force_returns_409_while_running(client, mod_headers, moderator_user):
    jobs = Connection().database["migration_jobs"]
    await jobs.update_one(
        {"_id": "source_files_number_migration"},
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
    obs_id = await seed_doc("sfn_rerun", ["a.fits", "b.fits"])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["updated"] == 1

    resp = await client.post(f"{MIGRATE_URL}?apply=true&force=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["updated"] == 0
    assert job["pass1"]["skipped"] == 1

    doc = await _collection().find_one({"_id": ObjectId(obs_id)})
    assert doc["source_files_number"] == 2
