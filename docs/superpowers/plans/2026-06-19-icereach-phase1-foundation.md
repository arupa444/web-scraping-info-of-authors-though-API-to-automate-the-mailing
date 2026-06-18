# iceReach Phase 1 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy single-file iceReach app with a multi-tenant, database-backed FastAPI backend that authenticates users, manages contacts/lists/segments, sends DKIM-signed tracked campaigns over SMTP, handles unsubscribe/suppression, exposes per-campaign analytics, and offers Gemini-powered AI assists — fronted by a React SPA shell.

**Architecture:** A package-structured FastAPI app (`backend/icereach/`) using SQLAlchemy 2.0 + Alembic (SQLite default, Postgres-swappable). Every table carries `workspace_id`; a request-scoped dependency enforces tenant isolation. Long work (sends, imports, DSN polling) runs through a DB-backed `Job` table + worker, evolving the current in-memory `JobManager`. A React (Vite + TS + TanStack Query + Tailwind + shadcn/ui) SPA talks to the JSON API over httpOnly cookie sessions with CSRF. AI lives behind one `ai/service.py` wrapping `google-genai` (`gemini-3-flash-preview`), degrading gracefully without a key.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, argon2-cffi (password hashing), itsdangerous (signed cookies/CSRF), dkimpy (DKIM signing), dnspython, google-genai, pytest + httpx TestClient; React 18, Vite, TypeScript, TanStack Query, React Router, Tailwind, shadcn/ui, Vitest.

**Reference spec:** `docs/superpowers/specs/2026-06-19-icereach-platform-design.md` (authoritative for data model §4, API §5, security §6, sending/tracking §7, deliverability §8, AI §9, analytics §10, SPA §11, acceptance §12).

**Honest delivery note (from spec §2):** Over SMTP, `delivered` and `complaint` are not truthfully sourceable; Phase 1 reports `sent`, opens, clicks, unsubscribes, and `hard/soft bounce` (from the DSN poller). `delivered_count` / `complaint_count` render as "—" until Phase 4.

---

## File Structure

```
backend/
  icereach/
    __init__.py
    main.py                 # FastAPI app factory, router registration, lifespan
    config.py               # pydantic-settings: DB url, secret key, base URL, GEMINI_API_KEY
    db.py                   # engine, SessionLocal, Base, get_db dependency
    models/
      __init__.py           # re-export all models
      base.py               # TimestampMixin, WorkspaceScopedMixin (workspace_id)
      workspace.py          # Workspace, User, Membership, Session, ApiKey
      contact.py            # Contact, ContactList, ListMembership, Segment, Suppression
      sending.py            # SendingDomain, Template, Campaign, CampaignVariant, Message, Event
      job.py                # Job, AuditLog, AIUsage
    schemas/                # Pydantic request/response models, one module per resource
    security/
      passwords.py          # argon2 hash/verify
      sessions.py           # signed session cookies, CSRF token issue/verify
      apikeys.py            # generate/hash/verify API keys (prefix + secret)
      deps.py               # current_user, current_workspace, require_role, api_key_auth
    routers/
      auth.py contacts.py lists.py segments.py campaigns.py
      analytics.py suppressions.py sending_domains.py ai.py
      public.py             # tracking pixel, click redirect, unsubscribe (no auth)
      jobs.py               # job status/list
    services/
      validation.py         # ported syntax+MX-cache ladder from app.py
      merge.py              # ported render_template + plaintext (HTML->text)
      smtp.py               # SmtpSession (ported) + DKIM signing
      dkim.py               # keygen, DNS record render, sign
      dns_verify.py         # SPF/DKIM/DMARC publish-and-verify
      tracking.py           # link rewrite, pixel/click token encode/decode, bot filter
      sender.py             # campaign send job: render, suppress-check, send, record Message/Event
      dsn.py                # return-path mailbox poller -> bounce events -> suppression
      segments.py           # segment rule evaluation engine
      analytics.py          # per-campaign aggregation
      queue.py              # DB-backed job claim/run/retry + worker loop
    ai/
      service.py            # gemini-3-flash-preview wrapper + degrade-without-key
      prompts.py            # prompt builders for subject/body/critique
  alembic/                  # migrations env + versions
  alembic.ini
  tests/                    # pytest: one module per router/service
frontend/
  (Vite React TS app: src/api, src/auth, src/pages, src/components, src/lib)
```

---

## Work-stream order

1. **WS-A** Project skeleton + config + DB + Base mixins
2. **WS-B** Models + Alembic migration
3. **WS-C** Auth: passwords, sessions, CSRF, signup/login/logout, workspace bootstrap, deps
4. **WS-D** API keys + tenant-scoping dependency
5. **WS-E** Contacts + Lists + import/validation (ports `validation.py`)
6. **WS-F** Segments engine
7. **WS-G** Sending domain: DKIM keygen + DNS verify
8. **WS-H** Campaign compose + send job (merge, DKIM sign, suppression, tracking) + DB queue/worker
9. **WS-I** Public endpoints: open pixel, click redirect, unsubscribe + suppression
10. **WS-J** DSN bounce poller
11. **WS-K** Analytics aggregation
12. **WS-L** AI service (Gemini) + endpoints
13. **WS-M** React SPA shell + auth + contacts/lists/campaign/analytics pages
14. **WS-N** Scraper removal + legacy cleanup + docs/deps

Each task below is TDD where logic warrants it. Commit after every task.

---

## WS-A — Skeleton, config, DB

### Task A1: Backend package + dependencies

**Files:**
- Create: `backend/icereach/__init__.py`, `backend/icereach/config.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add deps** (use `uv pip install` inside `.venv`, then record in pyproject):
  `sqlalchemy>=2.0`, `alembic`, `argon2-cffi`, `itsdangerous`, `dkimpy`, `google-genai`, `pytest`, `pytest-asyncio`, `httpx`. dnspython/pandas/fastapi already present.
- [ ] **Step 2: Write `config.py`** with pydantic-settings `Settings`:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./icereach.db"
    secret_key: str = "dev-insecure-change-me"
    base_url: str = "http://127.0.0.1:8000"     # public URL for tracking links
    gemini_api_key: str = ""
    session_cookie: str = "ice_session"
    csrf_cookie: str = "ice_csrf"
    session_max_age: int = 60 * 60 * 24 * 14

settings = Settings()
```
- [ ] **Step 3: Commit** `feat(backend): scaffold package + settings`.

### Task A2: DB engine, Base, session dependency

**Files:** Create `backend/icereach/db.py`; Test `backend/tests/test_db.py`

- [ ] **Step 1: Failing test** — `test_get_db_yields_session` opens `get_db()` generator, asserts it yields a `Session` and `execute(text("select 1"))` returns 1.
- [ ] **Step 2: Implement** engine from `settings.database_url` (with `connect_args={"check_same_thread": False}` for SQLite), `SessionLocal`, `class Base(DeclarativeBase)`, `get_db()` dependency (try/finally close).
- [ ] **Step 3: Run** `pytest backend/tests/test_db.py -v` → PASS.
- [ ] **Step 4: Commit** `feat(backend): db engine + session dependency`.

---

## WS-B — Models + migration

### Task B1: Base mixins

**Files:** Create `backend/icereach/models/base.py`

- [ ] **Step 1:** Implement `TimestampMixin` (`created_at`, `updated_at` server defaults) and `WorkspaceScopedMixin` (`workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)`).
- [ ] **Step 2: Commit** `feat(models): timestamp + workspace-scope mixins`.

### Task B2: Identity models

**Files:** Create `backend/icereach/models/workspace.py`; Test `backend/tests/test_models_identity.py`

- [ ] **Step 1: Failing test** — create a `Workspace`, `User`, `Membership(role="owner")`, flush, assert relationships resolve and `Membership` uniqueness on `(workspace_id, user_id)`.
- [ ] **Step 2: Implement** per spec §4: `Workspace(id,name,slug unique)`, `User(id,email unique,password_hash,name,is_active)`, `Membership(workspace_id,user_id,role)`, `Session(id,token_hash,user_id,workspace_id,expires_at)`, `ApiKey(id,workspace_id,prefix,secret_hash,name,scopes,last_used_at,revoked_at)`.
- [ ] **Step 3:** Run test → PASS. **Commit** `feat(models): workspace, user, membership, session, apikey`.

### Task B3: Contact models

**Files:** Create `backend/icereach/models/contact.py`; Test `backend/tests/test_models_contact.py`

- [ ] **Step 1: Failing test** — Contact with unique `(workspace_id, email)`; ListMembership status enum; Suppression unique `(workspace_id, email)`.
- [ ] **Step 2: Implement** per spec §4: `Contact(workspace_id,email,name,attributes JSON,status,source)`, `ContactList(workspace_id,name)`, `ListMembership(list_id,contact_id,status[subscribed|unsubscribed|pending|cleaned],subscribed_at)`, `Segment(workspace_id,name,rules JSON)`, `Suppression(workspace_id,email,reason[hard_bounce|complaint|unsubscribe|manual],created_at)`.
- [ ] **Step 3:** Run → PASS. **Commit** `feat(models): contacts, lists, segments, suppression`.

### Task B4: Sending models

**Files:** Create `backend/icereach/models/sending.py`; Test `backend/tests/test_models_sending.py`

- [ ] **Step 1: Failing test** — Campaign with variants; Message unique `(campaign_id, contact_id, variant_id)`; Event FK to Message.
- [ ] **Step 2: Implement** per spec §4: `SendingDomain(workspace_id,domain,dkim_selector,dkim_private_key,spf_verified,dkim_verified,dmarc_verified,status)`, `Template(workspace_id,name,subject,html,text)`, `Campaign(workspace_id,name,status,sending_domain_id,from_name,from_email,list_id?,segment_id?,scheduled_at,sent_at)`, `CampaignVariant(campaign_id,subject,html,text,weight)`, `Message(workspace_id,campaign_id,contact_id,variant_id,status[queued|sent|hard_bounce|soft_bounce|failed],message_id,sent_at,error)`, `Event(workspace_id,message_id,type[open|click|unsubscribe|bounce],url,user_agent,ip_hash,created_at)`.
- [ ] **Step 3:** Run → PASS. **Commit** `feat(models): sending domain, template, campaign, message, event`.

### Task B5: Job/audit/AI models + Alembic baseline

**Files:** Create `backend/icereach/models/job.py`, `backend/icereach/models/__init__.py`; Create `backend/alembic.ini`, `backend/alembic/env.py`; Test `backend/tests/test_migration.py`

- [ ] **Step 1: Implement** `Job(workspace_id,type,status,progress,payload JSON,result JSON,error,attempts,run_after,created_at)`, `AuditLog(workspace_id,user_id,action,target,meta JSON)`, `AIUsage(workspace_id,feature,tokens,created_at)`. `models/__init__.py` imports all.
- [ ] **Step 2:** `alembic init`, point `env.py` `target_metadata = Base.metadata`, url from `settings`.
- [ ] **Step 3:** `alembic revision --autogenerate -m "baseline"`; inspect the version file lists every table.
- [ ] **Step 4: Failing-then-pass test** — `test_migration_roundtrip`: run `alembic upgrade head` against a temp SQLite, assert all tables exist via `inspect(engine).get_table_names()`, then `alembic downgrade base` cleanly.
- [ ] **Step 5:** Run → PASS. **Commit** `feat(db): job/audit/ai models + alembic baseline`.

---

## WS-C — Auth

### Task C1: Password hashing

**Files:** Create `backend/icereach/security/passwords.py`; Test `backend/tests/test_passwords.py`

- [ ] **Step 1: Failing test** — `verify(hash(pw), pw)` True; wrong pw False; two hashes of same pw differ (salt).
- [ ] **Step 2: Implement** with `argon2.PasswordHasher` (`hash`, `verify` swallowing `VerifyMismatchError`→False).
- [ ] **Step 3:** Run → PASS. **Commit** `feat(security): argon2 password hashing`.

### Task C2: Sessions + CSRF

**Files:** Create `backend/icereach/security/sessions.py`; Test `backend/tests/test_sessions.py`

- [ ] **Step 1: Failing test** — issue a session token, store hash, resolve it back to user/workspace; expired token rejected; CSRF token round-trips and a tampered token fails.
- [ ] **Step 2: Implement** opaque random session token (store only `sha256` in `Session`), helpers `create_session(db,user,workspace)`, `resolve_session(db,token)`, and CSRF via `itsdangerous.URLSafeTimedSerializer` (double-submit: cookie + `X-CSRF-Token` header must match).
- [ ] **Step 3:** Run → PASS. **Commit** `feat(security): session tokens + CSRF`.

### Task C3: Auth dependencies

**Files:** Create `backend/icereach/security/deps.py`; Test `backend/tests/test_deps.py`

- [ ] **Step 1: Failing test** — `current_user` raises 401 without cookie; returns user with valid session; `require_role("admin")` raises 403 for member.
- [ ] **Step 2: Implement** `current_user`, `current_workspace` (from session's workspace), `require_role(*roles)` factory, and `enforce_csrf` dependency for mutating routes.
- [ ] **Step 3:** Run → PASS. **Commit** `feat(security): auth + tenant + role dependencies`.

### Task C4: Auth router (signup/login/logout/me)

**Files:** Create `backend/icereach/routers/auth.py`, `backend/icereach/schemas/auth.py`, `backend/icereach/main.py`; Test `backend/tests/test_auth_flow.py`

- [ ] **Step 1: Failing test** (TestClient) — POST `/api/auth/signup` {email,password,workspace_name} → 201, sets session cookie, creates Workspace+User+owner Membership; POST `/api/auth/login` wrong pw → 401; GET `/api/auth/me` with cookie → user+workspace; POST `/api/auth/logout` clears session.
- [ ] **Step 2: Implement** `create_app()` factory in `main.py` (registers routers, CORS for the SPA origin with credentials), and the four endpoints. Signup is transactional: user + workspace + membership + session.
- [ ] **Step 3:** Run → PASS. **Commit** `feat(auth): signup/login/logout/me`.

---

## WS-D — API keys + scoping

### Task D1: API key issue/verify

**Files:** Create `backend/icereach/security/apikeys.py`, `backend/icereach/routers/api_keys.py`; Test `backend/tests/test_apikeys.py`

- [ ] **Step 1: Failing test** — generate key returns `ice_<prefix>_<secret>` once; only `secret_hash`+`prefix` stored; `api_key_auth` resolves a valid `Authorization: Bearer` to its workspace; revoked key → 401.
- [ ] **Step 2: Implement** `generate()`, `hash_secret()`, `verify()`, an `api_key_auth` dependency (lookup by prefix, constant-time compare hash, update `last_used_at`), and CRUD endpoints (`POST/GET/DELETE /api/api-keys`).
- [ ] **Step 3:** Run → PASS. **Commit** `feat(security): API keys + programmatic auth`.

---

## WS-E — Contacts, Lists, Import/Validation

### Task E1: Port validation ladder

**Files:** Create `backend/icereach/services/validation.py`; Test `backend/tests/test_validation.py`

- [ ] **Step 1: Failing test** — `is_valid_syntax` accepts/rejects; `resolve_mx_hosts` is cached (monkeypatch resolver, call twice, assert one lookup); `validate_email` returns the 3-state ladder.
- [ ] **Step 2: Implement** by porting `app.py`'s `_get_resolver`, `_mx_cache`, `resolve_mx_hosts`, `is_valid_syntax`, `has_mx_record`, `validate_email` verbatim into this module (no behavior change).
- [ ] **Step 3:** Run → PASS. **Commit** `feat(services): port email validation ladder`.

### Task E2: Contacts CRUD + list management

**Files:** Create `backend/icereach/routers/contacts.py`, `backend/icereach/routers/lists.py`, `backend/icereach/schemas/contact.py`; Test `backend/tests/test_contacts.py`

- [ ] **Step 1: Failing test** — authed POST `/api/contacts` creates a contact scoped to the caller's workspace; a second workspace cannot read it (404); `POST /api/lists` + `POST /api/lists/{id}/contacts` adds membership; duplicate email in same workspace → 409.
- [ ] **Step 2: Implement** CRUD with every query filtered by `current_workspace`. List add/remove manages `ListMembership` with `status="subscribed"`.
- [ ] **Step 3:** Run → PASS. **Commit** `feat(contacts): contacts + lists CRUD (tenant-scoped)`.

### Task E3: CSV/Excel import as a background job

**Files:** Modify `backend/icereach/routers/contacts.py`; Create import handler in `backend/icereach/services/importer.py`; Test `backend/tests/test_import.py`

- [ ] **Step 1: Failing test** — POST `/api/contacts/import` (CSV upload, `validate=true`) returns a `job_id`; running the job inline creates contacts, skips invalid syntax, records counts in `Job.result`; suppressed emails are not subscribed.
- [ ] **Step 2: Implement** importer that reuses pandas read (ported from `app.py`), `validate_email` per row, upserts contacts, attaches to a target list, writes progress via the queue's progress callback.
- [ ] **Step 3:** Run → PASS. **Commit** `feat(contacts): background CSV/Excel import with validation`.

---

## WS-F — Segments

### Task F1: Segment rule engine

**Files:** Create `backend/icereach/services/segments.py`, `backend/icereach/routers/segments.py`; Test `backend/tests/test_segments.py`

- [ ] **Step 1: Failing test** — a rule `{"all":[{"field":"attributes.country","op":"eq","value":"US"},{"field":"status","op":"eq","value":"subscribed"}]}` resolves to the right contacts; `any`/`not` combinators work; unknown op → 422.
- [ ] **Step 2: Implement** a translator from the JSON rule DSL (spec §4/§5) to SQLAlchemy filters over `Contact` (+ JSON attribute access), with `all`/`any`/`not` and ops `eq,neq,contains,gt,lt,in,exists`. Endpoints: CRUD + `GET /api/segments/{id}/preview` (count + sample).
- [ ] **Step 3:** Run → PASS. **Commit** `feat(segments): JSON rule engine + preview`.

---

## WS-G — Sending domain (DKIM + DNS verify)

### Task G1: DKIM keygen + record render

**Files:** Create `backend/icereach/services/dkim.py`; Test `backend/tests/test_dkim.py`

- [ ] **Step 1: Failing test** — `generate_keypair()` returns PEM private + a DNS TXT value starting `v=DKIM1; k=rsa; p=`; `sign(message_bytes, domain, selector, private_key)` returns a `DKIM-Signature:` header that `dkim.verify` accepts against the published public key (use an in-test resolver stub).
- [ ] **Step 2: Implement** keygen with `cryptography`, DNS record render, and `sign()` via `dkimpy`.
- [ ] **Step 3:** Run → PASS. **Commit** `feat(deliverability): DKIM keygen + signing`.

### Task G2: SPF/DKIM/DMARC verify + sending-domain endpoints

**Files:** Create `backend/icereach/services/dns_verify.py`, `backend/icereach/routers/sending_domains.py`; Test `backend/tests/test_dns_verify.py`

- [ ] **Step 1: Failing test** — given a stubbed resolver, `verify_spf/verify_dkim/verify_dmarc(domain)` return booleans; `POST /api/sending-domains` returns the DNS records to publish; `POST /api/sending-domains/{id}/verify` flips the verified flags and `status`.
- [ ] **Step 2: Implement** verifiers (TXT lookups via the shared resolver) and endpoints; the MAIL FROM/return-path is pinned to `bounce.<domain>` for SPF alignment (spec §8.4).
- [ ] **Step 3:** Run → PASS. **Commit** `feat(deliverability): SPF/DKIM/DMARC verify + sending-domain API`.

---

## WS-H — Campaign send pipeline + queue

### Task H1: DB-backed job queue + worker

**Files:** Create `backend/icereach/services/queue.py`, `backend/icereach/routers/jobs.py`; Test `backend/tests/test_queue.py`

- [ ] **Step 1: Failing test** — `enqueue(db, workspace_id, type, payload)` inserts a `Job(status="queued")`; `claim_next()` atomically marks one `running` (no double-claim across two calls); a handler that raises increments `attempts` and reschedules until max → `failed` (DLQ). `GET /api/jobs/{id}` returns status/progress.
- [ ] **Step 2: Implement** claim via `UPDATE ... WHERE id IN (SELECT id ... status='queued' ORDER BY run_after LIMIT 1)` returning the row (SQLite-safe transaction), a registry mapping `type`→handler, a `progress_cb`, retry with backoff, DLQ + an `on_dlq` alert hook (log). Worker loop `run_worker()` for a separate process.
- [ ] **Step 3:** Run → PASS. **Commit** `feat(queue): DB-backed job queue + worker + DLQ`.

### Task H2: Port merge renderer + plaintext + SmtpSession

**Files:** Create `backend/icereach/services/merge.py`, `backend/icereach/services/smtp.py`; Test `backend/tests/test_merge.py`, `backend/tests/test_smtp.py`

- [ ] **Step 1: Failing test (merge)** — `render(content,row)` fills `{name}`, leaves unknown `{x}` intact; `html_to_text(html)` strips tags deterministically and keeps links as `text (url)`.
- [ ] **Step 2: Implement merge** by porting `render_template` and adding `html_to_text` (use a small deterministic HTML→text; no external service).
- [ ] **Step 3: Failing test (smtp)** — `SmtpSession` reuse + reconnect (stub `smtplib.SMTP`), and `send()` accepts a pre-built MIME message and DKIM-signs it before send.
- [ ] **Step 4: Implement smtp** by porting `SmtpSession` from `app.py`, adding a `build_message(...)` that creates multipart/alternative (text+html), sets `List-Unsubscribe` + `List-Unsubscribe-Post`, and DKIM-signs.
- [ ] **Step 5:** Run both → PASS. **Commit** `feat(services): port merge+smtp, add plaintext + DKIM + List-Unsubscribe`.

### Task H3: Tracking link rewrite + token codec

**Files:** Create `backend/icereach/services/tracking.py`; Test `backend/tests/test_tracking.py`

- [ ] **Step 1: Failing test** — `rewrite_links(html, message_id)` turns `<a href="x">` into `{base_url}/t/c/{token}` and appends a `{base_url}/t/o/{token}.png` pixel; `decode(token)` round-trips `(message_id, original_url)`; tampered token rejected; a known bot User-Agent is filtered by `is_bot(ua)`.
- [ ] **Step 2: Implement** signed tokens (`itsdangerous`), link rewriting (parse anchors), pixel injection, and a bot UA denylist (spec §7).
- [ ] **Step 3:** Run → PASS. **Commit** `feat(tracking): link rewrite + signed open/click tokens + bot filter`.

### Task H4: Campaign send job

**Files:** Create `backend/icereach/services/sender.py`, `backend/icereach/routers/campaigns.py`, `backend/icereach/schemas/campaign.py`; Test `backend/tests/test_send.py`

- [ ] **Step 1: Failing test** — create campaign → `POST /api/campaigns/{id}/send` enqueues a send job; running it (stubbed SMTP) creates one `Message` per subscribed, non-suppressed recipient with `status="sent"`, rewrites links, DKIM-signs, and is **idempotent** (re-running creates no duplicate Messages due to the unique `(campaign_id,contact_id,variant_id)`).
- [ ] **Step 2: Implement** `send_campaign(job)`: resolve audience (list or segment), exclude suppressed, pick variant by weight, render+rewrite per recipient, send via one `SmtpSession`, record `Message` (+ progress), mark campaign `sent`.
- [ ] **Step 3:** Run → PASS. **Commit** `feat(campaigns): compose + tracked, DKIM-signed, idempotent send job`.

---

## WS-I — Public tracking + unsubscribe

### Task I1: Open/click/unsubscribe endpoints

**Files:** Create `backend/icereach/routers/public.py`; Test `backend/tests/test_public.py`

- [ ] **Step 1: Failing test** — GET `/t/o/{token}.png` returns a 1x1 gif and records an `open` Event (bot UA → no event); GET `/t/c/{token}` 302-redirects to the original URL and records a `click`; GET `/u/{token}` shows a confirm page, POST confirms → adds `Suppression(reason=unsubscribe)`, sets `ListMembership.status=unsubscribed`, records `unsubscribe` Event; one-click `List-Unsubscribe-Post` works without the page.
- [ ] **Step 2: Implement** all three (no auth), decoding tokens, deduping opens/clicks per message, enforcing bot filter.
- [ ] **Step 3:** Run → PASS. **Commit** `feat(public): open/click tracking + unsubscribe + suppression`.

---

## WS-J — DSN bounce poller

### Task J1: Return-path DSN polling

**Files:** Create `backend/icereach/services/dsn.py`; Test `backend/tests/test_dsn.py`

- [ ] **Step 1: Failing test** — given a fixture DSN/MAILER-DAEMON message (multipart/report), `parse_dsn(raw)` extracts the failed recipient + status; processing it sets the matching `Message.status` to `hard_bounce` (5.x.x) or `soft_bounce` (4.x.x) and, on hard bounce, adds a `Suppression(reason=hard_bounce)`.
- [ ] **Step 2: Implement** an IMAP poller (config: bounce mailbox creds) registered as a job type `poll_dsn`, plus the parser (use `email` stdlib `message/delivery-status`).
- [ ] **Step 3:** Run → PASS. **Commit** `feat(deliverability): DSN bounce poller -> bounce events + suppression`.

---

## WS-K — Analytics

### Task K1: Per-campaign aggregation

**Files:** Create `backend/icereach/services/analytics.py`, `backend/icereach/routers/analytics.py`; Test `backend/tests/test_analytics.py`

- [ ] **Step 1: Failing test** — with seeded Messages/Events, `GET /api/campaigns/{id}/analytics` returns `sent`, `hard_bounce`, `soft_bounce`, `unique_opens`, `total_opens`, `unique_clicks`, `total_clicks`, `ctr`, `ctor`, `unsubscribes`, and `delivered=null`, `complaints=null` (spec §2.3/§10).
- [ ] **Step 2: Implement** aggregation queries (counts grouped by event type, unique by `(message_id)`), workspace-scoped. Null-render delivered/complaints.
- [ ] **Step 3:** Run → PASS. **Commit** `feat(analytics): per-campaign metrics (phase-honest)`.

---

## WS-L — AI service

### Task L1: Gemini wrapper + degrade

**Files:** Create `backend/icereach/ai/service.py`, `backend/icereach/ai/prompts.py`; Test `backend/tests/test_ai.py`

- [ ] **Step 1: Failing test** — with no `GEMINI_API_KEY`, `generate_subjects(brief)` raises a typed `AIDisabled` (router maps to 503 with a clear message); with a stubbed client, it returns a list of `{subject,preheader,rationale}` and records an `AIUsage` row.
- [ ] **Step 2: Implement** a thin client over `google-genai` pinned to `gemini-3-flash-preview`, structured-output prompts (subjects, body draft, spam/deliverability critique), guardrails (length caps, drop high spam-risk), and `AIUsage` logging.
- [ ] **Step 3: Commit** `feat(ai): gemini-3-flash-preview service + usage logging`.

### Task L2: AI endpoints

**Files:** Create `backend/icereach/routers/ai.py`, `backend/icereach/schemas/ai.py`; Test `backend/tests/test_ai_router.py`

- [ ] **Step 1: Failing test** — authed `POST /api/ai/subjects`, `/api/ai/body`, `/api/ai/critique` return the expected shapes (stubbed service); unauth → 401.
- [ ] **Step 2: Implement** the three endpoints delegating to the service.
- [ ] **Step 3: Commit** `feat(ai): subject/body/critique endpoints`.

---

## WS-M — React SPA

### Task M1: Vite app + API client + auth

**Files:** Create `frontend/` (Vite React TS), `frontend/src/lib/api.ts`, `frontend/src/auth/*`; Test `frontend/src/lib/api.test.ts` (Vitest)

- [ ] **Step 1:** Scaffold `npm create vite@latest frontend -- --template react-ts`; add TanStack Query, React Router, Tailwind, shadcn/ui; configure Vite dev proxy `/api`→backend and `credentials: 'include'`.
- [ ] **Step 2: Failing test** — `api.ts` attaches the CSRF header from cookie on mutations; 401 triggers redirect-to-login callback.
- [ ] **Step 3: Implement** typed fetch client, `AuthProvider` (uses `/api/auth/me`), login/signup forms.
- [ ] **Step 4:** `npm run build` succeeds; `vitest run` passes. **Commit** `feat(spa): vite shell + api client + auth`.

### Task M2: Core pages

**Files:** Create `frontend/src/pages/{Contacts,Lists,Campaigns,CampaignCompose,Analytics,Settings}.tsx`

- [ ] **Step 1:** Build Contacts (table + import), Lists, Campaign compose (subject/html + merge tag helper + **AI assist buttons** calling `/api/ai/*` + pre-send critique), Campaign list with send + live progress (poll `/api/jobs/{id}`), Analytics dashboard (cards from `/api/campaigns/{id}/analytics`, "—" for delivered/complaints), Settings (sending domains with DNS records to publish + verify button, API keys).
- [ ] **Step 2:** `npm run build` succeeds. Manually verify against a running backend (signup → add contacts → compose with AI → send to a Mailpit/local SMTP → see analytics).
- [ ] **Step 3: Commit** `feat(spa): contacts, lists, campaigns, analytics, settings`.

---

## WS-N — Scraper removal + cleanup

### Task N1: Remove scraper + retire legacy

**Files:** Delete scraper code from legacy `app.py`/templates; remove `templates/email_scraper.html`, `CLI_files/scrapName.py`; update `README.md`, `CLAUDE.md`, `pyproject.toml`, `run.py`.

- [ ] **Step 1: Failing test** — `backend/tests/test_no_scraper.py` asserts there is no route containing `scrape` in the new app and `search_pubmed` is not importable from the backend package.
- [ ] **Step 2: Implement** removal: delete the scraper router/functions/template/CLI; point `run.py` at `icereach.main:create_app`; update docs to describe the platform (remove scraping); ensure `uv pip` deps reflect additions/removals.
- [ ] **Step 3:** Run full suite `pytest backend/tests -q` → all PASS; `npm run build` → success. **Commit** `feat: remove email scraper; retire legacy app in favor of backend package`.

---

## Definition of Done (Phase 1)

- `pytest backend/tests -q` green; `alembic upgrade head` then `downgrade base` clean.
- Backend boots: `uvicorn icereach.main:create_app --factory`.
- Worker runs: `python -m icereach.services.queue` processes a send job.
- Manual E2E: signup → import contacts → create sending domain (see DNS records) → compose campaign (AI subject + critique) → send to local SMTP (Mailpit) → open/click/unsubscribe recorded → analytics show sent/opens/clicks/unsub with delivered/complaints as "—".
- SPA `npm run build` succeeds and the core flow works against the backend.
- No `scrape`/PubMed code remains.

## Out of scope (later phases, per spec §12)

Drag-drop builder (P2); automation journeys (P3); ESP adapters + complaint/FBL + A/B + send-time (P4); signup forms + public archive + public API + AI analytics narratives (P5); billing + quotas + RBAC + observability (P6).
