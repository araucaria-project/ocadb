"""Integration tests for GET /api/v2/observations/{id}/file-lineage."""
from tests.conftest import make_fits_header


def make_obs_payload(obs_name: str = "lineage_obs"):
    header = make_fits_header()
    return {
        "obs_name": obs_name,
        "file_name": f"{obs_name}.fits",
        "fits_header": header.model_dump(by_alias=True),
        "obs_tags": [],
    }


def make_file_payload(filename: str, obs_name: str, file_class: str = "raw", source_filenames=None):
    header = make_fits_header()
    return {
        "filename": filename,
        "file_class": file_class,
        "obs_name": obs_name,
        "file_status": {
            "observatory": {"ready": False, "check_needed": False, "status": "not_stored"},
            "hub": {"ready": False, "check_needed": False, "status": "not_stored"},
            "cloud": {"ready": False, "check_needed": False, "status": "not_stored"},
        },
        "fits_header": header.model_dump(by_alias=True),
        "access_tags": [],
        "source_filenames": source_filenames or [],
    }


async def create_obs(client, headers, obs_name: str) -> str:
    resp = await client.post("/api/v2/observations/", json=make_obs_payload(obs_name), headers=headers)
    assert resp.status_code == 201
    return resp.json()["_id"]


async def create_file(client, headers, filename: str, obs_name: str, file_class: str = "raw", source_filenames=None):
    resp = await client.post(
        "/api/v2/files/",
        json=make_file_payload(filename, obs_name, file_class, source_filenames),
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


LINEAGE_URL = "/api/v2/observations/{id}/file-lineage"


# --- auth / not found ---

async def test_lineage_requires_auth(client, beanie):
    resp = await client.get(LINEAGE_URL.format(id="000000000000000000000000"))
    assert resp.status_code == 401


async def test_lineage_not_found(client, auth_headers, regular_user):
    resp = await client.get(LINEAGE_URL.format(id="000000000000000000000000"), headers=auth_headers)
    assert resp.status_code == 404


# --- multi-level chain ---

async def test_lineage_walks_multi_level_chain(client, auth_headers, regular_user):
    obs_id = await create_obs(client, auth_headers, "lineage_chain")
    await create_file(client, auth_headers, "raw1.fits", "lineage_chain", file_class="raw")
    await create_file(client, auth_headers, "master1.fits", "lineage_chain", file_class="master",
                       source_filenames=["raw1.fits"])
    await create_file(client, auth_headers, "zdf1.fits", "lineage_chain", file_class="zdf",
                       source_filenames=["master1.fits"])

    resp = await client.get(LINEAGE_URL.format(id=obs_id), headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    assert set(body["roots"]) == {"raw1.fits", "master1.fits", "zdf1.fits"}
    assert set(body["nodes"].keys()) == {"raw1.fits", "master1.fits", "zdf1.fits"}
    assert body["nodes"]["master1.fits"]["file_class"] == "master"

    edges = {(e["from"], e["to"]) for e in body["edges"]}
    assert ("master1.fits", "raw1.fits") in edges
    assert ("zdf1.fits", "master1.fits") in edges


async def test_lineage_resolves_source_not_linked_to_this_observation(client, auth_headers, regular_user):
    """Source files are looked up globally by filename (see FITSFile.resolve_lineage),
    not scoped to the observation that references them — a calibration frame ingested
    under a different observation must still resolve."""
    await create_obs(client, auth_headers, "calib_owner")
    await create_file(client, auth_headers, "master_flat.fits", "calib_owner", file_class="master")

    obs_id = await create_obs(client, auth_headers, "lineage_cross_obs")
    await create_file(client, auth_headers, "zdf_a.fits", "lineage_cross_obs", file_class="zdf",
                       source_filenames=["master_flat.fits"])

    resp = await client.get(LINEAGE_URL.format(id=obs_id), headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    assert "master_flat.fits" in body["nodes"]
    assert body["nodes"]["master_flat.fits"]["obs_name"] == "calib_owner"
    assert {"from": "zdf_a.fits", "to": "master_flat.fits"} in body["edges"]


# --- shared source file ---

async def test_lineage_shared_source_appears_once_with_two_edges(client, auth_headers, regular_user):
    obs_id = await create_obs(client, auth_headers, "lineage_shared")
    await create_file(client, auth_headers, "master_flat.fits", "lineage_shared", file_class="master")
    await create_file(client, auth_headers, "zdf_a.fits", "lineage_shared", file_class="zdf",
                       source_filenames=["master_flat.fits"])
    await create_file(client, auth_headers, "zdf_b.fits", "lineage_shared", file_class="zdf",
                       source_filenames=["master_flat.fits"])

    resp = await client.get(LINEAGE_URL.format(id=obs_id), headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    assert list(body["nodes"].keys()).count("master_flat.fits") == 1  # appears once
    edges_to_master = [e for e in body["edges"] if e["to"] == "master_flat.fits"]
    assert {e["from"] for e in edges_to_master} == {"zdf_a.fits", "zdf_b.fits"}


# --- missing source file document ---

async def test_lineage_missing_source_document_stays_as_edge_only(client, auth_headers, regular_user):
    """A source_filenames entry with no matching FITSFile document (not yet ingested)
    should not appear in nodes, but the edge referencing it is still reported."""
    obs_id = await create_obs(client, auth_headers, "lineage_missing")
    await create_file(client, auth_headers, "zdf_missing.fits", "lineage_missing", file_class="zdf",
                       source_filenames=["never_ingested.fits"])

    resp = await client.get(LINEAGE_URL.format(id=obs_id), headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    assert "never_ingested.fits" not in body["nodes"]
    assert {"from": "zdf_missing.fits", "to": "never_ingested.fits"} in body["edges"]
