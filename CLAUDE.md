# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

iceReach is a multi-tenant, AI-assisted email **platform**: a FastAPI JSON API
(`backend/icereach/`) + a React SPA (`frontend/`). It was rebuilt from a legacy
single-file app; the old `app.py`, `templates/`, `CLI_files/`, and the **email
scraper are removed** — do not reintroduce scraping (guarded by
`backend/tests/test_no_scraper.py`).

Authoritative design: `docs/superpowers/specs/2026-06-19-icereach-platform-design.md`
(all 6 phases). Phase 1 plan: `docs/superpowers/plans/2026-06-19-icereach-phase1-foundation.md`.
Only Phase 1 is built so far.

## Commands

```bash
# Python deps (uv; never pip directly). pytest is configured via pyproject (pythonpath=backend).
uv venv && source .venv/bin/activate && uv pip install -r requirements.txt
pytest backend/tests -q                  # full backend suite
pytest backend/tests/test_send_pipeline.py -q   # a single file

# Run API (note --app-dir backend so `icereach` is importable)
uvicorn icereach.main:app --reload --app-dir backend --port 8000
python run.py                            # free port + browser; serves built SPA if frontend/dist exists
python -m icereach.services.queue        # background worker (run with PYTHONPATH=backend)

# Migrations
DATABASE_URL=sqlite:///./icereach.db alembic -c backend/alembic.ini upgrade head

# Frontend
cd frontend && npm install && npm run dev   # Vite dev server, proxies /api -> :8000
cd frontend && npm run build                # production build -> frontend/dist
```

## Architecture (the non-obvious parts)

**Tenant isolation is structural.** Every domain table carries `workspace_id`
(`models/base.py:WorkspaceScopedMixin`). Routers depend on
`security/deps.py:auth_context` → `AuthContext{user, workspace, membership}` and
**must** filter every query by `ctx.workspace.id`. Never trust an id from the path
without the workspace filter (see the `_owned()` helpers in routers).

**Auth = httpOnly session cookie + double-submit CSRF.** `security/sessions.py`
stores only the SHA-256 of the session token. The CSRF token is a signed cookie
(`ice_csrf`, readable by JS) that the SPA echoes as `X-CSRF-Token`. The CSRF check
is a middleware in `main.py` that fires for mutating `/api/*` requests **except**
login/signup and any request bearing an `Authorization: Bearer` API key. Tests must
send the `X-CSRF-Token` header on POST/PATCH/DELETE.

**Long work runs through the DB-backed queue, not in-request.** `services/queue.py`:
`enqueue()` inserts a `Job`; `claim_next()` atomically claims one (optimistic
update — no double-claim); handlers register via `@register("type")` and receive
`(db, job, progress_cb)`; failures retry with backoff then dead-letter. Handlers:
`sender.send_campaign`, `importer.run_import_job`, `dsn.poll_dsn`. The worker
(`run_worker`) is a separate process. Endpoints return `{job_id}`; the SPA polls
`GET /api/jobs/{id}`.

**Sending pipeline** (`services/sender.py`, registered as `send_campaign`):
resolve audience (list or segment) → drop suppressed → per recipient: create a
`Message` first (its id seeds tracking tokens), render `{merge}` tags
(`services/merge.py`), rewrite links + inject open pixel (`services/tracking.py`),
build a multipart message with `List-Unsubscribe` (`services/smtp.py`), DKIM-sign
if the domain is verified (`services/dkim.py`), send over one reused `SmtpSession`.
**Idempotent**: one `Message` per `(campaign, contact)`, so re-running resumes.

**Deliverability honesty (important).** Over SMTP, `delivered` and `complaint`
cannot be truthfully sourced — `services/analytics.py:campaign_metrics` returns
them as `None` and the UI shows `—` until ESP webhooks (Phase 4). Bounces come from
the **DSN poller** (`services/dsn.py`), which maps a bounce back to its `Message`
via the original `Message-ID` embedded in the report (tenant-safe), sets
hard/soft-bounce status, and auto-suppresses hard bounces.

**AI** (`ai/service.py`) wraps `google-genai` pinned to `gemini-3-flash-preview`.
Every capability raises `AIDisabled` (→ HTTP 503) when `GEMINI_API_KEY` is unset —
keep this graceful-degradation contract.

**Segments** (`services/segments.py`) compile a JSON rule DSL
(`all`/`any`/`not` + ops `eq,neq,contains,gt,lt,in,exists` over `email|name|status|
attributes.<key>`) to SQLAlchemy filters; unknown op/field raises `ValueError`
(routers map to 422).

## Conventions

- SQLAlchemy 2.0 style (`Mapped`/`mapped_column`, `select()`/`db.scalar(s)`).
- New routers are auto-included by `main.py`'s dynamic loop if the module exposes
  `router`; add the module name there if it's new.
- Tests: `backend/tests/conftest.py` points the app at a throwaway SQLite DB
  (set before import) and recreates the schema per test via the autouse fixture;
  use the `db` Session fixture or `TestClient(app)`.
- Dev `create_all` runs on startup, but **schema changes need an Alembic migration**
  (`render_as_batch=True` is set for SQLite). The migration test asserts a clean
  upgrade/downgrade roundtrip.
