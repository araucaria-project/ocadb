"""Tests for QueryBuilder, MultiSearchForm, and OcaWithin."""
import math
import pytest
from api.services.query_builder import QueryBuilder, MultiSearchForm
from api.services.oca_geospatial_query import OcaWithin
from ocadb.models.geo import ArchDistance


# --- MultiSearchForm ---

def test_multisearch_form_all_optional():
    form = MultiSearchForm()
    assert form.telescop is None
    assert form.object is None
    assert form.filter is None
    assert form.cone_search is None


def test_multisearch_form_with_telescop():
    form = MultiSearchForm(telescop="TEST-1m")
    assert form.telescop == "TEST-1m"


def test_multisearch_form_with_filter_list():
    form = MultiSearchForm(filter=["V", "B", "R"])
    assert "V" in form.filter
    assert "B" in form.filter


def test_multisearch_form_with_cone_search():
    ad = ArchDistance(ra=180.0, dec=-30.0, arc_seconds=600.0)
    form = MultiSearchForm(cone_search=ad)
    assert form.cone_search is not None
    assert form.cone_search.arc_seconds == 600.0


def test_multisearch_form_date_range():
    form = MultiSearchForm(date_obs_from="2024-01-01", date_obs_to="2024-12-31")
    assert form.date_obs_from == "2024-01-01"
    assert form.date_obs_to == "2024-12-31"


def test_multisearch_form_jd_range():
    form = MultiSearchForm(jd_from=2460000, jd_to=2460365)
    assert form.jd_from == 2460000
    assert form.jd_to == 2460365


def test_multisearch_form_oca_jd_range():
    form = MultiSearchForm(oca_jd_from=320, oca_jd_to=500)
    assert form.oca_jd_from == 320
    assert form.oca_jd_to == 500


def test_multisearch_form_with_tags():
    form = MultiSearchForm(tags={"raw", "metadata"})
    assert "raw" in form.tags


def test_multisearch_form_with_sort_expr():
    form = MultiSearchForm(sort_expr={"date_obs": -1})
    assert form.sort_expr == {"date_obs": -1}


def test_multisearch_form_with_pi():
    form = MultiSearchForm(pi="smith")
    assert form.pi == "smith"


# --- QueryBuilder ---

def test_query_builder_find_query_structure():
    qb = QueryBuilder(field="telescope_coordinates.lon_lat", coordinates=(-90.0, 45.0), radius=0.01)
    fq = qb.find_query
    assert "$geoWithin" in fq
    assert "$centerSphere" in fq["$geoWithin"]


def test_query_builder_geo_query_has_field():
    qb = QueryBuilder(field="telescope_coordinates.lon_lat", coordinates=(-90.0, 45.0), radius=0.01)
    gq = qb.geo_query
    assert "telescope_coordinates.lon_lat" in gq


def test_query_builder_center_sphere_coords():
    qb = QueryBuilder(field="myfield", coordinates=(10.0, -20.0), radius=0.005)
    sphere = qb.find_query["$geoWithin"]["$centerSphere"]
    assert sphere[0] == [10.0, -20.0]
    assert sphere[1] == 0.005


def test_query_builder_redact_with_access_tags():
    redact = QueryBuilder.redact_with_access_tags(["tag1", "tag2"])
    assert "$redact" in redact
    cond_str = str(redact)
    assert "setIntersection" in cond_str


# --- OcaWithin ---

def test_ocawithin_query_structure():
    ow = OcaWithin("telescope_coordinates.lon_lat", (-90.0, 45.0), 0.01)
    q = ow.query
    assert "telescope_coordinates.lon_lat" in q
    assert "$geoWithin" in q["telescope_coordinates.lon_lat"]
    assert "$centerSphere" in q["telescope_coordinates.lon_lat"]["$geoWithin"]


def test_ocawithin_center_sphere_coordinates():
    ow = OcaWithin("myfield", (30.0, -60.0), 0.02)
    sphere = ow.query["myfield"]["$geoWithin"]["$centerSphere"]
    assert sphere[0] == [30.0, -60.0]
    assert sphere[1] == 0.02


def test_ocawithin_redact_static():
    redact = OcaWithin.redact_with_access_tags(["a", "b"])
    assert "$redact" in redact
    assert "setIntersection" in str(redact)


def test_ocawithin_with_arch_distance_radius():
    ad = ArchDistance(ra=180.0, dec=-30.0, arc_seconds=600.0)
    ow = OcaWithin("telescope_coordinates.lon_lat", (ad.get_ref_lon(), ad.get_ref_lat()), ad.rad_distance())
    q = ow.query
    sphere = q["telescope_coordinates.lon_lat"]["$geoWithin"]["$centerSphere"]
    expected_rad = math.radians(600.0 / 3600.0)
    assert abs(sphere[1] - expected_rad) < 1e-10
