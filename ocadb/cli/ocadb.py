import asyncio
from typing import Annotated, Optional

import typer
from pymongo.errors import ConnectionFailure

import ocadb.cli.importer as importer
import ocadb.cli.register_user as register_user
from ocadb.database import Connection

app = typer.Typer(pretty_exceptions_enable=False)
app.add_typer(importer.app, name="import")
app.add_typer(register_user.app, name="user")

@app.callback()
def initialize(
        mongodb_url: Annotated[Optional[str], typer.Option(envvar="OCADB_MONGODB_URL", help="MongoDB connection string")] = None,
        database: Annotated[str, typer.Option(envvar="OCADB_MONGODB_DATABASE", help="Database name")] = "ocadb",
):
    """
    OCA Database CLI
    """
    app.loop = asyncio.get_event_loop()
    app.loop.run_until_complete(ainitialize(mongodb_url, database))

async def ainitialize(mongodb_url: Optional[str] = None, database: str = "ocadb"):
    """
    OCA Database CLI
    """
    conn = Connection()
    try:
        await conn.ensure_connection(mongodb_url, database)
    except ConnectionFailure as e:
        typer.echo(f"Failed to connect to database")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()