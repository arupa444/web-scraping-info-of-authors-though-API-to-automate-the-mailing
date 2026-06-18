"""Tests for icereach.services.importer.

All tests stay offline: the deliverability validator is monkeypatched so no DNS
lookups happen. We exercise import_rows directly (creates/updates/skips/
suppresses) and the run_import_job queue handler against a small CSV.
"""

import pandas as pd
import pytest

from icereach.models import (
    Contact,
    ContactList,
    ListMembership,
    Suppression,
    Workspace,
)
from icereach.services import importer


@pytest.fixture
def ws(db):
    workspace = Workspace(name="W", slug="w-importer")
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace


@pytest.fixture
def contact_list(db, ws):
    cl = ContactList(workspace_id=ws.id, name="Main")
    db.add(cl)
    db.commit()
    db.refresh(cl)
    return cl


@pytest.fixture(autouse=True)
def _all_deliverable(monkeypatch):
    """Default: every address is Deliverable (no DNS)."""
    monkeypatch.setattr(importer, "validate_email", lambda email: "Deliverable")


# --------------------------------------------------------------------------
# import_rows: happy path
# --------------------------------------------------------------------------
def test_valid_rows_create_contacts(db, ws):
    rows = [
        {"email": "ada@example.com", "name": "Ada"},
        {"email": "bob@example.com", "name": "Bob"},
    ]
    counts = importer.import_rows(db, ws.id, rows)
    assert counts == {"created": 2, "updated": 0, "skipped_invalid": 0, "suppressed": 0}

    contacts = db.query(Contact).filter(Contact.workspace_id == ws.id).all()
    assert {c.email for c in contacts} == {"ada@example.com", "bob@example.com"}
    assert {c.name for c in contacts} == {"Ada", "Bob"}


def test_extra_columns_go_into_attributes(db, ws):
    rows = [{"email": "ada@example.com", "name": "Ada", "company": "ACME", "tier": "gold"}]
    importer.import_rows(db, ws.id, rows)
    contact = db.query(Contact).filter(Contact.email == "ada@example.com").one()
    assert contact.attributes == {"company": "ACME", "tier": "gold"}


def test_email_key_is_case_insensitive(db, ws):
    rows = [{"Email": "ada@example.com", "Name": "Ada"}]
    counts = importer.import_rows(db, ws.id, rows)
    assert counts["created"] == 1
    contact = db.query(Contact).filter(Contact.email == "ada@example.com").one()
    assert contact.name == "Ada"
    # 'Email'/'Name' keys must not leak into attributes.
    assert contact.attributes == {}


def test_email_is_normalized_lowercase(db, ws):
    rows = [{"email": "  Ada@Example.COM  "}]
    importer.import_rows(db, ws.id, rows)
    assert db.query(Contact).filter(Contact.email == "ada@example.com").count() == 1


# --------------------------------------------------------------------------
# import_rows: list membership
# --------------------------------------------------------------------------
def test_list_id_creates_subscribed_membership(db, ws, contact_list):
    rows = [{"email": "ada@example.com", "name": "Ada"}]
    importer.import_rows(db, ws.id, rows, list_id=contact_list.id)

    contact = db.query(Contact).filter(Contact.email == "ada@example.com").one()
    membership = (
        db.query(ListMembership)
        .filter(
            ListMembership.list_id == contact_list.id,
            ListMembership.contact_id == contact.id,
        )
        .one()
    )
    assert membership.status == "subscribed"
    assert membership.subscribed_at is not None


def test_reimport_does_not_duplicate_membership(db, ws, contact_list):
    rows = [{"email": "ada@example.com", "name": "Ada"}]
    importer.import_rows(db, ws.id, rows, list_id=contact_list.id)
    importer.import_rows(db, ws.id, rows, list_id=contact_list.id)

    assert db.query(ListMembership).filter(ListMembership.list_id == contact_list.id).count() == 1


# --------------------------------------------------------------------------
# import_rows: invalid rows
# --------------------------------------------------------------------------
def test_invalid_rows_skipped(db, ws, monkeypatch):
    def fake_validate(email):
        return "Deliverable" if email == "good@example.com" else "Invalid syntax"

    monkeypatch.setattr(importer, "validate_email", fake_validate)

    rows = [
        {"email": "good@example.com"},
        {"email": "bad@@nope"},
    ]
    counts = importer.import_rows(db, ws.id, rows)
    assert counts["created"] == 1
    assert counts["skipped_invalid"] == 1
    assert db.query(Contact).filter(Contact.workspace_id == ws.id).count() == 1


def test_row_without_email_is_skipped_invalid(db, ws):
    rows = [{"name": "No Email"}, {"email": "", "name": "Empty"}]
    counts = importer.import_rows(db, ws.id, rows)
    assert counts["skipped_invalid"] == 2
    assert counts["created"] == 0


def test_validate_false_skips_validation(db, ws, monkeypatch):
    # If validation is disabled, the validator must never be consulted.
    def boom(email):  # pragma: no cover - asserts it's not called
        raise AssertionError("validate_email should not be called when validate=False")

    monkeypatch.setattr(importer, "validate_email", boom)
    counts = importer.import_rows(db, ws.id, [{"email": "any@thing.tld"}], validate=False)
    assert counts["created"] == 1


# --------------------------------------------------------------------------
# import_rows: suppression
# --------------------------------------------------------------------------
def test_suppressed_emails_counted_and_not_subscribed(db, ws, contact_list):
    db.add(Suppression(workspace_id=ws.id, email="blocked@example.com", reason="hard_bounce"))
    db.commit()

    rows = [
        {"email": "blocked@example.com", "name": "Blocked"},
        {"email": "fresh@example.com", "name": "Fresh"},
    ]
    counts = importer.import_rows(db, ws.id, rows, list_id=contact_list.id)

    assert counts["suppressed"] == 1
    assert counts["created"] == 1
    # Suppressed contact must not be created as a contact...
    assert db.query(Contact).filter(Contact.email == "blocked@example.com").count() == 0
    # ...and must not be subscribed to the list.
    assert db.query(ListMembership).filter(ListMembership.list_id == contact_list.id).count() == 1


def test_suppression_is_workspace_scoped(db, ws):
    # A suppression in another workspace must NOT block this workspace's import.
    other = Workspace(name="Other", slug="w-other")
    db.add(other)
    db.commit()
    db.refresh(other)
    db.add(Suppression(workspace_id=other.id, email="ada@example.com", reason="manual"))
    db.commit()

    counts = importer.import_rows(db, ws.id, [{"email": "ada@example.com"}])
    assert counts["created"] == 1
    assert counts["suppressed"] == 0


# --------------------------------------------------------------------------
# import_rows: re-import updates without duplicating
# --------------------------------------------------------------------------
def test_reimport_updates_existing_contact(db, ws):
    importer.import_rows(db, ws.id, [{"email": "ada@example.com", "name": "Ada"}])
    counts = importer.import_rows(
        db, ws.id, [{"email": "ada@example.com", "name": "Ada Lovelace", "tier": "gold"}]
    )

    assert counts == {"created": 0, "updated": 1, "skipped_invalid": 0, "suppressed": 0}
    contacts = db.query(Contact).filter(Contact.email == "ada@example.com").all()
    assert len(contacts) == 1  # no duplicate
    assert contacts[0].name == "Ada Lovelace"
    assert contacts[0].attributes.get("tier") == "gold"


# --------------------------------------------------------------------------
# run_import_job: queue handler
# --------------------------------------------------------------------------
class _FakeJob:
    def __init__(self, workspace_id, payload):
        self.workspace_id = workspace_id
        self.payload = payload


def test_run_import_job_reads_csv_and_imports(db, ws, contact_list, tmp_path):
    csv_path = tmp_path / "contacts.csv"
    pd.DataFrame(
        [
            {"email": "ada@example.com", "name": "Ada", "company": "ACME"},
            {"email": "bob@example.com", "name": "Bob", "company": "Globex"},
        ]
    ).to_csv(csv_path, index=False)

    progress_calls: list[tuple[float, str]] = []

    def progress(pct, msg=""):
        progress_calls.append((pct, msg))

    job = _FakeJob(ws.id, {"file_path": str(csv_path), "list_id": contact_list.id, "validate": True})
    result = importer.run_import_job(db, job, progress)

    assert result["created"] == 2
    assert db.query(Contact).filter(Contact.workspace_id == ws.id).count() == 2
    assert db.query(ListMembership).filter(ListMembership.list_id == contact_list.id).count() == 2
    # Progress was reported and reached 100.
    assert len(progress_calls) >= 2
    assert progress_calls[-1][0] == 100


def test_run_import_job_handles_latin1_encoding(db, ws, tmp_path):
    # A non-UTF-8 byte in the name must not break the read (encoding fallback).
    csv_path = tmp_path / "latin.csv"
    csv_path.write_bytes("email,name\nrene@example.com,Ren\xe9\n".encode("latin1"))

    job = _FakeJob(ws.id, {"file_path": str(csv_path)})
    result = importer.run_import_job(db, job, lambda *a, **k: None)

    assert result["created"] == 1
    contact = db.query(Contact).filter(Contact.email == "rene@example.com").one()
    assert contact.name == "Ren\xe9"


def test_run_import_job_requires_file_path(db, ws):
    job = _FakeJob(ws.id, {})
    with pytest.raises(ValueError):
        importer.run_import_job(db, job, lambda *a, **k: None)
