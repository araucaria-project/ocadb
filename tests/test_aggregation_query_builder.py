"""Tests for AggregationQueryBuilder pipeline generation."""
import pytest
from api.services.aggregation_query_builder import AggregationQueryBuilder


def test_aggregate_without_sort_has_two_stages():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["tag1"], page=1, page_size=10, sort_expr=None
    )
    assert len(pipeline) == 2


def test_aggregate_with_sort_has_three_stages():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["tag1"], page=1, page_size=10, sort_expr={"date_obs": -1}
    )
    assert len(pipeline) == 3


def test_aggregate_access_match_is_first_stage():
    for sort_expr in (None, {"date_obs": -1}):
        pipeline = AggregationQueryBuilder.aggregate(
            access_tags=["a", "b"], page=1, page_size=10, sort_expr=sort_expr
        )
        assert pipeline[0] == {"$match": {"access_tags": {"$in": ["a", "b"]}}}


def test_aggregate_sort_follows_access_match():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["tag1"], page=1, page_size=10, sort_expr={"date_obs": -1}
    )
    assert pipeline[1] == {"$sort": {"date_obs": -1}}


def test_aggregate_has_no_redact():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["tag1"], page=1, page_size=10, sort_expr={"date_obs": -1}
    )
    assert not any("$redact" in stage for stage in pipeline)


def test_aggregate_facet_stage_last():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["tag1"], page=1, page_size=10, sort_expr=None
    )
    assert "$facet" in pipeline[-1]


def test_aggregate_facet_has_metadata_and_data():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["tag1"], page=1, page_size=10, sort_expr=None
    )
    facet = pipeline[-1]["$facet"]
    assert "metadata" in facet
    assert "data" in facet


def test_aggregate_metadata_counts():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["tag1"], page=1, page_size=10, sort_expr=None
    )
    metadata = pipeline[-1]["$facet"]["metadata"]
    assert any("$count" in stage for stage in metadata)


def test_aggregate_data_has_skip_and_limit():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["tag1"], page=1, page_size=10, sort_expr=None
    )
    data = pipeline[-1]["$facet"]["data"]
    stage_keys = [list(s.keys())[0] for s in data]
    assert "$skip" in stage_keys
    assert "$limit" in stage_keys


def test_aggregate_page_2_skip_equals_page_size():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["tag1"], page=2, page_size=25, sort_expr=None
    )
    data = pipeline[-1]["$facet"]["data"]
    skip_stage = next(s for s in data if "$skip" in s)
    assert skip_stage["$skip"] == 25


def test_aggregate_empty_access_tags_matches_nothing():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=[], page=1, page_size=10, sort_expr=None
    )
    assert pipeline[0] == {"$match": {"access_tags": {"$in": []}}}


def test_aggregate_none_access_tags_matches_nothing():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=None, page=1, page_size=10, sort_expr=None
    )
    assert pipeline[0] == {"$match": {"access_tags": {"$in": []}}}


def test_page_stage_order():
    pipeline = AggregationQueryBuilder.page(
        access_tags=["x"], page=3, page_size=20, sort_expr={"fits_header.EXPTIME": 1}
    )
    assert pipeline == [
        {"$match": {"access_tags": {"$in": ["x"]}}},
        {"$sort": {"fits_header.EXPTIME": 1, "_id": 1}},
        {"$skip": 40},
        {"$limit": 20},
    ]


def test_page_uses_default_sort_without_sort_expr():
    for sort_expr in (None, {}):
        pipeline = AggregationQueryBuilder.page(
            access_tags=["x"], page=1, page_size=10, sort_expr=sort_expr
        )
        assert pipeline[1] == {"$sort": AggregationQueryBuilder.DEFAULT_SORT}


def test_stable_sort_appends_id_in_same_direction():
    assert AggregationQueryBuilder.stable_sort({"fits_header.AIRMASS": 1}) == {"fits_header.AIRMASS": 1, "_id": 1}
    assert AggregationQueryBuilder.stable_sort({"date_obs": -1}) == {"date_obs": -1, "_id": -1}


def test_stable_sort_keeps_explicit_id_and_does_not_mutate_input():
    sort_expr = {"_id": 1}
    assert AggregationQueryBuilder.stable_sort(sort_expr) == {"_id": 1}
    sort_expr = {"date_obs": 1}
    AggregationQueryBuilder.stable_sort(sort_expr)
    assert sort_expr == {"date_obs": 1}


def test_page_appends_projection():
    pipeline = AggregationQueryBuilder.page(
        access_tags=["x"], page=1, page_size=10, sort_expr=None,
        projection=AggregationQueryBuilder.LIST_PROJECTION,
    )
    assert pipeline[-1] == {"$project": AggregationQueryBuilder.LIST_PROJECTION}


def test_list_projection_keeps_table_fields():
    projection = AggregationQueryBuilder.LIST_PROJECTION
    for field in ("obs_name", "obs_tags", "fits_header.DATE-OBS", "fits_header.OBJECT", "fits_header.EXPTIME"):
        assert projection[field] == 1
    assert "fits_header" not in projection


def test_sort_hint_maps_sortable_columns_to_compound_indexes():
    assert AggregationQueryBuilder.sort_hint(None) == "access_tags_date_obs_id"
    assert AggregationQueryBuilder.sort_hint({"date_obs": 1}) == "access_tags_date_obs_id"
    assert AggregationQueryBuilder.sort_hint({"fits_header.AIRMASS": -1}) == "access_tags_airmass_id"
    assert AggregationQueryBuilder.sort_hint({"fits_header.EXPTIME": 1}) == "access_tags_exptime_id"


def test_sort_hint_none_for_unindexed_column():
    assert AggregationQueryBuilder.sort_hint({"fits_header.FILTER": 1}) is None


def test_capped_count_limits_before_counting():
    pipeline = AggregationQueryBuilder.capped_count(access_tags=["x"], cap=100)
    assert pipeline == [
        {"$match": {"access_tags": {"$in": ["x"]}}},
        {"$limit": 101},
        {"$count": "total_count"},
    ]


def test_capped_count_default_cap():
    pipeline = AggregationQueryBuilder.capped_count(access_tags=["x"])
    assert pipeline[1] == {"$limit": AggregationQueryBuilder.COUNT_CAP + 1}
