"""Integration tests for the /api/v2/observations/migrate-metadata endpoints."""
import asyncio

from ocadb.models import Observation
from ocadb.models.file import FITSFile, FileClassification
from tests.conftest import make_fits_header, make_storage_status

STATUS_URL = "/api/v2/observations/migrate-metadata/status"
MIGRATE_URL = "/api/v2/observations/migrate-metadata"


async def seed_pre_migration_obs(obs_name: str, file_specs: list[tuple[FileClassification, dict]],
                                  obs_metadata: dict | None = None) -> Observation:
    """file_specs: list of (file_class, metadata_dict) — metadata_dict={} simulates a file
    that already went through migration (or never had any)."""
    obs = Observation(obs_name=obs_name, file_name=f"{obs_name}.fits", fits_header=make_fits_header())
    await obs.insert()
    if obs_metadata:
        obs.metadata = obs_metadata
        await obs.replace()
    for i, (file_class, metadata) in enumerate(file_specs):
        f = FITSFile(
            filename=f"{obs_name}_{i}.fits",
            file_class=file_class,
            obs_name=obs_name,
            observation_id=obs.id,
            file_status=make_storage_status(),
            metadata=metadata,
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
    await seed_pre_migration_obs("mig_dry_meta", [(FileClassification.RAW, {"quality": "good"})])

    resp = await client.post(MIGRATE_URL, headers=mod_headers)
    assert resp.status_code == 202
    assert resp.json()["apply"] is False

    job = await wait_for_job_done(client, mod_headers)
    assert job["status"] == "done"
    assert job["pass1"]["updated"] == 1
    assert job["pass2"] is None

    obs = await Observation.find_one(Observation.obs_name == "mig_dry_meta")
    assert obs.metadata == {}  # untouched by dry run

    files = await FITSFile.find(FITSFile.obs_name == "mig_dry_meta").to_list()
    assert all(f.metadata for f in files)  # untouched by dry run


# --- apply: ZDF precedence on conflict, merge preserves existing obs metadata ---

async def test_apply_merges_metadata_from_single_file(client, mod_headers, moderator_user):
    await seed_pre_migration_obs("mig_merge_single", [(FileClassification.RAW, {"quality": "good", "snr": 12})])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["status"] == "done"

    obs = await Observation.find_one(Observation.obs_name == "mig_merge_single")
    assert obs.metadata == {"quality": "good", "snr": 12}
    assert "metadata" in obs.obs_tags

    files = await FITSFile.find(FITSFile.obs_name == "mig_merge_single").to_list()
    assert all(f.metadata == {} for f in files)


async def test_apply_zdf_wins_on_key_collision_raw_then_zdf(client, mod_headers, moderator_user):
    await seed_pre_migration_obs("mig_zdf_wins_order1", [
        (FileClassification.RAW, {"quality": "raw-value", "raw_only": 1}),
        (FileClassification.ZDF, {"quality": "zdf-value", "zdf_only": 2}),
    ])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    await wait_for_job_done(client, mod_headers)

    obs = await Observation.find_one(Observation.obs_name == "mig_zdf_wins_order1")
    assert obs.metadata == {"quality": "zdf-value", "raw_only": 1, "zdf_only": 2}


async def test_apply_zdf_wins_on_key_collision_zdf_then_raw(client, mod_headers, moderator_user):
    # Link order reversed from the previous test — ZDF should still win, proving
    # the precedence is order-independent (matches fits_header's ZDF precedence).
    await seed_pre_migration_obs("mig_zdf_wins_order2", [
        (FileClassification.ZDF, {"quality": "zdf-value", "zdf_only": 2}),
        (FileClassification.RAW, {"quality": "raw-value", "raw_only": 1}),
    ])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    await wait_for_job_done(client, mod_headers)

    obs = await Observation.find_one(Observation.obs_name == "mig_zdf_wins_order2")
    assert obs.metadata == {"quality": "zdf-value", "raw_only": 1, "zdf_only": 2}


async def test_apply_merge_preserves_existing_observation_metadata(client, mod_headers, moderator_user):
    await seed_pre_migration_obs(
        "mig_preserve_existing",
        [(FileClassification.RAW, {"new_key": "from_file"})],
        obs_metadata={"existing_key": "already_there"},
    )

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    await wait_for_job_done(client, mod_headers)

    obs = await Observation.find_one(Observation.obs_name == "mig_preserve_existing")
    assert obs.metadata == {"existing_key": "already_there", "new_key": "from_file"}


async def test_apply_skips_observation_with_no_file_metadata(client, mod_headers, moderator_user):
    await seed_pre_migration_obs("mig_no_meta", [(FileClassification.RAW, {})])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["skipped"] >= 1

    obs = await Observation.find_one(Observation.obs_name == "mig_no_meta")
    assert obs.metadata == {}
    assert "metadata" not in obs.obs_tags


async def test_apply_leaves_observation_with_no_files_untouched(client, mod_headers, moderator_user):
    await seed_pre_migration_obs("mig_meta_no_files", [])  # no linked files at all

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass1"]["skipped"] >= 1

    obs = await Observation.find_one(Observation.obs_name == "mig_meta_no_files")
    assert obs.metadata == {}


# --- concurrency guard ---

async def test_second_trigger_without_force_returns_409_while_running(client, mod_headers, moderator_user):
    # Manually mark the job as "running" to simulate an in-flight/stale run.
    from ocadb.database import Connection
    jobs = Connection().database["migration_jobs"]
    await jobs.update_one(
        {"_id": "metadata_migration"},
        {"$set": {"status": "running"}},
        upsert=True,
    )

    resp = await client.post(MIGRATE_URL, headers=mod_headers)
    assert resp.status_code == 409

    resp = await client.post(f"{MIGRATE_URL}?force=true", headers=mod_headers)
    assert resp.status_code == 202
    await wait_for_job_done(client, mod_headers)


# --- Pass 2 resumability (safe to retry after a simulated crash/redeploy) ---

async def test_pass2_rerun_is_safe(client, mod_headers, moderator_user):
    await seed_pre_migration_obs("mig_meta_rerun", [(FileClassification.RAW, {"quality": "good"})])

    resp = await client.post(f"{MIGRATE_URL}?apply=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass2"]["updated"] == 1

    files = await FITSFile.find(FITSFile.obs_name == "mig_meta_rerun").to_list()
    assert files[0].metadata == {}

    # Simulate a retry after an interrupted run.
    resp = await client.post(f"{MIGRATE_URL}?apply=true&force=true", headers=mod_headers)
    assert resp.status_code == 202
    job = await wait_for_job_done(client, mod_headers)
    assert job["pass2"]["skipped"] == 1  # already-empty file is skipped, not re-written
    assert job["pass2"]["updated"] == 0

    obs = await Observation.find_one(Observation.obs_name == "mig_meta_rerun")
    assert obs.metadata == {"quality": "good"}  # Pass 1 re-run is a no-op (merge unchanged), no data lost
