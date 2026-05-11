from datetime import datetime
from typing import List, Tuple, Optional
from abc import ABC
from typing import List

from beanie.odm.operators.find import BaseFindOperator
from pydantic import BaseModel

from ocadb.models.geo import ArchDistance


class BaseFindGeospatialOperator(BaseFindOperator, ABC): ...

class MultiSearchForm(BaseModel):
    cone_search: Optional[ArchDistance] = None
    telescop: Optional[str] = None
    date_obs_from: Optional[str] = None
    date_obs_to: Optional[str] = None
    oca_jd_from: Optional[int] = None
    oca_jd_to: Optional[int] = None
    jd_from: Optional[int] = None
    jd_to: Optional[int] = None
    imagetyp: Optional[str] = None
    obstype: Optional[str] = None
    object: Optional[str] = None
    sciprog: Optional[str] = None
    filter: Optional[List[str]] = None
    exptime_from: Optional[str] = None
    exptime_to: Optional[str] = None
    pi: Optional[str] = None
    sort_expr: Optional[dict] = None

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