"""Sending domains: register (DKIM keygen + DNS records), list, verify."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import SendingDomain
from ..schemas.sending import DnsRecordsOut, SendingDomainIn, SendingDomainOut
from ..security.deps import AuthContext, auth_context
from ..services.dkim import generate_keypair
from ..services.dns_verify import render_dns_records, verify_dkim, verify_dmarc, verify_spf

router = APIRouter(prefix="/api/sending-domains", tags=["sending-domains"])


def _out(d: SendingDomain) -> SendingDomainOut:
    return SendingDomainOut(
        id=d.id, domain=d.domain, provider=d.provider, dkim_selector=d.dkim_selector,
        spf_verified=d.spf_verified, dkim_verified=d.dkim_verified, dmarc_verified=d.dmarc_verified,
        status=d.status, smtp_host=d.smtp_host, verify_tls=d.verify_tls,
    )


def _records(d: SendingDomain) -> list[dict]:
    return render_dns_records(d.domain, d.dkim_selector, d.dkim_public_key)


def _owned(db: DbSession, ctx: AuthContext, domain_id: int) -> SendingDomain:
    d = db.scalar(select(SendingDomain).where(SendingDomain.id == domain_id, SendingDomain.workspace_id == ctx.workspace.id))
    if d is None:
        raise HTTPException(status_code=404, detail="Sending domain not found")
    return d


@router.post("", response_model=DnsRecordsOut, status_code=status.HTTP_201_CREATED)
def create_domain(body: SendingDomainIn, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    if db.scalar(select(SendingDomain).where(SendingDomain.workspace_id == ctx.workspace.id, SendingDomain.domain == body.domain.lower())):
        raise HTTPException(status_code=409, detail="Domain already registered")
    private_pem, dkim_txt = generate_keypair()
    d = SendingDomain(
        workspace_id=ctx.workspace.id, domain=body.domain.lower(),
        provider=body.provider, api_key=body.api_key,
        dkim_selector="icereach", dkim_private_key=private_pem, dkim_public_key=dkim_txt,
        smtp_host=body.smtp_host, smtp_port=body.smtp_port,
        smtp_username=body.smtp_username, smtp_password=body.smtp_password,
        verify_tls=body.verify_tls,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return DnsRecordsOut(domain=_out(d), records=_records(d))


@router.get("", response_model=list[SendingDomainOut])
def list_domains(ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    rows = db.scalars(select(SendingDomain).where(SendingDomain.workspace_id == ctx.workspace.id)).all()
    return [_out(d) for d in rows]


@router.get("/{domain_id}/dns", response_model=DnsRecordsOut)
def dns_records(domain_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    d = _owned(db, ctx, domain_id)
    return DnsRecordsOut(domain=_out(d), records=_records(d))


@router.post("/{domain_id}/verify", response_model=SendingDomainOut)
def verify(domain_id: int, ctx: AuthContext = Depends(auth_context), db: DbSession = Depends(get_db)):
    d = _owned(db, ctx, domain_id)
    d.spf_verified = verify_spf(d.domain)
    d.dkim_verified = verify_dkim(d.domain, d.dkim_selector)
    d.dmarc_verified = verify_dmarc(d.domain)
    d.status = "verified" if (d.spf_verified and d.dkim_verified and d.dmarc_verified) else "pending"
    db.commit()
    db.refresh(d)
    return _out(d)
