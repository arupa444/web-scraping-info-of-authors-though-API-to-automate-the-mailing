# iceReach — Multi-Tenant, AI-Assisted Email Platform

**One-line:** iceReach is a self-hostable, multi-tenant email marketing platform — contacts & lists, segments, DKIM-signed tracked campaign sends, unsubscribe/suppression, per-campaign analytics, and Gemini-powered AI assists — behind a FastAPI JSON API and a React SPA.

> This repo began as a single-file mailing tool (sender + filter + **scraper**). It has been rebuilt into a platform. The **scraper has been removed**; the legacy `app.py`/templates/CLI are retired in favor of the `backend/icereach` package.

---

## Status — All 6 phases built (205 backend tests green)

**P1 Foundation:** multi-tenant workspaces/users/roles, cookie sessions + CSRF, API keys; contacts, lists, segments (JSON rule engine), background CSV/Excel import (suppression-aware); campaign compose (`{merge}` tags), DB-backed job queue + worker, **DKIM-signed** sends, open/click tracking, one-click `List-Unsubscribe`; sending-domain DKIM keygen + SPF/DKIM/DMARC verify; **DSN bounce poller**; per-campaign analytics.

**P2 Email builder:** block document → client-safe inline-styled table HTML; template library; live `<iframe>` preview (= sent output); reusable saved-blocks; DKIM-signed test sends; campaigns seedable from a template.

**P3 Automation journeys:** enroll → `send` / `wait` / `condition` → done/exited; list-subscribe auto-enrollment; manual/segment enrollment; worker advances due journeys; AI drip drafting.

**P4 Deliverability/ESP:** provider adapters (**SMTP / Resend / SendGrid**); inbound webhooks (delivered/bounce/complaint) that make `delivered`/`complaints` real; **A/B** per-variant analytics + winner; send-time optimization.

**P5 Growth/API:** **signup forms** with double opt-in (hosted + confirm), public **newsletter archive**, public **`/v1` REST API** (API-key auth, incl. transactional `/v1/emails`), outbound webhooks, AI analytics narratives.

**P6 SaaS hardening:** monthly **send quotas** (enforced), **rate limiting** (429 + `Retry-After`), **audit log** + query, **RBAC** role gates, members API, and a **billing scaffold** (plans + checkout that applies a plan — *no live Stripe*).

**AI throughout** — Gemini `gemini-3-flash-preview`: subjects, body drafting, spam/deliverability critique, drip sequences, analytics narratives. Degrades gracefully (HTTP 503) without `GEMINI_API_KEY`. With ESP webhooks (P4) wired, `delivered`/`complaints` become real; over plain SMTP without webhooks they remain `—` (honest).

Design spec + per-phase plans: [spec](docs/superpowers/specs/2026-06-19-icereach-platform-design.md) · [P1](docs/superpowers/plans/2026-06-19-icereach-phase1-foundation.md) · [P2](docs/superpowers/plans/2026-06-19-icereach-phase2-builder.md) · [P3](docs/superpowers/plans/2026-06-19-icereach-phase3-automation.md) · [P4-6](docs/superpowers/plans/2026-06-19-icereach-phase4-6.md)

> **Not production-hardened:** billing is a scaffold; secrets (SMTP/DKIM/ESP/API keys) are stored unencrypted — encrypt at rest before real use; rate limiting is in-memory (single instance).

---

## Architecture

```
React SPA (Vite + TS, frontend/)  ──fetch, cookie session + CSRF──►  FastAPI JSON API (backend/icereach)
                                                                       │   AI service (google-genai, gemini-3-flash-preview)
                                                                       │   SMTP send + DKIM sign + open/click tracking
                                                                       │   DB-backed job queue + worker
                                                                       ▼
                                                          SQLAlchemy 2.0 + Alembic  →  SQLite (default) / Postgres
```

Every table is scoped to a `workspace_id`; tenant isolation is enforced at the query layer via the auth dependency. Long work (sends, imports, DSN polling) runs through the `Job` table + a worker process.

```
backend/icereach/
  config.py db.py main.py            # settings, engine/session, app factory (CORS + CSRF + SPA serving)
  models/                            # tenant-scoped SQLAlchemy models
  security/                          # passwords (argon2), sessions+CSRF, api keys, auth deps
  routers/                           # auth, api_keys, contacts, lists, segments, campaigns,
                                     #   sending_domains, analytics(in campaigns), ai, jobs, public
  services/                          # validation, merge, smtp, dkim, dns_verify, tracking,
                                     #   segments, analytics, importer, sender, dsn, queue
  ai/                                # gemini service + prompts
backend/alembic/                     # migrations
backend/tests/                       # pytest suite
frontend/                            # React SPA
```

---

## Setup

Requires Python **3.12+** and Node **18+**. Use [uv](https://docs.astral.sh/uv/) for Python deps.

```bash
# Backend
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Frontend
cd frontend && npm install && cd ..
```

Configuration is via env / `.env` (all optional in dev): `DATABASE_URL`, `SECRET_KEY`, `BASE_URL`
(public URL for tracking links), `FRONTEND_ORIGIN` (CORS), `GEMINI_API_KEY` (enables AI),
`BOUNCE_IMAP_HOST/USER/PASSWORD` (DSN poller).

---

## Running

**Dev (two processes):**

```bash
# API (auto-reload), serves on a free port
uvicorn icereach.main:app --reload --app-dir backend --port 8000
# SPA (Vite dev server, proxies /api -> :8000)
cd frontend && npm run dev
```

**Single process (serves built SPA + API):**

```bash
cd frontend && npm run build && cd ..
python run.py          # finds a free port, launches uvicorn, opens the browser
```

**Background worker** (processes queued sends/imports/bounces):

```bash
PYTHONPATH=backend python -m icereach.services.queue
```

---

## Database & migrations

SQLite by default; set `DATABASE_URL` to Postgres for production/multi-worker.

```bash
DATABASE_URL=sqlite:///./icereach.db alembic -c backend/alembic.ini upgrade head
```

(The app also `create_all`s on startup for dev convenience; production should rely on Alembic.)

---

## Testing

```bash
pytest backend/tests -q          # 168 backend tests
cd frontend && npm run build     # SPA type-checks + builds
```

---

## API overview

Auth uses an httpOnly session cookie + double-submit CSRF (send the `ice_csrf` cookie value as the `X-CSRF-Token` header on mutations). Programmatic access uses `Authorization: Bearer ice_…` API keys.

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/{signup,login,logout}`, `GET /api/auth/me` |
| API keys | `GET/POST/DELETE /api/api-keys` |
| Contacts | `GET/POST/PATCH/DELETE /api/contacts`, `POST /api/contacts/import` |
| Lists | `GET/POST /api/lists`, `POST/DELETE /api/lists/{id}/contacts...` |
| Segments | `GET/POST/DELETE /api/segments`, `GET /api/segments/{id}/preview` |
| Campaigns | `GET/POST /api/campaigns`, `POST /api/campaigns/{id}/send`, `GET /api/campaigns/{id}/analytics` |
| Sending domains | `POST/GET /api/sending-domains`, `GET .../dns`, `POST .../verify` |
| AI | `POST /api/ai/{subjects,body,critique}` |
| Jobs | `GET /api/jobs/{id}` (poll for progress) |
| Public (no auth) | `GET /t/o/{token}.png` (open), `GET /t/c/{token}` (click), `GET|POST /u/{token}` (unsubscribe) |

Interactive docs at `/docs` when the server is running.

---

## Security & compliance notes

- No public exposure without a reverse proxy + TLS; sessions/CSRF assume HTTPS in production (set secure cookies).
- Deliverability follows 2024 bulk-sender rules: SPF + DKIM + DMARC alignment, `List-Unsubscribe` + one-click. Always honor unsubscribes (enforced via the suppression list).
- Secrets (SMTP/DKIM/API keys) live in the DB — encrypt at rest before any real deployment (tracked for hardening).

## License

MIT.
