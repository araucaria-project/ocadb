"""
Shared logic for migrating FITSFile storage status from SCHEDULED to ON_DEMAND,
mirroring fits_header_migration.py / metadata_migration.py's shape. Used by the
remote migration endpoint (api/routers/observations_v2.py).

Single pass (safe, idempotent): for each FITSFile, for every storage location
(observatory, hub, cloud) currently at SCHEDULED, flip it to ON_DEMAND. Files
with no SCHEDULED location are skipped, so this is freely re-runnable.
"""
from typing import Awaitable, Callable, Optional

from ocadb.models.file import FITSFile, StorageLocationStatus, StorageStatusType

ProgressCallback = Optional[Callable[[dict], Awaitable[None]]]

_PROGRESS_EVERY = 50

_LOCATIONS = ("observatory", "hub", "cloud")


async def run_pass1(dry_run: bool, on_progress: ProgressCallback = None) -> dict:
    total = await FITSFile.count()
    updated, skipped, errors = 0, 0, 0

    async for f in FITSFile.find_all():
        try:
            changed = {}
            for loc in _LOCATIONS:
                location_status = getattr(f.file_status, loc)
                if location_status.status == StorageStatusType.SCHEDULED:
                    changed[f"file_status.{loc}"] = StorageLocationStatus.on_demand().model_dump()

            if not changed:
                skipped += 1
                continue

            if not dry_run:
                await f.update({"$set": changed})
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
