
from .object import Object, Periodicity, Brightness
from .geo import SkyCoord, SkyCoordPolygon
from .user import User, UserInDB
from .observation import Observation, FitsHeader

from .geo import document_models as geo_document_models
from .object import document_models as object_document_models
from .observation import document_models as observation_document_models

# User models are always available as they're core domain models
user_document_models = [UserInDB]

document_models = geo_document_models + object_document_models + user_document_models + observation_document_models