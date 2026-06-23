"""Tests for ocadb.files.common — model_object_from_dict."""
import pytest
from ocadb.files.common import model_object_from_dict
from ocadb.exceptions import InsufficietData
from ocadb.models import Object


# --- Happy path ---

def test_basic_object_creation():
    obj = model_object_from_dict({"name": "TZ For", "ra": "03:14:00", "dec": "-28:00:00"})
    assert obj.name == "TZ For"
    assert isinstance(obj, Object)


def test_canonized_name_set():
    obj = model_object_from_dict({"name": "TZ For", "ra": "03:14:00", "dec": "-28:00:00"})
    assert obj.canonized_name == "tzfor"


def test_decimal_ra_dec():
    obj = model_object_from_dict({"name": "TestObj", "ra": 180.0, "dec": -30.0})
    assert abs(obj.coo.radec[0] - 180.0) < 0.1
    assert abs(obj.coo.radec[1] - (-30.0)) < 0.1


def test_aliases_included():
    obj = model_object_from_dict({
        "name": "TZ For",
        "ra": "03:14:00",
        "dec": "-28:00:00",
        "aliases": ["TZ Fornacis", "V* TZ For"],
    })
    assert len(obj.aliases) == 2


def test_aliases_canonized():
    obj = model_object_from_dict({
        "name": "TZ For",
        "ra": "03:14:00",
        "dec": "-28:00:00",
        "aliases": ["TZ Fornacis"],
    })
    assert "tzfornacis" in obj.aliases


def test_brightness_v_band():
    obj = model_object_from_dict({"name": "TestStar", "ra": 0.0, "dec": 0.0, "V": 12.5})
    b = next((b for b in obj.brightness if b.band == "V"), None)
    assert b is not None
    assert abs(b.value - 12.5) < 0.001


def test_brightness_multiple_bands():
    obj = model_object_from_dict({"name": "TestStar", "ra": 0.0, "dec": 0.0, "V": 12.5, "B": 13.0, "R": 11.8})
    bands = {b.band for b in obj.brightness}
    assert "V" in bands
    assert "B" in bands
    assert "R" in bands


def test_brightness_mband_notation():
    obj = model_object_from_dict({"name": "TestStar", "ra": 0.0, "dec": 0.0, "mV": 14.2})
    b = next((b for b in obj.brightness if b.band == "V"), None)
    assert b is not None
    assert abs(b.value - 14.2) < 0.001


def test_hname_becomes_primary_name():
    obj = model_object_from_dict({
        "hname": "Preferred Name",
        "name": "Alternate Name",
        "ra": 0.0,
        "dec": 0.0,
    })
    assert obj.name == "Preferred Name"


def test_hname_alternate_becomes_alias():
    obj = model_object_from_dict({
        "hname": "Preferred Name",
        "name": "Alternate Name",
        "ra": 0.0,
        "dec": 0.0,
    })
    canonized_alt = "alternatename"
    assert canonized_alt in obj.aliases


def test_epoch_default():
    obj = model_object_from_dict({"name": "TestStar", "ra": 0.0, "dec": 0.0})
    assert obj.coo.epoch == 2000.0


def test_epoch_custom():
    obj = model_object_from_dict({"name": "TestStar", "ra": 0.0, "dec": 0.0, "epoch": 1950})
    assert obj.coo.epoch == 1950.0


# --- Missing required fields ---

def test_missing_name_raises():
    with pytest.raises(InsufficietData):
        model_object_from_dict({"ra": "00:00:00", "dec": "00:00:00"})


def test_missing_ra_raises():
    with pytest.raises(InsufficietData):
        model_object_from_dict({"name": "TestStar", "dec": "00:00:00"})


def test_missing_dec_raises():
    with pytest.raises(InsufficietData):
        model_object_from_dict({"name": "TestStar", "ra": "00:00:00"})


def test_missing_all_required_raises():
    with pytest.raises(InsufficietData):
        model_object_from_dict({})


def test_error_message_mentions_missing_field():
    with pytest.raises(InsufficietData) as exc:
        model_object_from_dict({"name": "Star"})
    assert "ra" in str(exc.value).lower() or "dec" in str(exc.value).lower()


# --- Default band ---

def test_default_band_v():
    obj = model_object_from_dict({"name": "TestStar", "ra": 0.0, "dec": 0.0, "V": 10.0})
    assert obj.brightness[0].band == "V"


def test_no_brightness_when_none_provided():
    obj = model_object_from_dict({"name": "TestStar", "ra": 0.0, "dec": 0.0})
    assert obj.brightness == []
