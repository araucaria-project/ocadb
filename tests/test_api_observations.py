"""Integration tests for /api/v2/observations endpoints."""
import pytest
from tests.conftest import make_fits_header


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
