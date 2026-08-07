"""Tests for Observation model validators and domain logic."""
import pytest
from datetime import datetime

from ocadb.models import Observation, FitsHeader
from ocadb.models.geo import SkyCoord
from tests.conftest import make_fits_header


# --- store_skycoord validator ---

async def test_store_skycoord_uses_ra_dec_when_present(beanie):
    obs = Observation(
        obs_name="test_skycoord_radec",
        fits_header=make_fits_header(**{"RA": 90.0, "DEC": 45.0}),
    )
    assert obs.telescope_coordinates is not None
    ra, dec = obs.telescope_coordinates.radec
    assert abs(ra - 90.0) < 0.001
    assert abs(dec - 45.0) < 0.001


async def test_store_skycoord_falls_back_to_ra_tel(beanie):
    header = make_fits_header(**{"RA": None, "DEC": None, "RA_TEL": 270.0, "DEC_TEL": -60.0})
    obs = Observation(obs_name="test_skycoord_tel", fits_header=header)
    ra, dec = obs.telescope_coordinates.radec
    assert abs(ra - 270.0) < 0.001
    assert abs(dec - (-60.0)) < 0.001


async def test_store_skycoord_geojson_longitude_in_range(beanie):
    obs = Observation(obs_name="test_lon_range", fits_header=make_fits_header(**{"RA": 350.0, "DEC": 10.0}))
    lon = obs.telescope_coordinates.lon_lat.coordinates[0]
    assert -180.0 <= lon <= 180.0


# --- store_canonical_object validator ---

async def test_store_canonical_object_strips_spaces(beanie):
    obs = Observation(obs_name="test_canon_space", fits_header=make_fits_header(**{"OBJECT": "TZ For"}))
    assert obs.canonized_object_name == "tzfor"


async def test_store_canonical_object_strips_special_chars(beanie):
    obs = Observation(obs_name="test_canon_dash", fits_header=make_fits_header(**{"OBJECT": "SMC-T2CEP-14"}))
    assert obs.canonized_object_name == "smct2cep14"


async def test_store_canonical_object_lowercases(beanie):
    obs = Observation(obs_name="test_canon_case", fits_header=make_fits_header(**{"OBJECT": "V0441 CYG"}))
    assert obs.canonized_object_name == "v0441cyg"


async def test_store_canonical_object_raises_when_object_none(beanie):
    """name_canonizator(None) raises TypeError — OBJECT field must not be None."""
    import pytest
    with pytest.raises(TypeError):
        Observation(obs_name="test_canon_none", fits_header=make_fits_header(**{"OBJECT": None}))


# --- store_obs_date validator ---

async def test_store_obs_date_iso_format(beanie):
    obs = Observation(
        obs_name="test_date_iso",
        fits_header=make_fits_header(**{"DATE-OBS": "2024-03-21T14:25:00"}),
    )
    assert isinstance(obs.date_obs, datetime)
    assert obs.date_obs.year == 2024
    assert obs.date_obs.month == 3
    assert obs.date_obs.day == 21


async def test_store_obs_date_with_timezone(beanie):
    obs = Observation(
        obs_name="test_date_tz",
        fits_header=make_fits_header(**{"DATE-OBS": "2024-06-01T22:00:00+00:00"}),
    )
    assert isinstance(obs.date_obs, datetime)
    assert obs.date_obs.year == 2024


async def test_store_obs_date_with_fractional_seconds(beanie):
    obs = Observation(
        obs_name="test_date_frac",
        fits_header=make_fits_header(**{"DATE-OBS": "2024-12-31T23:59:59.999"}),
    )
    assert isinstance(obs.date_obs, datetime)
    assert obs.date_obs.year == 2024


# --- store_tags validator ---

async def test_store_tags_includes_instrume(beanie):
    obs = Observation(
        obs_name="test_tags_instrume",
        fits_header=make_fits_header(**{"INSTRUME": "SBIG-CAM"}),
    )
    assert "SBIG-CAM" in obs.access_tags


async def test_store_tags_includes_origin(beanie):
    obs = Observation(
        obs_name="test_tags_origin",
        fits_header=make_fits_header(**{"ORIGIN": "OCA"}),
    )
    assert "OCA" in obs.access_tags


async def test_store_tags_includes_pi(beanie):
    obs = Observation(
        obs_name="test_tags_pi",
        fits_header=make_fits_header(**{"PI": "smith"}),
    )
    assert "smith" in obs.access_tags


async def test_store_tags_includes_calib_obstype(beanie):
    obs = Observation(
        obs_name="test_tags_calib",
        fits_header=make_fits_header(**{"OBSTYPE": "calib"}),
    )
    assert "calib" in obs.access_tags


async def test_store_tags_excludes_science_obstype(beanie):
    obs = Observation(
        obs_name="test_tags_sci",
        fits_header=make_fits_header(**{"OBSTYPE": "science"}),
    )
    assert "science" not in obs.access_tags


async def test_store_tags_empty_when_no_fields(beanie):
    obs = Observation(
        obs_name="test_tags_empty",
        fits_header=make_fits_header(**{"INSTRUME": None, "ORIGIN": None, "PI": None, "OBSTYPE": "science"}),
    )
    assert obs.access_tags == []


# --- store_oca_jd validator ---

async def test_store_oca_jd_modulo_10000(beanie):
    obs = Observation(
        obs_name="test_oca_jd",
        fits_header=make_fits_header(**{"JD": 2460320.5}),
    )
    assert obs.oca_jd == 2460320 % 10000


async def test_store_oca_jd_none_when_jd_missing(beanie):
    obs = Observation(
        obs_name="test_oca_jd_none",
        fits_header=make_fits_header(**{"JD": None}),
    )
    assert obs.oca_jd is None


# --- store_file method ---

async def test_store_file_adds_file_to_observation(beanie):
    from ocadb.models.file import FITSFile, FileClassification
    from tests.conftest import make_storage_status
    obs = Observation(obs_name="test_store_file", fits_header=make_fits_header())
    fits_file = FITSFile(
        filename="test.fits",
        file_class=FileClassification.RAW,
        obs_name="test_store_file",
        file_status=make_storage_status(),
    )
    await obs.store_file(fits_file)
    assert fits_file in obs.files
    assert FileClassification.RAW in obs.filetypes


# --- adopt_header_if_precedent / ZDF-wins-over-RAW priority ---

async def test_raw_then_zdf_ends_with_zdf_header(beanie):
    """RAW arrives first (no header recorded yet), then ZDF arrives — ZDF must win."""
    from ocadb.models.file import FileClassification
    obs = Observation(obs_name="test_priority_raw_then_zdf", fits_header=make_fits_header(**{"TELESCOP": "raw-scope"}))
    assert obs.fits_header_source is None

    adopted = obs.adopt_header_if_precedent(FileClassification.RAW, make_fits_header(**{"TELESCOP": "raw-scope"}))
    assert adopted is True
    assert obs.fits_header_source == FileClassification.RAW
    assert obs.fits_header.TELESCOP == "raw-scope"

    adopted = obs.adopt_header_if_precedent(FileClassification.ZDF, make_fits_header(**{"TELESCOP": "zdf-scope"}))
    assert adopted is True
    assert obs.fits_header_source == FileClassification.ZDF
    assert obs.fits_header.TELESCOP == "zdf-scope"


async def test_zdf_then_raw_keeps_zdf_header(beanie):
    """ZDF arrives first, then a later RAW upload must NOT clobber it."""
    from ocadb.models.file import FileClassification
    obs = Observation(obs_name="test_priority_zdf_then_raw", fits_header=make_fits_header(**{"TELESCOP": "initial"}))

    adopted = obs.adopt_header_if_precedent(FileClassification.ZDF, make_fits_header(**{"TELESCOP": "zdf-scope"}))
    assert adopted is True
    assert obs.fits_header_source == FileClassification.ZDF

    adopted = obs.adopt_header_if_precedent(FileClassification.RAW, make_fits_header(**{"TELESCOP": "raw-scope"}))
    assert adopted is False
    assert obs.fits_header_source == FileClassification.ZDF
    assert obs.fits_header.TELESCOP == "zdf-scope"


async def test_adopt_header_none_is_noop(beanie):
    from ocadb.models.file import FileClassification
    obs = Observation(obs_name="test_priority_none", fits_header=make_fits_header(**{"TELESCOP": "initial"}))
    adopted = obs.adopt_header_if_precedent(FileClassification.ZDF, None)
    assert adopted is False
    assert obs.fits_header.TELESCOP == "initial"


async def test_store_file_adopts_header_via_fits_file(beanie):
    """store_file should adopt fits_file's own header when no explicit header is passed."""
    from ocadb.models.file import FITSFile, FileClassification
    from tests.conftest import make_storage_status
    obs = Observation(obs_name="test_store_file_header", fits_header=make_fits_header(**{"TELESCOP": "initial"}))
    fits_file = FITSFile(
        filename="test_zdf.fits",
        file_class=FileClassification.ZDF,
        obs_name="test_store_file_header",
        file_status=make_storage_status(),
        fits_header=make_fits_header(**{"TELESCOP": "zdf-scope"}),
    )
    await obs.store_file(fits_file)
    assert obs.fits_header.TELESCOP == "zdf-scope"
    assert obs.fits_header_source == FileClassification.ZDF


# --- persistence ---

async def test_observation_insert_and_find(beanie):
    obs = Observation(obs_name="test_persist_001", fits_header=make_fits_header())
    await obs.insert()
    found = await Observation.find_one(Observation.obs_name == "test_persist_001")
    assert found is not None
    assert found.obs_name == "test_persist_001"


async def test_observation_unique_obs_name(beanie):
    from pymongo.errors import DuplicateKeyError
    obs1 = Observation(obs_name="duplicate_obs", fits_header=make_fits_header())
    await obs1.insert()
    obs2 = Observation(obs_name="duplicate_obs", fits_header=make_fits_header())
    with pytest.raises(DuplicateKeyError):
        await obs2.insert()


async def test_observation_canonized_name_persisted(beanie):
    obs = Observation(obs_name="test_persist_canon", fits_header=make_fits_header(**{"OBJECT": "Beta Lyr"}))
    await obs.insert()
    found = await Observation.find_one(Observation.obs_name == "test_persist_canon")
    assert found.canonized_object_name == "betalyr"


async def test_observation_date_obs_persisted(beanie):
    obs = Observation(obs_name="test_persist_date", fits_header=make_fits_header(**{"DATE-OBS": "2023-07-04T10:00:00"}))
    await obs.insert()
    found = await Observation.find_one(Observation.obs_name == "test_persist_date")
    assert found.date_obs.year == 2023
    assert found.date_obs.month == 7


async def test_observation_metadata_update(beanie):
    obs = Observation(obs_name="test_meta_update", fits_header=make_fits_header())
    await obs.insert()
    obs.store_metadata({"quality": "good", "snr": 42.0})
    assert obs.metadata["quality"] == "good"
    assert "metadata" in obs.obs_tags


async def test_observation_fits_header_dict_coercion(beanie):
    """Observation.__init__ re-assigns fits_header from kwargs after super().__init__(),
    so the dict is NOT coerced to FitsHeader on the Python object — validators work
    on the super().__init__() copy but the raw dict is then stored back. This is a
    known quirk: always pass FitsHeader instances, not dicts, to avoid surprising behavior."""
    header_dict = {
        "DATE-OBS": "2024-05-01T12:00:00",
        "RA": 60.0,
        "DEC": 20.0,
        "OBJECT": "V Sge",
    }
    obs = Observation(obs_name="test_dict_coerce", fits_header=header_dict)
    # The validators run on a temporary copy, then __init__ writes the raw dict back
    assert obs.canonized_object_name == "vsge"  # validator DID run (on the temp copy)
    assert isinstance(obs.date_obs, datetime)     # validator DID run
