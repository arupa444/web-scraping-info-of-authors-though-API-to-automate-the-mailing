"""AI assist endpoints (Gemini). Returns 503 when AI is disabled (no API key)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..ai import service as ai_service
from ..schemas.ai import BodyIn, CritiqueIn, SubjectsIn
from ..security.deps import AuthContext, auth_context

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _guard(fn, *args):
    try:
        return fn(*args)
    except ai_service.AIDisabled as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/subjects")
def subjects(body: SubjectsIn, ctx: AuthContext = Depends(auth_context)):
    return {"variants": _guard(ai_service.generate_subjects, body.brief, body.n, body.tone)}


@router.post("/body")
def body_draft(body: BodyIn, ctx: AuthContext = Depends(auth_context)):
    return _guard(ai_service.draft_body, body.brief, body.tone)


@router.post("/critique")
def critique(body: CritiqueIn, ctx: AuthContext = Depends(auth_context)):
    return _guard(ai_service.critique_deliverability, body.subject, body.html)
