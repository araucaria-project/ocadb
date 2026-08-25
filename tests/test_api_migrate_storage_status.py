"""Integration tests for the /api/v2/observations/migrate-storage-status endpoints."""
import asyncio

from ocadb.models.file import FITSFile, FileClassification, StorageLocationStatus, StorageStatus, StorageStatusType

STATUS_URL = "/api/v2/observations/migrate-storage-status/status"
MIGRATE_URL = "/api/v2/observations/migrate-storage-status"


def make_status(observatory: StorageStatusType, hub: StorageStatusType, cloud: StorageStatusType) -> StorageStatus:
    return StorageStatus(
        observatory=StorageLocationStatus(ready=False, check_needed=False, status=observatory),
        hub=StorageLocationStatus(ready=False, check_needed=False, status=hub),
        cloud=StorageLocationStatus(ready=False, check_needed=False, status=cloud),
    )


async def seed_file(obs_name: str, file_status: StorageStatus) -> FITSFile:
    f = FITSFile(
        filename=f"{obs_name}.fits",
        file_class=FileClassification.RAW,
        obs_name=obs_name,
        file_status=file_status,
    )
    await f.insert()
    return f


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
    await seed_file("ss_dry", make_status(
        StorageStatusType.SCHEDULED, StorageStatusType.STORED, StorageStatusType.SCHEDULED))

    resp = await client.post(MIGRATE_URL, headers=mod_headers)
    assert resp.status_code == 202
    assert resp.json()["apply"] is False

    job = await wait_for_job_done(client, mod_headers)
    assert job["status"] == "done"
    assert job["pass1"]["updated"] == 1

    f = await FITSFile.find_one(FITSFile.obs_name == "ss_dry")
    assert f.file_status.observatory.status == StorageStatusType.SCHEDULED  # untouched by dry run
    assert f.file_status.cloud.status == StorageStatusType.SCHEDULED


# --- apply ---

async def test_apply_flips_only_scheduled_locations(client, mod_headers, moderator_user):
    await seed_file("ss_apply_mixed", make_status(
        StorageStatusType.SCHEDULED, StorageStatusType.STORED, StorageStatusType.SCHEDULED))

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["status"] == "done"
    assert job["pass1"]["updated"] == 1

    f = await FITSFile.find_one(FITSFile.obs_name == "ss_apply_mixed")
    assert f.file_status.observatory.status == StorageStatusType.ON_DEMAND
    assert f.file_status.cloud.status == StorageStatusType.ON_DEMAND
    assert f.file_status.hub.status == StorageStatusType.STORED  # untouched, was not SCHEDULED


async def test_apply_skips_file_with_no_scheduled_location(client, mod_headers, moderator_user):
    await seed_file("ss_no_scheduled", make_status(
        StorageStatusType.STORED, StorageStatusType.STORED, StorageStatusType.NOT_STORED))

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["skipped"] >= 1

    f = await FITSFile.find_one(FITSFile.obs_name == "ss_no_scheduled")
    assert f.file_status.observatory.status == StorageStatusType.STORED
    assert f.file_status.cloud.status == StorageStatusType.NOT_STORED


# --- concurrency guard ---

async def test_second_trigger_without_force_returns_409_while_running(client, mod_headers, moderator_user):
    from ocadb.database import Connection
    jobs = Connection().database["migration_jobs"]
    await jobs.update_one(
        {"_id": "storage_status_migration"},
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
    await seed_file("ss_rerun", make_status(
        StorageStatusType.SCHEDULED, StorageStatusType.STORED, StorageStatusType.STORED))

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["updated"] == 1

    resp = await client.post(f"{MIGRATE_URL}?apply=true&force=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["updated"] == 0
    assert job["pass1"]["skipped"] == 1

    f = await FITSFile.find_one(FITSFile.obs_name == "ss_rerun")
    assert f.file_status.observatory.status == StorageStatusType.ON_DEMAND
