import math
from typing import Tuple, Literal, Optional

import pymongo
from beanie import Document, Indexed
from pydantic import BaseModel, Field, field_validator

class Point2D(BaseModel):
    """GeoJSON Point 2D geometry object"""
    type: Literal["Point"] = "Point"
    coordinates: Tuple[float, float]  # (-180, 180) for longitude!


class SkyCoord(BaseModel):
    lon_lat: Point2D  # internal and database representation (-180, 180) for longitude
    epoch: float = 2000.0

    def __init__(self, **kwargs):
        radec = kwargs.pop('radec', None)
        if radec is not None:
            lonlat = self._radec_to_lonlat(radec)
            kwargs['lon_lat'] = Point2D(coordinates=lonlat)
        super().__init__(**kwargs)

    @property
    def radec(self) -> Tuple[float, float]:
        if self.lon_lat:
            return self._lonlat_to_radec(self.lon_lat.coordinates)
        return (0.0, 0.0)  # default value if _lon_lat is not set

    @radec.setter
    def radec(self, value: Tuple[float, float]):
        lonlat = self._radec_to_lonlat(value)
        self.lon_lat = Point2D(coordinates=lonlat)


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

class ArchDistance(BaseModel):
    ra: float = 0.0
    dec: float = 0.0
    arc_degrees: float = 0.0
    arc_minutes: float = 0.0
    arc_seconds: float = 0.0

    # internal representations
    _sky_coord: SkyCoord = SkyCoord(radec=(0.0, 0.0))
    _degrees: float = 0.0
    _geo_meters: float = 0.0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # pop the corresponding args
        self.ra = kwargs.pop('ra', 0.0)
        self.dec = kwargs.pop('dec', 0.0)
        self.arc_degrees = kwargs.pop('arc_degrees', 0.0)
        self.arc_minutes = kwargs.pop('arc_minutes', 0.0)
        self.arc_seconds = kwargs.pop('arc_seconds', 0.0)

        self._sky_coord = SkyCoord(radec=(self.ra, self.dec))
        self.geo_meters()

    def geo_meters(self) -> float:
        # compute the internal degree representation
        self._degrees = self.arc_degrees + (self.arc_minutes / 60.0) + (self.arc_seconds / 36000.0)

        # compute the corresponding internal distance in meters at the surface
        rad_to_km = 6378.1
        deg_to_rad = math.pi/180.0
        # equat_circ = 40075704.0  # earths circumference at equator
        self._geo_meters = self._degrees * deg_to_rad * rad_to_km * 1000 # get meters out of degrees, ref https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2d/calculate-distances/
        return self._geo_meters

    def get_ref_lon(self) -> float:
        return self._sky_coord.lon_lat.coordinates[0]

    def get_ref_lat(self) -> float:
        return self._sky_coord.lon_lat.coordinates[1]

class GeoSearchLocationDistance(BaseModel):
    """SkyCoord Point with distance object"""
    sky_coord: Optional[SkyCoord]
    sky_distance: Optional[ArchDistance]


document_models = []
