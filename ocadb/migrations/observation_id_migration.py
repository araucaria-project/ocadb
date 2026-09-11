"""
Backfill FITSFile.observation_id for files whose id was never linked back to
their parent Observation, mirroring source_files_number_migration.py's shape.
Used by the remote migration endpoint (api/routers/observations_v2.py).

Root cause (see api/routers/files_v2.py:upsert_fitsfile, fixed alongside this
migration): on first insert, the file was appended into the parent
Observation's own `files` list, but observation_id was never written back onto
the FITSFile document itself — and on every subsequent upsert of the same
file, the endpoint's `$set` unconditionally overwrote observation_id with the
client-supplied value, which is always null (it's a server-assigned field no
client ever populates). Every file that has ever been upserted twice ends up
permanently stuck at observation_id: null, which silently breaks anything that
queries FITSFile by observation_id — notably the moderator upload-approval
flow (bulk-approve-uploads) and the has_requested_files search filter.

Single pass (safe, idempotent): builds a file_id -> observation_id map from the
Observation side's `files` back-references (a Beanie Link[FITSFile], stored in
Mongo as a DBRef), then sets observation_id on every FITSFile missing it. A
file that no Observation anywhere references (a true orphan, not just a
missing back-reference) is left untouched and counted under `errors` — this
migration only repairs the missing back-reference from data that's already
present; it never fabricates a link.
"""
from typing import Awaitable, Callable, Optional

from ocadb.database import Connection

ProgressCallback = Optional[Callable[[dict], Awaitable[None]]]

_PROGRESS_EVERY = 50


async def _build_file_to_observation_map(observations_collection) -> dict:
    """One pass over observations, reading only the `files` back-reference list —
    cheap relative to the fits_files collection this backfill is really about."""
    mapping = {}
    async for doc in observations_collection.find({}, projection={"files": 1}):
        for file_ref in doc.get("files") or []:
            file_id = getattr(file_ref, "id", None)  # DBRef.id
            if file_id is not None:
                mapping[file_id] = doc["_id"]
    return mapping


async def run_pass1(dry_run: bool, on_progress: ProgressCallback = None) -> dict:
    db = Connection().database
    fits_files = db["fits_files"]
    observations = db["observations"]

    file_to_obs = await _build_file_to_observation_map(observations)

    query = {"observation_id": None}
    total = await fits_files.count_documents(query)
    updated, skipped, errors = 0, 0, 0

    async for doc in fits_files.find(query, projection={"_id": 1}):
        try:
            obs_id = file_to_obs.get(doc["_id"])
            if obs_id is None:
                # Orphan: no Observation references this file at all — a data
                # problem this migration can't repair, not a bug in it.
                errors += 1
                continue

            if not dry_run:
                await fits_files.update_one({"_id": doc["_id"]}, {"$set": {"observation_id": obs_id}})
            updated += 1
        except Exception:
            errors += 1

        if on_progress and (updated + skipped + errors) % _PROGRESS_EVERY == 0:
            await on_progress({"pass": 1, "dry_run": dry_run, "total": total,
                                "updated": updated, "skipped": skipped, "errors": errors})

    result = {"pass": 1, "dry_run": dry_run, "total": total,
              "updated": updated, "skipped": skipped, "errors": errors}
    if on_progress:
        await on_progress(result)
    return result
