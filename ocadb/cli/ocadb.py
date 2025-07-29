import asyncio

import typer
from pymongo.errors import ConnectionFailure

import ocadb.cli.importer as importer
from ocadb.database import Connection

app = typer.Typer(pretty_exceptions_enable=False)
app.add_typer(importer.app, name="import")

@app.callback()
def initialize():
    """
    OCA Database CLI
    """
    app.loop = asyncio.get_event_loop()
    app.loop.run_until_complete(ainitialize())

async def ainitialize():
    """
    OCA Database CLI
    """
    conn = Connection()
    try:
        await conn.ensure_connection()
    except ConnectionFailure as e:
        typer.echo(f"Failed to connect to database")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()