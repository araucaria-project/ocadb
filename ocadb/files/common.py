from __future__ import annotations

import re

from pyaraucaria.coordinates import ra_to_decimal, dec_to_decimal

from ocadb import models as models
from ocadb.exceptions import InsufficietData
from ocadb.models.geo import SkyCoord




def model_object_from_dict(obj: dict) -> models.Object:
    obligatory = {'name', 'ra', 'dec'}
    if not obligatory <= obj.keys():
        raise InsufficietData(f"Missing obligatory fields: {obligatory - obj.keys()}")

    # deal with coords
    ra = ra_to_decimal(obj['ra'])
    dec = dec_to_decimal(obj['dec'])
    epoch = float(obj.get('epoch', 2000))

    coo = SkyCoord(radec = (ra, dec), epoch=epoch)

    # deal with names
    name_alt = None
    name = obj.pop('hname', None)
    if name is None:
        name = obj.pop('name')
    else:
        name_alt = obj.pop('name')
    aliases = obj.pop('aliases', [])
    if name_alt is not None:
        aliases.append(name_alt)

    # deal with brightness
    filters = ['V', 'B', 'R', 'I', 'J', 'H', 'K', 'Ic']
    default_band = obj.pop('band', 'V')[0].upper()
    brightness_dict = {}
    for f in filters:
        if f in obj:
            brightness_dict[f] = float(obj.pop(f))
        elif f'm{f}' in obj:
            brightness_dict[f] = float(obj.pop(f'm{f}'))
    brightness = []
    if default_band in brightness_dict:  # just keep it first
        brightness.append(models.Brightness(band=default_band, value=brightness_dict.pop(default_band)))
    for band, value in brightness_dict.items():
        brightness.append(models.Brightness(band=band, value=value))




    o = models.Object(
        name=name,
        coo=coo,
        aliases=aliases,
        brightness=brightness,
    )
    return o
