"""
Shared logic for the metadata -> Observation migration (mirrors
fits_header_migration.py's shape — see that module's docstring for the overall
pattern). Used by both the local CLI script
(scripts/migrate_metadata_to_observation.py) and the remote migration endpoint
(api/routers/observations_v2.py).

Pass 1 (safe, idempotent): for each Observation, merge every linked FITSFile's
non-empty metadata into Observation.metadata. Non-ZDF files are merged first
(in link order), then ZDF files last (in link order), so a ZDF file's keys
always win on collision — mirroring the ZDF-over-RAW/other precedent used for
fits_header. Sets the "metadata" obs_tag if the merged result is non-empty;
never clears it (Pass 1 is purely additive).

Pass 2 (destructive but freely resumable — unlike fits_header's Pass 2, there's
no derived scalar to preserve first, so this can be re-run at any time):
for every FITSFile, clear metadata to {}. Files with metadata already empty
are skipped rather than re-written, purely to keep progress counters
meaningful on a retry.
"""
from typing import Awaitable, Callable, Optional

from ocadb.models.observation import Observation
from ocadb.models.file import FITSFile, FileClassification

ProgressCallback = Optional[Callable[[dict], Awaitable[None]]]

_PROGRESS_EVERY = 50


def merge_metadata(obs_metadata: dict, files: list[FITSFile]) -> dict:
    """Non-ZDF files' metadata merged first (link order), ZDF files' last (link
    order) — so ZDF's keys win on collision, matching fits_header's precedence."""
    non_zdf = [f for f in files if f.file_class != FileClassification.ZDF and f.metadata]
    zdf = [f for f in files if f.file_class == FileClassification.ZDF and f.metadata]

    merged = dict(obs_metadata)
    for f in non_zdf:
        merged.update(f.metadata)
    for f in zdf:
        merged.update(f.metadata)
    return merged


async def run_pass1(dry_run: bool, on_progress: ProgressCallback = None) -> dict:
    total = await Observation.count()
    updated, skipped, errors = 0, 0, 0

    async for obs in Observation.find_all(fetch_links=True):
        try:
            files = [f for f in obs.files if isinstance(f, FITSFile) and f.metadata]
            if not files:
                skipped += 1
                continue

            merged = merge_metadata(obs.metadata, files)
            if merged == obs.metadata:
                skipped += 1
                continue

            if not dry_run:
                obs_tags = set(obs.obs_tags)
                if merged:
                    obs_tags.add("metadata")
                await obs.update({"$set": {"metadata": merged, "obs_tags": list(obs_tags)}})
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
    """Freely resumable — files with metadata already empty are skipped rather
    than re-written, purely to keep progress counters meaningful on a retry."""
    total = await FITSFile.count()
    updated, skipped, errors = 0, 0, 0

    async for f in FITSFile.find_all():
        try:
            if not f.metadata:
                skipped += 1
                continue
            await f.update({"$set": {"metadata": {}}})
            updated += 1
        except Exception:
            errors += 1

        if on_progress and (updated + skipped + errors) % (_PROGRESS_EVERY * 4) == 0:
            await on_progress({"pass": 2, "total": total, "updated": updated, "skipped": skipped, "errors": errors})

    result = {"pass": 2, "total": total, "updated": updated, "skipped": skipped, "errors": errors}
    if on_progress:
        await on_progress(result)
    return result
