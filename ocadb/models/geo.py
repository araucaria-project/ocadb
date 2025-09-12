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
        if radec is not None:
            lonlat = self._radec_to_lonlat(radec)
            kwargs['_lon_lat'] = Point2D(coordinates=lonlat)
        super().__init__(**kwargs)

    @property
    def radec(self) -> Tuple[float, float]:
        if self._lon_lat:
            return self._lonlat_to_radec(self._lon_lat.coordinates)
        return (0.0, 0.0)  # default value if _lon_lat is not set

    @radec.setter
    def radec(self, value: Tuple[float, float]):
        lonlat = self._radec_to_lonlat(value)
        self._lon_lat = Point2D(coordinates=lonlat)


    @staticmethod
    def _lonlat_to_radec(lonlat: Tuple[float, float]) -> Tuple[float, float]:
        longitude, latitude = lonlat
        ra = (longitude + 360.0) % 360
        return ra, latitude

    @staticmethod
    def _radec_to_lonlat(radec: Tuple[float, float]) -> Tuple[float, float]:
        ra, dec = radec
        longitude = (ra + 180.0) % 360 - 180
        return longitude, dec



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
