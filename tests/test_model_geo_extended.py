"""Extended geo model tests: ArchDistance, SkyCoord edge cases, roundtrip accuracy."""
import math
import pytest
from ocadb.models.geo import SkyCoord, ArchDistance, GeoSearchLocationDistance


# --- SkyCoord edge cases ---

def test_skycoord_ra_zero():
    sc = SkyCoord(radec=(0.0, 0.0))
    ra, dec = sc.radec
    assert abs(ra) < 0.001
    assert abs(dec) < 0.001


def test_skycoord_ra_360_equals_ra_0():
    sc360 = SkyCoord(radec=(360.0, 0.0))
    sc0 = SkyCoord(radec=(0.0, 0.0))
    assert sc360.lon_lat.coordinates == sc0.lon_lat.coordinates


def test_skycoord_north_pole():
    sc = SkyCoord(radec=(0.0, 90.0))
    assert sc.lon_lat.coordinates[1] == 90.0


def test_skycoord_south_pole():
    sc = SkyCoord(radec=(0.0, -90.0))
    assert sc.lon_lat.coordinates[1] == -90.0


def test_skycoord_longitude_always_in_range():
    for ra in [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0, 359.9]:
        sc = SkyCoord(radec=(ra, 0.0))
        lon = sc.lon_lat.coordinates[0]
        assert -180.0 <= lon <= 180.0, f"RA={ra} gave longitude={lon}"


def test_skycoord_radec_roundtrip():
    for ra in [10.0, 90.0, 180.0, 270.0, 350.0]:
        for dec in [-80.0, -45.0, 0.0, 45.0, 80.0]:
            sc = SkyCoord(radec=(ra, dec))
            back_ra, back_dec = sc.radec
            assert abs(back_ra - ra) < 0.001, f"RA roundtrip failed: {ra} -> {back_ra}"
            assert abs(back_dec - dec) < 0.001, f"DEC roundtrip failed: {dec} -> {back_dec}"


def test_skycoord_radec_setter():
    sc = SkyCoord(radec=(0.0, 0.0))
    sc.radec = (120.0, 30.0)
    ra, dec = sc.radec
    assert abs(ra - 120.0) < 0.001
    assert abs(dec - 30.0) < 0.001


def test_skycoord_epoch_default():
    sc = SkyCoord(radec=(0.0, 0.0))
    assert sc.epoch == 2000.0


def test_skycoord_custom_epoch():
    sc = SkyCoord(radec=(0.0, 0.0), epoch=1950.0)
    assert sc.epoch == 1950.0


# --- ArchDistance ---

def test_archdistance_construction():
    ad = ArchDistance(ra=180.0, dec=-30.0, arc_seconds=3600.0)
    assert ad.ra == 180.0
    assert ad.dec == -30.0
    assert ad.arc_seconds == 3600.0


def test_archdistance_rad_distance_1_degree():
    ad = ArchDistance(ra=0.0, dec=0.0, arc_seconds=3600.0)
    expected = math.radians(1.0)
    assert abs(ad.rad_distance() - expected) < 1e-10


def test_archdistance_rad_distance_60_arcseconds():
    ad = ArchDistance(ra=0.0, dec=0.0, arc_seconds=60.0)
    expected = math.radians(60.0 / 3600.0)
    assert abs(ad.rad_distance() - expected) < 1e-10


def test_archdistance_rad_distance_zero():
    ad = ArchDistance(ra=0.0, dec=0.0, arc_seconds=0.0)
    assert ad.rad_distance() == 0.0


def test_archdistance_get_ref_lon():
    ad = ArchDistance(ra=270.0, dec=0.0, arc_seconds=0.0)
    lon = ad.get_ref_lon()
    assert -180.0 <= lon <= 180.0


def test_archdistance_get_ref_lat():
    ad = ArchDistance(ra=0.0, dec=-45.0, arc_seconds=0.0)
    assert ad.get_ref_lat() == -45.0


def test_archdistance_large_radius():
    ad = ArchDistance(ra=180.0, dec=0.0, arc_seconds=18000.0)
    expected = math.radians(5.0)
    assert abs(ad.rad_distance() - expected) < 1e-10


@pytest.mark.parametrize("arcsec,expected_rad", [
    (3600.0, math.pi / 180.0),
    (1800.0, math.pi / 360.0),
    (7200.0, math.pi / 90.0),
])
def test_archdistance_rad_distance_parametrized(arcsec, expected_rad):
    ad = ArchDistance(ra=0.0, dec=0.0, arc_seconds=arcsec)
    assert abs(ad.rad_distance() - expected_rad) < 1e-10


# --- GeoSearchLocationDistance ---

def test_geo_search_location_distance():
    sc = SkyCoord(radec=(180.0, -30.0))
    ad = ArchDistance(ra=180.0, dec=-30.0, arc_seconds=600.0)
    gld = GeoSearchLocationDistance(sky_coord=sc, sky_distance=ad)
    assert gld.sky_coord is not None
    assert gld.sky_distance.arc_seconds == 600.0


def test_geo_search_location_distance_optional_fields():
    gld = GeoSearchLocationDistance(sky_coord=None, sky_distance=None)
    assert gld.sky_coord is None
    assert gld.sky_distance is None
