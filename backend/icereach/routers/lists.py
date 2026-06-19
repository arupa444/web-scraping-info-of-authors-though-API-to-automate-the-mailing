"""Contact lists + membership (workspace-scoped)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Contact, ContactList, ListMembership
from ..schemas.contact import ListAddIn, ListIn, ListOut
from ..security.deps import AuthContext, auth_context

router = APIRouter(prefix="/api/lists", tags=["lists"])


def _out(lst: ContactList) -> ListOut:
    return ListOut(id=lst.id, name=lst.name, description=lst.description)


def _get_owned(db: DbSession, ctx: AuthContext, list_id: int) -> ContactList:
    lst = db.scalar(select(ContactList).where(ContactList.id == list_id, ContactList.workspace_id == ctx.workspace.id))
    if lst is None:
        raise HTTPException(status_code=404, detail="List not found")
    return lst


@router.post("", response_model=ListOut, status_code=status.HTTP_201_CREATED)
def create_list(body: ListIn, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    lst = ContactList(workspace_id=ctx.workspace.id, name=body.name, description=body.description)
    db.add(lst)
    db.commit()
    db.refresh(lst)
    return _out(lst)


@router.get("", response_model=list[ListOut])
def list_lists(ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    rows = db.scalars(select(ContactList).where(ContactList.workspace_id == ctx.workspace.id).order_by(ContactList.id)).all()
    return [_out(x) for x in rows]


@router.get("/{list_id}/variables")
def list_variables(list_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    """Merge variables usable for this list: the standard fields plus the union
    of custom attribute keys across the list's contacts. Powers the template
    builder's personalization suggestions."""
    _get_owned(db, ctx, list_id)
    rows = db.scalars(
        select(Contact)
        .join(ListMembership, ListMembership.contact_id == Contact.id)
        .where(ListMembership.list_id == list_id, Contact.workspace_id == ctx.workspace.id)
    ).all()
    keys: set[str] = set()
    for c in rows:
        for k in (c.attributes or {}).keys():
            keys.add(str(k))
    return {"standard": ["name", "email"], "attributes": sorted(keys)}


@router.post("/{list_id}/contacts", status_code=status.HTTP_200_OK)
def add_contacts(list_id: int, body: ListAddIn, ctx: AuthContext = Depends(auth_context),
                 db: DbSession = Depends(get_db)):
    lst = _get_owned(db, ctx, list_id)
    added = 0
    newly_subscribed: list[int] = []
    for cid in body.contact_ids:
        contact = db.scalar(select(Contact).where(Contact.id == cid, Contact.workspace_id == ctx.workspace.id))
        if contact is None:
            continue
        existing = db.scalar(
            select(ListMembership).where(ListMembership.list_id == lst.id, ListMembership.contact_id == cid)
        )
        if existing is None:
            db.add(ListMembership(list_id=lst.id, contact_id=cid, status="subscribed", subscribed_at=datetime.utcnow()))
            added += 1
            newly_subscribed.append(cid)
    db.commit()

    # Trigger any list_subscribe automations for the newly-added contacts.
    if newly_subscribed:
        from ..services.automation import enroll_for_list
        enroll_for_list(db, ctx.workspace.id, lst.id, newly_subscribed)
    return {"added": added}


@router.delete("/{list_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_contact(list_id: int, contact_id: int, ctx: AuthContext = Depends(auth_context),
                   db: DbSession = Depends(get_db)):
    lst = _get_owned(db, ctx, list_id)
    membership = db.scalar(
        select(ListMembership).where(ListMembership.list_id == lst.id, ListMembership.contact_id == contact_id)
    )
    if membership is not None:
        db.delete(membership)
        db.commit()
