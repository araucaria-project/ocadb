"""
Backfill Observation.source_files_number from the old, now-dropped source_files
array field, mirroring storage_status_migration.py's shape. Used by the remote
migration endpoint (api/routers/observations_v2.py).

Observation.source_files (a Set[str], never pruned) was replaced by
source_files_number (a plain int) — see ocadb/models/observation.py:store_file.
Existing documents still have the old "source_files" array sitting in Mongo
(Beanie/pydantic silently ignores unknown fields on read), so this reads it via
the raw collection rather than the Observation model and sets
source_files_number = len(source_files) wherever that hasn't been done yet.

Single pass (safe, idempotent): documents with no "source_files" array, or
where source_files_number is already set to that length, are skipped, so this
is freely re-runnable. This does NOT remove the old "source_files" field —
that's left for a manual cleanup pass later.
"""
from typing import Awaitable, Callable, Optional

from ocadb.database import Connection

ProgressCallback = Optional[Callable[[dict], Awaitable[None]]]

_PROGRESS_EVERY = 50


async def run_pass1(dry_run: bool, on_progress: ProgressCallback = None) -> dict:
    collection = Connection().database["observations"]
    query = {"source_files": {"$exists": True}}
    total = await collection.count_documents(query)
    updated, skipped, errors = 0, 0, 0

    async for doc in collection.find(query, projection={"source_files": 1, "source_files_number": 1}):
        try:
            target = len(doc.get("source_files") or [])
            if doc.get("source_files_number") == target:
                skipped += 1
                continue

            if not dry_run:
                await collection.update_one({"_id": doc["_id"]}, {"$set": {"source_files_number": target}})
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
