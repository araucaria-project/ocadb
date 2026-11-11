"""Create or update araucarians from a YAML file. Mongo stays the source of truth;
the file is only input. Passwords, moderator and disabled flags are never touched.

File format (a top-level list works too)::

    users:
      - araucaria_id: jkowalski
        email: jkowalski@camk.edu.pl
        full_name: Jan Kowalski
        access_tags: [CAMK PAN]
"""
from dataclasses import dataclass, field

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator
from pymongo.errors import DuplicateKeyError

from api.services.database_connection import DatabaseConnection
from ocadb.models.user import normalize_email


class SeedEntry(BaseModel):
    araucaria_id: str = Field(min_length=1)
    email: str | None = None
    full_name: str | None = None
    access_tags: list[str] = []

    @field_validator("access_tags", mode="before")
    @classmethod
    def _blank_tags(cls, v):
        # A key left blank in YAML (`access_tags:`) parses as None.
        return [] if v is None else v


@dataclass
class SeedReport:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_seed_file(text: str) -> tuple[list[SeedEntry], list[str]]:
    """Return valid entries and a list of problems with the others."""
    data = yaml.safe_load(text) or []
    if isinstance(data, dict):
        data = data.get("users") or []
    if not isinstance(data, list):
        return [], ["expected a list of users or a 'users:' key"]
    entries, problems, seen = [], [], set()
    for i, raw in enumerate(data, start=1):
        if isinstance(raw, dict) and "araucaria_id" not in raw and "username" in raw:
            raw = {**raw, "araucaria_id": raw.pop("username")}
        try:
            entry = SeedEntry.model_validate(raw)
        except ValidationError as e:
            problems.append(f"entry {i}: {e.errors()[0]['loc']} {e.errors()[0]['msg']}")
            continue
        entry.araucaria_id = entry.araucaria_id.strip()
        if "@" in entry.araucaria_id:
            # An email used as the Araucaria ID is stored like an email: lowercase.
            entry.araucaria_id = normalize_email(entry.araucaria_id)
        entry.email = normalize_email(entry.email)
        if entry.araucaria_id in seen:
            problems.append(f"entry {i}: duplicate araucaria_id {entry.araucaria_id!r}")
            continue
        seen.add(entry.araucaria_id)
        entries.append(entry)
    return entries, problems


async def seed_users(entries: list[SeedEntry], replace_tags: bool = False, dry_run: bool = False) -> SeedReport:
    report = SeedReport()
    for entry in entries:
        user_id = entry.araucaria_id
        # Lookups by an address match both emails and email-style IDs, so the
        # address must not point at another user either way.
        if entry.email:
            owner = await DatabaseConnection.get_user_by_identifier(entry.email)
            if owner is not None and owner.username != user_id:
                report.problems.append(f"{user_id}: email {entry.email} already belongs to {owner.username}, skipped")
                continue
        if "@" in user_id:
            owner = await DatabaseConnection.get_user_by_identifier(user_id)
            if owner is not None and owner.username != user_id:
                report.problems.append(f"{user_id}: already the email of {owner.username}, skipped")
                continue

        user = await DatabaseConnection.get_user(user_id)
        if not entry.email and not (user and user.email):
            report.warnings.append(f"{user_id}: no email, cannot log in with emailed codes")
        if user is None:
            if not dry_run:
                try:
                    await DatabaseConnection.create_user(
                        username=user_id, email=entry.email, full_name=entry.full_name or "",
                        hashed_password=None, access_tags=list(dict.fromkeys(entry.access_tags)),
                    )
                except DuplicateKeyError:
                    report.problems.append(f"{user_id}: email {entry.email} already in use, skipped")
                    continue
            report.created.append(user_id)
            continue

        changes: dict = {}
        if entry.email and entry.email != normalize_email(user.email):
            changes["email"] = entry.email
        if entry.full_name and entry.full_name != user.full_name:
            changes["full_name"] = entry.full_name
        current_tags = user.access_tags or []
        tags = list(dict.fromkeys(entry.access_tags if replace_tags else current_tags + entry.access_tags))
        if tags != current_tags:
            changes["access_tags"] = tags
        if not changes:
            report.unchanged.append(user_id)
            continue
        if not dry_run:
            try:
                await user.set(changes)
            except DuplicateKeyError:
                report.problems.append(f"{user_id}: email {entry.email} already in use, skipped")
                continue
        report.updated.append(f"{user_id} ({', '.join(changes)})")
    return report
