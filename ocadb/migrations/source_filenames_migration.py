"""
Shared logic for clearing FITSFile.source_filenames on RAW files, mirroring
storage_status_migration.py's shape. Used by the remote migration endpoint
(api/routers/observations_v2.py).

A bug in source_files list generation left some RAW files with a non-empty
source_filenames list; RAW files never have source files by definition, so this
is a single pass (safe, idempotent): for each FITSFile with file_class == RAW
and a non-empty source_filenames list, set it to []. Files already empty are
skipped, so this is freely re-runnable.
"""
from typing import Awaitable, Callable, Optional

from ocadb.models.file import FileClassification, FITSFile

ProgressCallback = Optional[Callable[[dict], Awaitable[None]]]

_PROGRESS_EVERY = 50


async def run_pass1(dry_run: bool, on_progress: ProgressCallback = None) -> dict:
    query = {"file_class": FileClassification.RAW.value, "source_filenames": {"$ne": []}}
    total = await FITSFile.find(query).count()
    updated, errors = 0, 0

    async for f in FITSFile.find(query):
        try:
            if not dry_run:
                await f.update({"$set": {"source_filenames": []}})
            updated += 1
        except Exception:
            errors += 1

        if on_progress and (updated + errors) % _PROGRESS_EVERY == 0:
            await on_progress({"pass": 1, "dry_run": dry_run, "total": total,
                                "updated": updated, "errors": errors})

    result = {"pass": 1, "dry_run": dry_run, "total": total,
              "updated": updated, "errors": errors}
    if on_progress:
        await on_progress(result)
    return result
