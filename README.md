# iceReach — Multi-Tenant, AI-Assisted Email Platform

**One-line:** iceReach is a self-hostable, multi-tenant email marketing platform — contacts & lists, segments, DKIM-signed tracked campaign sends, unsubscribe/suppression, per-campaign analytics, and Gemini-powered AI assists — behind a FastAPI JSON API and a React SPA.

> This repo began as a single-file mailing tool (sender + filter + **scraper**). It has been rebuilt into a platform. The **scraper has been removed**; the legacy `app.py`/templates/CLI are retired in favor of the `backend/icereach` package.

---

## Status — Phases 1–3 built (186 backend tests green)

**Phase 1 — Foundation:** multi-tenant workspaces/users/roles, cookie sessions + CSRF, API keys; contacts, lists, segments (JSON rule engine), background CSV/Excel import (suppression-aware); campaign compose (`{merge}` tags), DB-backed job queue + worker, reused SMTP connection per batch, **DKIM-signed** sends, open/click tracking, one-click `List-Unsubscribe`; sending-domain DKIM keygen + SPF/DKIM/DMARC verify; **DSN bounce poller** → hard/soft bounce + auto-suppression; per-campaign analytics; AI assists.

**Phase 2 — Email builder:** block document → client-safe inline-styled table HTML (heading/text/button/image/divider/spacer/columns); template library; live `<iframe>` preview (= sent output); reusable saved-blocks; DKIM-signed test sends; campaigns seedable from a template.

**Phase 3 — Automation journeys:** enroll → `send` / `wait` / `condition` (segment filter) → done/exited; list-subscribe auto-enrollment; manual/segment enrollment; runs view; worker advances due journeys on idle ticks; AI drip-sequence drafting.

**AI throughout** — Gemini `gemini-3-flash-preview`: subject generation, body drafting, pre-send spam/deliverability critique, drip-sequence drafting. Degrades gracefully (HTTP 503) without `GEMINI_API_KEY`. *(Honest:* `delivered`/`complaints` are not truthfully sourceable over SMTP, so analytics render them as `—` until ESP integration in Phase 4.)*

Remaining phases (P4 ESP adapters + complaint/FBL + A/B + send-time, P5 public API + signup forms + archive, P6 billing/quotas/RBAC/audit UI) are **designed** in the spec and built incrementally. See:

- Design spec (all 6 phases): [docs/superpowers/specs/2026-06-19-icereach-platform-design.md](docs/superpowers/specs/2026-06-19-icereach-platform-design.md)
- Phase plans: [P1](docs/superpowers/plans/2026-06-19-icereach-phase1-foundation.md) · [P2](docs/superpowers/plans/2026-06-19-icereach-phase2-builder.md) · [P3](docs/superpowers/plans/2026-06-19-icereach-phase3-automation.md)

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
