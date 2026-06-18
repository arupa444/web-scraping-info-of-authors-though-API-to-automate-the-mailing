"""Contact importer: upsert rows into Contacts (+ optional list membership).

Turns arbitrary tabular rows (parsed from CSV/Excel uploads, or built by other
services) into workspace-scoped ``Contact`` records. Each row must carry an
``email`` (the key match is case-insensitive); a ``name`` is promoted to the
dedicated column, and every other key is stored verbatim in
``Contact.attributes``.

The importer is deliberately idempotent: re-importing the same address updates
the existing contact instead of creating a duplicate (enforced by the
``(workspace_id, email)`` unique constraint). It also honours the workspace
suppression list and the deliverability validator so dirty uploads cannot
silently subscribe junk or already-bounced addresses.

A queue handler (``run_import_job``) wraps :func:`import_rows` for background
processing: it reads an uploaded file path off the job payload, parses it with
pandas (porting the encoding-fallback read from the legacy ``app.py``), and
reports progress.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Contact, ListMembership, Suppression
from .queue import register
from .validation import validate_email

# Extensions handled as Excel workbooks (everything else is treated as CSV).
_EXCEL_EXTENSIONS = (".xlsx", ".xls", ".xlsn", ".xlsb", ".xltm", ".xltx")
# CSV encodings tried in order, mirroring the legacy single-file app.
_CSV_ENCODINGS = ("utf-8", "latin1", "cp1252")


def _extract_email(row: dict[str, Any]) -> Optional[str]:
    """Return the normalized email from a row using a case-insensitive key.

    Looks for any key that equals ``"email"`` ignoring case/surrounding
    whitespace. Returns the lower-cased, stripped address, or ``None`` when no
    usable email key/value is present.
    """
    for key, value in row.items():
        if key is None:
            continue
        if str(key).strip().lower() == "email":
            if value is None:
                return None
            email = str(value).strip().lower()
            return email or None
    return None


def _extract_name(row: dict[str, Any]) -> Optional[str]:
    """Return the contact name from a row using a case-insensitive ``name`` key."""
    for key, value in row.items():
        if key is None:
            continue
        if str(key).strip().lower() == "name":
            if value is None:
                return None
            name = str(value).strip()
            return name or None
    return None


def _build_attributes(row: dict[str, Any]) -> dict[str, Any]:
    """Collect every key except the email/name keys into the attributes dict."""
    attributes: dict[str, Any] = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized = str(key).strip().lower()
        if normalized in ("email", "name"):
            continue
        attributes[str(key)] = value
    return attributes


def import_rows(
    db: Session,
    workspace_id: int,
    rows: list[dict],
    list_id: int | None = None,
    validate: bool = True,
) -> dict:
    """Upsert contact ``rows`` into a workspace, optionally adding list membership.

    Args:
        db: Active SQLAlchemy session.
        workspace_id: Owning workspace id; all reads/writes are scoped to it.
        rows: Iterable of dicts. Each needs an ``email`` (case-insensitive key);
            an optional ``name`` is promoted to the column, all other keys are
            merged into ``Contact.attributes``.
        list_id: When given, ensure a subscribed ``ListMembership`` for every
            contact that is created or updated (and not suppressed).
        validate: When true, rows whose address is not ``"Deliverable"`` per
            :func:`validate_email` are skipped (counted as ``skipped_invalid``).

    Returns:
        Counts dict ``{created, updated, skipped_invalid, suppressed}``.
    """
    counts = {"created": 0, "updated": 0, "skipped_invalid": 0, "suppressed": 0}

    # Pre-load suppressed addresses for this workspace (one query, set lookup).
    suppressed_emails = {
        e.lower()
        for e in db.scalars(
            select(Suppression.email).where(Suppression.workspace_id == workspace_id)
        ).all()
    }

    for row in rows:
        if not isinstance(row, dict):
            counts["skipped_invalid"] += 1
            continue

        email = _extract_email(row)
        if not email:
            counts["skipped_invalid"] += 1
            continue

        if validate and validate_email(email) != "Deliverable":
            counts["skipped_invalid"] += 1
            continue

        if email in suppressed_emails:
            # Counted, but never subscribed.
            counts["suppressed"] += 1
            continue

        name = _extract_name(row)
        attributes = _build_attributes(row)

        contact = db.scalars(
            select(Contact).where(
                Contact.workspace_id == workspace_id, Contact.email == email
            )
        ).first()

        if contact is None:
            contact = Contact(
                workspace_id=workspace_id,
                email=email,
                name=name,
                attributes=attributes,
                source="import",
            )
            db.add(contact)
            db.flush()  # assign contact.id for membership wiring
            counts["created"] += 1
        else:
            if name is not None:
                contact.name = name
            if attributes:
                # Merge so an import that omits a column does not drop prior data.
                merged = dict(contact.attributes or {})
                merged.update(attributes)
                contact.attributes = merged
            counts["updated"] += 1

        if list_id is not None:
            _ensure_membership(db, list_id, contact.id)

    db.commit()
    return counts


def _ensure_membership(db: Session, list_id: int, contact_id: int) -> None:
    """Ensure a subscribed ``ListMembership`` exists for (list, contact)."""
    membership = db.scalars(
        select(ListMembership).where(
            ListMembership.list_id == list_id,
            ListMembership.contact_id == contact_id,
        )
    ).first()
    if membership is None:
        db.add(
            ListMembership(
                list_id=list_id,
                contact_id=contact_id,
                status="subscribed",
                subscribed_at=datetime.utcnow(),
            )
        )
    else:
        membership.status = "subscribed"
        if membership.subscribed_at is None:
            membership.subscribed_at = datetime.utcnow()


def _read_dataframe(file_path: str):
    """Read a CSV/Excel file into a pandas DataFrame (encoding-fallback for CSV).

    Ports the encoding-fallback read from the legacy ``app.py``: CSV files are
    tried as utf-8, then latin1, then cp1252 (common for Windows-saved files);
    Excel workbooks are read directly.
    """
    import pandas as pd

    lower = file_path.lower()
    if lower.endswith(_EXCEL_EXTENSIONS):
        return pd.read_excel(file_path)

    last_error: Optional[Exception] = None
    for encoding in _CSV_ENCODINGS:
        try:
            return pd.read_csv(file_path, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    raise ValueError(
        f"Could not read CSV file {file_path} with any of {_CSV_ENCODINGS}: {last_error}"
    )


def _rows_from_dataframe(df) -> list[dict]:
    """Convert a DataFrame to row dicts, dropping pandas NaN sentinels."""
    records = df.where(df.notna(), None).to_dict("records")
    cleaned: list[dict] = []
    for record in records:
        cleaned.append({k: v for k, v in record.items() if v is not None})
    return cleaned


@register("import_contacts")
def run_import_job(
    db: Session,
    job: Any,
    progress: Callable[[float, str], None],
) -> dict:
    """Queue handler: parse an uploaded file and import its rows.

    Reads ``job.payload`` ``{file_path, list_id, validate}``, parses the file
    via pandas (with CSV encoding fallback), converts it to rows, and delegates
    to :func:`import_rows` scoped to ``job.workspace_id``.

    Returns the counts dict from :func:`import_rows`.
    """
    payload = job.payload or {}
    file_path = payload.get("file_path")
    list_id = payload.get("list_id")
    validate = payload.get("validate", True)

    if not file_path:
        raise ValueError("import_contacts job payload requires 'file_path'")

    progress(5, "Reading file")
    df = _read_dataframe(file_path)

    progress(35, "Parsing rows")
    rows = _rows_from_dataframe(df)

    progress(60, f"Importing {len(rows)} rows")
    counts = import_rows(
        db,
        workspace_id=job.workspace_id,
        rows=rows,
        list_id=list_id,
        validate=validate,
    )

    progress(100, "Import complete")
    return counts
