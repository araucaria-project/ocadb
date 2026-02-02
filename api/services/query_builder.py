from typing import List, Tuple
from abc import ABC
from typing import List

from beanie.odm.operators.find import BaseFindOperator

class BaseFindGeospatialOperator(BaseFindOperator, ABC): ...

class QueryBuilder(BaseFindOperator):
    def __init__(
        self, field, coordinates: Tuple[float, float], radius: float
    ):
        self.field = field
        self.coordinates = coordinates
        self.radius = radius

    @property
    def find_query(self):
        return {"$geoWithin": {"$centerSphere": [[self.coordinates[0], self.coordinates[1]], self.radius]}}


    @property
    def geo_query(self):
        return {
            self.field: {"$geoWithin": {"$centerSphere": [[self.coordinates[0], self.coordinates[1]], self.radius]}}
        }

    @staticmethod
    def redact_with_access_tags(access_tags):
        return {"$redact": {
            "$cond": {"if": {"$gt": [{"$size": {"$setIntersection": ["$access_tags", access_tags]}}, 0]},
                      "then": "$$KEEP", "else": "$$PRUNE"}}}