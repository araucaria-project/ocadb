"""Integration tests for the /api/v2/observations/migrate-source-filenames endpoints."""
import asyncio

from ocadb.models.file import FITSFile, FileClassification, StorageLocationStatus, StorageStatus, StorageStatusType

STATUS_URL = "/api/v2/observations/migrate-source-filenames/status"
MIGRATE_URL = "/api/v2/observations/migrate-source-filenames"


def make_storage_status() -> StorageStatus:
    loc = StorageLocationStatus(ready=False, check_needed=False, status=StorageStatusType.NOT_STORED)
    return StorageStatus(observatory=loc, hub=loc, cloud=loc)


async def seed_file(obs_name: str, file_class: FileClassification, source_filenames: list[str]) -> FITSFile:
    f = FITSFile(
        filename=f"{obs_name}.fits",
        file_class=file_class,
        obs_name=obs_name,
        source_filenames=source_filenames,
        file_status=make_storage_status(),
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
    await seed_file("sf_dry", FileClassification.RAW, ["bogus_source.fits"])

    resp = await client.post(MIGRATE_URL, headers=mod_headers)
    assert resp.status_code == 202
    assert resp.json()["apply"] is False

    job = await wait_for_job_done(client, mod_headers)
    assert job["status"] == "done"
    assert job["pass1"]["updated"] == 1

    f = await FITSFile.find_one(FITSFile.obs_name == "sf_dry")
    assert f.source_filenames == ["bogus_source.fits"]  # untouched by dry run


# --- apply ---

async def test_apply_clears_raw_source_filenames(client, mod_headers, moderator_user):
    await seed_file("sf_apply", FileClassification.RAW, ["bogus_source.fits", "another.fits"])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["status"] == "done"
    assert job["pass1"]["updated"] == 1

    f = await FITSFile.find_one(FITSFile.obs_name == "sf_apply")
    assert f.source_filenames == []


async def test_apply_skips_non_raw_files(client, mod_headers, moderator_user):
    await seed_file("sf_zdf", FileClassification.ZDF, ["bogus_source.fits"])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["updated"] == 0

    f = await FITSFile.find_one(FITSFile.obs_name == "sf_zdf")
    assert f.source_filenames == ["bogus_source.fits"]  # untouched: not RAW


async def test_apply_skips_raw_file_already_empty(client, mod_headers, moderator_user):
    await seed_file("sf_already_empty", FileClassification.RAW, [])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["total"] == 0
    assert job["pass1"]["updated"] == 0


# --- concurrency guard ---

async def test_second_trigger_without_force_returns_409_while_running(client, mod_headers, moderator_user):
    from ocadb.database import Connection
    jobs = Connection().database["migration_jobs"]
    await jobs.update_one(
        {"_id": "source_filenames_migration"},
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
    await seed_file("sf_rerun", FileClassification.RAW, ["bogus_source.fits"])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["updated"] == 1

    resp = await client.post(f"{MIGRATE_URL}?apply=true&force=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["updated"] == 0
    assert job["pass1"]["total"] == 0

    f = await FITSFile.find_one(FITSFile.obs_name == "sf_rerun")
    assert f.source_filenames == []
