import pytest
from ocadb.models.geo import SkyCoord

# Sample data: pairs (RA, DEC) and expected GeoJSON coordinates conterparts (longitude, latitude)
test_data = [
    (0.0, 0.0),
    (180.0, -45.0),
    (360.0, 90.0),
    (90.0, 45.0),
    (270.0, -60.0),
    (10.0, 0.0),
    (350.0, 0.0),
]

@pytest.mark.parametrize("radec", test_data)
def test_radec_to_geojson_conversion(radec):
    sky_coord = SkyCoord(radec=radec)
    assert sky_coord.radec == (radec[0] % 360, radec[1])  # 360° == 0°
    assert -180.0 <= sky_coord._lon_lat.coordinates[0] <= 180.0
