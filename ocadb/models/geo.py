from typing import Tuple, Literal

import pymongo
from beanie import Document, Indexed
from pydantic import BaseModel, field_validator



class Point2D(BaseModel):
    """GeoJSON Point 2D geometry object"""
    type: Literal["Point"] = "Point"
    coordinates: Tuple[float, float]  # (-180, 180) for longitude!


class SkyCoord(BaseModel):
    _lon_lat: Point2D  # internal and database representation (-180, 180) for longitude
    epoch: float = 2000.0

    def __init__(self, **kwargs):
        radec = kwargs.pop('radec', None)
        super().__init__(**kwargs)
        if radec is not None:
            self.radec = radec
    @property
    def radec(self) -> Tuple[float, float]:
        if self._lon_lat:
            longitude, latitude = self._lon_lat.coordinates
            ra = (longitude + 360) % 360
            dec = latitude
            return ra, dec
        return (0.0, 0.0)  # Domyślne wartości lub obsługa błędów

    @radec.setter
    def radec(self, value: Tuple[float, float]):
        ra, dec = value
        longitude = (ra + 180.0) % 360 - 180
        self._lon_lat = Point2D(coordinates=(longitude, dec))


    # class Settings:
    #     name = "skycoord"
    #     indexes = [
    #         [
    #             ("radec", pymongo.GEOSPHERE),
    #         ],
    #     ]



class Polygon2D(BaseModel):
    type: Literal["Polygon"]
    coordinates: list[Tuple[float, float]]

class SkyCoordPolygon(BaseModel):
    radec: Polygon2D
    epoch: float = 2000.0


document_models = []
