from __future__ import annotations

from io import TextIOWrapper
from pathlib import Path
from typing import Optional, Generator

from pyaraucaria.lookup_objects import ObjectsDatabase

import ocadb.models as models
from ocadb.exceptions import InsufficietData
from ocadb.files.common import model_object_from_dict


def read_tab_all(
        tab_all_file: Optional[Path | TextIOWrapper] = None,
        objects: Optional[list[str]] = None
) -> Generator[models.Object, None, None]:

    odb = ObjectsDatabase(tab_all=tab_all_file, radec_decimal=True)

    if not objects:
        objects = odb.all_objects.keys()

    for obj_name in objects:
        obj = odb.lookup_object(obj_name)
        try:
            mobj: models.Object = model_object_from_dict(obj)
        except InsufficietData as e:
            pass
        else:
            yield mobj