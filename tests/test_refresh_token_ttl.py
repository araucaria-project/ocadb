"""Verifies RefreshTokenDocument has a real MongoDB TTL index on expires_at,
so expired/revoked tokens are garbage-collected by MongoDB itself rather than
accumulating forever."""
from ocadb.models.refresh_token import RefreshTokenDocument


async def test_expires_at_has_ttl_index(beanie):
    info = await RefreshTokenDocument.get_motor_collection().index_information()

    ttl_indexes = [spec for spec in info.values() if "expireAfterSeconds" in spec]
    assert len(ttl_indexes) == 1, f"expected exactly one TTL index, found: {info}"

    ttl_index = ttl_indexes[0]
    assert ttl_index["expireAfterSeconds"] == 0
    assert ttl_index["key"] == [("expires_at", 1)]
