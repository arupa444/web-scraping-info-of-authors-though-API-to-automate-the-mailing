"""Prompt-builder helpers for the AI service (§9.2 ``ai/prompts.py``).

Each helper returns a single fully-rendered prompt string asking the model for
**strict JSON only**. User-supplied text (briefs, subjects, HTML) is passed as
clearly delimited *data*, never as instructions, to harden against prompt
injection (§9.6). Bumping a template's wording should bump ``PROMPT_VERSION`` so
the cache key and ledger reflect the change (§9.4).
"""

from __future__ import annotations

# Versioned so the runner can key cache + ledger on the exact prompt text (§9.2).
PROMPT_VERSION = "v1"


def _delimit(label: str, text: str) -> str:
    """Wrap untrusted user content in a clearly labeled, fenced block.

    The fences signal to the model that the content is data to analyze, not
    instructions to follow (§9.6 prompt-injection hardening).
    """
    return f"<{label}>\n{text}\n</{label}>"


def subjects_prompt(brief: str, n: int = 5, tone: str = "professional") -> str:
    """Build the prompt for :func:`icereach.ai.service.generate_subjects` (§9.5.1).

    Args:
        brief: The campaign brief or body the subjects should describe.
        n: Number of distinct subject-line variants to request.
        tone: Desired voice (e.g. ``"professional"``, ``"friendly"``).

    Returns:
        A prompt instructing the model to return a JSON array of
        ``{subject, preheader, rationale}`` objects.
    """
    return (
        f"You are an expert email marketer. Write {n} distinct, high-performing "
        f"subject lines in a {tone} tone for the campaign described below.\n"
        "Rules: each subject is at most 78 characters; each preheader is at most "
        "110 characters; avoid spam-trigger phrasing and ALL-CAPS; do not "
        "fabricate facts beyond the brief.\n"
        "Respond with JSON only: an array of exactly "
        f"{n} objects, each with the keys "
        '"subject" (string), "preheader" (string), and "rationale" (string '
        "explaining why the line should perform). Return no prose outside the "
        "JSON.\n\n"
        f"{_delimit('brief', brief)}"
    )


def body_prompt(brief: str, tone: str = "professional") -> str:
    """Build the prompt for :func:`icereach.ai.service.draft_body` (§9.5.2).

    Args:
        brief: What the email should say / accomplish.
        tone: Desired voice for the copy.

    Returns:
        A prompt instructing the model to return a JSON object with ``html`` and
        ``text`` keys for a ``multipart/alternative`` message.
    """
    return (
        f"You are an expert email copywriter. Draft a marketing email in a {tone} "
        "tone from the brief below.\n"
        "The HTML must be email-client-safe: table-friendly, inline styles only, "
        "no <script>, no <iframe>, no external CSS or JS, no remote stylesheets. "
        "Include a clear call to action and emit the reserved single-brace tokens "
        "{unsubscribe_url} and {physical_address} verbatim (single braces, not "
        "double) where the platform will inject them.\n"
        'Respond with JSON only: an object with the keys "html" (the email-safe '
        'HTML body) and "text" (a plaintext alternative conveying the same '
        "content). Return no prose outside the JSON.\n\n"
        f"{_delimit('brief', brief)}"
    )


def critique_prompt(subject: str, html: str) -> str:
    """Build the prompt for :func:`icereach.ai.service.critique_deliverability` (§9.5.4).

    The critique is advisory only; the deterministic §8.8 gate remains
    authoritative for compliance.

    Args:
        subject: The candidate subject line.
        html: The candidate HTML body.

    Returns:
        A prompt instructing the model to return a JSON object with
        ``spam_risk``, ``issues``, and ``suggestions``.
    """
    return (
        "You are a deliverability and spam-filter expert. Critique the email "
        "subject and HTML body below for the risk of being flagged as spam or "
        "junked by modern mailbox providers. Consider spammy wording, "
        "misleading subjects, link/image ratio, and missing compliance "
        "affordances. Your critique is advisory only.\n"
        'Respond with JSON only: an object with the keys "spam_risk" (a float '
        "from 0.0 = very safe to 1.0 = almost certainly spam), "
        '"issues" (an array of short strings describing problems found), and '
        '"suggestions" (an array of short strings with concrete fixes). Return '
        "no prose outside the JSON.\n\n"
        f"{_delimit('subject', subject)}\n"
        f"{_delimit('html', html)}"
    )


def sequence_prompt(goal: str, steps: int = 3) -> str:
    """Build the prompt for :func:`icereach.ai.service.draft_sequence` (drip journey)."""
    return (
        f"You are an email lifecycle expert. Design a {steps}-email drip sequence "
        "for the goal below. Space the emails sensibly with wait days between them.\n"
        "Each email's HTML must be email-client-safe (inline styles, no script/iframe). "
        "Use the reserved token {name} where the recipient's name belongs.\n"
        "Respond with JSON only: an array of exactly "
        f"{steps} objects, each with the keys "
        '"subject" (string), "html" (email-safe HTML body), and "wait_days" '
        "(integer days to wait BEFORE sending this email; 0 for the first). "
        "Return no prose outside the JSON.\n\n"
        f"{_delimit('goal', goal)}"
    )
