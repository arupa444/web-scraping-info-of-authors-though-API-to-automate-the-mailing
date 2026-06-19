"""SaaS hardening: audit logs, members (RBAC), billing scaffold."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import AuditLog, Membership, User, Workspace
from ..schemas.admin import (
    AuditLogOut,
    BillingOut,
    CheckoutIn,
    MemberInviteIn,
    MemberOut,
    PlanOut,
    RoleUpdateIn,
)
from ..security.deps import AuthContext, auth_context, require_role
from ..security.passwords import hash_password
from ..services import quota
from ..services.audit import log as audit_log

# ---- Audit logs (admin) ----
audit_router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


@audit_router.get("", response_model=list[AuditLogOut])
def list_audit(ctx: AuthContext = Depends(require_role("owner", "admin")), db: DbSession = Depends(get_db), limit: int = 100):
    limit = max(1, min(limit, 500))  # negative LIMIT is "unbounded" in SQLite — clamp
    rows = db.scalars(
        select(AuditLog).where(AuditLog.workspace_id == ctx.workspace.id).order_by(AuditLog.id.desc()).limit(limit)
    ).all()
    return [AuditLogOut(id=r.id, action=r.action, target=r.target, user_id=r.user_id, meta=r.meta, created_at=r.created_at) for r in rows]


# ---- Members (RBAC) ----
members_router = APIRouter(prefix="/api/members", tags=["members"])


@members_router.get("", response_model=list[MemberOut])
def list_members(ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    rows = db.execute(
        select(Membership, User).join(User, User.id == Membership.user_id).where(Membership.workspace_id == ctx.workspace.id)
    ).all()
    return [MemberOut(user_id=u.id, email=u.email, name=u.name, role=m.role) for m, u in rows]


@members_router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def add_member(body: MemberInviteIn, ctx: AuthContext = Depends(require_role("owner", "admin")), db: DbSession = Depends(get_db)):
    # Only an owner may grant the admin role; admins can only add members.
    if body.role == "admin" and ctx.membership.role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can grant the admin role")
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None:
        user = User(email=body.email.lower(), password_hash=hash_password(body.password))
        db.add(user)
        db.flush()
    if db.scalar(select(Membership).where(Membership.workspace_id == ctx.workspace.id, Membership.user_id == user.id)):
        raise HTTPException(status_code=409, detail="Already a member")
    db.add(Membership(workspace_id=ctx.workspace.id, user_id=user.id, role=body.role))
    db.commit()
    audit_log(db, ctx.workspace.id, "member.added", target=body.email, user_id=ctx.user.id)
    return MemberOut(user_id=user.id, email=user.email, name=user.name, role=body.role)


@members_router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(user_id: int, ctx: AuthContext = Depends(require_role("owner", "admin")), db: DbSession = Depends(get_db)):
    m = db.scalar(select(Membership).where(Membership.workspace_id == ctx.workspace.id, Membership.user_id == user_id))
    if m is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if m.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot remove the workspace owner")
    db.delete(m)
    db.commit()
    audit_log(db, ctx.workspace.id, "member.removed", target=str(user_id), user_id=ctx.user.id)


# ---- Billing (SCAFFOLD — no live Stripe) ----
billing_router = APIRouter(prefix="/api/billing", tags=["billing"])

_PLANS = [
    PlanOut(key="free", name="Free", monthly_send_limit=1000, price_usd=0),
    PlanOut(key="pro", name="Pro", monthly_send_limit=50000, price_usd=29),
    PlanOut(key="scale", name="Scale", monthly_send_limit=500000, price_usd=99),
]


@billing_router.get("/plans", response_model=list[PlanOut])
def plans(ctx: AuthContext = Depends(auth_context)):
    return _PLANS


@billing_router.get("", response_model=BillingOut)
def current(ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    return BillingOut(plan=ctx.workspace.plan, monthly_send_limit=ctx.workspace.monthly_send_limit,
                      sent_this_month=quota.sent_this_month(db, ctx.workspace.id))


@billing_router.post("/checkout")
def checkout(body: CheckoutIn, ctx: AuthContext = Depends(require_role("owner", "admin")), db: DbSession = Depends(get_db)):
    plan = next((p for p in _PLANS if p.key == body.plan), None)
    if plan is None:
        raise HTTPException(status_code=400, detail="Unknown plan")
    # SCAFFOLD: a real implementation creates a Stripe Checkout Session and returns its URL.
    # Here we apply the plan directly and return a placeholder URL.
    ws = db.get(Workspace, ctx.workspace.id)
    ws.plan = plan.key
    ws.monthly_send_limit = plan.monthly_send_limit
    db.commit()
    audit_log(db, ctx.workspace.id, "billing.plan_changed", target=plan.key, user_id=ctx.user.id)
    return {"checkout_url": f"https://billing.example/checkout?plan={plan.key}", "applied": True, "note": "scaffold — no live Stripe"}
