"""AI service: the single Gemini entry point (§9).

Wraps ``google-genai`` and pins the model to ``settings.gemini_model``
(``gemini-3-flash-preview``). Every capability requests strict JSON.

Degradation (§9.8): when ``GEMINI_API_KEY`` is unset, :func:`is_enabled` is
``False`` and every capability raises :class:`AIDisabled` rather than touching
the network. Callers (the router) translate that into the typed ``degraded``
envelope; the core platform is unaffected.
"""

from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import types

from ..config import settings
from . import prompts

# JSON mode: ask the model for a parseable response, no free-text wrapping (§9.1).
_JSON_MIME = "application/json"


class AIDisabled(Exception):
    """Raised by every capability when no ``GEMINI_API_KEY`` is configured.

    This is the structural form of §9.8 degradation: the service never calls the
    network and never raises a 500 from a missing key — it raises this typed
    exception, which the AI router converts to a ``degraded`` result envelope.
    """


def is_enabled() -> bool:
    """Return ``True`` iff an API key is configured (§9.1 / §9.8).

    When ``False`` the client is never built and every capability degrades.
    """
    return bool(settings.gemini_api_key)


def _client() -> genai.Client:
    """Construct the Gemini client (single factory; §9.1 single entry point).

    Raises:
        AIDisabled: if AI is not enabled (no API key). This guards against ever
            building a client — and therefore ever hitting the network — in the
            degraded state.
    """
    if not is_enabled():
        raise AIDisabled("AI is disabled: GEMINI_API_KEY is not set")
    return genai.Client(api_key=settings.gemini_api_key)


def _generate_json(prompt: str, *, temperature: float, max_output_tokens: int) -> Any:
    """Call Gemini in JSON mode and parse the response.

    Builds the client via :func:`_client` (which enforces the enabled gate),
    issues a single ``generate_content`` call pinned to ``settings.gemini_model``
    with ``response_mime_type=application/json``, and parses ``response.text``.

    Args:
        prompt: The fully-rendered prompt text.
        temperature: Sampling temperature for this capability.
        max_output_tokens: Output token cap for cost control (§9.7).

    Returns:
        The decoded JSON value (``list`` or ``dict``).
    """
    client = _client()
    config_kwargs: dict[str, Any] = dict(
        response_mime_type=_JSON_MIME,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    # Gemini 3 spends "thinking" tokens before output; for these structured tasks we
    # don't need it, and leaving it on truncates the JSON within the token budget.
    try:
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    except (AttributeError, TypeError):  # older SDK without ThinkingConfig
        pass

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    return json.loads(_clean_json(response.text))


def _clean_json(text: str) -> str:
    """Strip markdown fences / stray prose so json.loads sees pure JSON."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
        t = t.strip()
    # Fall back to the outermost JSON array/object if extra text wraps it.
    if not t[:1] in ("{", "["):
        start = min((t.find(c) for c in "[{" if t.find(c) != -1), default=-1)
        end = max(t.rfind("]"), t.rfind("}"))
        if start != -1 and end > start:
            t = t[start:end + 1]
    return t


def generate_subjects(
    brief: str, n: int = 5, tone: str = "professional"
) -> list[dict]:
    """Generate subject-line variants for a campaign (§9.5.1).

    Args:
        brief: The campaign brief or body to base subjects on.
        n: How many variants to request.
        tone: Desired voice.

    Returns:
        A list of ``{"subject", "preheader", "rationale"}`` dicts.

    Raises:
        AIDisabled: if AI is not enabled.
    """
    if not is_enabled():
        raise AIDisabled("AI is disabled: GEMINI_API_KEY is not set")
    prompt = prompts.subjects_prompt(brief, n=n, tone=tone)
    raw = _generate_json(prompt, temperature=0.9, max_output_tokens=600)
    # The model may wrap the array under a key; accept either shape.
    variants = raw if isinstance(raw, list) else raw.get("variants") or raw.get("subjects") or []
    return [
        {
            "subject": str(item.get("subject", "")),
            "preheader": str(item.get("preheader", "")),
            "rationale": str(item.get("rationale", "")),
        }
        for item in variants
        if isinstance(item, dict)
    ]


def draft_body(brief: str, tone: str = "professional") -> dict:
    """Draft an email body in HTML + plaintext (§9.5.2).

    Args:
        brief: What the email should say.
        tone: Desired voice.

    Returns:
        A ``{"html", "text"}`` dict.

    Raises:
        AIDisabled: if AI is not enabled.
    """
    if not is_enabled():
        raise AIDisabled("AI is disabled: GEMINI_API_KEY is not set")
    prompt = prompts.body_prompt(brief, tone=tone)
    raw = _generate_json(prompt, temperature=0.7, max_output_tokens=2048)
    data = raw if isinstance(raw, dict) else {}
    return {
        "html": str(data.get("html", "")),
        "text": str(data.get("text", "")),
    }


def critique_deliverability(subject: str, html: str) -> dict:
    """Critique a draft for spam/deliverability risk (§9.5.4).

    Advisory only — the deterministic §8.8 preflight gate is authoritative.

    Args:
        subject: The candidate subject line.
        html: The candidate HTML body.

    Returns:
        A ``{"spam_risk": float, "issues": list[str], "suggestions": list[str]}``
        dict.

    Raises:
        AIDisabled: if AI is not enabled.
    """
    if not is_enabled():
        raise AIDisabled("AI is disabled: GEMINI_API_KEY is not set")
    prompt = prompts.critique_prompt(subject, html)
    raw = _generate_json(prompt, temperature=0.1, max_output_tokens=800)
    data = raw if isinstance(raw, dict) else {}
    try:
        spam_risk = float(data.get("spam_risk", 0.0))
    except (TypeError, ValueError):
        spam_risk = 0.0
    return {
        "spam_risk": spam_risk,
        "issues": [str(x) for x in (data.get("issues") or [])],
        "suggestions": [str(x) for x in (data.get("suggestions") or [])],
    }
