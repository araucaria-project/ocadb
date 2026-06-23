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


def test_aggregate_first_stage_with_sort_is_sort():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["tag1"], page=1, page_size=10, sort_expr={"date_obs": -1}
    )
    assert "$sort" in pipeline[0]
    assert pipeline[0]["$sort"] == {"date_obs": -1}


def test_aggregate_redact_stage_present_without_sort():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["tag1"], page=1, page_size=10, sort_expr=None
    )
    assert "$redact" in pipeline[0]


def test_aggregate_redact_stage_present_with_sort():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["tag1"], page=1, page_size=10, sort_expr={"date_obs": -1}
    )
    assert "$redact" in pipeline[1]


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


def test_aggregate_page_1_skip_is_zero():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["tag1"], page=1, page_size=10, sort_expr=None
    )
    data = pipeline[-1]["$facet"]["data"]
    skip_stage = next(s for s in data if "$skip" in s)
    assert skip_stage["$skip"] == 0


def test_aggregate_page_2_skip_equals_page_size():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["tag1"], page=2, page_size=25, sort_expr=None
    )
    data = pipeline[-1]["$facet"]["data"]
    skip_stage = next(s for s in data if "$skip" in s)
    assert skip_stage["$skip"] == 25


def test_aggregate_limit_equals_page_size():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["tag1"], page=1, page_size=30, sort_expr=None
    )
    data = pipeline[-1]["$facet"]["data"]
    limit_stage = next(s for s in data if "$limit" in s)
    assert limit_stage["$limit"] == 30


def test_aggregate_redact_uses_set_intersection():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["a", "b"], page=1, page_size=10, sort_expr=None
    )
    redact = pipeline[0]["$redact"]
    cond_str = str(redact)
    assert "setIntersection" in cond_str
    assert "access_tags" in cond_str


def test_aggregate_redact_keep_prune_logic():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["a"], page=1, page_size=10, sort_expr=None
    )
    redact = pipeline[0]["$redact"]
    cond_str = str(redact)
    assert "KEEP" in cond_str
    assert "PRUNE" in cond_str


def test_aggregate_empty_access_tags():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=[], page=1, page_size=10, sort_expr=None
    )
    assert len(pipeline) >= 2


def test_aggregate_page_3():
    pipeline = AggregationQueryBuilder.aggregate(
        access_tags=["x"], page=3, page_size=20, sort_expr=None
    )
    data = pipeline[-1]["$facet"]["data"]
    skip_stage = next(s for s in data if "$skip" in s)
    assert skip_stage["$skip"] == 40
