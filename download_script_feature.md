# Download Script Generation Feature

## Background

`ocascripts/fitscollectdownloader.py` uses `ocafitsfiles.render_download_script()` to generate
self-contained POSIX shell scripts that download FITS files from OCADB. We want to expose this
capability directly from the OCADB frontend.

### What the generated script does

- Embeds a username and a list of FITS filenames
- Prompts for password at runtime (or reads `$OCADB_PASSWORD` / `-p` flag)
- Authenticates against `/api/v1/auth/plaintoken/` (already exists in ocadb)
- For each filename fetches a presigned S3 URL from `/api/v1/files/by-filename/{key}/plainurl?expires_in=…` (already exists)
- Downloads files with `curl`/`wget` and verifies them

Both API endpoints the script depends on already exist in ocadb.

---

## Proposed Implementation

### Backend

**New dependency** — add `ocafitsfiles` to `pyproject.toml` (git dep, same pattern as `pyaraucaria`).
The `render_download_script` function is the only thing needed from it.

**New endpoint:**
```
POST /api/v2/observations/download-script
Auth: required (username taken from the authenticated JWT)
Body: { obs_ids: ["id1", "id2", ...], file_classes: ["zdf"] }
Response: text/x-shellscript, Content-Disposition: attachment; filename=download.sh
```

The endpoint:
1. Resolves the given observation IDs → fetches linked FITSFile records
2. Filters by `file_classes` (e.g. `zdf`, `raw`; empty = all)
3. Builds a filename list (one per line)
4. Calls `render_download_script(data_block, username=current_user)`
5. Returns the script as a file download

### Frontend — observation selection

#### Entry point: "Select for download" toggle button

A bi-stable toggle button sits in the top-right area above the main results table (in the pagination/count bar). Label:
- Normal mode: `Select for download`
- Active mode: `Cancel selection` (or visually highlighted/active state)

Clicking it toggles `selectMode = signal<boolean>(false)`. Exiting select mode clears all selections.

#### Select mode behaviour

When `selectMode` is true:
1. **Checkbox column** appears as the leftmost column in the table, with a "select all on current page" header checkbox.
2. Clicking a row checkbox toggles that observation in/out of `selectedObsIds`.
3. Row click no longer opens the observation detail modal — only the checkbox area is interactive for selection. (Or: row click toggles selection instead of opening the modal.)

#### Exiting select mode

Toggling the button back clears `selectedObsIds` and removes the checkbox column.

#### Signals needed in `AppComponent`

```typescript
selectMode = signal<boolean>(false);
selectedObsIds = signal<Set<string>>(new Set());
```

#### DOWNLOAD button (shopping cart)

Sits immediately to the right of the "Select for download" toggle button. Always visible.

- **No observations selected**: greyed out / disabled appearance, subscript shows `0`
- **≥1 observation selected**: active/highlighted appearance, subscript updates to show count of selected observations
- The subscript count updates live as selections change
- Behaviour on click: to be defined

---

## Files to change

| File | Change |
|------|--------|
| `pyproject.toml` | Add `ocafitsfiles` git dependency |
| `api/routers/observations_v2.py` | New `POST /download-script` endpoint |
| `frontend/src/app.component.ts` | `selectedObsIds` signal + selection handlers |
| `frontend/src/app.component.html` | Checkbox column + selection toolbar |
| `frontend/src/services/ocadb.service.ts` | `downloadScript()` method |

Estimated ~100–150 lines of new code.

---

## Open questions / things to finalize

- Which file classes to offer in the UI? (`zdf`, `raw`, both, all)
- Should "select all" select across pages or only the current page?
- Default `expires_in` for the presigned URLs embedded in the script (current default in `ocafitsfiles`: 604800 s = 7 days)
- How row clicks behave in select mode: toggle selection vs. open detail modal (decide before implementing)
