"""Integration tests for /api/v1/objects endpoints."""
import pytest
from ocadb.models import Object
from ocadb.models.geo import SkyCoord


def make_object_payload(**overrides):
    base = {
        "name": "TZ For",
        "coo": {"lon_lat": {"type": "Point", "coordinates": [-90.0, -28.0]}, "epoch": 2000.0},
        "aliases": [],
        "brightness": [],
        "periodicity": [],
    }
    base.update(overrides)
    return base


# --- POST /api/v1/objects/ ---

async def test_create_object_requires_auth(client, beanie):
    resp = await client.post("/api/v1/objects/", json=make_object_payload())
    assert resp.status_code == 401


async def test_create_object_success(client, auth_headers, regular_user):
    resp = await client.post("/api/v1/objects/", json=make_object_payload(), headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "TZ For"


async def test_create_object_canonizes_name(client, auth_headers, regular_user):
    resp = await client.post(
        "/api/v1/objects/",
        json=make_object_payload(name="V0441 CYG"),
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["canonized_name"] == "v0441cyg"


# --- GET /api/v1/objects/ ---

async def test_list_objects_empty(client, beanie):
    resp = await client.get("/api/v1/objects/")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_objects_returns_created(client, auth_headers, regular_user):
    await client.post("/api/v1/objects/", json=make_object_payload(name="Alpha"), headers=auth_headers)
    await client.post("/api/v1/objects/", json=make_object_payload(name="Beta"), headers=auth_headers)
    resp = await client.get("/api/v1/objects/")
    assert resp.status_code == 200
    names = [o["name"] for o in resp.json()]
    assert "Alpha" in names
    assert "Beta" in names


async def test_list_objects_public(client, beanie):
    resp = await client.get("/api/v1/objects/")
    assert resp.status_code == 200


# --- GET /api/v1/objects/{id} ---

async def test_get_object_by_id(client, auth_headers, regular_user):
    create = await client.post("/api/v1/objects/", json=make_object_payload(), headers=auth_headers)
    obj_id = create.json()["_id"]
    resp = await client.get(f"/api/v1/objects/{obj_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "TZ For"


async def test_get_object_not_found(client, beanie):
    resp = await client.get("/api/v1/objects/000000000000000000000001")
    assert resp.status_code == 404


# --- PUT /api/v1/objects/{id} ---

async def test_update_object_requires_auth(client, auth_headers, regular_user):
    create = await client.post("/api/v1/objects/", json=make_object_payload(), headers=auth_headers)
    obj_id = create.json()["_id"]
    updated = make_object_payload(name="Updated Object")
    resp = await client.put(f"/api/v1/objects/{obj_id}", json=updated)
    assert resp.status_code == 401


async def test_update_object_not_found_with_auth(client, auth_headers, regular_user):
    updated = make_object_payload(name="Updated Object")
    resp = await client.put("/api/v1/objects/000000000000000000000001", json=updated, headers=auth_headers)
    assert resp.status_code == 404


# --- DELETE /api/v1/objects/{id} ---

async def test_delete_object_success(client, auth_headers, regular_user):
    create = await client.post("/api/v1/objects/", json=make_object_payload(), headers=auth_headers)
    obj_id = create.json()["_id"]
    resp = await client.delete(f"/api/v1/objects/{obj_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert "deleted" in resp.json()["message"].lower()


async def test_delete_object_not_found(client, auth_headers, regular_user):
    resp = await client.delete("/api/v1/objects/000000000000000000000001", headers=auth_headers)
    assert resp.status_code == 404


async def test_delete_object_requires_auth(client, auth_headers, regular_user):
    create = await client.post("/api/v1/objects/", json=make_object_payload(), headers=auth_headers)
    obj_id = create.json()["_id"]
    resp = await client.delete(f"/api/v1/objects/{obj_id}")
    assert resp.status_code == 401


async def test_deleted_object_not_findable(client, auth_headers, regular_user):
    create = await client.post("/api/v1/objects/", json=make_object_payload(), headers=auth_headers)
    obj_id = create.json()["_id"]
    await client.delete(f"/api/v1/objects/{obj_id}", headers=auth_headers)
    resp = await client.get(f"/api/v1/objects/{obj_id}")
    assert resp.status_code == 404
