"""
Register a user of OCADB.

"""
from enum import verify
from getpass import getpass
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









