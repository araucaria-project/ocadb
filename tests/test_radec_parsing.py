import pytest

from ocadb.models.geo import ArchDistance
from ocadb.utils.radec import parse_radec, split_radec


@pytest.mark.parametrize("combined,expected_ra,expected_dec", [
    ("161.265, -59.684", 161.265, -59.684),
    ("161.265 -59.684", 161.265, -59.684),
    ("10:45:03.6 -59:41:04", 161.265, -59.684444),
    ("10:45:03.6, -59:41:04", 161.265, -59.684444),
    ("10 45 03.6 -59 41 04", 161.265, -59.684444),
    ("10h45m03.6s -59:41:04s", 161.265, -59.684444),
    ("10 45 03.6, -59 41 04", 161.265, -59.684444),
    ("10:45:03.6 +59:41:04", 161.265, 59.684444),
    ("10:45:03.6 -59.684", 161.265, -59.684),
])
def test_parse_radec(combined, expected_ra, expected_dec):
    ra, dec = parse_radec(combined)
    assert ra == pytest.approx(expected_ra, abs=1e-3)
    assert dec == pytest.approx(expected_dec, abs=1e-3)


@pytest.mark.parametrize("combined", [
    "garbage",
    "",
    "12:34:56",
])
def test_parse_radec_invalid(combined):
    with pytest.raises(ValueError):
        parse_radec(combined)


def test_split_radec_sign_token_fallback():
    assert split_radec("10 45 03.6 -59 41 04") == ("10 45 03.6", "-59 41 04")


def test_arch_distance_from_coordinates_string():
    ad = ArchDistance(coordinates="161.265, -59.684", arc_seconds=30.0)
    assert ad.ra == pytest.approx(161.265)
    assert ad.dec == pytest.approx(-59.684)
    assert ad.arc_seconds == 30.0


def test_arch_distance_backward_compatible_with_floats():
    ad = ArchDistance(ra=161.265, dec=-59.684, arc_seconds=30.0)
    assert ad.ra == pytest.approx(161.265)
    assert ad.dec == pytest.approx(-59.684)
