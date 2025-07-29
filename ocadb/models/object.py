from typing import Literal, Optional

from beanie import Document
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from pyaraucaria.lookup_objects import name_canonizator


from ocadb.models.geo import SkyCoord, SkyCoordPolygon

PeriodicityType = Literal['eb', 'puls', 'rot', 'other', 'unknown']


class Periodicity(BaseModel):
    kind: PeriodicityType
    priority: int
    model: Optional[str] = None
    period: Optional[float] = None
    hjd0: Optional[float] = None

class Brightness(BaseModel):
    band: str
    value: float

class Object(Document):
    name: str
    canonized_name: str = ''
    aliases: list[str] = []

    brightness: list[Brightness] = []
    coo: SkyCoord
    area: Optional[SkyCoordPolygon] = None
    periodicity: list[Periodicity] = []
    parent_object_id: Optional[str] = None

    class Config:
        extra = 'allow'

    @model_validator(mode='after')
    def canonized_name_validator(self):
        """Sets canonized_name field to canonized name of the object."""
        self.canonized_name = self.name_canonizator(self.name)
        return self

    @field_validator('aliases')
    @classmethod
    def canonize_aliases(cls, aliases: list[str]) -> list[str]:
        """Canonizes aliases, as they are stored in this form in the database."""
        return [cls.name_canonizator(a) for a in aliases]


    @staticmethod
    def name_canonizator(name: str) -> str:
        """Name canonization by removing any non-alphanumeric characters and converting to lower case"""
        return name_canonizator(name)


document_models = [Object]


class BandRequest(BaseModel):
    band: str
    sn: float


class ObservationParameters(Document):
    telescope_id: str
    objects_ids: list[str]
    requested_bands: list[BandRequest]
    priority: int

class SceduledObservationParameters(Document):
    objects_ids: list[str]
    squence: str
    priority: int
    enabled: bool
    start_time: float
    end_time: float

class Project(Document):
    name: str
    pi_id: str
    description: Optional[str]
    objects_ids: list[str]
    priority: int

    observation_parameters: ObservationParameters

