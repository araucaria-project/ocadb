"""
Shared logic for the fits_header -> Observation migration (see
Observation.adopt_header_if_precedent for the same ZDF-over-RAW/other priority
rule applied going forward on new writes). Used by both the local CLI script
(scripts/migrate_fits_header_to_observation.py) and the remote migration
endpoint (api/routers/observations_v2.py), so the two never drift apart.

Pass 1 (safe, idempotent): for each Observation, pick the winning linked file's
header (ZDF if present and has a header, else the first file with a header)
and $set it (plus fits_header_source) on the Observation.

Pass 2 (destructive, NOT re-runnable): for every FITSFile, copy
fits_header.IMAGETYP into image_type, then $unset fits_header. Pass 2 destroys
Pass 1's only data source, so Pass 1 must always run first.
"""
from typing import Awaitable, Callable, Optional

from ocadb.models.observation import Observation
from ocadb.models.file import FITSFile, FileClassification

ProgressCallback = Optional[Callable[[dict], Awaitable[None]]]

_PROGRESS_EVERY = 50


def pick_winner(files: list[FITSFile]) -> Optional[tuple[FITSFile, FileClassification]]:
    """ZDF wins if present and has a header; else first file with any header."""
    zdf = next((f for f in files if f.file_class == FileClassification.ZDF and f.fits_header is not None), None)
    if zdf is not None:
        return zdf, FileClassification.ZDF
    fallback = next((f for f in files if f.fits_header is not None), None)
    if fallback is not None:
        return fallback, fallback.file_class
    return None


async def run_pass1(dry_run: bool, on_progress: ProgressCallback = None) -> dict:
    total = await Observation.count()
    updated, skipped, errors = 0, 0, 0

    async for obs in Observation.find_all(fetch_links=True):
        try:
            files = [f for f in obs.files if isinstance(f, FITSFile)]
            winner = pick_winner(files)
            if winner is None:
                skipped += 1
                continue
            winning_file, winning_class = winner

            if not dry_run:
                await obs.update({"$set": {
                    "fits_header": winning_file.fits_header,
                    "fits_header_source": winning_class,
                }})
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


async def run_pass2(on_progress: ProgressCallback = None) -> dict:
    """Idempotent/resumable: files with fits_header already None (stripped by an earlier,
    possibly-interrupted run) are skipped rather than re-written, so a retry after a crash
    or redeploy can't clobber an already-correct image_type with None."""
    total = await FITSFile.count()
    updated, skipped, errors = 0, 0, 0

    async for f in FITSFile.find_all():
        try:
            if f.fits_header is None:
                skipped += 1
                continue
            await f.update({"$set": {"image_type": f.fits_header.IMAGETYP}, "$unset": {"fits_header": ""}})
            updated += 1
        except Exception:
            errors += 1

        if on_progress and (updated + skipped + errors) % (_PROGRESS_EVERY * 4) == 0:
            await on_progress({"pass": 2, "total": total, "updated": updated, "skipped": skipped, "errors": errors})

    result = {"pass": 2, "total": total, "updated": updated, "skipped": skipped, "errors": errors}
    if on_progress:
        await on_progress(result)
    return result
