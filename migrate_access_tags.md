# Migration: Backfill `access_tags` on FITSFile Documents

## Context

After adding `access_tags: List[str] = Field(default_factory=list)` to `FITSFile` and a
`propagate_access_tags` hook on `Observation`, existing MongoDB documents lack the field.
Reads are safe (the default kicks in), but the field values won't be correct until backfilled.

---

## How Beanie Validates

- **On read**: Beanie passes the raw BSON dict to Pydantic model construction. Validation fires for every fetched document.
  - Fields with `default` / `default_factory` → safe. Missing field gets the default silently.
  - Required fields with no default → `ValidationError` on every read of old documents.
- **On raw Motor `update_many`**: No Python object is constructed, so no Beanie/Pydantic validation fires.
- **On `doc.save()` / `doc.replace()`**: Validates only at object construction time; the write itself doesn't re-validate DB state.

---

## Migration Script

**File**: `migrate_access_tags.py` (repo root)

Two phases using raw Motor (bypasses Python validation entirely, safe for production):

- **Phase 1** — Backfill missing field with `[]` for all FITSFile docs
- **Phase 2** — Re-derive correct tags from parent Observations (matching what `propagate_access_tags` would do)

```python
import asyncio
from api.config import Settings
from ocadb.database import Connection

async def main():
    settings = Settings()
    conn = Connection()
    await conn.ensure_connection(
        connection_string=settings.MONGODB_URL,
        database_name=settings.MONGODB_DATABASE,
    )
    db = conn.database
    fits_col = db["fits_files"]
    obs_col = db["observations"]

    # Phase 1: backfill missing field
    r = await fits_col.update_many(
        {"access_tags": {"$exists": False}},
        {"$set": {"access_tags": []}},
    )
    print(f"Phase 1: {r.modified_count} FITSFile docs backfilled with access_tags=[]")

    # Phase 2: propagate correct tags from Observations
    updated, obs_count = 0, 0
    cursor = obs_col.find(
        {"files": {"$exists": True, "$ne": []}, "access_tags": {"$exists": True, "$ne": []}},
        projection={"files": 1, "access_tags": 1},
    )
    async for obs_doc in cursor:
        tags = obs_doc.get("access_tags", [])
        if not isinstance(tags, list):
            continue  # guard against Field(list[str]) type-object default bug on Observation
        file_ids = [ref["$id"] for ref in obs_doc.get("files", []) if isinstance(ref, dict)]
        if not file_ids:
            continue
        res = await fits_col.update_many({"_id": {"$in": file_ids}}, {"$set": {"access_tags": tags}})
        updated += res.modified_count
        obs_count += 1
        if obs_count % 100 == 0:
            print(f"  processed {obs_count} observations...")
    print(f"Phase 2: {updated} FITSFile docs updated from {obs_count} Observations")
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
```

Run with:

```bash
poetry run python migrate_access_tags.py
```

---

## Index Creation

The new `access_tags` index on `FITSFile` is created **automatically** on app startup because
`init_beanie(allow_index_dropping=True)` compares declared indexes against MongoDB and creates
any that are missing. The migration script triggers this too via `ensure_connection()`.

---

## Verification

```bash
# Before running: verify the format of file links stored in observations
mongosh ocadb --eval 'db.observations.findOne({"files": {$ne:[]}}, {files:1})'

# After running:
mongosh ocadb --eval 'db.fits_files.countDocuments({"access_tags": {$exists: false}})'  # → 0
mongosh ocadb --eval 'db.fits_files.getIndexes()'  # → includes access_tags_1
```
