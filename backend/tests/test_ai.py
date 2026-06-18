"""AI service tests — fully offline (no network, per §9 invariants).

Covers degradation (no key -> AIDisabled) and parsing of canned JSON into the
documented list-of-dicts shape via a fake Gemini client.
"""

import json

import pytest

from icereach.ai import service


def test_disabled_by_default_raises():
    """With the default empty GEMINI_API_KEY, capabilities degrade hard.

    conftest sets GEMINI_API_KEY="" so is_enabled() is False and the capability
    must raise AIDisabled rather than attempt a network call.
    """
    assert service.is_enabled() is False
    with pytest.raises(service.AIDisabled):
        service.generate_subjects("Launch our new product")


class _FakeResponse:
    """Mimics the google-genai response object: exposes a `.text` attribute."""

    def __init__(self, text: str):
        self.text = text


class _FakeModels:
    """Mimics `client.models` with a canned `generate_content`."""

    def __init__(self, payload: str):
        self._payload = payload
        self.last_call: dict = {}

    def generate_content(self, *, model, contents, config):
        # Record the call so we can assert the model is pinned + JSON requested.
        self.last_call = {"model": model, "contents": contents, "config": config}
        return _FakeResponse(self._payload)


class _FakeClient:
    """Stand-in for genai.Client; never touches the network."""

    def __init__(self, payload: str):
        self.models = _FakeModels(payload)


def test_generate_subjects_parses_canned_json(monkeypatch):
    """is_enabled()->True + fake client factory -> parsed list-of-dicts."""
    canned = json.dumps(
        [
            {
                "subject": "Your new product is here",
                "preheader": "Be the first to try it",
                "rationale": "Curiosity + early access framing.",
            },
            {
                "subject": "Meet the upgrade you asked for",
                "preheader": "Faster, simpler, yours today",
                "rationale": "Speaks to existing user requests.",
            },
        ]
    )
    fake = _FakeClient(canned)

    # Force the enabled gate True and swap the single client factory for a fake.
    monkeypatch.setattr(service, "is_enabled", lambda: True)
    monkeypatch.setattr(service, "_client", lambda: fake)

    result = service.generate_subjects("Launch our new product", n=2, tone="friendly")

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(item, dict) for item in result)
    assert set(result[0].keys()) == {"subject", "preheader", "rationale"}
    assert result[0]["subject"] == "Your new product is here"
    assert result[1]["preheader"] == "Faster, simpler, yours today"

    # The single call must be pinned to the configured model and request JSON.
    call = fake.models.last_call
    assert call["model"] == service.settings.gemini_model
    assert call["config"].response_mime_type == "application/json"


def test_generate_subjects_accepts_wrapped_array(monkeypatch):
    """A model that nests the array under `variants` is still parsed."""
    canned = json.dumps(
        {"variants": [{"subject": "Hello", "preheader": "Hi", "rationale": "Short."}]}
    )
    fake = _FakeClient(canned)
    monkeypatch.setattr(service, "is_enabled", lambda: True)
    monkeypatch.setattr(service, "_client", lambda: fake)

    result = service.generate_subjects("brief", n=1)

    assert result == [{"subject": "Hello", "preheader": "Hi", "rationale": "Short."}]


def test_draft_body_and_critique_parse(monkeypatch):
    """draft_body and critique_deliverability parse their canned JSON shapes."""
    monkeypatch.setattr(service, "is_enabled", lambda: True)

    body_client = _FakeClient(
        json.dumps({"html": "<p>Hi {physical_address}</p>", "text": "Hi"})
    )
    monkeypatch.setattr(service, "_client", lambda: body_client)
    body = service.draft_body("brief")
    assert body == {"html": "<p>Hi {physical_address}</p>", "text": "Hi"}

    critique_client = _FakeClient(
        json.dumps(
            {
                "spam_risk": 0.2,
                "issues": ["Subject is a bit long"],
                "suggestions": ["Shorten the subject"],
            }
        )
    )
    monkeypatch.setattr(service, "_client", lambda: critique_client)
    critique = service.critique_deliverability("A subject", "<p>body</p>")
    assert critique["spam_risk"] == 0.2
    assert critique["issues"] == ["Subject is a bit long"]
    assert critique["suggestions"] == ["Shorten the subject"]


def test_other_capabilities_raise_when_disabled():
    """All capabilities — not just subjects — degrade hard without a key."""
    with pytest.raises(service.AIDisabled):
        service.draft_body("brief")
    with pytest.raises(service.AIDisabled):
        service.critique_deliverability("s", "<p>h</p>")
