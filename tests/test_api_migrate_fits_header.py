"""Integration tests for the /api/v2/observations/migrate-fits-header endpoints."""
import asyncio

from ocadb.models import Observation
from ocadb.models.file import FITSFile, FileClassification
from tests.conftest import make_fits_header, make_storage_status

STATUS_URL = "/api/v2/observations/migrate-fits-header/status"
MIGRATE_URL = "/api/v2/observations/migrate-fits-header"


async def seed_pre_migration_obs(obs_name: str, file_specs: list[tuple[FileClassification, str | None]]) -> Observation:
    """file_specs: list of (file_class, telescop_or_None). None telescop => fits_header=None on that file
    (simulates a file that already went through migration)."""
    obs = Observation(obs_name=obs_name, file_name=f"{obs_name}.fits", fits_header=make_fits_header())
    await obs.insert()
    for i, (file_class, telescop) in enumerate(file_specs):
        header = make_fits_header(TELESCOP=telescop) if telescop is not None else None
        f = FITSFile(
            filename=f"{obs_name}_{i}.fits",
            file_class=file_class,
            obs_name=obs_name,
            observation_id=obs.id,
            file_status=make_storage_status(),
            fits_header=header,
        )
        await f.insert()
        await obs.update({"$push": {"files": f.to_ref()}})
    return obs


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


# --- dry run (Pass 1 only) ---

async def test_dry_run_does_not_modify_documents(client, mod_headers, moderator_user):
    await seed_pre_migration_obs("mig_dry_only_raw", [(FileClassification.RAW, "raw-scope")])

    resp = await client.post(MIGRATE_URL, headers=mod_headers)
    assert resp.status_code == 202
    assert resp.json()["apply"] is False

    job = await wait_for_job_done(client, mod_headers)
    assert job["status"] == "done"
    assert job["pass1"]["updated"] == 1
    assert job["pass2"] is None

    obs = await Observation.find_one(Observation.obs_name == "mig_dry_only_raw")
    assert obs.fits_header_source is None  # untouched by dry run

    files = await FITSFile.find(FITSFile.obs_name == "mig_dry_only_raw").to_list()
    assert all(f.fits_header is not None for f in files)  # untouched by dry run


# --- apply: ZDF precedence, order independence ---

async def test_apply_raw_then_zdf_adopts_zdf(client, mod_headers, moderator_user):
    await seed_pre_migration_obs("mig_raw_then_zdf", [
        (FileClassification.RAW, "raw-scope"),
        (FileClassification.ZDF, "zdf-scope"),
    ])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["status"] == "done"

    obs = await Observation.find_one(Observation.obs_name == "mig_raw_then_zdf")
    assert obs.fits_header_source == FileClassification.ZDF
    assert obs.fits_header.TELESCOP == "zdf-scope"

    files = await FITSFile.find(FITSFile.obs_name == "mig_raw_then_zdf").to_list()
    assert all(f.fits_header is None for f in files)


async def test_apply_zdf_then_raw_keeps_zdf(client, mod_headers, moderator_user):
    await seed_pre_migration_obs("mig_zdf_then_raw", [
        (FileClassification.ZDF, "zdf-scope"),
        (FileClassification.RAW, "raw-scope"),
    ])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    await wait_for_job_done(client, mod_headers)

    obs = await Observation.find_one(Observation.obs_name == "mig_zdf_then_raw")
    assert obs.fits_header_source == FileClassification.ZDF
    assert obs.fits_header.TELESCOP == "zdf-scope"


async def test_apply_leaves_observation_with_no_files_untouched(client, mod_headers, moderator_user):
    obs = await seed_pre_migration_obs("mig_no_files", [])  # no linked files at all
    original_header = obs.fits_header.model_dump()

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["skipped"] >= 1

    obs = await Observation.find_one(Observation.obs_name == "mig_no_files")
    assert obs.fits_header_source is None
    assert obs.fits_header.model_dump() == original_header


async def test_apply_skips_observation_with_no_headers(client, mod_headers, moderator_user):
    await seed_pre_migration_obs("mig_no_header", [(FileClassification.RAW, None)])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["skipped"] >= 1

    obs = await Observation.find_one(Observation.obs_name == "mig_no_header")
    assert obs.fits_header_source is None


# --- concurrency guard ---

async def test_second_trigger_without_force_returns_409_while_running(client, mod_headers, moderator_user, monkeypatch):
    # Manually mark the job as "running" to simulate an in-flight/stale run.
    from ocadb.database import Connection
    jobs = Connection().database["migration_jobs"]
    await jobs.update_one(
        {"_id": "fits_header_migration"},
        {"$set": {"status": "running"}},
        upsert=True,
    )

    resp = await client.post(MIGRATE_URL, headers=mod_headers)
    assert resp.status_code == 409

    resp = await client.post(f"{MIGRATE_URL}?force=true", headers=mod_headers)
    assert resp.status_code == 202
    await wait_for_job_done(client, mod_headers)


# --- Pass 2 resumability (safe to retry after a simulated crash/redeploy) ---

async def test_pass2_rerun_does_not_clobber_image_type(client, mod_headers, moderator_user):
    await seed_pre_migration_obs("mig_rerun", [(FileClassification.RAW, "raw-scope")])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass2"]["updated"] == 1

    files = await FITSFile.find(FITSFile.obs_name == "mig_rerun").to_list()
    assert files[0].image_type == "object"  # from make_fits_header's default IMAGETYP

    # Simulate a retry after an interrupted run: trigger apply=true again with force=true.
    resp = await client.post(f"{MIGRATE_URL}?apply=true&force=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass2"]["skipped"] == 1  # already-migrated file is skipped, not overwritten
    assert job["pass2"]["updated"] == 0

    files = await FITSFile.find(FITSFile.obs_name == "mig_rerun").to_list()
    assert files[0].image_type == "object"  # unchanged, not clobbered to None
