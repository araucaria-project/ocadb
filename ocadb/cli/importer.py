"""
Imports data from various sources and formats into the OCA database.

No data is written to the database without user confirmation.
"""
from pathlib import Path
from typing import Optional, Tuple, Annotated, List

import typer

from ocadb.files.tab_all import read_tab_all

app = typer.Typer(help=__doc__)


@app.command()
def taball(
        file: Annotated[typer.FileText, typer.Option(help='File to import from. If None default TAB.ALL is used')] = None,
        objects: Annotated[List[str], typer.Argument(help='List of names (or aliases) from TAB.ALL to be imported')] = None,
):
    """ Import data form TAB.ALL alike files.

    If no file is specified, data is imported from default TAB.ALL file.
    You can optionally specify objects to import, otherwise all entries are imported."""
    print(f"Importing: {file}")

    path = None
    try:
        path = Path(file.name)
        file.close()
    except AttributeError:
        pass

    ta_objects = list(read_tab_all(path, objects))

@app.command()
def tpg(tpg_all_file: str):
    print(f"Deleting item: {tpg_all_file}")

