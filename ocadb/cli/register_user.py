"""
Register a user of OCADB.

"""
from enum import verify
from getpass import getpass
from pathlib import Path
from typing import Annotated
from ocadb.models import User, UserInDB
from api.services.database_connection import DatabaseConnection
from api.services.crypto_service import CryptoService
import typer
import asyncio


app = typer.Typer(help=__doc__)

@app.command("register")
def register_user():
    """ register user of OCADB. """
    user_username = input("Enter username: ")

    user_password = getpass("Enter password: ")

    while True:
        verify_password = getpass("Verify password: ")
        if user_password == verify_password:
            break
        else:
            print("Passwords do not match!")

    user_full_name = input("Enter full name: ")

    user_email = input("Enter email: ")

    user_access_tags = input("Enter access tags separated by ';': ").split(';')
    user_access_tags = list(filter(None, user_access_tags)) # remove possible last empty element

    hashed_password = CryptoService.get_password_hash(user_password)
    user_to_insert = UserInDB(username=user_username, hashed_password=hashed_password, email=user_email,
                              full_name=user_full_name, access_tags=user_access_tags)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(insert_user_into_db(user_to_insert))

async def insert_user_into_db(user: UserInDB):
    inserted_user = await DatabaseConnection.create_user(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        hashed_password=user.hashed_password,
        access_tags=user.access_tags
    )

    print("User " + inserted_user.username + " created.")
    print(inserted_user)


@app.command("seed")
def seed(
        file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="YAML file with users")],
        replace_tags: Annotated[bool, typer.Option(help="Replace access tags instead of adding to them")] = False,
        dry_run: Annotated[bool, typer.Option(help="Only print what would change")] = False,
):
    """Create or update users from a YAML file (araucaria_id, email, full_name, access_tags).

    Never changes passwords, moderator or disabled flags. Safe to run repeatedly.
    """
    from ocadb.cli.seed_users import parse_seed_file, seed_users

    entries, problems = parse_seed_file(file.read_text(encoding="utf-8"))
    loop = asyncio.get_event_loop()
    report = loop.run_until_complete(seed_users(entries, replace_tags=replace_tags, dry_run=dry_run))
    prefix = "[dry run] " if dry_run else ""
    for label, items in (("created", report.created), ("updated", report.updated),
                         ("unchanged", report.unchanged)):
        typer.echo(f"{prefix}{label}: {len(items)}")
        for item in items if label != "unchanged" else []:
            typer.echo(f"  {item}")
    for w in report.warnings:
        typer.echo(f"warning: {w}")
    for p in problems + report.problems:
        typer.echo(f"problem: {p}", err=True)
    if problems or report.problems:
        raise typer.Exit(code=1)

