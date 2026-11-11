"""`ocadb user seed`: idempotent upsert of araucarians from YAML."""
from ocadb.cli.seed_users import parse_seed_file, seed_users
from api.services.database_connection import DatabaseConnection
from api.services.crypto_service import CryptoService

SEED = """
users:
  - araucaria_id: jkowalski
    email: JKowalski@CAMK.edu.pl
    full_name: Jan Kowalski
    access_tags: [CAMK PAN]
  - araucaria_id: testuser
    email: test@example.com
    full_name: Test User Renamed
    access_tags: [NEW-TAG]
  - username: noemail
    full_name: No Email
"""


async def test_parse_seed_file():
    entries, problems = parse_seed_file(SEED)
    assert problems == []
    assert [e.araucaria_id for e in entries] == ["jkowalski", "testuser", "noemail"]
    assert entries[0].email == "jkowalski@camk.edu.pl"


async def test_parse_seed_file_allows_blank_fields():
    entries, problems = parse_seed_file("- araucaria_id: a\n  email: a@b.c\n  full_name:\n  access_tags:\n")
    assert problems == []
    assert entries[0].access_tags == [] and entries[0].full_name is None


async def test_parse_seed_file_reports_bad_entries():
    entries, problems = parse_seed_file("- araucaria_id: a\n- araucaria_id: a\n- email: x@y.z\n")
    assert len(entries) == 1
    assert len(problems) == 2


async def test_seed_creates_and_updates(regular_user):
    entries, _ = parse_seed_file(SEED)
    report = await seed_users(entries)
    assert report.created == ["jkowalski", "noemail"]
    assert report.updated == ["testuser (full_name, access_tags)"]
    assert any("noemail" in w for w in report.warnings)

    new = await DatabaseConnection.get_user("jkowalski")
    assert new.hashed_password is None
    assert new.access_tags == ["CAMK PAN"]

    existing = await DatabaseConnection.get_user("testuser")
    assert CryptoService.verify_password("testpass123", existing.hashed_password)
    assert existing.full_name == "Test User Renamed"
    assert existing.access_tags == ["TEST-CAM", "AKOND", "testpi", "NEW-TAG"]


async def test_seed_is_idempotent(regular_user):
    entries, _ = parse_seed_file(SEED)
    await seed_users(entries)
    report = await seed_users(entries)
    assert report.created == [] and report.updated == []
    assert sorted(report.unchanged) == ["jkowalski", "noemail", "testuser"]


async def test_seed_replace_tags(regular_user):
    entries, _ = parse_seed_file(SEED)
    await seed_users(entries, replace_tags=True)
    assert (await DatabaseConnection.get_user("testuser")).access_tags == ["NEW-TAG"]


async def test_seed_dry_run_changes_nothing(regular_user):
    entries, _ = parse_seed_file(SEED)
    report = await seed_users(entries, dry_run=True)
    assert report.created == ["jkowalski", "noemail"]
    assert await DatabaseConnection.get_user("jkowalski") is None
    assert (await DatabaseConnection.get_user("testuser")).full_name == "Test User"


async def test_seed_skips_email_owned_by_other_user(regular_user):
    entries, _ = parse_seed_file("- araucaria_id: intruder\n  email: TEST@example.com\n")
    report = await seed_users(entries)
    assert report.created == []
    assert "already belongs to testuser" in report.problems[0]


async def test_seed_email_as_araucaria_id(beanie):
    entries, _ = parse_seed_file("- araucaria_id: Rolf.Chini@GMX.de\n  email: rolf.chini@gmx.de\n")
    report = await seed_users(entries)
    assert report.created == ["rolf.chini@gmx.de"]
    assert (await DatabaseConnection.get_user_by_identifier("ROLF.chini@gmx.de")).username == "rolf.chini@gmx.de"


async def test_seed_skips_id_that_is_another_users_email(regular_user):
    entries, _ = parse_seed_file("- araucaria_id: test@example.com\n")
    report = await seed_users(entries)
    assert report.created == []
    assert "already the email of testuser" in report.problems[0]


async def test_seed_skips_email_that_is_another_users_id(beanie):
    await seed_users(parse_seed_file("- araucaria_id: a@example.com\n")[0])
    report = await seed_users(parse_seed_file("- araucaria_id: other\n  email: a@example.com\n")[0])
    assert report.created == []
    assert "already belongs to a@example.com" in report.problems[0]


async def test_seed_no_warning_when_stored_email_exists(regular_user):
    entries, _ = parse_seed_file("- araucaria_id: testuser\n  full_name: Test User\n")
    report = await seed_users(entries)
    assert report.warnings == []
