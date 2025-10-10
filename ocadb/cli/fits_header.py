"""
FITS header operations.

No data is written to the database without user confirmation.
"""
from pathlib import Path
from typing import Optional, Tuple, Annotated, List
import json
import typer

app = typer.Typer(help=__doc__)


@app.command("import")
def himport(
        file: typer.FileText
):
    """ Import header data form fits files."""
    print(f"Importing FITS header from: {file.name}")

    json_data = {}
    path = Path(file.name)

    # reserved_keywords = ['COMMENT', 'HISTORY', 'END']

    with open(path) as fits_file:
        for line in fits_file:
            try:
                line_els = line.split('=')

                header_field = line_els[0].strip()
                header_value = line_els[1].split('/')[0].strip().strip('\'')

                json_data[header_field] = header_value
            except:
                pass

    print(json.dumps(json_data))



