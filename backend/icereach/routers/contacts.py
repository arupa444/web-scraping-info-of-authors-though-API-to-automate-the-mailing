"""Contacts CRUD (workspace-scoped). The CSV/Excel import endpoint lives here too,
added once the importer service is available."""

from __future__ import annotations

import os
import shutil
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Contact
from ..schemas.contact import ContactIn, ContactOut, ContactUpdate
from ..security.deps import AuthContext, auth_context
from ..services import importer  # noqa: F401 — registers the import_contacts handler
from ..services.queue import enqueue

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


def _out(c: Contact) -> ContactOut:
    return ContactOut(id=c.id, email=c.email, name=c.name, attributes=c.attributes or {}, status=c.status)


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def create_contact(body: ContactIn, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    exists = db.scalar(
        select(Contact).where(Contact.workspace_id == ctx.workspace.id, Contact.email == body.email.lower())
    )
    if exists is not None:
        raise HTTPException(status_code=409, detail="Contact with this email already exists")
    c = Contact(workspace_id=ctx.workspace.id, email=body.email.lower(), name=body.name, attributes=body.attributes)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _out(c)


@router.post("/import", status_code=status.HTTP_202_ACCEPTED)
def import_contacts(
    file: UploadFile = File(...),
    list_id: int | None = Form(None),
    validate_emails: bool = Form(True),
    ctx: AuthContext = Depends(auth_context),
    db: DbSession = Depends(get_db),
):
    suffix = os.path.splitext(file.filename or "upload.csv")[1] or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        path = tmp.name
    job = enqueue(db, ctx.workspace.id, "import_contacts", {"file_path": path, "list_id": list_id, "validate": validate_emails})
    return {"job_id": job.id, "status_url": f"/api/jobs/{job.id}"}


@router.get("", response_model=list[ContactOut])
def list_contacts(ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db),
                  limit: int = 100, offset: int = 0):
    rows = db.scalars(
        select(Contact).where(Contact.workspace_id == ctx.workspace.id)
        .order_by(Contact.id).limit(min(limit, 500)).offset(offset)
    ).all()
    return [_out(c) for c in rows]


def _get_owned(db: DbSession, ctx: AuthContext, contact_id: int) -> Contact:
    c = db.scalar(select(Contact).where(Contact.id == contact_id, Contact.workspace_id == ctx.workspace.id))
    if c is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return c


@router.get("/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    return _out(_get_owned(db, ctx, contact_id))


@router.patch("/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: int, body: ContactUpdate, ctx: AuthContext = Depends(auth_context),
                   db: DbSession = Depends(get_db)):
    c = _get_owned(db, ctx, contact_id)
    if body.name is not None:
        c.name = body.name
    if body.attributes is not None:
        c.attributes = body.attributes
    if body.status is not None:
        c.status = body.status
    db.commit()
    db.refresh(c)
    return _out(c)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(contact_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    db.delete(_get_owned(db, ctx, contact_id))
    db.commit()
