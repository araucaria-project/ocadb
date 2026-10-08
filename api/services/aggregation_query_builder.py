class AggregationQueryBuilder:
    # Exact counts over a large unfiltered result set are O(collection size); above this
    # the API reports the count as capped and the UI shows "10,000+".
    COUNT_CAP = 10_000

    # Must match the {access_tags, date_obs, _id} compound index on Observation, so the
    # default listing is served straight from the index instead of a blocking sort.
    DEFAULT_SORT = {"date_obs": -1, "_id": -1}

    # Fields the results table actually renders. The full document (complete FITS header,
    # coordinates, files, ...) is fetched by id when an observation is opened.
    LIST_PROJECTION = {
        "obs_name": 1,
        "obs_tags": 1,
        "oca_jd": 1,
        "date_obs": 1,
        "metadata": 1,
        "created_at": 1,
        "updated_at": 1,
        **{f"fits_header.{key}": 1 for key in (
            "DATE-OBS", "OBJECT", "TELESCOP", "IMAGETYP", "OBSTYPE", "FILTER",
            "EXPTIME", "AIRMASS", "RA", "DEC", "PI", "SCIPROG",
        )},
    }

    @staticmethod
    def match_access_tags(access_tags):
        # Equivalent to the former $redact/$setIntersection check, but a plain $match can
        # use the access_tags index instead of evaluating an expression on every document.
        return {"$match": {"access_tags": {"$in": access_tags or []}}}

    @staticmethod
    def aggregate(access_tags, page, page_size, sort_expr):
        pipeline = [AggregationQueryBuilder.match_access_tags(access_tags)]
        if sort_expr:
            pipeline.append({"$sort": sort_expr})
        pipeline.append({
            "$facet": {
                "metadata": [{"$count": 'total_count'}],
                "data": [{"$skip": (page - 1) * page_size}, {"$limit": page_size}],
            },
        })
        return pipeline

    @staticmethod
    def stable_sort(sort_expr):
        # Without a unique tie-breaker, documents sharing a sort value (e.g. EXPTIME=30) come
        # back in an arbitrary order per query, so skip/limit pages repeat and skip rows.
        # _id runs in the same direction as the primary key so the {access_tags, <key>, _id}
        # indexes on Observation can serve the sort.
        sort = dict(sort_expr or AggregationQueryBuilder.DEFAULT_SORT)
        sort.setdefault("_id", next(iter(sort.values())))
        return sort

    @staticmethod
    def page(access_tags, page, page_size, sort_expr, projection=None):
        pipeline = [
            AggregationQueryBuilder.match_access_tags(access_tags),
            {"$sort": AggregationQueryBuilder.stable_sort(sort_expr)},
            {"$skip": (page - 1) * page_size},
            {"$limit": page_size},
        ]
        if projection:
            pipeline.append({"$project": projection})
        return pipeline

    @staticmethod
    def capped_count(access_tags, cap=COUNT_CAP):
        # $limit before $count stops the scan after cap + 1 matches; the extra one tells
        # "exactly cap" apart from "more than cap".
        return [
            AggregationQueryBuilder.match_access_tags(access_tags),
            {"$limit": cap + 1},
            {"$count": "total_count"},
        ]
