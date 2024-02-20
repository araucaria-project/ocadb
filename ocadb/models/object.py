from imaplib import Literal

from beanie import Document
from pydantic import BaseModel
import pymongo


from ocadb.models.geo import SkyCoord

PeriodicityType = Literal['eb', 'puls', 'rot']

hello_t = Literal['Hello', 'Hello world']


class Periodicity(BaseModel):
    kind: PeriodicityType
    priority: int
    model: str = None
    period: float = None
    hjd0: float = None


class Object(Document):
    name: str
    coo: SkyCoord
    periodicity: list[Periodicity]

document_models = [Object]
