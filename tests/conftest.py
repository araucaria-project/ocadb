import pytest

from ocadb.database import Connection

testdb_connection_string = "mongodb://localhost:27017/test"


@pytest.fixture()
async def beanie():
    client = await Connection().ensure_connection(connection_string=testdb_connection_string)
    return client
