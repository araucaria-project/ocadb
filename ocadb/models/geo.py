from typing import Tuple, Literal

import pymongo
from beanie import Document, Indexed
from pydantic import BaseModel

Position = Tuple[float, float]


class Point2D(BaseModel):
    type: Literal["Point"]
    coordinates: Position


class SkyCoord(Document):
    radec: Point2D
    epoch: float = 2000.0

    class Settings:
        name = "skycoord"
        indexes = [
            [
                ("radec", pymongo.GEOSPHERE),
            ],
        ]


document_models = [SkyCoord]
