"""Integration tests for /api/v2/observations endpoints."""
import pytest
from tests.conftest import make_fits_header
from ocadb.models.download_script_event import DownloadScriptEvent


def make_obs_payload(obs_name: str = "obs_test_001", **header_overrides):
    header = make_fits_header(**header_overrides)
    return {
        "obs_name": obs_name,
        "file_name": f"{obs_name}.fits",
        "fits_header": header.model_dump(by_alias=True),
        "obs_tags": [],
    }


# --- POST /api/v2/observations/ ---

async def test_create_observation_requires_auth(client, beanie):
    resp = await client.post("/api/v2/observations/", json=make_obs_payload())
    assert resp.status_code == 401


async def test_create_observation_success(client, auth_headers, regular_user):
    resp = await client.post("/api/v2/observations/", json=make_obs_payload(), headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["obs_name"] == "obs_test_001"


async def test_create_observation_duplicate_returns_403(client, auth_headers, regular_user):
    await client.post("/api/v2/observations/", json=make_obs_payload(), headers=auth_headers)
    resp = await client.post("/api/v2/observations/", json=make_obs_payload(), headers=auth_headers)
    assert resp.status_code == 403


async def test_create_observation_canonizes_object_name(client, auth_headers, regular_user):
    resp = await client.post(
        "/api/v2/observations/",
        json=make_obs_payload(obs_name="obs_canon_001", **{"OBJECT": "V* Beta Lyr"}),
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["canonized_object_name"] == "vbetalyr"


# --- GET /api/v2/observations/{id}/ ---

async def test_get_observation_by_id(client, auth_headers, regular_user):
    create = await client.post("/api/v2/observations/", json=make_obs_payload(), headers=auth_headers)
    obs_id = create.json()["_id"]
    resp = await client.get(f"/api/v2/observations/{obs_id}/", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["obs_name"] == "obs_test_001"


async def test_get_observation_not_found(client, auth_headers, regular_user):
    resp = await client.get("/api/v2/observations/000000000000000000000001/", headers=auth_headers)
    assert resp.status_code == 404


async def test_get_observation_requires_auth(client, beanie):
    resp = await client.get("/api/v2/observations/000000000000000000000001/")
    assert resp.status_code == 401


# --- GET /api/v2/observations/{id}/short ---

async def test_get_observation_short(client, auth_headers, regular_user):
    create = await client.post("/api/v2/observations/", json=make_obs_payload(), headers=auth_headers)
    obs_id = create.json()["_id"]
    resp = await client.get(f"/api/v2/observations/{obs_id}/short", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["obs_name"] == "obs_test_001"


# --- PUT /api/v2/observations/{id}/metadata ---

async def test_update_metadata(client, auth_headers, regular_user):
    create = await client.post("/api/v2/observations/", json=make_obs_payload(), headers=auth_headers)
    obs_id = create.json()["_id"]
    resp = await client.put(
        f"/api/v2/observations/{obs_id}/metadata",
        json={"quality": "good", "snr": 42.5},
        headers=auth_headers,
    )
    assert resp.status_code == 200


async def test_update_metadata_not_found(client, auth_headers, regular_user):
    resp = await client.put(
        "/api/v2/observations/000000000000000000000001/metadata",
        json={"quality": "good"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# --- DELETE /api/v2/observations/{id}/ ---

async def test_delete_observation(client, auth_headers, regular_user):
    create = await client.post("/api/v2/observations/", json=make_obs_payload(), headers=auth_headers)
    obs_id = create.json()["_id"]
    resp = await client.delete(f"/api/v2/observations/{obs_id}/", headers=auth_headers)
    assert resp.status_code == 200


async def test_delete_observation_not_found(client, auth_headers, regular_user):
    resp = await client.delete("/api/v2/observations/000000000000000000000001/", headers=auth_headers)
    assert resp.status_code == 404


# --- Search by observation name ---

async def test_get_by_observation_name(client, auth_headers, regular_user):
    await client.post("/api/v2/observations/", json=make_obs_payload(obs_name="named_obs"), headers=auth_headers)
    resp = await client.get("/api/v2/observations/by-observation-name/named_obs/", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["obs_name"] == "named_obs"


async def test_get_by_observation_name_not_found(client, auth_headers, regular_user):
    resp = await client.get("/api/v2/observations/by-observation-name/nonexistent/", headers=auth_headers)
    assert resp.status_code == 404


async def test_get_by_observation_name_resolves_linked_files(client, auth_headers, regular_user):
    """The aggregation pipeline behind by-observation-name doesn't resolve
    files: List[Link[FITSFile]] the way GET /{id}/ (fetch_links=True) does — without a
    fix, files comes back empty even though the observation has linked files."""
    header = make_fits_header()
    await client.post("/api/v2/observations/", json=make_obs_payload(obs_name="obs_with_linked_file"), headers=auth_headers)
    await client.post(
        "/api/v2/files/",
        json={
            "filename": "linked.fits",
            "file_class": "raw",
            "obs_name": "obs_with_linked_file",
            "file_status": {
                "observatory": {"ready": False, "check_needed": False, "status": "not_stored"},
                "hub": {"ready": False, "check_needed": False, "status": "not_stored"},
                "cloud": {"ready": False, "check_needed": False, "status": "not_stored"},
            },
            "fits_header": header.model_dump(by_alias=True),
            "access_tags": [],
            "source_filenames": [],
        },
        headers=auth_headers,
    )

    resp = await client.get("/api/v2/observations/by-observation-name/obs_with_linked_file/", headers=auth_headers)
    assert resp.status_code == 200
    files = resp.json()["files"]
    assert len(files) == 1
    assert files[0]["filename"] == "linked.fits"


# --- POST /api/v2/observations/download-script ---

async def test_download_script_logs_event(client, auth_headers, regular_user):
    header = make_fits_header()
    create = await client.post(
        "/api/v2/observations/", json=make_obs_payload(obs_name="dl_script_obs"), headers=auth_headers
    )
    obs_id = create.json()["_id"]
    await client.post(
        "/api/v2/files/",
        json={
            "filename": "dl_script_obs.fits",
            "file_class": "raw",
            "obs_name": "dl_script_obs",
            "file_status": {
                "observatory": {"ready": False, "check_needed": False, "status": "not_stored"},
                "hub": {"ready": False, "check_needed": False, "status": "not_stored"},
                "cloud": {"ready": False, "check_needed": False, "status": "not_stored"},
            },
            "fits_header": header.model_dump(by_alias=True),
            "access_tags": [],
            "source_filenames": [],
        },
        headers=auth_headers,
    )

    resp = await client.post(
        "/api/v2/observations/download-script",
        json={"obs_ids": [obs_id], "include_calibration": False, "file_types": None},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert b"dl_script_obs.fits" in resp.content

    events = await DownloadScriptEvent.find(DownloadScriptEvent.username == regular_user.username).to_list()
    assert len(events) == 1
    event = events[0]
    assert event.obs_ids == [obs_id]
    assert event.obs_names == ["dl_script_obs"]
    assert event.filenames == ["dl_script_obs.fits"]
    assert event.file_count == 1
    assert event.include_calibration is False


# --- Search by object ---

async def test_list_by_object_name(client, auth_headers, regular_user):
    await client.post(
        "/api/v2/observations/",
        json=make_obs_payload(obs_name="tz_obs_001", **{"OBJECT": "TZ For"}),
        headers=auth_headers,
    )
    resp = await client.get("/api/v2/observations/by-object/TZ For/", headers=auth_headers)
    assert resp.status_code == 200


async def test_list_by_object_not_found(client, auth_headers, regular_user):
    resp = await client.get("/api/v2/observations/by-object/UnknownObject/", headers=auth_headers)
    assert resp.status_code == 404


# --- Search by filter ---

async def test_list_by_filter(client, auth_headers, regular_user):
    await client.post(
        "/api/v2/observations/",
        json=make_obs_payload(obs_name="filter_obs_001", **{"FILTER": "B"}),
        headers=auth_headers,
    )
    resp = await client.get("/api/v2/observations/by-filter/B/", headers=auth_headers)
    assert resp.status_code == 200


async def test_list_by_filter_not_found(client, auth_headers, regular_user):
    resp = await client.get("/api/v2/observations/by-filter/X-ray/", headers=auth_headers)
    assert resp.status_code == 404


# --- Values endpoints ---

async def test_values_telescop_returns_list(client, auth_headers, regular_user):
    await client.post("/api/v2/observations/", json=make_obs_payload(), headers=auth_headers)
    resp = await client.get("/api/v2/observations/values/telescop", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_values_imagetyp_returns_list(client, auth_headers, regular_user):
    resp = await client.get("/api/v2/observations/values/imagetyp", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_values_obstype_returns_list(client, auth_headers, regular_user):
    resp = await client.get("/api/v2/observations/values/obstype", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_values_pi_returns_list(client, auth_headers, regular_user):
    resp = await client.get("/api/v2/observations/values/pi", headers=auth_headers)
    assert resp.status_code == 200


async def test_values_tags_returns_list(client, auth_headers, regular_user):
    resp = await client.get("/api/v2/observations/values/tags", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# --- Access control (redact) ---

async def test_user_cannot_see_obs_with_different_tags(client, beanie):
    from ocadb.models import UserInDB
    from api.services.auth_service import AuthService
    from datetime import timedelta

    user_a = UserInDB(
        username="user_a",
        email="a@test.com",
        full_name="User A",
        hashed_password="x",
        access_tags=["TAG-A"],
    )
    await user_a.insert()
    user_b = UserInDB(
        username="user_b",
        email="b@test.com",
        full_name="User B",
        hashed_password="x",
        access_tags=["TAG-B"],
    )
    await user_b.insert()

    token_a = AuthService.create_access_token({"sub": "user_a"}, expires_delta=timedelta(minutes=30))
    token_b = AuthService.create_access_token({"sub": "user_b"}, expires_delta=timedelta(minutes=30))
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    obs_payload = make_obs_payload(obs_name="restricted_obs", **{"INSTRUME": "TAG-A", "ORIGIN": None, "PI": None})
    create_resp = await client.post("/api/v2/observations/", json=obs_payload, headers=headers_a)
    assert create_resp.status_code == 201

    resp_a = await client.get("/api/v2/observations/by-observation-name/restricted_obs/", headers=headers_a)
    assert resp_a.status_code == 200

    resp_b = await client.get("/api/v2/observations/by-observation-name/restricted_obs/", headers=headers_b)
    assert resp_b.status_code == 404


# --- obs-tags CRUD ---

async def test_add_obs_tag(client, auth_headers, regular_user):
    create = await client.post("/api/v2/observations/", json=make_obs_payload(), headers=auth_headers)
    obs_id = create.json()["_id"]
    resp = await client.post(
        f"/api/v2/observations/{obs_id}/obs-tags",
        json={"tag_name": "mytag"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "mytag" in resp.json()["obs_tags"]


async def test_remove_obs_tag(client, auth_headers, regular_user):
    create = await client.post("/api/v2/observations/", json=make_obs_payload(), headers=auth_headers)
    obs_id = create.json()["_id"]
    await client.post(f"/api/v2/observations/{obs_id}/obs-tags", json={"tag_name": "removeme"}, headers=auth_headers)
    resp = await client.request("DELETE", f"/api/v2/observations/{obs_id}/obs-tags", json={"tag_name": "removeme"}, headers=auth_headers)
    assert resp.status_code == 200
    assert "removeme" not in resp.json()["obs_tags"]


# --- source-files-count correction ---

async def test_set_source_files_count_requires_auth(client, beanie):
    resp = await client.put("/api/v2/observations/000000000000000000000000/source-files-count", json={"count": 3})
    assert resp.status_code == 401


async def test_set_source_files_count_not_found(client, auth_headers, regular_user):
    resp = await client.put(
        "/api/v2/observations/000000000000000000000000/source-files-count",
        json={"count": 3}, headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_set_source_files_count_updates_value(client, auth_headers, regular_user):
    from ocadb.models.observation import Observation

    create = await client.post("/api/v2/observations/", json=make_obs_payload(), headers=auth_headers)
    obs_id = create.json()["_id"]

    resp = await client.put(
        f"/api/v2/observations/{obs_id}/source-files-count",
        json={"count": 4}, headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["source_files_number"] == 4

    obs = await Observation.get(obs_id)
    assert obs.source_files_number == 4


async def test_set_source_files_count_rejects_negative(client, auth_headers, regular_user):
    create = await client.post("/api/v2/observations/", json=make_obs_payload(), headers=auth_headers)
    obs_id = create.json()["_id"]

    resp = await client.put(
        f"/api/v2/observations/{obs_id}/source-files-count",
        json={"count": -1}, headers=auth_headers,
    )
    assert resp.status_code == 422


# --- SearchTag endpoints ---

async def test_create_search_tag(client, auth_headers, regular_user):
    resp = await client.post(
        "/api/v2/observations/values/tags",
        json={"tag_name": "newtag", "tag_description": "A new tag", "tag_color": "#ff0000"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["tag_name"] == "newtag"


async def test_create_duplicate_search_tag_returns_409(client, auth_headers, regular_user):
    await client.post("/api/v2/observations/values/tags", json={"tag_name": "duptag"}, headers=auth_headers)
    resp = await client.post("/api/v2/observations/values/tags", json={"tag_name": "duptag"}, headers=auth_headers)
    assert resp.status_code == 409


async def test_update_search_tag_requires_moderator(client, auth_headers, regular_user):
    await client.post("/api/v2/observations/values/tags", json={"tag_name": "modtag"}, headers=auth_headers)
    resp = await client.put(
        "/api/v2/observations/values/tags/modtag",
        json={"tag_description": "edited"},
        headers=auth_headers,
    )
    assert resp.status_code == 403


async def test_update_search_tag_description_and_color(client, auth_headers, mod_headers, regular_user, moderator_user):
    await client.post("/api/v2/observations/values/tags", json={"tag_name": "edittag"}, headers=auth_headers)
    resp = await client.put(
        "/api/v2/observations/values/tags/edittag",
        json={"tag_description": "new desc", "tag_color": "bg-red-900/40"},
        headers=mod_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tag_name"] == "edittag"
    assert body["tag_description"] == "new desc"
    assert body["tag_color"] == "bg-red-900/40"


async def test_rename_search_tag_cascades_to_observations(client, auth_headers, mod_headers, regular_user, moderator_user):
    await client.post("/api/v2/observations/values/tags", json={"tag_name": "oldname"}, headers=auth_headers)
    create = await client.post("/api/v2/observations/", json=make_obs_payload(obs_name="obs_tag_rename"), headers=auth_headers)
    obs_id = create.json()["_id"]
    await client.post(f"/api/v2/observations/{obs_id}/obs-tags", json={"tag_name": "oldname"}, headers=auth_headers)

    resp = await client.put(
        "/api/v2/observations/values/tags/oldname",
        json={"tag_name": "newname"},
        headers=mod_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["tag_name"] == "newname"

    obs_resp = await client.get(f"/api/v2/observations/{obs_id}/", headers=auth_headers)
    assert "newname" in obs_resp.json()["obs_tags"]
    assert "oldname" not in obs_resp.json()["obs_tags"]


async def test_rename_search_tag_to_existing_name_returns_409(client, auth_headers, mod_headers, regular_user, moderator_user):
    await client.post("/api/v2/observations/values/tags", json={"tag_name": "taga"}, headers=auth_headers)
    await client.post("/api/v2/observations/values/tags", json={"tag_name": "tagb"}, headers=auth_headers)
    resp = await client.put(
        "/api/v2/observations/values/tags/taga",
        json={"tag_name": "tagb"},
        headers=mod_headers,
    )
    assert resp.status_code == 409


async def test_update_search_tag_not_found(client, mod_headers, moderator_user):
    resp = await client.put(
        "/api/v2/observations/values/tags/nonexistent",
        json={"tag_description": "x"},
        headers=mod_headers,
    )
    assert resp.status_code == 404


async def test_delete_search_tag_requires_moderator(client, auth_headers, regular_user):
    await client.post("/api/v2/observations/values/tags", json={"tag_name": "deltag"}, headers=auth_headers)
    resp = await client.delete("/api/v2/observations/values/tags/deltag", headers=auth_headers)
    assert resp.status_code == 403


async def test_delete_search_tag_removes_from_observations(client, auth_headers, mod_headers, regular_user, moderator_user):
    await client.post("/api/v2/observations/values/tags", json={"tag_name": "removeme"}, headers=auth_headers)
    create = await client.post("/api/v2/observations/", json=make_obs_payload(obs_name="obs_tag_delete"), headers=auth_headers)
    obs_id = create.json()["_id"]
    await client.post(f"/api/v2/observations/{obs_id}/obs-tags", json={"tag_name": "removeme"}, headers=auth_headers)

    resp = await client.delete("/api/v2/observations/values/tags/removeme", headers=mod_headers)
    assert resp.status_code == 200
    assert resp.json()["observations_updated"] == 1

    obs_resp = await client.get(f"/api/v2/observations/{obs_id}/", headers=auth_headers)
    assert "removeme" not in obs_resp.json()["obs_tags"]

    tags_resp = await client.get("/api/v2/observations/values/tags", headers=auth_headers)
    assert "removeme" not in [t["tag_name"] for t in tags_resp.json()]


async def test_delete_search_tag_not_found(client, mod_headers, moderator_user):
    resp = await client.delete("/api/v2/observations/values/tags/nonexistent", headers=mod_headers)
    assert resp.status_code == 404


# --- POST /api/v2/observations/search ---

async def test_multi_search_by_telescop(client, auth_headers, regular_user):
    await client.post(
        "/api/v2/observations/",
        json=make_obs_payload(obs_name="search_obs_001", **{"TELESCOP": "ZEISS-1m"}),
        headers=auth_headers,
    )
    resp = await client.post(
        "/api/v2/observations/search",
        json={"telescop": "ZEISS-1m"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"][0]["fits_header"]["TELESCOP"] == "ZEISS-1m"


async def test_multi_search_has_requested_files_filter(client, auth_headers, regular_user):
    await client.post("/api/v2/observations/", json=make_obs_payload(obs_name="search_no_requested"), headers=auth_headers)

    await client.post("/api/v2/observations/", json=make_obs_payload(obs_name="search_has_requested"), headers=auth_headers)
    await client.post(
        "/api/v2/files/",
        json={
            "filename": "search_requested.fits",
            "file_class": "raw",
            "obs_name": "search_has_requested",
            "file_status": {
                "observatory": {"ready": False, "check_needed": False, "status": "not_stored"},
                "hub": {"ready": False, "check_needed": False, "status": "not_stored"},
                "cloud": {"ready": False, "check_needed": False, "status": "not_stored"},
            },
            "fits_header": make_fits_header().model_dump(by_alias=True),
            "access_tags": [],
            "source_filenames": [],
        },
        headers=auth_headers,
    )
    await client.put(
        "/api/v2/files/file-status/search_requested.fits/",
        json={
            "observatory": {"ready": False, "check_needed": False, "status": "not_stored"},
            "hub": {"ready": False, "check_needed": False, "status": "not_stored"},
            "cloud": {"ready": False, "check_needed": False, "status": "requested"},
        },
        headers=auth_headers,
    )

    resp = await client.post(
        "/api/v2/observations/search",
        json={"has_requested_files": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    obs_names = [o["obs_name"] for o in resp.json()["data"]]
    assert obs_names == ["search_has_requested"]


def _file_payload(filename, obs_name, file_class="raw", source_filenames=None):
    return {
        "filename": filename,
        "file_class": file_class,
        "obs_name": obs_name,
        # held by the hub, not yet uploaded — the only requestable cloud state
        "file_status": {
            "observatory": {"ready": True, "check_needed": False, "status": "stored"},
            "hub": {"ready": True, "check_needed": False, "status": "stored"},
            "cloud": {"ready": False, "check_needed": False, "status": "on_demand"},
        },
        "fits_header": make_fits_header().model_dump(by_alias=True),
        "access_tags": [],
        "source_filenames": source_filenames or [],
    }


async def test_multi_search_has_requested_files_follows_calibration_chain(client, auth_headers, regular_user):
    """A request on a raw calibration frame, two source_filenames levels below a science
    file, marks every observation consuming it, and requested_by lists every requester of
    the observation's own and calibration files."""
    from ocadb.models.file import FITSFile

    # Calibration chain with no parent observation: flat raw -> master flat
    calib = {
        "chain_flat_raw.fits": ("raw", []),
        "chain_master_flat.fits": ("master", ["chain_flat_raw.fits"]),
    }
    for filename, (file_class, sources) in calib.items():
        payload = _file_payload(filename, "chain_calibration", file_class, sources)
        payload.pop("fits_header")
        await FITSFile.model_validate(payload).insert()

    # chain_a: raw + zdf (calibrated with the master flat); chain_b: zdf only, same master
    # flat; chain_c: unrelated raw file
    for obs_name, files in {
        "chain_a": [("chain_a_raw.fits", "raw", []), ("chain_a_zdf.fits", "zdf", ["chain_a_raw.fits", "chain_master_flat.fits"])],
        "chain_b": [("chain_b_zdf.fits", "zdf", ["chain_master_flat.fits"])],
        "chain_c": [("chain_c_raw.fits", "raw", [])],
    }.items():
        await client.post("/api/v2/observations/", json=make_obs_payload(obs_name=obs_name), headers=auth_headers)
        for filename, file_class, sources in files:
            resp = await client.post("/api/v2/files/", json=_file_payload(filename, obs_name, file_class, sources), headers=auth_headers)
            assert resp.status_code == 201

    await FITSFile.request_cloud_uploads(["chain_flat_raw.fits"], "alice")
    await FITSFile.request_cloud_uploads(["chain_a_raw.fits"], "bob")

    resp = await client.post("/api/v2/observations/search", json={"has_requested_files": True}, headers=auth_headers)
    assert resp.status_code == 200
    requested_by = {o["obs_name"]: o["requested_by"] for o in resp.json()["data"]}
    assert requested_by == {"chain_a": ["alice", "bob"], "chain_b": ["alice"]}


async def test_request_cloud_uploads_flips_only_on_demand(client, auth_headers, regular_user):
    """Only ON_DEMAND files (held by the hub) are requestable — e.g. an observatory-only
    NOT_STORED file has no copy the hub could upload after approval."""
    from ocadb.models.file import FITSFile

    statuses = ["on_demand", "not_stored", "deleted", "corrupted", "stored"]
    for status in statuses:
        payload = _file_payload(f"req_status_{status}.fits", "req_status")
        payload["file_status"]["cloud"]["status"] = status
        payload.pop("fits_header")
        await FITSFile.model_validate(payload).insert()

    flipped = await FITSFile.request_cloud_uploads([f"req_status_{s}.fits" for s in statuses], "alice")

    assert flipped == 1
    for status in statuses:
        f = await FITSFile.find_one(FITSFile.filename == f"req_status_{status}.fits")
        assert f.file_status.cloud.status.value == ("requested" if status == "on_demand" else status)


@pytest.mark.parametrize("file_class, image_type, expected", [
    ("raw", "science", "raw"),
    ("raw", "object", "raw"),
    ("zdf", "OBJECT", "zdf"),
    ("zdf", " Science ", "zdf"),
    ("raw", "flat", "flat"),
    ("master", "Zero", "master_zero"),
    ("master", "object", "unknown"),
    ("raw", None, "unknown"),
    (None, None, "unknown"),
])
def test_classify_file(file_class, image_type, expected):
    from api.routers.observations_v2 import _classify_file
    assert _classify_file(file_class, image_type) == expected


async def test_request_files_matches_object_imagetyp_science_frames(client, auth_headers, regular_user):
    """Science frames with FITS IMAGETYP 'object' (any case) count as raw/zdf — they used
    to classify as 'unknown', so the modal's default raw+zdf request 404'd with
    "No files found for the selected observations"."""
    resp = await client.post("/api/v2/observations/", json=make_obs_payload(obs_name="req_object"), headers=auth_headers)
    obs_id = resp.json()["_id"]
    for filename, file_class, imagetyp in [("req_object_raw.fits", "raw", "object"),
                                           ("req_object_zdf.fits", "zdf", "OBJECT"),
                                           ("req_object_master.fits", "master", "flat")]:
        payload = _file_payload(filename, "req_object", file_class)
        payload["fits_header"] = make_fits_header(IMAGETYP=imagetyp).model_dump(by_alias=True)
        assert (await client.post("/api/v2/files/", json=payload, headers=auth_headers)).status_code == 201

    resp = await client.post("/api/v2/observations/request-files",
                             json={"obs_ids": [obs_id], "include_calibration": False, "file_types": ["zdf", "raw"]},
                             headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["file_count"] == 2


async def test_request_files_other_selects_observations_own_master(client, auth_headers, regular_user):
    """'other' picks the observation's own files that are neither zdf nor raw (masters)."""
    resp = await client.post("/api/v2/observations/", json=make_obs_payload(obs_name="req_master_obs"), headers=auth_headers)
    obs_id = resp.json()["_id"]
    for filename, file_class in [("req_master_obs_raw.fits", "raw"), ("req_master_obs.fits", "master")]:
        payload = _file_payload(filename, "req_master_obs", file_class)
        payload["fits_header"] = make_fits_header(IMAGETYP="flat").model_dump(by_alias=True)
        assert (await client.post("/api/v2/files/", json=payload, headers=auth_headers)).status_code == 201

    assert await _request_file_count(client, auth_headers, obs_id, False, ["other"]) == 1
    assert await _request_file_count(client, auth_headers, obs_id, False, ["zdf", "raw", "other"]) == 2


async def _request_file_count(client, auth_headers, obs_id, include_calibration, file_types):
    resp = await client.post("/api/v2/observations/request-files",
                             json={"obs_ids": [obs_id], "include_calibration": include_calibration,
                                   "file_types": file_types},
                             headers=auth_headers)
    return resp.json().get("file_count") if resp.status_code == 200 else resp.status_code


async def test_request_files_raw_selects_calibration_observations_own_files(client, auth_headers, regular_user):
    """'raw' selects an observation's own raw files whatever their IMAGETYP, so a flat
    observation's raw flat needs no calibration options."""
    resp = await client.post("/api/v2/observations/", json=make_obs_payload(obs_name="req_flat_obs"), headers=auth_headers)
    obs_id = resp.json()["_id"]
    payload = _file_payload("req_flat_obs.fits", "req_flat_obs", "raw")
    payload["fits_header"] = make_fits_header(IMAGETYP="flat").model_dump(by_alias=True)
    assert (await client.post("/api/v2/files/", json=payload, headers=auth_headers)).status_code == 201

    assert await _request_file_count(client, auth_headers, obs_id, False, ["raw"]) == 1
    assert await _request_file_count(client, auth_headers, obs_id, False, ["zdf"]) == 404


async def test_request_files_sections_filter_their_own_files(client, auth_headers, regular_user):
    """Observation-file types filter the observation's files; calibration types filter
    only its source files; a section with nothing selected keeps all of its files."""
    from ocadb.models.file import FITSFile

    for filename, file_class, imagetyp in [("src_flat.fits", "raw", "flat"),
                                           ("src_master_flat.fits", "master", "flat")]:
        payload = _file_payload(filename, "src_calib", file_class)
        payload.pop("fits_header")
        await FITSFile.model_validate({**payload, "image_type": imagetyp}).insert()
    resp = await client.post("/api/v2/observations/", json=make_obs_payload(obs_name="req_sections"), headers=auth_headers)
    obs_id = resp.json()["_id"]
    for filename, file_class in [("req_sections_raw.fits", "raw"), ("req_sections_zdf.fits", "zdf")]:
        payload = _file_payload(filename, "req_sections", file_class,
                                source_filenames=["src_flat.fits", "src_master_flat.fits"])
        payload["fits_header"] = make_fits_header(IMAGETYP="object").model_dump(by_alias=True)
        assert (await client.post("/api/v2/files/", json=payload, headers=auth_headers)).status_code == 201

    assert await _request_file_count(client, auth_headers, obs_id, True, ["zdf", "master_flat"]) == 2
    assert await _request_file_count(client, auth_headers, obs_id, True, ["zdf", "raw"]) == 4
    assert await _request_file_count(client, auth_headers, obs_id, True, ["flat"]) == 3
    assert await _request_file_count(client, auth_headers, obs_id, False, ["zdf", "flat"]) == 1


async def test_multi_search_empty_result_returns_404(client, auth_headers, regular_user):
    resp = await client.post(
        "/api/v2/observations/search",
        json={"telescop": "NONEXISTENT-SCOPE"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_multi_search_by_object(client, auth_headers, regular_user):
    await client.post(
        "/api/v2/observations/",
        json=make_obs_payload(obs_name="search_by_obj", **{"OBJECT": "V Sge"}),
        headers=auth_headers,
    )
    resp = await client.post(
        "/api/v2/observations/search",
        json={"object": "V Sge"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
