
from typing import List, Tuple
from abc import ABC
from typing import List

from beanie.odm.operators.find import BaseFindOperator



# [{ "$match": {"telescope_coordinates.lon_lat": {"$geoWithin": { "$centerSphere": [ [ -85, -12 ], 0.5 ] }}}},
#   { "$redact": {"$cond": {"if": {"$gt": [{"$size": {"$setIntersection": ["$access_tags", ['DW936_BV']]}}, 0]},"then": "$$KEEP", "else": "$$PRUNE"}}}]

class BaseFindGeospatialOperator(BaseFindOperator, ABC): ...

class OcaWithin(BaseFindGeospatialOperator):
    def __init__(
        self, field, coordinates: Tuple[float, float], radius: float
    ):
        self.field = field
        self.coordinates = coordinates
        self.radius = radius

    @property
    def query(self):
        return {
            self.field: {
                "$geoWithin": {
                    "$centerSphere": [
                                [self.coordinates[0], self.coordinates[1]],
                                self.radius
                    ]
                }
            }
        }
