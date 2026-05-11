
from typing import List, Tuple
from abc import ABC
from typing import List

class AggregationQueryBuilder:
    @staticmethod
    def aggregate(match_query, access_tags, page, page_size, sort_expr):
        if not sort_expr:
            return [
                {
                    "$match": match_query
                },
                {
                    "$redact": {
                        "$cond": {"if": {"$gt": [{"$size": {"$setIntersection": ["$access_tags", access_tags]}}, 0]},
                              "then": "$$KEEP", "else": "$$PRUNE"}}
                },
                {
                    "$facet": {
                        "metadata": [{ "$count": 'total_count' }],
                        "data": [{ "$skip": (page - 1) * page_size }, { "$limit": page_size }],
                    },
                },
            ]
        else:
            return [
                {
                    "$match": match_query
                },
                {
                    "$sort": sort_expr
                },
                {
                    "$redact": {
                        "$cond": {"if": {"$gt": [{"$size": {"$setIntersection": ["$access_tags", access_tags]}}, 0]},
                                  "then": "$$KEEP", "else": "$$PRUNE"}}
                },
                {
                    "$facet": {
                        "metadata": [{"$count": 'total_count'}],
                        "data": [{"$skip": (page - 1) * page_size}, {"$limit": page_size}],
                    },
                },
            ]