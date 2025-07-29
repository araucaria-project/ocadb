import pytest
from pyaraucaria.lookup_objects import name_canonizator

from ocadb.models.geo import SkyCoord
from ocadb.models.object import Object

test_data = [
    ('TZ For', 'tzfor'),
    ('TZ_For', 'tzfor'),
    ('tz-for', 'tzfor'),
    ('SMC-T2CEP-14', 'smct2cep14'),
    ('TYC1396-393-1', 'tyc13963931'),
]


@pytest.mark.parametrize("names", test_data)
@pytest.mark.asyncio
async def test_canonized_name_validator(beanie, names):
    name, cname = names
    coo = SkyCoord(radec=(0, 0))
    o = Object(name=name, coo=coo)
    assert o.canonized_name == cname

@pytest.mark.asyncio
async def test_canonized_aliases(beanie):
    coo = SkyCoord(radec=(0, 0))
    aliases = [d[0] for d in test_data]
    caliases = [d[1] for d in test_data]
    o = Object(name='test_object', coo=coo, aliases=aliases)
    assert o.aliases == caliases