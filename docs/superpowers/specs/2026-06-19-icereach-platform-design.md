# iceReach Platform — Design Spec

> **Status:** Authoritative single source of truth for the iceReach build (all phases).
> **Supersedes:** the legacy single-file FastAPI app (`app.py`), Jinja/Bootstrap templates, the in-memory `JobManager` (`jobs.py`), and the email Scraper (removed entirely).
> **Locked decisions** (do not revisit): Scraper removed; tenant-aware from day 1; React SPA (Vite + TS + TanStack Query + React Router + Tailwind + shadcn/ui) against a FastAPI JSON API; SQLAlchemy 2.0 + Alembic, SQLite default / Postgres-swappable; httpOnly cookie sessions + CSRF for the SPA, separate API keys for programmatic access; DB-backed job queue evolving the current `JobManager`, arq/Redis later; AI via Google Gemini `gemini-3-flash-preview` through one AI service module; ESP adapter layer (SMTP today, SES/Resend/SendGrid later).

---

## 1. Overview & Goals

iceReach evolves an existing single-file FastAPI mailing tool into a multi-tenant, best-in-class email marketing platform. The current app sends personalized HTML email over a user-supplied SMTP server, validates addresses (syntax + cached MX), renders `{column}` merge tags from CSV rows, and runs long operations through an in-memory background job manager. It has no database, no auth, no persistence, no tracking, and no compliance handling. iceReach keeps the parts that work (the merge renderer, the validation ladder, the MX cache, the job-polling UX) and rebuilds everything else on a durable, tenant-isolated, deliverability-correct foundation.

**Primary goals**

1. **Tenant-isolated SaaS.** Every record is scoped to a `workspace_id`; isolation is enforced structurally at the data layer, never by reviewer diligence.
2. **Deliverability that survives 2024+ mailbox rules.** SPF + DKIM + DMARC alignment, List-Unsubscribe + one-click (RFC 8058), suppression law, complaint/bounce circuit-breakers, and warmup are first-class — not deferred. (See §8 and the honest delivery note in §2 for exactly what is buildable in the first phase under SMTP.)
3. **Durable, resumable sending.** A worker crash or `uvicorn --reload` must never double-send, skip, or drop a recipient.
4. **AI as an additive assistant.** Gemini drafts subjects, bodies, plaintext, and critiques deliverability — always behind one service module, always human-in-the-loop, never authoritative for compliance, fully degradable when `GEMINI_API_KEY` is absent.
5. **Typed, API-first SPA.** A React SPA talks only to a versioned JSON API whose types it generates from OpenAPI.
6. **Incremental, honest delivery.** All six phases are designed here; §2 and §12 state precisely what is built-and-tested versus scaffolded in the first build.

**Non-goals (this build):** real-time inbox/seed-box deliverability testing networks, a visual analytics warehouse, and a full marketplace of ESP integrations beyond the adapter seam.

---

## 2. Scope & Honest Delivery Note

All six phases are *designed* in this document. The first build does not implement all six. This section is the honest contract about what is realistically **built and tested**, **implemented (core)**, or **scaffolded** in the first build, and — critically — it resolves the single largest design hazard the critics raised: **a P1 platform must not present delivery signals (delivered/bounce/complaint) or pass a preflight gate that depends on infrastructure that only exists in P4.**

### 2.1 The two hard truths about P1 (SMTP-only)

1. **SMTP `sendmail()` success ≠ delivered.** Over SMTP, the relay accepting a message means *accepted for relay*, nothing more. Bounces and complaints arrive **asynchronously** as DSN/MAILER-DAEMON messages to the return-path mailbox and as ARF/FBL reports — they are not returned by `sendmail()`. Therefore any "delivered", "hard_bounce", "soft_bounce", or "complaint" signal needs an ingestion source.
2. **Gmail/Yahoo bulk-sender rules (Feb 2024) require SPF + DKIM + DMARC alignment for senders above ~5k/day.** A bulk send without DKIM signing and a DMARC-aligned MAIL FROM will be junked or rejected. A preflight that hard-blocks on "unverified/unsigned domain" is incoherent if the verification + signing code is P4.

iceReach resolves both by **moving the load-bearing pieces of email authentication into P1** and by **labeling every analytics metric with the phase that populates it**.

### 2.2 What moves into P1 (out of the original P4 placement)

- **DKIM signing + SPF/DKIM/DMARC DNS publish-and-verify** for the *single configured sending domain* move to **P1**. P1 ships the `SendingDomain` verification pipeline (generate selector + keypair, render DNS records, poll-and-verify SPF/DKIM/DMARC) and DKIM-signs every outbound message. The MAIL FROM / return-path domain is pinned to an iceReach-controlled subdomain of the verified sending domain so **SPF aligns under DMARC** (see §8.4).
- **A return-path bounce mailbox + DSN poller** moves to **P1** so `hard_bounce`/`soft_bounce` have a real source under SMTP. **Complaint/FBL (ARF) ingestion remains P4** (it requires per-ESP FBL registration that SMTP self-hosting generally cannot provide).

### 2.3 Per-metric phase ownership (authoritative)

| Metric / signal | Source | Populated in |
|---|---|---|
| `sent` / `accepted` | SMTP relay accepted (classified `SendResult`) | **P1** |
| `hard_bounce` / `soft_bounce` | **P1:** return-path DSN poller. **P4:** ESP webhooks | **P1** (DSN) |
| `delivered` | **P1:** *not separately confirmable over SMTP* — `sent` is the terminal positive state and reports label opens/clicks against `sent`, not `delivered`. **P4:** ESP delivery webhooks populate true `delivered` | **P4** (true delivery); P1 shows `sent` |
| `complaint` | **P4:** FBL/ARF (SMTP) and ESP complaint webhooks. **P1:** only a manual/one-click-unsub proxy | **P4** |
| `open` / `click` | iceReach pixel + click redirect (bot-filtered) | **P1** |
| `unsubscribe` | one-click + hosted page | **P1** |
| auto-suppress on `hard_bounce` | DSN poller → suppression | **P1** |
| auto-suppress on `complaint` | FBL/ESP webhook → suppression | **P4** |

P1 campaign analytics therefore show: sent, **hard/soft bounces (from DSN)**, opens (unique/total, bot-filtered), clicks (unique/total), CTR, CTOR, unsubscribes. **`delivered_count` and `complaint_count` render as "—" (not yet available) in P1** and become live in P4. Counters never claim a number they cannot source.

### 2.4 Build-status matrix

| Phase | Built & tested | Implemented (core) | Scaffolded only |
|---|---|---|---|
| **P1** | tenant DB + migrations; auth + sessions + CSRF + API keys; SPA shell; contacts/lists/import+validate; campaign compose + DKIM-signed send to list/segment; open/click tracking; unsubscribe + suppression + List-Unsubscribe; **SPF/DKIM/DMARC verify + sign for one domain**; **DSN bounce poller**; segment rule-evaluation engine; per-campaign analytics (per §2.3); AI v1; **deterministic HTML→text** plaintext; audit-log writes; DLQ + alert hook | — | complaint/FBL ingestion; multi-ESP adapters |
| **P2** | template library, live preview, test sends | drag-drop block builder, reusable blocks | client-render farm previews |
| **P3** | automation engine (triggers/delays/conditions/branches), drip | journey canvas UI; AI sequence drafting | advanced re-entry/frequency analytics |
| **P4** | SES/Resend/SendGrid adapters; bounce **+ complaint** webhooks; A/B testing; FBL/ARF | send-time optimization; dedicated IP pools | per-ISP routing |
| **P5** | signup forms + double-opt-in confirmation send; public newsletter archive | public REST API + outbound webhooks; advanced segments; AI analytics narratives | API explorer console |
| **P6** | quotas + rate limiting + audit-log UI | billing scaffold (Stripe), granular RBAC, observability surfaces | SSO/SAML |

### 2.5 Throughput/deployment honesty

The SQLite default supports a **single worker** (no `SKIP LOCKED`). The fairness/round-robin and multi-worker token-bucket design is **dead code until Postgres**. The phase boundary is explicit: **Postgres is required before running more than one concurrent worker or sending above the single-worker throughput ceiling** (target boundary: > ~50k messages/day or any multi-worker deployment). RLS (§6) is likewise a Postgres-only backstop; the app-layer scoping guard is the sole isolation control on SQLite and is therefore mandatory and tested.

---

## 3. Architecture

iceReach is a FastAPI JSON API + a standalone worker process + a React SPA, over one relational database and a pluggable ESP adapter. The API never sends mail directly and never imports `smtplib`; all mail leaves through the adapter, driven by the worker.

```
                         ┌──────────────────────────────────────────────┐
                         │                React SPA                      │
                         │  Vite+TS · TanStack Query · Router · Tailwind │
                         │  shadcn/ui · openapi-fetch (typed client)     │
                         └───────────────┬──────────────────────────────┘
                          httpOnly cookie │ + X-CSRF-Token (mutations)
                          credentials:incl│ X-Workspace-Id (UNTRUSTED hint)
                                          ▼
   API keys (Bearer) ───────────►┌────────────────────────────────────────┐
   Public signed tokens ────────►│            FastAPI  /api/v1             │
   (/t /u /c /f, ESP webhooks)   │  auth · CSRF · workspace-scope resolver │
                                 │  routers: contacts campaigns ai jobs …  │
                                 │  AI service module (single Gemini entry) │
                                 │  ESP adapter interface (NO smtplib here) │
                                 └───┬───────────────┬──────────────┬──────┘
                                     │ reads/writes  │ enqueue       │ audit
                                     ▼               ▼               ▼
                          ┌───────────────────────────────────────────────┐
                          │      Database (SQLAlchemy 2.0 + Alembic)       │
                          │  SQLite default · Postgres-swappable           │
                          │  workspaces users memberships sessions api_keys│
                          │  contacts lists segments suppressions tokens   │
                          │  sending_domains identities templates campaigns│
                          │  messages events jobs automations audit_log    │
                          │  webhooks webhook_deliveries ai_usage mx_cache  │
                          │  campaign_stats(frozen) global_suppressions     │
                          └───────────────┬───────────────────────────────┘
                                          │ claim (FOR UPDATE SKIP LOCKED / BEGIN IMMEDIATE)
                                          ▼
            ┌──────────────────────────────────────────────────────────────┐
            │                  Worker(s)  python -m icereach.worker          │
            │  claim loop · lease/heartbeat · reaper · DLQ                    │
            │  campaign_send → materialize messages → send_batch             │
            │  per-recipient: suppression+global gate → render(DKIM) → ESP   │
            │  circuit-breaker (complaint/bounce auto-pause) · token bucket  │
            │  DSN bounce poller (P1) · webhook_process (P4)                 │
            └───────┬───────────────────────────────────────────┬──────────┘
                    │ EmailAdapter.send (classified SendResult)  │
                    ▼                                            ▼
       ┌────────────────────────┐                  ┌───────────────────────────┐
       │  SMTP adapter (P1)      │                  │ SES/Resend/SendGrid (P4)  │
       │  pooled SmtpSession     │                  │ HTTPS JSON · native webhooks│
       │  DKIM-signed · MAIL FROM│                  │ native idempotency/tracking │
       │  aligned return-path    │                  └───────────────────────────┘
       └───────────┬─────────────┘
                   │ outbound mail            inbound:
                   ▼                          DSN→return-path mailbox (P1 poller)
            recipients / MTAs ──────────────► FBL/ARF + ESP webhooks (P4)
                                              tracking pixel/click/unsub → /t /u (public)
```

**Process boundaries.** API and worker are separate processes sharing only the database (and Redis once arq lands). The API restarting never kills in-flight sends. The SPA is a static bundle served behind the same origin (so cookies and the tracking base URL share a domain) or a sibling subdomain with CORS configured for credentials.

**Public surfaces** (tracking, unsubscribe, archive, forms, ESP webhooks) are the only unauthenticated data-touching routes; each is gated by an HMAC-signed opaque token or provider-signature verification, and each is rate-limited (§6.9, §7.10).

---

## 4. Data Model

SQLAlchemy 2.0 declarative (`Mapped[...]` / `mapped_column`), Alembic for all schema changes, SQLite default, Postgres-swappable.

### 4.0 Canonical enum registry (single source of truth)

**Every section references these. No section may define a divergent enum.** Stored as `String` + a Python `enum.StrEnum` with a `CHECK` constraint (portable, migration-friendly).

| Enum | Values |
|---|---|
| `MembershipRole` | `owner` · `admin` · `member` · `viewer` |
| `JobType` | `campaign_send` · `send_batch` · `contact_import` · `contact_export` · `validation` · `webhook_process` · `dsn_poll` · `ai_batch` |
| `JobStatus` | `queued` · `claimed` · `running` · `done` · `error` · `canceled` · `dead` |
| `MessageStatus` | `pending` · `rendered` · `queued` · `sending` · `sent` · `bounced` · `failed` · `suppressed` · `canceled` (true `delivered` set only by P4 webhook; see `delivered_at`) |
| `BounceType` | `hard` · `soft` · `block` · `complaint` (nullable; set alongside `bounced`) |
| `EventType` | `queued` · `sent` · `delivered` · `deferred` · `bounced` · `opened` · `clicked` · `complained` · `unsubscribed` · `failed` |
| `SuppressionReason` | `unsubscribe` · `hard_bounce` · `complaint` · `manual` (workspace scope); the platform-wide table uses the same set plus provenance — there is no `global` *reason*; cross-tenant suppression is a **separate table**, §4.5 |
| `CampaignStatus` | `draft` · `scheduled` · `sending` · `sent` · `paused` · `canceled` (US spelling, one `l`, everywhere) |
| `ValidationStatus` | `unknown` · `pending` · `valid_syntax` · `has_mx` · `deliverable` · `invalid_syntax` · `no_mx` (see §4.4 for which the P1 validator actually produces) |
| `AIStatus` (envelope **and** ledger) | `ok` · `cached` · `degraded` · `rate_limited` · `quota_exceeded` · `invalid_output` · `error` |
| `AutomationRunStatus` | `active` · `waiting` · `completed` · `exited` · `failed` |
| `TokenPurpose` | `email_verify` · `password_reset` · `invite` · `optin_confirm` |

Notes resolving prior divergence:
- **Message status vs bounce split:** one `bounced` *status* + a `bounce_type` column (`hard`/`soft`/`block`/`complaint`). There are no `hard_bounce`/`soft_bounce` *statuses*. True `delivered` is represented by a non-null `delivered_at` + a `delivered` Event (P4), not a distinct status set by SMTP.
- **Event tense:** `opened`/`clicked` (past tense) everywhere. `accepted` is **not** an event type; the worker writes a `sent` event on relay acceptance.
- **Job:** `send_batch`, `webhook_process`, `dsn_poll`, `contact_export` are first-class; `claimed`, `canceled`, and `dead` (DLQ terminal) are valid statuses.

### 4.1 Conventions (apply to every table)

- **Base & mixins.** Single declarative `Base`. `TimestampMixin` → `created_at`/`updated_at` (`DateTime(timezone=True)`, server defaults, `onupdate=now()`), all UTC, tz-aware; naive datetimes rejected at the schema boundary. `WorkspaceScopedMixin` → non-null `workspace_id` FK (`ondelete="CASCADE"`, indexed) + the standard composite index.
- **Primary keys.** UUID via a portable `GUID` TypeDecorator (`CHAR(36)` on SQLite, native `UUID` on Postgres). UUIDs prevent cross-tenant id-guessing and ease import idempotency.
- **Portability types.** `JSONType` → `JSONB` on Postgres, `JSON`/text on SQLite. `EncryptedString` (AES-256-GCM envelope via `cryptography`, DEK per secret wrapped by a master key from env; `key_id` recorded). `CIEmail` TypeDecorator: **stores lowercased `String(320)` and normalizes on bind** — this replaces any use of Postgres `citext` (SQLite has none). Email comparison is always lower-normalized at write time; case-insensitivity is a property of the value, not the column type.
- **Enums.** `String` + `enum.StrEnum` + `CHECK`, from §4.0. No native PG enums.
- **Tenant scoping is mandatory and structural.** Every business table carries `workspace_id`. All tenant queries go through a workspace-scoped session helper that injects `workspace_id == current_workspace`; ad-hoc cross-tenant access requires a named, audited admin path. Cross-tenant uniqueness always includes `workspace_id`.
- **Soft delete.** Nullable `deleted_at` on user-facing entities (Contacts, Campaigns, Templates, Lists, Segments, Automations); partial indexes / query filters exclude soft-deleted rows. Suppression, Event, AuditLog, and frozen stats rows are never soft-deleted.

### 4.2 Tenancy, identity & auth

**`Workspace`** — tenant root; everything cascades from here.

| Column | Type | Notes |
|---|---|---|
| `id` | GUID PK | |
| `name` | String(255) | |
| `slug` | String(64) | **unique** (global), URL-safe |
| `plan` | String enum | `free`/`pro`/… (P6 billing hook) |
| `status` | String | `active`/`suspended` |
| `sending_quota_daily` | Integer | nullable; enforced at enqueue + send (§6.10) |
| `physical_address` | Text | CAN-SPAM/GDPR footer; **required before any bulk send** |
| `default_sending_identity_id` | GUID FK → sending_identities | nullable; see resolution below |
| `settings` | JSONType | tracking defaults, timezone, branding |
| timestamps | | |

- Unique(`slug`). **Default identity rule:** `Workspace.default_sending_identity_id` is the single source of truth for the default; `SendingIdentity` has **no `is_default` flag** (the prior dual mechanism is removed).

**`User`** — global person; auth identity lives here, not membership.

| Column | Type | Notes |
|---|---|---|
| `id` | GUID PK | |
| `email` | CIEmail | **unique** (global), login id |
| `password_hash` | String | Argon2id; nullable if SSO-only (P6) |
| `name` | String(255) | |
| `status` | String | `pending`/`active`/`disabled` |
| `email_verified_at` | DateTime | nullable |
| `last_login_at` | DateTime | nullable |
| timestamps | | |

**`Membership`** — join scoping a user into a workspace; role lives here.

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK | | |
| `user_id` | GUID FK → users | |
| `role` | String enum `MembershipRole` | `owner`/`admin`/`member`/`viewer` |
| `invited_by_id` | GUID FK → users | nullable |
| `accepted_at` | DateTime | nullable (pending invite) |
| timestamps | | |

- **Unique(`workspace_id`, `user_id`)**; Index(`user_id`). Exactly one `owner` per workspace (enforced in service layer + a partial unique index where supported). Role precedence: `owner > admin > member > viewer` (capability matrix in §6.2).

**`Session`** — server-side store backing the SPA cookie.

| Column | Type | Notes |
|---|---|---|
| `id` | GUID PK | internal row id |
| `session_token_hash` | String | SHA-256 of the opaque cookie token; lookup by hash |
| `user_id` | GUID FK → users | |
| `active_workspace_id` | GUID FK | switchable; **the trusted workspace** for the request |
| `csrf_secret` | String | per-session double-submit secret |
| `ip` / `user_agent` | String | audit + "active sessions" UI |
| `expires_at` | DateTime | sliding, capped at absolute max (30 d) |
| `revoked_at` | DateTime | nullable |
| timestamps | | |

- Index(`session_token_hash`), Index(`user_id`), Index(`expires_at`). Cookie name `ir_session` (§6.4).

**`ApiKey`** — programmatic access, per workspace.

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK | | |
| `name` | String | human label |
| `prefix` | String(16) | non-secret, shown in UI; format `irk_live_…`/`irk_test_…` |
| `key_hash` | String | **SHA-256, no salt** (high-entropy token; O(1) prefix lookup) |
| `scopes` | JSONType | e.g. `["contacts:read","campaigns:send"]` |
| `created_by_id` | GUID FK → users | |
| `last_used_at` / `expires_at` / `revoked_at` | DateTime | nullable |
| timestamps | | |

- **Unique(`prefix`)** global; Index(`workspace_id`), Index(`key_hash`). Plaintext shown once at creation. Never logged; only `prefix` + `last_used_at` surfaced. (Hashing is firmly SHA-256, not Argon2 — §6.7.)

**`Token`** — generic single-use, expiring, hashed tokens (resolves the missing home for verify/reset/optin).

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK | | |
| `workspace_id` | GUID FK | nullable (account-level verify/reset are not workspace-scoped) |
| `user_id` | GUID FK → users | nullable |
| `purpose` | String enum `TokenPurpose` | `email_verify`/`password_reset`/`invite`/`optin_confirm` |
| `token_hash` | String | SHA-256 of the emailed token; lookup by hash |
| `payload` | JSONType | e.g. invite role + email; optin contact/list ids |
| `expires_at` | DateTime | |
| `consumed_at` | DateTime | nullable; single-use |
| `created_at` | DateTime | |

- Index(`token_hash`), Index(`purpose`, `expires_at`). Invites also surface in member endpoints; the `invite` purpose carries `{email, role, workspace_id}`.

### 4.3 Contacts, custom fields, lists, segments, tags

**`ContactField`** — custom-field schema registry (resolves the SPA "custom field manager" / `/fields` having no backing table).

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK | | |
| `key` | String(64) | the merge-tag name used as `{key}` |
| `label` | String | UI label |
| `type` | String enum | `text`/`number`/`date`/`bool` |
| `default_value` | String | nullable; the **per-field configured fallback** (§8.7) |

- **Unique(`workspace_id`, `key`)**. `key` is validated against `^[a-z][a-z0-9_]*$` so it matches the merge regex word-class. Reserved keys (`unsubscribe_url`, `physical_address`, `view_in_browser_url`) are blocked.

**`Contact`** — per-workspace contact store; one email per row.

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK | | |
| `email` | CIEmail(320) | normalized lowercase |
| `email_canonical` | CIEmail(320) | dedupe key (lowercased; optional gmail-dot/plus stripping) |
| `first_name` / `last_name` | String | nullable |
| `attributes` | JSONType | custom fields keyed by `ContactField.key`; become `{key}` merge tags |
| `validation_status` | String enum `ValidationStatus` | §4.4 |
| `validated_at` | DateTime | nullable |
| `engagement_score` | Integer | nullable (P4/P5) |
| `consent_source` | String | GDPR provenance (import/form/api/manual) |
| `consent_at` | DateTime | nullable |
| `deleted_at` | DateTime | soft delete (GDPR erasure path, §8.6) |
| timestamps | | |

- **Unique(`workspace_id`, `email_canonical`)** → dedupe + upsert per tenant. Index(`workspace_id`, `validation_status`), Index(`workspace_id`, `created_at`).
- **Erasure note:** on GDPR erasure the Contact row is hard-deleted; the suppression record that may need to outlive it stores a **salted one-way hash**, not the plaintext email (§4.5, §8.6).

**`ContactList`**

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK | | |
| `name` | String | Unique(`workspace_id`, `name`) |
| `double_optin` | Boolean | enforce confirmed opt-in (confirmation send path is P1, §8.5) |
| `deleted_at` | DateTime | |

**`ListMembership`** (subscription) — per-list status, separate from global suppression.

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK | | denormalized for scoped queries |
| `list_id` | GUID FK → contact_lists | |
| `contact_id` | GUID FK → contacts | |
| `status` | String enum | `pending`/`subscribed`/`unsubscribed`/`cleaned`/`complained` |
| `optin_token_id` | GUID FK → tokens | nullable (double-opt-in confirmation) |
| `subscribed_at` / `unsubscribed_at` | DateTime | transition timestamps |
| `source` | String | import/form/api |

- **Unique(`list_id`, `contact_id`)**; Index(`workspace_id`, `list_id`, `status`). `cleaned` = removed after a hard bounce.

**`Segment`** — saved dynamic query; rule tree evaluated by the deterministic engine (§5/§7).

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK | | |
| `name` | String | Unique(`workspace_id`, `name`) |
| `definition` | JSONType | AND/OR rule tree over attributes, tags, engagement, list membership, open/click recency |
| `is_dynamic` | Boolean | dynamic vs snapshot |
| `last_evaluated_at` / `cached_count` | DateTime / Integer | nullable |

- The same `definition` shape is the AI NL→segment compile target (P5). The **rule-evaluation engine that materializes a segment to recipients is a hard P1 dependency** (campaigns target segments in P1).

**`Tag`** / **`ContactTag`**

- `Tag(id, workspace_id, name)` — Unique(`workspace_id`, `name`).
- `ContactTag(contact_id, tag_id, workspace_id)` — Unique(`contact_id`, `tag_id`), indexed both directions.

### 4.4 Validation status & the MX cache

The P1 validator is the existing ladder (regex syntax → cached MX). It produces exactly **four** of the enum values: `invalid_syntax`, `no_mx`, `deliverable` (= has valid syntax **and** an MX record), and `unknown`/`pending` (not yet validated / in flight). The richer states `valid_syntax` and `has_mx` are **reserved for a future SMTP-probe / accept-all detector** and are not produced in P1. Mapping from the current `validate_email()` strings: `Invalid syntax → invalid_syntax`; `Domain not found / no MX record → no_mx`; `Deliverable → deliverable`. This removes the prior self-contradiction (six states, three outcomes).

**`MxCache`** — promotes the in-process `_mx_cache` to a shared table.

| Column | Type | Notes |
|---|---|---|
| `domain` | String(255) PK | lowercased |
| `has_mx` | Boolean | result |
| `checked_at` | DateTime | |
| `expires_at` | DateTime | **TTL policy below** |

- **TTL policy (resolves the "transient failure poisons a domain forever" hazard):** positive results TTL **7 days**; **negative results TTL 1 hour** (short, so a transient DNS timeout cannot permanently mark a good domain `no_mx`). On lookup-miss/expiry the resolver is re-queried and the row upserted. The cache is global (shared across workspaces/jobs) but advisory: a `no_mx` contact is *skipped at send time*, and a re-validation pass runs before each campaign materialization so stale negatives self-heal.

### 4.5 Suppression (workspace + platform-wide)

**`Suppression`** — workspace do-not-send wall.

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK | | |
| `email_canonical` | CIEmail(320) | normal entries (live contact) |
| `email_hash` | String(64) | **HMAC-SHA256(canonical_email, pepper)**; set on GDPR erasure (§8.6) |
| `reason` | String enum `SuppressionReason` | `unsubscribe`/`hard_bounce`/`complaint`/`manual` |
| `source_message_id` | GUID FK → messages | nullable (provenance) |
| `created_at` | DateTime | (no soft delete; purge only via explicit window) |

- **Unique(`workspace_id`, `email_canonical`)** and **Unique(`workspace_id`, `email_hash`)**; send-time lookup checks both. Upsert keeps the earliest/most-severe reason. A re-import of an unsubscribed address stays suppressed because the match is on the canonical email (or its hash after erasure), not on `contact_id`.

**`GlobalSuppression`** — platform-wide, cross-workspace do-not-send (resolves the missing global mechanism; there is **no `global` reason value** — it is a separate table).

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK | | not workspace-scoped |
| `email_hash` | String(64) | HMAC-SHA256 of canonical email (privacy across tenants) |
| `reason` | String enum | `hard_bounce`/`complaint` (reputation-relevant on shared infra) |
| `created_at` | DateTime | |

- **Unique(`email_hash`)**, indexed. On shared SMTP/IP infrastructure a hard bounce or complaint in one workspace is reputation-relevant platform-wide; send-time enforcement checks `GlobalSuppression` **in addition to** the workspace `Suppression`. Cross-tenant suppression stores only a hash, never plaintext, so it does not leak one tenant's contacts to another.

### 4.6 Sending identities & domains

**`SendingDomain`** — verified sending domain with DNS-auth status; drives DKIM signing (P1) and the tracking base URL.

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK | | |
| `domain` | String | e.g. `mail.acme.com` |
| `dkim_selector` | String | e.g. `ir1` |
| `dkim_public_key` | Text | published in DNS |
| `dkim_private_key` | **EncryptedString** | encrypted at rest; used by the signer |
| `return_path_domain` | String | bounce/MAIL FROM subdomain, e.g. `bounce.mail.acme.com` (**SPF alignment**, §8.4) |
| `spf_verified` / `dkim_verified` / `dmarc_verified` | Boolean | DNS check results |
| `tracking_subdomain` | String | per-workspace authenticated tracking host |
| `verification_status` | String enum | `pending`/`verified`/`failed` |
| `verified_at` | DateTime | nullable |

- **Unique(`workspace_id`, `domain`)**. **P1 ships the verify + sign pipeline** (generate selector/keypair, render SPF/DKIM/DMARC records, poll-verify). Bulk send is blocked unless a `verified` domain exists with `dkim_verified` true.

**`SendingIdentity`** — from-address bound to a domain + ESP config behind the adapter.

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK | | |
| `sending_domain_id` | GUID FK → sending_domains | required before send |
| `from_name` / `from_email` | String | `from_email` must be on the verified domain |
| `reply_to` | String | nullable |
| `esp_type` | String enum | `smtp`/`ses`/`resend`/`sendgrid` |
| `esp_config` | JSONType | non-secret (host, port, region) |
| `smtp_password` / `esp_api_key` | **EncryptedString** | encrypted, never logged/returned |
| `stream` | String enum | `transactional`/`broadcast` (reputation separation) |

- **Unique(`workspace_id`, `from_email`, `stream`)**. Replaces the per-request SMTP creds + single reused `SmtpSession`; the worker builds a **pool** from this row per job. The default is `Workspace.default_sending_identity_id` (no row-level flag).

### 4.7 Templates & campaigns

**`Template`**

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK | | |
| `name` | String | Unique(`workspace_id`, `name`) |
| `subject` | String | may contain `{column}` / `{column|fallback}` |
| `preheader` | String | nullable |
| `html_body` | Text | sanitized, merge-tagged |
| `text_body` | Text | nullable; deterministic HTML→text if absent (§8.7) |
| `blocks_json` | JSONType | nullable (P2 builder source of truth) |
| `version` | Integer | versioning |
| `deleted_at` | DateTime | |

**`Campaign`** — broadcast to a list or segment; denormalized live counters.

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK | | |
| `name` | String | |
| `status` | String enum `CampaignStatus` | `draft`/`scheduled`/`sending`/`sent`/`paused`/`canceled` |
| `template_id` | GUID FK → templates | nullable (inline content allowed) |
| `sending_identity_id` | GUID FK → sending_identities | |
| `target_list_id` / `target_segment_id` | GUID FK | one of |
| `scheduled_at` | DateTime | tz-aware UTC; nullable for send-now |
| `track_opens` / `track_clicks` | Boolean | per-send toggles |
| `send_job_id` | GUID FK → jobs | nullable; the campaign_send job |
| live counters | Integer | `total_recipients`, `sent_count`, `bounce_hard_count`, `bounce_soft_count`, `open_count`, `unique_open_count`, `click_count`, `unique_click_count`, `unsubscribe_count` (`delivered_count`/`complaint_count` populated P4, §2.3) |
| `deleted_at` | DateTime | |

- Index(`workspace_id`, `status`), Index(`workspace_id`, `scheduled_at`). **Schedule idempotency (resolves double-click double-send):** a **partial unique index on `send_job_id` + a state-machine guard** ensures `schedule` only transitions `draft`/`scheduled` → `scheduled`/`sending` and creates **at most one** active `campaign_send` job. The API also accepts an `Idempotency-Key` (§5).
- Live counters are derived from `Event` rows, cached on the row, reconciled by a job that excludes bot opens — but the durable analytics of record is the frozen rollup below.

**`CampaignStats`** (frozen rollup) — survives Event retention purge.

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK · `campaign_id` FK (unique) | | |
| frozen counters | Integer | same metric set as Campaign, **immutable once the campaign reaches `sent` + the reconciliation window closes** |
| `top_links` | JSONType | clickmap snapshot |
| `frozen_at` | DateTime | |

- Resolves the "Events purged at 90 days → counters unrebuildable" hazard: once a campaign completes and the reconciliation window closes, totals are frozen here. Events may then expire (§4.9) without losing historical campaign numbers.

**`CampaignVariant`** (A/B) — **P4** per the phase map (the SPA A/B editor and winner auto-send are P4, not P1; reconciled in §11/§12).

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK · `campaign_id` FK | | |
| `label` | String | "A"/"B" |
| `subject` / `from_name` | String | nullable overrides |
| `template_id` | GUID FK → templates | nullable |
| `weight` | Integer | % of audience |
| `is_winner` | Boolean | |

- **Unique(`campaign_id`, `label`)**. Every `Message` references the variant sent.

### 4.8 Messages, events, jobs

**`Message`** (send) — one row per recipient per campaign/transactional send; unit of tracking, idempotency, audit.

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK | | |
| `campaign_id` | GUID FK → campaigns | nullable (transactional) |
| `variant_id` | GUID FK → campaign_variants | nullable (P4) |
| `contact_id` | GUID FK → contacts | nullable |
| `to_email` | CIEmail(320) | snapshot at send time |
| `tracking_token` | String | **opaque, HMAC-signed**; basis for pixel + click + unsub |
| `dedupe_key` | String | one message per contact per campaign |
| `idempotency_key` | String | nullable; dedupes client/worker retries |
| `status` | String enum `MessageStatus` | §4.0 |
| `bounce_type` | String enum `BounceType` | nullable |
| `provider_message_id` | String | ESP/relay id for webhook correlation |
| `subject_snapshot` | String | rendered subject |
| `html_snapshot` / `text_snapshot` | Text | snapshotted at first render → byte-identical retries |
| `error_code` / `error_detail` | Text | classified SMTP/ESP reason (never credentials) |
| `attempts` / `next_attempt_at` | Integer / DateTime | per-message retry |
| `sent_at` / `delivered_at` | DateTime | `delivered_at` set only by P4 delivery webhook |
| timestamps | | |

- **Unique(`tracking_token`)** global; **Unique(`campaign_id`, `dedupe_key`)**; **Unique(`workspace_id`, `idempotency_key`)** where present. Index(`workspace_id`, `campaign_id`, `status`), Index(`provider_message_id`).
- Per-message status + `attempts` enable resumable jobs and per-recipient retry — replacing the fragile single reused `SmtpSession`. The current `send_email` returning `True` on `SMTPRecipientsRefused` (a swallowed failure) is fixed by the classified `SendResult` (§7.4).

**`Event`** — append-only engagement/delivery log; source for analytics rollups.

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK · `message_id` FK | | |
| `type` | String enum `EventType` | §4.0 |
| `occurred_at` | DateTime | provider/observed time |
| `url` | Text | nullable (`clicked`) |
| `ip` / `user_agent` | String | bot/prefetch filtering |
| `is_bot` | Boolean | Apple MPP / scanner / prefetch |
| `provider_event_id` | String | nullable; webhook dedupe |
| `payload` | JSONType | raw provider event |

- **Unique(`provider_event_id`)** where present → dedupes retried/forged webhooks (signature verified before insert). Index(`workspace_id`, `message_id`, `type`), Index(`workspace_id`, `type`, `occurred_at`). A `bounced`(hard)/`complained` event triggers a `Suppression` (and `GlobalSuppression`) upsert.

**`Job`** — DB-backed queue, evolving `JobManager`.

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK | | |
| `type` | String enum `JobType` | §4.0 (incl. `send_batch`, `webhook_process`, `dsn_poll`, `contact_export`) |
| `status` | String enum `JobStatus` | §4.0 (incl. `claimed`, `canceled`, `dead`) |
| `priority` | Integer | lower = sooner; transactional < bulk (separate lanes) |
| `progress` | Integer | 0–100 (from current `set_progress`) |
| `message` | String | human status |
| `payload` | JSONType | job args (never credentials) |
| `result` | JSONType | nullable (mirrors current `result`) |
| `artifacts` | JSONType | key→stored-path (mirrors current `files`) |
| `last_error` | Text | truncated; **never credentials** |
| `attempts` / `max_attempts` | Integer | retry/backoff; on exhaust → `dead` (DLQ) |
| `claimed_by` | String | worker id (host/pid) lease holder |
| `claimed_at` / `lease_expires_at` | DateTime | visibility timeout for crash recovery |
| `run_after` | DateTime | scheduled/delayed execution |
| `idempotency_key` | String | Unique(`workspace_id`, key) — dedupes enqueue |
| timestamps | | retention sweep, as today |

- Index(`status`, `priority`, `run_after`) — the dequeue query; partial index `WHERE status IN ('queued','claimed')`; Index(`workspace_id`, `type`, `created_at`). Preserves the `JobManager` public shape (`id/type/status/progress/message/result/files→artifacts/error/created_at/updated_at`) while adding persistence, leasing, retries, priority, scheduling, and a DLQ. arq/Redis later swaps the dequeue mechanism, not this table.

### 4.9 Retention

- **Events:** configurable per workspace, default **90 days**; raw bodies are never stored beyond `Message.html_snapshot`/`text_snapshot` (themselves purgeable on a separate, shorter window after `sent`). Before any Event purge, `CampaignStats` must be frozen (§4.7) — the purge job asserts this.
- **Jobs:** retention sweep as today (default 6 h for terminal jobs; `dead` jobs retained longer for DLQ replay).
- **Sessions/Tokens:** swept after `expires_at`.

### 4.10 Webhooks (outbound) & deliveries

**`Webhook`** (outbound endpoints — the `/webhooks` API has no backing table otherwise).

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK | | |
| `url` | String | consumer endpoint |
| `event_types` | JSONType | subscribed `EventType`s |
| `signing_secret` | **EncryptedString** | HMAC secret |
| `signing_secret_prev` | **EncryptedString** | nullable; dual-secret rotation grace (§5/§8) |
| `secret_rotated_at` | DateTime | nullable |
| `active` | Boolean | |

**`WebhookDelivery`** (attempt log — backs `/deliveries` + `/replay`).

| Column | Type | Notes |
|---|---|---|
| `id` GUID PK · `workspace_id` FK · `webhook_id` FK | | |
| `event_id` | String | stable id for consumer dedupe |
| `event_type` | String enum | |
| `payload` | JSONType | |
| `status` | String enum | `pending`/`success`/`failed` |
| `attempts` / `next_attempt_at` | Integer / DateTime | backoff |
| `response_code` / `response_body` | Integer / Text | truncated |
| `signed_at` | DateTime | timestamp included in the signature (replay window, §8) |

### 4.11 Automation (P3, modeled now)

**`Automation`** (journey definition): `id`, `workspace_id`, `name`, `status` (`draft`/`active`/`paused`/`archived`), `trigger_type` (`list_join`/`tag_added`/`date`/`custom_event`/`api`), `trigger_config` JSON, `graph_json` JSON.

**`AutomationStep`**: `id`, `workspace_id`, `automation_id`, `step_type` (`send_email`/`delay`/`condition`/`add_tag`/`remove_tag`/`update_field`/`branch`), `config` JSON, `position`, `next_step_id`, `branch_true_step_id`, `branch_false_step_id`.

**`AutomationRun`** (one contact's traversal): `id`, `workspace_id`, `automation_id`, `contact_id`, `current_step_id`, `status` (`AutomationRunStatus`), `wait_until` DateTime, `context` JSON. Index(`workspace_id`, `status`, `wait_until`) drives "wake runs due now". **Unique(`automation_id`, `contact_id`)** unless re-entry is enabled (then add a `cycle` discriminator).

### 4.12 Governance: audit & AI usage

**`AuditLog`** (append-only; **written from P1 at every state-changing handler**, §12 — the UI is P6 but the rows exist from P1 for consent/opt-out provenance): `id`, `workspace_id` (nullable for account-level), `actor_user_id` (nullable), `actor_api_key_id` (nullable), `action` (e.g. `contact.unsubscribed`, `campaign.sent`, `apikey.created`), `target_type`/`target_id`, `metadata` JSON (before/after, ip), `created_at`. Index(`workspace_id`, `created_at`), Index(`workspace_id`, `target_type`, `target_id`).

**`AIUsage`** (per-call ledger; the status column uses the **full `AIStatus` enum**, resolving the prior `ok/error/cached`-only mismatch): `id`, `workspace_id`, `feature` (`subject_gen`/`body_draft`/`rewrite`/`spam_critique`/`plaintext_gen`/`segment_compile`/`sequence_draft`/`analytics_narrative`/`send_time`), `model` (`gemini-3-flash-preview`), `prompt_tokens`/`completion_tokens`, `cache_key` (nullable), `request_user_id` (nullable), `target_type`/`target_id`, `status` (`AIStatus`), `latency_ms`, `created_at`. Index(`workspace_id`, `feature`, `created_at`), Index(`cache_key`). AI output is never authoritative; it lands in draft fields pending human approval.

### 4.13 Load-bearing constraints (summary)

- **Tenant cascade:** `Workspace` → all business tables via `ondelete="CASCADE"` on `workspace_id`.
- **Dedupe & idempotency uniques:** `Contact(workspace_id, email_canonical)`, `Suppression(workspace_id, email_canonical|email_hash)`, `GlobalSuppression(email_hash)`, `Message(campaign_id, dedupe_key)`, `Message(tracking_token)`, `Message(workspace_id, idempotency_key)`, `Event(provider_event_id)`, `Job(workspace_id, idempotency_key)`, `ApiKey(prefix)`, `Membership(workspace_id, user_id)`, `ListMembership(list_id, contact_id)`, `Campaign(send_job_id)` (partial).
- **Send-time hot path** (all indexed): before handing a `Message` to the adapter, the worker checks (a) `Suppression(workspace_id, canonical|hash)`, (b) `GlobalSuppression(hash)`, (c) `ListMembership.status == subscribed` (for list sends), (d) `Contact.validation_status != no_mx/invalid_syntax`, (e) a `verified` + `dkim_verified` `SendingDomain`.

---

## 5. API Surface

All app endpoints live under `/api/v1`. Public links use short, stable, unversioned prefixes (`/t`, `/u`, `/c`, `/f`) so generated URLs stay compact; ESP inbound webhooks use `/api/v1/esp-webhooks/{provider}`. Everything except the public group is **workspace-scoped**.

### 5.1 Conventions

| Concern | Convention |
|---|---|
| Base path | `/api/v1`; public links `/t` `/u` `/c` `/f`; ESP inbound `/api/v1/esp-webhooks/{provider}` |
| Auth schemes | **Session** = `ir_session` httpOnly cookie + `X-CSRF-Token` on unsafe methods; **API key** = `Authorization: Bearer irk_live_…`; **Public** = signed opaque token in URL or provider signature |
| Workspace scoping | **Effective workspace = `session.active_workspace_id` (or `api_key.workspace_id`).** The `X-Workspace-Id` header and `/w/:id/` URLs are **UNTRUSTED hints** — the server validates the hint against the caller's memberships and, if valid, switches the session's active workspace; it is **never** trusted as the source of authority. Cross-workspace access returns **404**, never 403 (no existence leak). |
| Pagination | Cursor-based: `?limit=&cursor=` → `{ data, next_cursor, has_more }` |
| Filtering/sort | `?q=&sort=field:asc&filter[status]=…` |
| Idempotency | `Idempotency-Key` header **required** on `POST /sends`, `POST /sends/batch`, AI generation, and `POST /campaigns/{id}/schedule`; 24 h dedupe window |
| Errors | `{ error: { code, message, field?, request_id } }`, structured codes (`validation_error`, `suppressed_recipient`, `quota_exceeded`, `preflight_failed`, …) |
| Rate limits | `429` + `Retry-After` + `X-RateLimit-*`; per-key, per-workspace, and per-IP/per-token (public) buckets |
| Timestamps | UTC ISO-8601; scheduling carries an explicit IANA timezone |
| Long operations | `202 { job_id }`; poll `GET /jobs/{id}` |

### 5.2 Auth & Session — `/api/v1/auth`

| Method | Path | Purpose | Auth |
|---|---|---|---|
| POST | `/auth/signup` | Create first user + bootstrap workspace + owner membership | Public |
| POST | `/auth/login` | Email+password → set `ir_session` cookie + CSRF | Public |
| POST | `/auth/logout` | Invalidate session | Session |
| GET | `/auth/me` | User + memberships + active workspace + role | Session |
| GET/POST | `/auth/csrf` | Issue/rotate CSRF token (double-submit) | Session |
| POST | `/auth/verify-email` | Consume `email_verify` token | Public(token) |
| POST | `/auth/password/forgot` | Trigger reset email (creates `password_reset` token) | Public |
| POST | `/auth/password/reset` | Reset with token → revoke all sessions | Public(token) |
| POST | `/auth/switch-workspace` | Re-scope session to another membership | Session |

- Login → `{ user, workspaces[], active_workspace_id }` + `Set-Cookie`. Generic errors for unknown-email vs wrong-password (no enumeration). Platform transactional mail (verify/reset/invite) uses iceReach's own sending identity, separate from tenant bulk traffic.

### 5.3 Workspaces, members, API keys

`/api/v1/workspaces`: GET list (Session), POST create (Session), GET `{id}` (member), PATCH `{id}` (admin — name, `physical_address`, defaults, tracking domain), DELETE `{id}` (owner; GDPR data-deletion schedule), GET `{id}/usage` (admin — quotas, send counts, bounce-rate trend vs thresholds). Settings shape: `{ default_from_name, default_reply_to, postal_address, tracking_domain, sending_paused, complaint_rate, bounce_rate }`; `postal_address` is required before any bulk send.

`/api/v1/workspaces/{wid}/members`: GET list (member), POST `invites` (admin; role ≤ inviter's), POST `invites/{token}/accept` (Session/Public-token), PATCH `{user_id}` (admin), DELETE `{user_id}` (admin). Roles: `owner`/`admin`/`member`/`viewer` (§6.2).

`/api/v1/workspaces/{wid}/api-keys`: GET list (metadata only), POST create (admin — returns plaintext **once**), POST `{id}/rotate`, DELETE `{id}` (revoke), GET `{id}/usage`. Scopes: `contacts:read|write`, `campaigns:read|write`, `send`, `events:read`, `suppressions:write`, `keys:manage`. Prefix `irk_live_`/`irk_test_`; stored SHA-256.

### 5.4 Contacts, custom fields, lists, segments

`/api/v1/contacts`: GET list/search; POST create (upsert on canonical email); GET/PATCH/DELETE `{id}` (DELETE = GDPR erasure: hard-delete contact, keep a **hashed** suppression); POST `import` (`202 {job_id}`; column mapping, dedupe, upsert, import-time validation, **multi-email row explosion** §14); POST `import/preview`; GET `export` (`202 {job_id}`); POST `{id}/tags`; GET `{id}/activity`; POST `validate`. Import is multipart: `file + { mapping, list_id?, update_existing, validate, consent_source }`. **Import limits (resolves OOM): max 250k rows, max 50 MB, max 200 columns, streaming/chunked parse** (no full pandas load); over-limit → `413`. Import never resurrects suppressed addresses.

`/api/v1/fields` (custom-field registry, backs `ContactField`): GET list, POST create, PATCH `{id}`, DELETE `{id}`.

`/api/v1/lists`: GET, POST, GET/PATCH/DELETE `{id}` (PATCH sets single/double opt-in), GET `{id}/contacts`, POST `{id}/contacts`, DELETE `{id}/contacts/{cid}`. POST `{id}/optin/resend` — **trigger/resend a double-opt-in confirmation email** for pending members (makes `double_optin` lists functional in P1; §8.5).

`/api/v1/segments`: GET, POST, GET/PATCH/DELETE `{id}`, POST `preview` (evaluate without saving → count + sample, via the deterministic engine), GET `{id}/contacts`. Rule shape: `{ match: "all"|"any", conditions: [{ field, op, value }], groups: [...] }`, ops `eq|contains|gt|lt|in|tag_present|opened_within|not_opened_within|clicked_within`. Consumed verbatim by the P5 AI NL→segment builder.

### 5.5 Templates & campaigns

`/api/v1/templates`: GET, POST, GET/PATCH/DELETE `{id}`, POST `{id}/duplicate`, POST `{id}/preview` (render with sample merge → sanitized HTML + plaintext). HTML always passes the email-safe sanitizer. `{column}`/`{column|fallback}` resolve via the extended renderer (§8.7).

`/api/v1/campaigns`: GET list (status + headline metrics); POST create draft; GET/PATCH/DELETE `{id}`; POST `{id}/duplicate`; POST `{id}/test-send` (to given addresses, sample merge; explicit override bypasses suppression for the test only); POST `{id}/preflight` (compliance + spam critique → blockers + warnings); POST `{id}/schedule` (**`Idempotency-Key` required**; now / future ts + IANA tz → creates exactly one `campaign_send` job under the state-machine guard, §4.7); POST `{id}/pause`; POST `{id}/resume`; POST `{id}/cancel`; GET `{id}/recipients` (resolved audience minus suppressed). Campaign shape: `{ id, name, subject, preheader, from_name, from_email, reply_to, sending_identity_id, html, plaintext?, audience:{list_ids[],segment_ids[]}, tracking:{opens,clicks}, status }`. **`preflight` is a hard gate:** `schedule` rejects with `412 preflight_failed` if blocking checks fail (missing unsubscribe, missing postal address, **unverified or DKIM-unsigned sending domain**, unresolvable merge tags) — and because DKIM verify+sign ships in P1 (§2.2), a P1 domain *can* pass.

### 5.6 Sends — transactional & batch — `/api/v1/sends`

POST `/sends` (one personalized email; **`Idempotency-Key` required**); POST `/sends/batch` (≤1000 personalized versions; `Idempotency-Key` required); GET `/sends/{id}`; DELETE `/sends/{id}` (cancel scheduled). Send shape: `{ to, from, reply_to?, subject, html?, text?, template_id?, merge_vars?, headers?, attachments?, tags?, tracking?, send_at? }`. **Attachment limits (resolves abuse vector): total ≤ 10 MB, per-file ≤ 7 MB, MIME allowlist (pdf, common images, docx/xlsx/pptx, txt, csv, zip), executable types blocked, AV scan (ClamAV) before send;** violations → `422 attachment_rejected`. Suppression enforced (`422 suppressed_recipient`). Per-message retry/backoff and connection pooling replace the single reused `SmtpSession`.

### 5.7 Events, analytics, suppressions, sending identities

`/api/v1/...` analytics: GET `/campaigns/{id}/analytics` (sent, hard/soft bounces, unique+total opens/clicks, CTR, CTOR, unsubs; `delivered`/`complaint` shown as "—" until P4; bot-filtered), GET `/campaigns/{id}/links`, GET `/campaigns/{id}/recipients/events`, GET `/events`, GET `/analytics/overview`, GET `/analytics/export` (`202 {job_id}`).

`/api/v1/suppressions`: GET list (filter by reason), POST add (one or many), GET `/{email}` (status/reason/time), DELETE `/{email}` (manual entries only — bounce/complaint not removable; admin), POST `import` (`202 {job_id}`). Soft bounces never auto-suppress.

`/api/v1/sending-identities`: GET list (+ verification status), POST create (domain or SMTP/ESP config; credentials encrypted), GET `{id}` (incl. DNS records to publish — SPF/DKIM/DMARC + return-path), POST `{id}/verify` (re-check DNS / DKIM), PATCH `{id}`, DELETE `{id}`. Sends from an unverified/unsigned domain are blocked at preflight.

### 5.8 AI — `/api/v1/ai`

All through the single AI service (`gemini-3-flash-preview`, strict JSON, output sanitized, cached, never auto-send), with per-workspace AI rate/cost limits and **phase-gating** (endpoints for later-phase capabilities return `404`/`feature_not_enabled` until their phase is on, §9.9):

| Path | Purpose | Phase |
|---|---|---|
| POST `/ai/subject-lines` | Subject/preheader variants + rank | P1 |
| POST `/ai/body-draft` | Draft HTML body from brief, merge-tag-aware | P1 |
| POST `/ai/rewrite` | Tone/length/locale rewrite or translate | P1 |
| POST `/ai/spam-critique` | Pre-send deliverability/spam critique | P1 |
| POST `/ai/plaintext` | Plaintext from HTML (AI; deterministic fallback always present) | P1 |
| POST `/ai/merge-tag-check` | Detect unresolvable `{column}` refs, suggest field/fallback | P1 |
| POST `/ai/sequence-draft` | Goal → journey outline | P3 |
| POST `/ai/send-time` | Grounded send-window recommendation | P4 |
| POST `/ai/segment-from-text` | NL → segment rule JSON | P5 |
| POST `/ai/analytics-narrative` | Metrics → plain-English summary | P5 |

Each returns the shared envelope `{ status, data, model, prompt_version, cached, usage, warnings, request_id }` (§9.3).

### 5.9 Outbound webhooks, inbound ESP, jobs

`/api/v1/webhooks` (outbound, admin): GET list, POST register (URL + filter → returns signing secret), PATCH `{id}`, DELETE `{id}`, POST `{id}/rotate-secret` (**dual-secret grace rotation**), POST `{id}/test`, GET `{id}/deliveries` (from `WebhookDelivery`), POST `{id}/deliveries/{did}/replay`. Outbound payloads are HMAC-signed over `{timestamp}.{body}` with a **replay-tolerance window** (±5 min); each event carries a stable `event_id` (§8).

`/api/v1/esp-webhooks/{provider}` (inbound, Public + **HMAC signature verify**, P4): ingest bounce/complaint/delivery from SES/Resend/SendGrid/Mailgun. Verified, deduped by `provider_event_id`, processed async via a `webhook_process` job (200 fast). Hard bounce/complaint → suppress; soft bounce → retry.

`/api/v1/jobs`: GET `{id}` (status/progress/result), GET `{id}/download/{key}` (artifact; **ownership-checked**: requester's workspace must match job's; keys non-guessable), POST `{id}/cancel`. Backed by the DB job table; preserves the `{job_id}` poll + `download/{key}` contract so SPA migration is incremental.

### 5.10 Public — tracking, unsubscribe, forms (signed tokens, rate-limited)

Single canonical scheme (resolving the `/t/o.png` vs `.gif` and `/u` vs `/t/u` divergence): **open pixel is `.gif`; unsubscribe lives under `/u`.**

| Method | Path | Purpose |
|---|---|---|
| GET | `/t/o/{token}.gif` | Open-tracking pixel (1×1 transparent GIF, `Cache-Control: no-store`) |
| GET | `/t/c/{token}` | Click redirect — validate signed token + signed target, log click, 302 |
| GET | `/u/{token}` | Hosted unsubscribe / preference page |
| POST | `/u/{token}` | One-click unsubscribe (backs `List-Unsubscribe-Post`, RFC 8058) |
| GET | `/c/{token}` | "View in browser" / newsletter archive (P5) |
| GET | `/f/{form_id}` | Hosted signup form (P5) |
| POST | `/f/{form_id}/submit` | Form submit → contact upsert, honeypot/captcha, double-opt-in trigger (P5) |
| GET | `/f/confirm/{token}` | Double-opt-in confirmation (pending → subscribed) |

- Every token is opaque, per-send, HMAC-signed, validated; no guessable ids, no open redirects (the click target is signed and re-verified before the 302). **Unsubscribe links are never rewritten through click tracking.** The `List-Unsubscribe` header pairs the `https:` POST target with `List-Unsubscribe-Post: List-Unsubscribe=One-Click`. **Public-group rate limits (resolves the leaked-token DoS/metric-inflation surface): per-IP and per-token throttles** on `/t/o`, `/t/c`, `/u` (e.g. per-token open dedupe window + per-IP burst cap); excess is dropped/deduped, not counted.

---

## 6. Auth, Tenancy & Security

Two non-negotiable pillars from day 1: **tenant isolation** (every row belongs to one `workspace_id`, no query crosses it without an audited reason) and **credential safety** (the current app takes the SMTP password as a plaintext `sender_password` form field; the moment we persist credentials and keys, plaintext is a breach risk — everything here is encrypted-at-rest or hashed, and never logged).

### 6.1 Threat model & principles

| Threat | Mitigation |
|---|---|
| Cross-tenant read/write | Mandatory `workspace_id` scoping at the ORM/session layer, not per-handler |
| Session hijacking / XSS token theft | httpOnly + Secure + SameSite cookies; no tokens in JS storage |
| CSRF on cookie routes | Double-submit token + Origin checks on all unsafe methods |
| Credential theft from DB dump | Argon2id (passwords); AES-256-GCM envelope (SMTP/ESP secrets); SHA-256 (API keys, session/reset/invite tokens) |
| Stolen/leaked API key | Hashed at rest, scoped, prefixed for revocation, rate-limited, rotatable |
| Brute force / stuffing | Per-IP + per-account login throttling + lockout + breached-password rejection |
| Privilege escalation | Server-side role checks on every mutation; never trust client-asserted role |
| Client-asserted workspace | `X-Workspace-Id` treated as untrusted hint, validated against memberships (§5.1) |
| One abusive tenant poisoning reputation | Per-workspace quotas, complaint/bounce monitoring, **auto-pause circuit-breaker** (§7.8), warmup (§8.9) |
| Repudiation | Append-only audit log, written from P1 |

Principles: deny by default; fail closed; defense in depth; least privilege; secrets are write-only from the API's perspective; every security decision is server-side.

### 6.2 Roles & capability matrix

Four roles, fixed precedence `owner > admin > member > viewer`.

| Capability | owner | admin | member | viewer |
|---|---|---|---|---|
| View dashboards/reports | ✓ | ✓ | ✓ | ✓ |
| Send campaigns; manage contacts/lists/templates/segments | ✓ | ✓ | ✓ | — |
| Edit suppression | ✓ | ✓ | ✓ | — |
| Invite/remove members; change roles | ✓ | ✓ | — | — |
| Manage SMTP/ESP credentials & sending domains | ✓ | ✓ | — | — |
| Create/revoke API keys | ✓ | ✓ | — | — |
| View audit log | ✓ | ✓ | — | — |
| Transfer ownership, delete workspace, billing (P6) | ✓ | — | — | — |

Exactly one owner; ownership moves via explicit transfer (old owner → admin). An admin cannot modify/remove the owner. A user cannot remove themselves if sole owner. The enum extends in P6 (custom RBAC) without migration churn because role lives on `memberships`.

### 6.3 Session auth (SPA)

Opaque random token (≥256 bits) in an httpOnly cookie; the SPA never reads it.

```
Set-Cookie: ir_session=<opaque-token>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=1209600
```

Token stored **hashed** (`sessions.session_token_hash`). Sliding expiry capped at an absolute max (30 d). Logout deletes the row (instant revocation — the JWT-less advantage). Password change / "log out everywhere" revokes all sessions. `ip`/`user_agent` power an "active sessions" UI. **Active workspace** = `sessions.active_workspace_id`; switching is a server call that re-validates membership.

### 6.4 CSRF

Cookie auth ⇒ every unsafe method (POST/PUT/PATCH/DELETE) needs CSRF defense; safe methods are exempt. Two layers: (1) **Origin/Referer allowlist**; (2) **double-submit** — a non-httpOnly `ir_csrf` cookie the SPA echoes in `X-CSRF-Token`; server requires header == cookie. Cookie name `ir_csrf`, header `X-CSRF-Token` (the SPA section conforms to these names). API-key requests (no cookie) are CSRF-exempt; ESP webhooks are HMAC-verified, not session/CSRF.

### 6.5 Auth flows

- **Signup → workspace:** validate email (reuse cached syntax+MX), reject breached/weak passwords, Argon2id-hash, create `pending` user, send signed single-use `email_verify` token (in `tokens`). On verify: set `email_verified_at`, create first workspace + `owner` membership, open session. Bulk send blocked until `physical_address` is set.
- **Login:** constant-time Argon2 verify (always run the hash, even for unknown email, to avoid timing enumeration); generic errors; throttle/lockout; optional TOTP hook (P6).
- **Invite:** admin/owner POST invite (role ≤ inviter; admins may invite admin/member/viewer, not owner). Store hashed `invite` token + expiry; single-use. Acceptance attaches existing user or runs a constrained signup. Audit `invite.sent`/`invite.accepted`.
- **Password reset:** signed single-use `password_reset` token (hashed); on use set new Argon2 hash and **revoke all sessions**. Generic response (no enumeration).

### 6.6 API keys

Format `irk_live_<workspace-short>_<random>` / `irk_test_…`. `prefix` (first ~12 chars incl. mode) stored plaintext for display/revocation; full key shown once. At rest **SHA-256, no salt** (high-entropy token; salt buys nothing and would break O(1) prefix lookup; Argon2 is for low-entropy passwords only). Verify: parse prefix → look up candidate → constant-time hash compare. Transport `Authorization: Bearer irk_…`; never in query strings; never logged beyond prefix. Lifecycle: rotate (new key, old valid for grace window, then revoke), revoke (immediate), optional expiry, `last_used_at`.

### 6.7 Password & credential storage

| Secret | Method | Rationale |
|---|---|---|
| User passwords | **Argon2id** (memory-hard, per-user salt; bcrypt fallback) | defeats offline cracking of low-entropy secrets; rehash on login if cost increases |
| API keys | **SHA-256**, no salt, prefix-indexed | high-entropy; O(1) lookup |
| Session/verify/reset/invite/optin tokens | random ≥256-bit, stored **hashed** | DB leak ≠ live tokens |
| SMTP/ESP credentials | **AES-256-GCM envelope** (DEK per secret, wrapped by master key; `key_id` recorded) | must be decrypted to use SMTP login |
| Suppression-on-erasure email | **HMAC-SHA256(email, pepper)** | compliant retention without storing PII (§8.6) |

Password policy: minimum length + breached-password screen (k-anonymity / HIBP range or local set); no composition rules that push toward weak patterns.

### 6.8 Per-request workspace scoping (the highest-leverage control)

Lifecycle: **authenticate** (session or API key → principal) → **resolve workspace** (`session.active_workspace_id` or `api_key.workspace_id`; the `X-Workspace-Id` hint is validated against memberships and may switch the active workspace, but is never the trust source) → **bind context** (`current_workspace_id`, role/scopes in a request-scoped `ContextVar`/dependency) → **authorize** (role for UI, scope for API) → **scope every query**.

Enforcement, defense in depth:
- **Primary:** workspace-scoped repository/session that injects `workspace_id` automatically; raw cross-tenant access requires a named, audited admin path.
- **Secondary:** on writes, assert the loaded object's `workspace_id` matches context (catches IDOR via a valid foreign id) — return 404, not 403.
- **Tertiary (Postgres prod only):** RLS policies keyed off a per-connection `app.workspace_id`. **SQLite has no RLS**, so the app-layer guard is mandatory and is the sole control on the default deployment; RLS becomes load-bearing only once Postgres is mandatory (§2.5).
- **Tests:** a standing isolation suite asserting workspace A cannot read/update/delete B's records (expect 404).

**Background jobs:** every `Job` carries `workspace_id` + `created_by`; `/jobs/{id}` and `/jobs/{id}/download/{key}` verify requester workspace == job workspace; download keys are non-guessable. Workers carry the job's workspace context so suppression and quota checks are tenant-correct (fixing the current unscoped in-memory manager where any job id grants artifact access).

### 6.9 Rate limiting & abuse controls

| Surface | Limit (tunable) | Response |
|---|---|---|
| Login/reset (per IP + per account) | 5–10/min then exponential backoff; lockout after N fails | 429; lockout email |
| Signup (per IP) | low | 429 |
| API (per key) | per-tier 60–600/min | 429 + `Retry-After` + `X-RateLimit-*` |
| AI assists (per workspace) | budget-based | 429 |
| Send enqueue (per workspace) | bounded by quota + queue pacing | 429 / queued |
| **Public tracking/unsub** (per IP + per token) | per-token open dedupe; per-IP burst cap | drop/dedupe (not counted) |

Counters: in-process token bucket in P1, Redis when arq lands. P6 adds per-workspace abuse detection (volume spikes, high bounce/complaint) that auto-throttles/suspends a tenant.

### 6.10 Secrets handling

- **Master/app secrets** (cookie-signing key, encryption master key, suppression pepper, `GEMINI_API_KEY`) from env / secrets manager, never committed (extends the existing `os.getenv` pattern; `.gitignore` already excludes env files).
- **Tenant SMTP/ESP secrets** encrypted before DB, decrypted only in the worker at send time, in memory, minimum lifetime; never returned by any API (write-only: client sends a new value or leaves unchanged; API exposes only "configured: true/false"); never in `jobs.payload`, logs, or `last_error`.
- **Never log secrets:** scrub `Authorization`, passwords, SMTP creds from logs and traces (the current code passes `sender_password` as an argument that could surface in a stack trace — the new architecture redacts).
- **TLS verification:** the current `SmtpSession._context()` sets `CERT_NONE` for non-major hosts (MITM risk). The adapter **verifies by default**; an explicit, per-credential, audited opt-out is required for self-signed internal relays and is surfaced as a warning.
- **Key rotation:** master keys rotatable via the envelope scheme (re-wrap DEKs; `key_id` records the wrapping version).

### 6.11 SaaS hardening (P6)

Per-workspace daily/monthly send caps (enforced at enqueue **and** send); audit-log UI over the P1-written rows; granular/custom RBAC on the `memberships.role` seam; structured request logs (secrets scrubbed) + auth-failure/rate-limit metrics + anomaly alerting; SSO/SAML + enforced 2FA workspace policy; tenant data export + hard-delete honoring suppression retention.

### 6.12 Audit & DLQ are P1 cross-cutting, not P6

To make the GDPR/CAN-SPAM provenance the spec leans on actually exist, **every state-changing handler writes an `AuditLog` row starting in P1** (the *UI* is P6). Separately, a **dead-letter queue + alert hook** for jobs exhausting `max_attempts` (`status='dead'`) is available from P1 — P1–P5 sends never fail silently; the P6 observability work adds dashboards on top.

---

## 7. Sending Pipeline, Queue & Tracking

Turns "send campaign to a list/segment" into durable per-recipient delivery, tracks it, and feeds engagement/suppression back. Evolves the in-memory `JobManager` and the single reused `SmtpSession` into a DB-backed, tenant-scoped, resumable pipeline behind an ESP adapter. All tables/queries/endpoints are workspace-scoped (§6).

### 7.1 Design goals

- **Durable & resumable** — a crash or `--reload` never double-sends, skips, or loses a recipient; state lives in the DB.
- **Per-recipient isolation** — one bad address / 5xx / render error never aborts the campaign.
- **Idempotent at every boundary** — enqueue, claim, send, webhook ingest all dedupe.
- **ESP-agnostic** — send/track/suppress never imports `smtplib`; it talks to an adapter.
- **Suppression is law** — no suppressed address is ever mailed, even via a new campaign or fresh import (workspace **and** global).
- **Compliant by construction** — unsubscribe headers, physical address, DKIM signing, pre-send checks enforced in the pipeline.

### 7.2 Overview

```
Campaign(draft) --schedule(idempotent,state-guard)--> campaign_send job
  --> validate sendable (verified+DKIM domain, unsubscribe+address, preflight)
  --> materialize Messages (dedupe-on-email, skip suppressed up front)
  --> fan out send_batch jobs (~100–500)
  --> worker claims batch --> per recipient: suppression+global gate
       -> render (merge, plaintext, unsub/address inject) -> DKIM sign -> ESP.send
  --> Message.status transitions; circuit-breaker watches complaint/bounce rate
  --> events (open/click/unsub) + DSN poller (bounce) -> suppressions + rollups
```

### 7.3 The worker

Standalone `python -m icereach.worker`, separate from the API, so an API restart never kills in-flight sends.

**Claim loop (Postgres):**
```sql
UPDATE jobs SET status='claimed', claimed_by=:wid, claimed_at=now(),
  lease_expires_at=now() + interval '60 s'
WHERE id = (SELECT id FROM jobs
            WHERE status='queued' AND run_after <= now()
            ORDER BY priority, run_after
            FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING *;
```
- **SQLite default:** no `SKIP LOCKED`; emulate with `BEGIN IMMEDIATE` + `UPDATE … WHERE id IN (SELECT … LIMIT 1)`. **Single-worker only** on SQLite; multi-worker requires Postgres (§2.5).
- **Crash recovery:** a reaper requeues `claimed` jobs whose `lease_expires_at < now()`; long batches **heartbeat** to extend the lease; per-message idempotent state means a requeued batch resumes from the first non-terminal message — no double-sends.
- **Fairness/backpressure (Postgres):** round-robin across `workspace_id` (or weight by quota); per-workspace token bucket — empty bucket → re-defer via `run_after`, not spin.
- **DLQ:** on `attempts == max_attempts` the job goes `dead`; an alert hook fires; `/jobs` exposes it; replay is an admin action.

**Job decomposition:** `campaign_send` validates sendability, materializes `messages` (idempotent via `dedupe_key`), fans out `send_batch` jobs. `send_batch` runs the throttled send loop. `dsn_poll` (P1) ingests bounces; `webhook_process` (P4) ingests ESP events.

### 7.4 ESP adapter interface

The single choke point through which all mail leaves.
```python
class EmailAdapter(Protocol):
    def open_session(self) -> "SendSession": ...
    def capabilities(self) -> AdapterCaps: ...   # native_open_tracking, batch, webhooks, idempotency, dkim

class SendSession(Protocol):
    def send(self, msg: OutboundMessage) -> SendResult: ...
    def send_batch(self, msgs: list[OutboundMessage]) -> list[SendResult]: ...
    def close(self) -> None: ...
```
`OutboundMessage` is provider-neutral: `from`, `to`, `subject`, `html`, `text`, `headers` (incl. `List-Unsubscribe`), `dkim` (selector/private-key handle), `mail_from` (aligned return-path), `idempotency_key`, `tracking_token`, `metadata`. `SendResult` = `{status: accepted|deferred|rejected, provider_message_id, code, detail, retryable}` — **classified**, so the worker decides retry-vs-suppress without parsing raw SMTP strings.

| Concern | SMTP adapter (P1) | SES/Resend/SendGrid (P4) |
|---|---|---|
| Transport | `smtplib` over a pooled `SmtpSession` | HTTPS JSON API |
| DKIM | iceReach signs (P1) | native or iceReach |
| Open/click | iceReach pixel + link rewrite | toggle native vs iceReach via `capabilities()` |
| Idempotency | `messages.idempotency_key` guard | native header |
| Bounce/complaint | DSN poller (P1) / FBL (P4) | signed webhooks (P4) |
| List-Unsubscribe | iceReach sets headers | ESP passes through |

**Reusing `SmtpSession`** (current code at `app.py` ~179–241): becomes the internals of the SMTP `SendSession`, with three fixes to documented fragility — (1) **pool, not singleton** (2–8 configurable); (2) **per-message error isolation** — the current `send_email` returning `True` on `SMTPRecipientsRefused` (a swallowed failure at ~282–283) is replaced by classifying `SMTPRecipientsRefused`/5xx → `rejected` (suppress candidate), `SMTPServerDisconnected`/timeout/421/4xx → `deferred` (retry); (3) **bounded reconnect + backoff**. Credentials are decrypted only inside the adapter at session-open, held in memory for the session, never in `jobs.payload`/logs.

### 7.5 Merge-tag rendering

Extends the current `render_template()` (`app.py` ~246, regex `\{(\w+)\}`). The single merge contract (§8.7): `{column}` and `{column|fallback}`; per-`ContactField` configured default applies when no inline fallback is given; HTML-escape CSV-derived values; pipeline-injected unsub/address/view-in-browser values (never from user data); render-time validation flags unknown tags as a pre-send warning; **every message is `multipart/alternative` with a deterministic plaintext part** (AI optional, html2text mandatory, §8.7); rendered HTML/text + subject snapshotted on the `messages` row at first render for byte-identical retries.

### 7.6 Batching & throttling

`campaign_send` slices recipients into `send_batch` jobs (~100–500). Native-batch ESPs use `send_batch()` (up to ~500–1000 personalized versions/call); SMTP iterates the pool. **Per-workspace token bucket** (rate + burst), persisted across restarts; empty → defer via `run_after`. **Separate lanes** by priority: transactional (high) and bulk never share a bucket or stream. Honor provider signals (SMTP 421/`Retry-After`, ESP 429) by backing off the whole bucket. Warmup ramp overlays the bucket (§8.9).

### 7.7 Retry policy (per message)

| Result | Examples | Action |
|---|---|---|
| `accepted` | 250 / 2xx | mark `sent`; await DSN/webhook |
| `deferred` (retryable) | 4xx, timeout, disconnect, 429 | exp backoff (1m,5m,30m,2h), cap `max_attempts`, then `failed` |
| `rejected` (hard) | 5xx, recipient refused, invalid | `failed` immediately; classify for suppression |

Soft bounces (mailbox full, greylist) are **deferred**, never suppressed; hard bounces are suppressed. Conflating the two is explicitly avoided.

### 7.8 Circuit-breaker (auto-pause)

Resolves "warns but never halts a running blast." During a `campaign_send`, the worker maintains a rolling complaint-rate and hard-bounce-rate over the messages already processed. **Crossing 0.1% complaint or a configurable hard-bounce threshold → throttle; crossing 0.3% complaint (the Gmail cliff) or a high hard-bounce rate → auto-PAUSE the job** (`Campaign.status='paused'`, remaining batches `canceled`/held), write an `AuditLog` row, and surface an in-product alert. Resume is an explicit human action. This protects reputation before a human can react.

### 7.9 Idempotency (end to end)

| Layer | Mechanism | Guarantee |
|---|---|---|
| Schedule | `Idempotency-Key` + `Campaign` state-machine + partial unique on `send_job_id` | double-click never double-sends a whole list |
| Enqueue | `jobs.idempotency_key` UNIQUE per workspace | client retry doesn't dup jobs |
| Materialize | `messages.dedupe_key` UNIQUE(`campaign_id`,`contact_id`) | a contact appears once per campaign even across lists |
| Claim | `FOR UPDATE SKIP LOCKED` + lease | no two workers process one job |
| Send | `messages.idempotency_key` to ESP; SMTP guards on non-terminal `messages.status` | provider-side dedupe; SMTP no double-send |
| Webhook ingest | `events.provider_event_id` UNIQUE | replayed events are no-ops |

A message transitions `pending→sending` only under a row guard; the worker re-reads status after claim. **P1 honesty:** the crash-between-"ESP accepted" and "DB committed" reconciliation that ideally uses a delivery webhook keyed on `provider_message_id` does **not** have a delivery webhook in P1 (SMTP). In P1 the guard is the SMTP-side `messages.status` check plus the DSN poller correlating later bounces; true delivery-webhook reconciliation arrives in P4. This is stated rather than assumed.

### 7.10 Tracking

All tracked URLs use the per-message `tracking_token` (opaque, HMAC-signed). Tracking requires a stable HTTPS **public base URL**, ideally a per-workspace authenticated tracking subdomain (avoids shared-host reputation + open-redirect risk). Toggleable per send and per link. Public endpoints are rate-limited per IP and per token (§6.9).

- **Open pixel** `GET /t/o/{token}.gif` — verify signature, write `opened`, return 1×1 transparent GIF, `Cache-Control: no-store`. **Bot-filtering:** Apple MPP and scanners prefetch images; known prefetch UAs/IPs and same-instant-as-send opens are `is_bot=true` and excluded from headline metrics. Opens are never a sole success/A-B-winner metric.
- **Click redirect** `GET /t/c/{token}` — at render every `<a href>` (except unsubscribe — never rewritten) is rewritten with the original URL signed into the token; the endpoint verifies the signature (closes open-redirect), writes `clicked` with the original URL, 302s. `mailto:`/`tel:` pass through.
- **Unsubscribe** (canonical `/u`): headers `List-Unsubscribe: <https://…/u/{token}>, <mailto:unsub+{token}@…>` + `List-Unsubscribe-Post: List-Unsubscribe=One-Click`. `POST /u/{token}` (one-click, no login) → `unsubscribed` event + `Suppression(reason=unsubscribe)`, honored immediately (well under the 2-day rule). `GET /u/{token}` → hosted confirmation + preference center (opt-down P5). The `mailto:` path is processed by the inbound handler into the same suppression path.

### 7.11 Bounce / complaint ingestion

| Source | Path | Phase |
|---|---|---|
| SMTP DSN / MAILER-DAEMON | **`dsn_poll` job** reads the return-path mailbox, parses DSN, classifies → `events` + `suppressions` | **P1** |
| SMTP FBL/ARF (complaints) | ARF parsing from FBL feeds → suppress | P4 |
| ESP | signed webhooks `POST /api/v1/esp-webhooks/{provider}` | P4 |

Handler requirements: verify HMAC before trusting payload (unsigned forged bounces rejected `401`); dedupe on `provider_event_id`; process async via `webhook_process` (200 fast); classify hard bounce/complaint → suppress (workspace + global), soft → defer; correlate via `provider_message_id`; complaint-rate monitoring feeds the circuit-breaker (§7.8).

### 7.12 Migration from current code

| Current | Becomes |
|---|---|
| In-memory `JobManager` (dies on restart) | `jobs` table + standalone worker, leased claim, resumable, DLQ |
| One shared `SmtpSession` per blast | pooled `SmtpSession`s inside the SMTP `SendSession` |
| `send_email()` returning `True` on recipient-refused | classified `SendResult`; status drives retry/suppress |
| `render_template()` literal-passthrough on miss | extended: `{tag|fallback}`, configured defaults, HTML escaping, mandatory plaintext + unsub/address inject, render-time validation |
| Inline `validate_email` (syntax+MX, in-proc cache) | reused at import + materialization; cache promoted to `MxCache` with TTL policy |
| No tracking/unsub/suppression | pixel + click + List-Unsubscribe/one-click + workspace & global suppression enforced at send |
| Direct `smtplib` in the request path | all sending behind `EmailAdapter`; core never imports `smtplib` |
| `CERT_NONE` TLS for custom hosts | verify by default; audited opt-out only |

---

## 8. Deliverability & Compliance

This section is where the critics' single largest hole is closed: **email authentication and bounce handling are P1, not P4.**

### 8.1 Why P1 must authenticate

Gmail/Yahoo bulk-sender rules (Feb 2024) require, for senders above ~5k/day: a DKIM-signed message, SPF or DKIM aligned with the From domain under a published DMARC policy, one-click List-Unsubscribe (RFC 8058) honored within ~2 days, and complaint rates kept below 0.3% (ideally under 0.1%). A P1 platform that bulk-sends without these is junked or rejected. iceReach therefore ships SPF/DKIM/DMARC publish-and-verify + DKIM signing in P1 for a single configured sending domain.

### 8.2 DKIM signing (P1)

On domain setup the platform generates a DKIM selector + RSA-2048 keypair; the public key is shown as a DNS TXT record to publish; the private key is stored `EncryptedString` on `SendingDomain`. The worker DKIM-signs every outbound message (SMTP adapter) over a standard header set + body hash. `preflight` blocks send unless `dkim_verified` is true.

### 8.3 SPF (P1)

The DNS UI shows the SPF TXT record to publish for the return-path domain (and `from_email` domain) authorizing the sending host/relay. Verification polls DNS and sets `spf_verified`.

### 8.4 DMARC alignment & MAIL FROM / return-path (P1)

Resolves "no DMARC alignment story / envelope-from may differ from From silently." DMARC passes only when SPF **and/or** DKIM **aligns** with the From domain.
- **DKIM alignment:** the signing `d=` domain equals the `from_email` domain (or an aligned subdomain) — guaranteed because the DKIM key belongs to the verified `SendingDomain`.
- **SPF alignment:** SPF authenticates the **MAIL FROM / envelope-from (return-path)**, which must be on a domain aligned with the From domain. iceReach therefore pins `mail_from` to `SendingDomain.return_path_domain` (a subdomain of the verified domain, e.g. `bounce.mail.acme.com`), so SPF aligns under DMARC and bounces flow to a mailbox iceReach controls (feeding the §7.11 DSN poller). The platform renders the recommended DMARC record (`p=none` to start, advising `p=quarantine`/`reject`) and verifies `dmarc_verified`.

### 8.5 Double opt-in (functional in P1)

`ContactList.double_optin` and `ListMembership.optin_token_id` exist in P1; the **confirmation send path is P1**. When a contact is added to a `double_optin` list (import/API/`POST /lists/{id}/contacts`), the member is `pending`, an `optin_confirm` token is created, and a confirmation email is sent via the platform/identity send path. `POST /lists/{id}/optin/resend` re-triggers it. `GET /f/confirm/{token}` (public) flips `pending → subscribed`. The hosted *form* (`/f/{form_id}`) is P5, but double-opt-in for imported/API contacts works in P1.

### 8.6 GDPR erasure vs suppression retention

Resolves "DELETE keeps suppression hash, but schema stored plaintext `email_canonical`." On erasure (`DELETE /contacts/{id}`): the `Contact` row is hard-deleted; if a suppression must persist (legal obligation under CAN-SPAM/PECR to not re-mail an unsubscribed/bounced address), the `Suppression` row's `email_canonical` is cleared and `email_hash = HMAC-SHA256(canonical_email, pepper)` is set. Send-time enforcement therefore hashes the candidate recipient and compares against `email_hash` as well as `email_canonical`. The lawful basis (legal obligation) is recorded in the suppression provenance/audit row. Cross-tenant `GlobalSuppression` stores only the hash from the start.

### 8.7 Merge-tag contract (single, end to end)

Resolves the two competing fallback mechanisms and the `{{TOKEN}}` mismatch.
- **One syntax:** `{column}` and `{column|fallback}`. Both inline-fallback and per-field configured default exist; **resolution order:** value present → use it; else inline `|fallback` if given; else `ContactField.default_value`; else empty string (never the literal `{column}` shipped to a subscriber).
- **Extended regex (replaces `\{(\w+)\}`):** `\{(\w+)(?:\|([^}]*))?\}` — group 1 = column, group 2 = optional fallback. The renderer HTML-escapes resolved values.
- **Special platform tokens are `{column}`-style, not `{{ }}`:** `{unsubscribe_url}`, `{physical_address}`, `{view_in_browser_url}` are **reserved keys** the pipeline injects (per-message, signed) at render; they are not contact fields and cannot be overridden by data. **AI body-draft (§9.5.2) must emit these single-brace reserved tokens**, not `{{UNSUBSCRIBE}}` — the AI output contract is aligned to the renderer contract here.
- **Deterministic plaintext is a hard P1 dependency:** every message is `multipart/alternative`; the plaintext part is generated by a deterministic html2text converter **always**, regardless of `GEMINI_API_KEY`. The AI plaintext capability (§9) is an optional quality improvement layered on top; if AI is degraded, the deterministic text still satisfies the mandatory-plaintext rule. (The current `send_email` attaches HTML only — this closes that gap.)

### 8.8 CAN-SPAM / List-Unsubscribe checklist (enforced in preflight)

Deterministic, non-AI, authoritative (the AI critique is advisory only): physical postal address present in footer (`{physical_address}` resolves; `Workspace.physical_address` set); functioning unsubscribe (`{unsubscribe_url}` + `List-Unsubscribe`/`List-Unsubscribe-Post` headers); accurate From/Reply-To on a verified domain; no deceptive subject; all merge tags resolvable; DKIM-signed + DMARC-aligned domain. Any failure → `412 preflight_failed`.

### 8.9 Warmup / IP & domain ramp (referenced P1, concrete P4)

Resolves "no warmup → first real send burns reputation." New sending domains/IPs ramp gradually: the per-workspace token bucket (§7.6) is overlaid with a **warmup schedule** — a daily volume ceiling that increases on a curve (e.g. 50 → 100 → 500 → … day over day) until reaching the configured `sending_quota_daily`. P1 enforces the ramp ceiling on the single SMTP domain; P4 makes it concrete per dedicated IP/pool. Sends over the day's ramp ceiling defer to the next window rather than blasting a cold domain.

### 8.10 Monitoring

Rolling per-workspace complaint-rate and bounce-rate are tracked and surfaced in-product against the **0.1% warn / 0.3% halt** thresholds; the §7.8 circuit-breaker auto-pauses an in-flight blast on breach. P1 bounce signal is the DSN poller; complaint signal becomes live in P4 (FBL/ESP).

---

## 9. AI Service (Gemini `gemini-3-flash-preview`)

One module all AI features route through. Wraps `google-genai`, pins `gemini-3-flash-preview`, exposes one typed function per capability plus a thin FastAPI router. Every capability is workspace-scoped, schema-validated, cached, metered, degradable, and **phase-gated**.

### 9.1 Invariants

| Principle | Rule |
|---|---|
| Single entry point | No other module imports `google-genai`; client constructed once, injected |
| Structured output only | JSON mode (`response_mime_type="application/json"`) + Pydantic `response_schema`; no regex parsing of free text |
| Output untrusted | validate against Pydantic, then sanitize (HTML allowlist; merge tags re-validated against the real column set) before DB/email |
| Human-in-the-loop | AI never sends/schedules/mutates contacts/suppression; the module is structurally read-only w.r.t. those tables |
| Tenant isolation | every function takes `workspace_id`; prompts built only from that workspace's data; cache/quota/ledger keyed by workspace |
| Grounded | facts (columns, metrics) passed in the prompt; model told to use only provided fields and emit "missing data" rather than fabricate |
| Graceful degradation | no `GEMINI_API_KEY` → typed `degraded` result, never a 500; UI hides AI; core sending unaffected |

### 9.2 Module layout

`ai/client.py` (lazy singleton, `is_enabled()`, pinned model constant) · `ai/runner.py` (the one `run(...)` every capability calls) · `ai/schemas.py` (Pydantic request/response = the `response_schema` source) · `ai/prompts.py` (versioned templates; version in cache key + ledger) · `ai/sanitize.py` (HTML allowlist, merge-tag validator/repair, link/UTM checks) · `ai/capabilities/*.py` · `ai/usage.py` (ledger, quota, rate limiter) · `ai/router.py` (`/api/v1/ai/*`, auth + CSRF + scoping + **phase gate**).

### 9.3 Shared envelope

```
AIResult[T] = {
  status: AIStatus,            # ok|cached|degraded|rate_limited|quota_exceeded|invalid_output|error
  data: T | null,             # null unless status in {ok, cached}
  model: "gemini-3-flash-preview",
  prompt_version: str,
  cached: bool,
  usage: { input_tokens, output_tokens, est_cost_usd } | null,
  warnings: [str],
  request_id: str
}
```
`status` uses the canonical `AIStatus` enum (§4.0) — the same set the `AIUsage` ledger stores, so the ledger can represent `degraded`/`rate_limited`/`quota_exceeded`/`invalid_output` (resolving the prior `ok/error/cached`-only mismatch). `cached` is both a boolean and reflected by `status=cached`.

### 9.4 Runner gate order (short-circuits to typed result)

1. **Enabled** — `is_enabled()` false → `degraded`.
2. **Quota** — monthly token budget per workspace → `quota_exceeded`.
3. **Rate limit** — per-workspace token bucket (default 60/min) → `rate_limited` (HTTP 429 + `Retry-After`).
4. **Cache** — key `sha256(capability + prompt_version + model + canonical(inputs) + workspace_id)`; hit → `cached`, no spend.
5. **Call** — JSON mode, schema, temperature, `max_output_tokens`, 20 s timeout; retry on 429/5xx/timeout (≤2, exp backoff).
6. **Validate** — parse into Pydantic; failure → one repair retry with the error appended; second failure → `invalid_output`.
7. **Sanitize** — HTML/merge-tag/link post-processing.
8. **Meter + cache** — record usage; store sanitized result with capability TTL.

Defaults: temp 0.1–0.2 (analytics/spam/segment/send-time), 0.4–0.7 (rewrite/body), 0.9 (subjects); cache 24 h (grounded), 1 h (creative), 0 (sequence draft).

### 9.5 Capabilities

Shared merge-tag awareness: callers pass `available_columns` (the `ContactField.key` set); the model uses only those tags with `{tag|fallback}`; post-validation re-runs the §8.7 extended regex and flags unknown tags.

- **9.5.1 Subjects + variants (P1).** In: `{ body_or_brief, audience?, tone, n=5, available_columns, product_context? }`. Out: `variants[{subject≤78, preheader≤110, predicted_open_band, spam_risk, rationale, merge_tags_used}]`. Guardrails: length truncation, merge validation, drop `spam_risk>0.8`, dedupe. Temp 0.9, ~300 tok, cache 1 h. Degraded → existing manual multi-subject input (the app already supports a subject list with random pick at `app.py` ~59/~442).
- **9.5.2 Body draft (P1).** In: `{ brief, audience?, tone, length, available_columns, cta?, brand_voice?, locale="en", must_include? }`. Out: `{ subject, preheader, html, plaintext, merge_tags_used, assumptions }`. Prompt: email-client-safe HTML (table-friendly, inline-style-ready, no `<script>`/external CSS/JS), include CTA, **emit the reserved single-brace tokens `{unsubscribe_url}` and `{physical_address}`** (not `{{ }}`; §8.7) which the platform injects at send. Guardrails: `ai/sanitize.py` allowlist; merge validation; verify reserved tokens present; never send-ready until §9.5.4 critique + the deterministic preflight pass. Temp 0.7, ~1500 tok.
- **9.5.3 Rewrite/shorten/extend/tone/translate (P1).** Hard constraint: preserve all `{column}` tags + HTML structure/links verbatim; translate copy only. Post-check output tag/link set ⊇ input set; re-sanitize. Temp 0.4.
- **9.5.4 Pre-send spam/deliverability critique (P1).** In includes `has_unsubscribe`, `has_physical_address`, `link_domains`, `image_to_text_ratio`, `is_bulk`. Out: `{ score, verdict: pass|warn|block, issues[{severity,code,message,fix,location?}], summary }`. **Advisory only** — the deterministic §8.8 gate is authoritative and hard-blocks regardless of AI verdict. Temp 0.1.
- **9.5.5 Plaintext (P1).** AI plaintext for `multipart/alternative` — but the deterministic html2text path (§8.7) is the mandatory hard dependency; AI is a quality layer. Degraded → deterministic text only.
- **9.5.6 Sequence drafting (P3).** Goal → editable multi-step graph + per-step copy. Each email sanitized + merge-validated; loads into the builder as a draft, never armed; each step's email passes critique before it can send. Temp 0.6, no cache.
- **9.5.7 Send-time recommendations (P4).** Aggregated workspace history only (never raw PII) → ranked windows with `basis`; recommendation only (scheduler executes). Apple MPP open-inflation caveat injected when basis relies on opens.
- **9.5.8 NL→segment (P5).** Exact contact field/event/tag lists → filter AST; `unresolved_terms` for unmappable; AST validated against the §5.4 grammar; previewed before save, never auto-applied.
- **9.5.9 Analytics narratives (P5).** Real numbers + baseline → plain-English summary + anomalies; never compute new metrics; numbers in the narrative cross-checked against input (reject hallucinated figures). Read-only.

### 9.6 Cross-cutting guardrails

HTML sanitization on every HTML-producing capability (allowlist; strip `<script>`/`<iframe>`/event handlers/`javascript:`/`data:`/remote CSS). Merge-tag safety via the §8.7 extended regex (unknown tag → warning at compose, `invalid_output` after one repair). No AI auto-send/auto-mutate (structurally read-only). Compliance authority is deterministic (§8.8). Prompt-injection hardening: user/CSV text passed as clearly delimited data, never instructions; output schemas constrain returns.

### 9.7 Cost & usage (`ai/usage.py`)

Per-call ledger row → `AIUsage` (§4.12) with the full `AIStatus`. Monthly token budget per workspace (config + plan tier P6); soft warn 80%, hard `quota_exceeded` 100%. Per-workspace token-bucket rate limit (60/min default → 429 + `Retry-After`). Cost controls: capability `max_output_tokens`, aggressive caching for grounded calls, client-side debounce on inline calls, heavy capabilities require explicit action + show an estimate. Privacy: prompts log metadata + hashes by default, not bodies/PII; aggregated history for §9.5.7/9.5.9, never raw contact PII.

### 9.8 Degradation (no `GEMINI_API_KEY`)

`is_enabled()` false → no client built → runner short-circuits to `degraded` (no exception, no 500); router returns 200 with the degraded envelope; the SPA's `useAIEnabled()` hides AI affordances; the core platform is fully functional (manual compose, manual subjects, manual segments, manual journeys, and the deterministic compliance/spam gate). **Send compliance never depends on AI.**

### 9.9 Phasing & gating

The AI router enforces **phase gates** keyed off platform config so half-built capabilities aren't exposed before their phase. P1: 9.5.1–9.5.5 + merge-tag-check + deterministic plaintext + full runner/usage/degradation infra. P3: 9.5.6. P4: 9.5.7. P5: 9.5.8, 9.5.9. Calling a not-yet-enabled endpoint returns `feature_not_enabled`. **Quota/rate-limit infra lands in P1** (it is part of the runner); P6 *billing* folds AI usage into plan tiers and per-key AI scoping — it does not introduce quota enforcement, it monetizes the existing one (resolving the P1-vs-P6 overlap).

### 9.10 Dependency

Add `google-genai` via `uv` (per global instructions, `uv pip install` inside the activated `.venv`); wire `GEMINI_API_KEY` through the existing pydantic-settings config alongside the current env keys.

---

## 10. Analytics

### 10.1 Sources & honesty

Analytics are computed from `Event` (bot-filtered) and frozen into `CampaignStats` (§4.7) before Event retention purge. **Per §2.3, each metric is labeled by the phase that populates it; P1 does not display numbers it cannot source** (`delivered_count` and `complaint_count` render as "—" until P4).

### 10.2 Per-campaign

Counts: sent; hard/soft bounces (P1 from DSN); unique + total opens; unique + total clicks; CTR; CTOR; unsubscribes (P1). `delivered`, complaints (P4). Rates use proper denominators (against `sent` in P1; against `delivered` once P4 provides it), with trend over time and top-links/clickmap. Deliverability guardrails (bounce-rate, and complaint-rate once P4) shown inline against 0.1%/0.3%.

### 10.3 Workspace overview

Rates over time, filterable by tag/identity; usage vs quota; complaint/bounce trend vs thresholds; job/queue health. Feeds the P5 AI analytics narrative.

### 10.4 Bot filtering

Apple MPP / scanner / prefetch opens flagged `is_bot=true` and excluded from headline metrics; opens are never a sole success or A/B-winner metric. Narratives note MWP inflation when bot-filtering is unavailable.

### 10.5 Exports

`GET /analytics/export` and `GET /contacts/export` run as jobs (`202 {job_id}`) and surface artifacts via `/jobs/{id}/download/{key}`.

---

## 11. React SPA Architecture

A single-page React app (Vite + TypeScript) talking only to `/api/v1`. Pure API client: no Jinja, no Bootstrap; the legacy `templates/*.html` and `static/` are retired; the Scraper UI is removed.

### 11.1 Principles

API-first and typed end-to-end (types generated from OpenAPI). Server state (TanStack Query) vs client state (React context / Zustand) strictly separated. Every read is workspace-scoped, baked into query keys. Async-job-aware from day one (shared `useJob`). Security posture matches the API: httpOnly cookie session (JS never sees it), CSRF on mutations, untrusted HTML sanitized (DOMPurify) before the DOM.

### 11.2 Stack

Vite + `@vitejs/plugin-react-swc`; TypeScript strict (`noUncheckedIndexedAccess`, `@/*` alias); React Router data router; TanStack Query v5; **openapi-fetch + openapi-typescript** (types from `/openapi.json`, regen in CI); Zustand (small stores) + context for auth/workspace; React Hook Form + Zod; Tailwind (tokenized, dark mode via `class`); shadcn/ui (owned in `components/ui`); TanStack Table; Recharts (Visx for clickmaps); `@dnd-kit` (P2) + React Flow (P3); DOMPurify; date-fns + date-fns-tz; Vitest + Testing Library + MSW, Playwright E2E; ESLint + Prettier + typescript-eslint + Husky/lint-staged.

### 11.3 Layout (feature-sliced)

```
src/
  app/            router.tsx · providers.tsx · layouts/(Root,Auth,Workspace,Settings)
  lib/
    api/          schema.d.ts (generated) · client.ts · jobs.ts
    query/        queryClient · keys.ts · defaults
    auth/         session context · csrf · route guards
    utils/        cn() · formatters · tz · sanitizeHtml()
  features/       auth dashboard contacts lists segments templates builder(P2)
                  campaigns automations(P3) analytics forms(P5) settings suppression
  components/     ui/ (shadcn) · shared/ (AppShell, DataTable, JobProgress, …)
  hooks/  styles/  test/  main.tsx
```
Per-feature: `routes/ · api/ (query+mutation hooks) · components/ · schemas.ts · types.ts`.

### 11.4 Routing

React Router data router; auth + workspace enforced at layout boundaries. Public auth routes under `AuthLayout`; everything else under `WorkspaceLayout` (authed + workspace selected); `/settings/*` under `SettingsLayout` (role-gated). **Workspace switch:** default header-based active workspace persisted server-side; optional `/w/:workspaceId/...` deep links — **the id is an untrusted hint validated against memberships server-side (§5.1); the SPA never asserts authority.** Top-level features are `React.lazy`-split (builder, journey canvas, charts are heavy). Each route segment has an `errorElement`. Wizards (campaign compose, contact import) are nested routes so the URL is the source of truth for the step. Role gating from `/auth/me` (`owner|admin|member|viewer`); UI hides what the API forbids (API is authority).

### 11.5 Auth/CSRF contract

Server sets httpOnly `ir_session` (Secure, SameSite=Lax) on login; CSRF via non-httpOnly `ir_csrf` cookie echoed in `X-CSRF-Token`, primed via `GET /auth/csrf` on boot; all requests `credentials:'include'`. Boot: `GET /auth/me` → 200 hydrates user/memberships/active-workspace/role; 401 → `/login` (preserve `returnTo`). Response interceptor: 401 clears auth + Query cache → `/login`; CSRF 403 → one-time CSRF refetch + retry, then surface a permission error.

### 11.6 API client & data layer

`createClient<paths>({ baseUrl:'/api/v1', credentials:'include' })`. Request middleware injects `X-CSRF-Token` (mutations), `X-Workspace-Id` (the untrusted active-workspace hint), and an **`Idempotency-Key`** (UUID) on send/create/schedule. Response middleware normalizes `{error:{code,message,field,request_id}}` to a typed `ApiError`, centralizes 401/403. Query-key factory `qk` starts every key with `[workspaceId, domain, …]` so switching workspaces invalidates cleanly. Defaults: `staleTime` ~30 s (lists), longer for reference data; no retry on 4xx, exp backoff on 5xx; `refetchOnWindowFocus` for dashboards/reports. Lists use `useInfiniteQuery` + TanStack Table virtualization (100k+ contacts). Mutations colocated; optimistic for cheap toggles (tag/list/suppression) with rollback. **`useJob`** polls `/jobs/{id}` (`{id,type,status,progress,message,result,artifacts,error}`) until terminal; `<JobProgress>` renders progress/message + artifact downloads; imports/validations/sends/AI batches flow through it (SSE/WebSocket swaps the interval later behind the same hook).

### 11.7 State management

Server/persistent → TanStack Query. Auth/session → context (from `me`). Cross-cutting UI → Zustand. Builder/canvas working graph → Zustand store per editor, autosave-debounced to API (block/graph JSON). Wizard/form → RHF + URL step. Table filters/pagination/sort/tab → React Router search params. Rule of thumb: if the server owns it, it isn't duplicated into Zustand (builder editors are the deliberate exception).

### 11.8 Page inventory by phase

- **P1:** Auth (login/signup/accept-invite/forgot/reset); App shell (workspace switcher, role-aware nav, command palette); Dashboard (KPI cards per §2.3 — sent/opens/clicks/bounces/unsub; deliverability health vs 0.1%/0.3%; job activity; AI tips); Contacts (virtualized table, detail with attributes/tags/subscription/activity timeline, **custom field manager → `/fields`**); Import wizard (upload → mapping → dedupe/upsert preview → validation → **job** with progress + error report + suppression-collision + **multi-email-row explosion** warning); Lists; Segments (rule builder + live count via deterministic engine; NL→segment is P5-gated); Templates (HTML editor with `{column}`/`{column|fallback}` insert + defaults, versions, test render); **Campaigns compose** (From/identity → audience(list/segment) → content(HTML + merge + live preview + plaintext) → AI assists(subject/body/spam-critique) → settings(tracking, schedule+tz, List-Unsubscribe) → **PreSendChecklist** → send/schedule via job, idempotency-keyed); Campaign report (per §10.2; "—" for delivered/complaints in P1); Suppression; Test sends; AI panel v1; Settings (workspace incl. physical address; members & roles; API keys; AI usage; **sending domains with SPF/DKIM/DMARC DNS UI + verify — P1**).
- **P2:** Block builder (`@dnd-kit`, palette, per-block settings, desktop/mobile preview, brand kit; export = inlined table-based HTML); reusable blocks; template library v2; multi-client preview & test sends.
- **P3:** Drip editor; journey canvas (React Flow: triggers/delays/branches/A-B-split/actions/goals, quiet hours, frequency caps; autosave graph JSON; validate before activation); AI sequence drafting; enrollment & run history.
- **P4:** Sending domains (extends P1) + identities + ESP/provider config (adapter choice, encrypted show-once creds, transactional vs broadcast streams); webhooks/events (inbound bounce/complaint status, signed-payload health); **A/B (advanced) + winner auto-send + send-time optimization — A/B lives here, not P1 (§12 reconciliation)**; deliverability dashboard.
- **P5:** Signup forms (builder, double opt-in, honeypot/captcha, hosted/embed, submissions); preference center + public archive ("view in browser"); advanced segmentation (RFM/engagement; expanded NL→segment); public API & outbound-webhook console (subscriptions, delivery log, replay); AI analytics narratives.
- **P6:** Billing (Stripe checkout/portal/invoices); quotas & usage meters + rate-limit status; **audit-log UI** over P1-written rows; granular RBAC matrix + SSO/SAML; observability surfaces (job/queue + webhook health).

### 11.9 Shared components & safety

`AppShell`/`WorkspaceSwitcher`/`NavSidebar`; `DataTable` (server pagination/sort/pinning/virtualization/bulk actions); `JobProgress`; `AsyncButton` (pending/disabled + idempotency-key wiring); `MergeTagInput`/`MergeTagMenu` (insert `{column}` with existence check + defaults, §8.7 syntax); `EmailPreview` (DOMPurify-sanitized desktop/mobile iframe with sample-row merge); `RuleBuilder` (AND/OR groups, reused for journey branches); `AiAssistPanel` ("AI — review before send"); `PreSendChecklist` (unsubscribe present, physical address, suppression count, **domain-auth status**, spam score); `StatCard`/`MetricChart`/`ClickMap`; `FileDropzone`+`ImportMapper`; `EmptyState`/`ErrorState`/`PermissionGate`; `ConfirmDialog`. Baked-in rules: sanitize all untrusted HTML (AI + CSV-derived) before render; idempotency keys on every send/create/schedule mutation; never let AI auto-send (staged + must pass `PreSendChecklist`); workspace-scoped query keys everywhere; timezone correctness (UTC stored, tz pickers, never naive datetimes).

---

## 12. Phase Breakdown & Acceptance Criteria

| Phase | Scope | Status target this build |
|---|---|---|
| 1 Foundation | tenant DB+auth+API keys, SPA shell, contacts+lists+import/validate, campaign compose+send, open/click tracking, unsubscribe+suppression+List-Unsubscribe, per-campaign analytics, AI v1 | Build fully + test |
| 2 Builder | drag-drop block email builder, template library, live preview, test sends | Implement core |
| 3 Automation | journeys: triggers/delays/conditions/branches, drip sequences, AI sequence drafting | Implement engine + basic UI |
| 4 Deliverability/ESP | SES/Resend/SendGrid adapters, SPF/DKIM/DMARC + signing, bounce/complaint webhooks, A/B testing, send-time optimization | Adapters + A/B + webhooks |
| 5 Growth/API | signup forms, public archive, public REST API + webhooks, advanced segments, AI analytics narratives | Public API + forms |
| 6 SaaS hardening | billing (Stripe), quotas, rate limiting, audit logs, RBAC, observability | Quotas+rate limit+audit; billing scaffold |

**Reconciliations applied to the table above:**
- The P4 row keeps "SPF/DKIM/DMARC + signing" as the *full multi-domain/dedicated-IP + ESP-native* story; the **single-domain SPF/DKIM/DMARC verify-and-sign subset is pulled forward into P1** (§2.2, §8) because P1 preflight hard-blocks on an unsigned domain. The two are not in conflict — P1 ships the minimum authentication required to send at all; P4 generalizes it across ESPs and dedicated IPs.
- **A/B testing is P4** (per this table and the locked phase map). The earlier SPA draft that placed an A/B editor in P1 is overridden: the `CampaignVariant` table is *modeled* in P1 but the A/B editor, winner selection, and **winner auto-send ship in P4** (§4.7, §11.8). Click-based winner metrics depend on P1 tracking, which is fine, but winner auto-send is a sending behavior gated to P4 send-time infra.
- **Bounce ingestion:** P1 ships the **SMTP DSN poller** (so `hard_bounce`/`soft_bounce` are real in P1); **ESP webhook ingestion and complaint/FBL** are P4. P1 analytics omit `delivered`/`complaint` (§2.3).

### 12.1 P1 acceptance criteria (Build fully + test)

- A new user signs up, verifies email, gets an owner workspace; cannot bulk-send until `physical_address` is set.
- Isolation suite: workspace A cannot read/update/delete B's contacts/campaigns/jobs/artifacts (404, not 403).
- Import: CSV/XLSX up to limits (§5.4) streams without OOM; multi-email rows explode into individual contacts; dedupe-on-canonical; validation populates `ValidationStatus`; suppressed addresses never resurrected.
- Sending domain: generate DKIM keypair + selector; publish SPF/DKIM/DMARC + return-path records; verify sets all four flags; preflight passes only when verified+signed.
- Campaign send: schedule is idempotent (double-click → one job); messages materialize once; suppressed (workspace + global) skipped; every message is DKIM-signed, `multipart/alternative` with deterministic plaintext, carries `List-Unsubscribe`/`-Post` and resolved `{physical_address}`/`{unsubscribe_url}`; worker survives restart with no double-send.
- Tracking: open pixel `.gif` and click redirect log bot-filtered events; one-click unsubscribe suppresses immediately; public endpoints rate-limited.
- Bounces: DSN poller classifies hard→suppress (workspace+global), soft→retry.
- Circuit-breaker auto-pauses a blast crossing the bounce threshold.
- Analytics show sent/bounces/opens/clicks/unsubs (no fabricated delivered/complaint); `CampaignStats` freezes before Event purge.
- AI v1 returns sanitized, schema-valid output; with `GEMINI_API_KEY` unset everything degrades and sending/compliance still works.
- Audit rows written for login, role/credential/key changes, sends, suppression edits, consent changes; jobs exhausting retries land in DLQ with an alert.

### 12.2 P2–P6 acceptance (summarized)

- **P2:** builder exports client-safe inlined HTML; live preview matches sent output; test sends work.
- **P3:** automation engine wakes due runs (`wait_until`), executes delays/conditions/branches, enrolls list/segment, resumes after restart; AI drafts an editable (never auto-armed) journey.
- **P4:** at least one ESP adapter passes the same send/track/suppress contract as SMTP; ESP webhooks (signed, deduped) populate `delivered`/bounce/complaint; A/B picks a winner by click and auto-sends; send-time recommendation is advisory only.
- **P5:** hosted form → double-opt-in confirmation → subscribed; public newsletter archive renders; public API + outbound webhooks (signed with timestamp, replay-tolerant, rotatable, delivery-logged); AI narrative numbers cross-check against inputs.
- **P6:** quota blocks at enqueue and send; rate limits return 429 + `Retry-After`; audit-log UI filters by actor/action/time; Stripe scaffold creates a customer + plan; granular RBAC gates actions.

---

## 13. Testing Strategy

- **Unit:** the extended merge renderer (`{tag|fallback}`, configured defaults, reserved-token injection, HTML escaping); validation ladder + `MxCache` TTL (positive 7 d / negative 1 h, re-validate on expiry); classified `SendResult` mapping (recipient-refused → `rejected`, disconnect/timeout/421 → `deferred`); DKIM signature correctness; DMARC alignment (DKIM `d=` and MAIL FROM domain match From).
- **Tenant isolation (mandatory, app-layer):** parametrized over every workspace-scoped resource — A cannot touch B (expect 404). Runs on SQLite (the default, RLS-less) so the app-layer guard is proven the sole control.
- **Idempotency:** double schedule → one `campaign_send` job; replayed enqueue → one job; replayed ESP webhook (P4) → no-op; SMTP retry on a non-terminal message doesn't double-send.
- **Worker durability:** kill the worker mid-batch; reaper requeues the leased job; resume sends exactly the remaining recipients (assert no duplicate `Message` sends). Single-worker on SQLite; multi-worker `SKIP LOCKED` contention test on Postgres.
- **Circuit-breaker:** synthetic high-bounce stream auto-pauses the job at threshold.
- **Compliance gate:** preflight blocks (412) on missing unsubscribe / address / unverified-or-unsigned domain / unresolvable tags; passes when all present; AI critique cannot override the deterministic block.
- **GDPR erasure:** delete contact → contact gone, suppression retained as `email_hash`; send-time hash-compare still blocks the erased address.
- **Limits/abuse:** import over row/size/column caps → 413, no OOM (streamed); oversized/disallowed attachment → 422; AV-flagged attachment blocked; public tracking endpoint throttled per-IP/per-token.
- **AI:** schema-validation failure → one repair retry → `invalid_output`; degraded mode (no key) returns typed `degraded`, never 500; ledger records the full `AIStatus`; prompt-injection payloads in CSV/brief don't alter behavior.
- **Migration/transform:** legacy `name`/`emails` (semicolon-separated) rows explode correctly into contacts in a bootstrap workspace (§14).
- **SPA:** MSW mocks the OpenAPI surface; component tests for `JobProgress`/`PreSendChecklist`/`MergeTagInput`/`EmailPreview` (DOMPurify strips `<script>`). Playwright E2E: signup → verify → set address → import → compose → preflight → schedule → poll job → see report; workspace-switch shows no stale cross-tenant data.
- **Type safety:** `openapi-typescript` regen in CI fails the build on drift.
- **Migrations:** Alembic up/down round-trips on SQLite and Postgres; expand/contract policy verified (additive deploy → backfill → switch reads → drop) for the Postgres swap (§14).

---

## 14. Scraper Removal & Migration

### 14.1 Scraper removal

The email Scraper is removed entirely (locked decision). Delete the Scraper routes, its Jinja templates/static assets, the NCBI/`requests`-based scraping code, and the `NCBI_API_KEY` usage. Remove now-unused dependencies (`requests`, scraping helpers) from `pyproject.toml` after confirming no other module imports them. The SPA ships no Scraper UI. Any documentation, the runner scripts, and the README are updated to a two-tool-plus-platform story (Sender + Filter evolve into Contacts/Campaigns; Scraper is gone).

### 14.2 Legacy data shape & multi-email rows

The current importer requires `name` + `emails`, where `emails` is **semicolon-separated** (`app.py` ~399: `[e.strip() for e in str(emails).split(';') if e.strip()]`) — one CSV row could fan out to many recipients. The new model is **one email per Contact** with `Unique(workspace_id, email_canonical)`. The import pipeline therefore **explodes** a multi-email row into multiple Contacts:
- Split `emails` on `;` (and `,` as a tolerant secondary); trim; lowercase to `email_canonical`; drop empties.
- For each address create/upsert a Contact; `name` maps to `first_name`/`last_name` (best-effort split) and the original row's other columns land in `attributes` (so existing `{column}` merge tags still resolve).
- De-dupe within the file and against existing contacts by canonical email; collisions with suppression are flagged in the import job's error/warning report (not silently mailed).
- The behavior change (one row → many recipients becomes one row → many contacts that are then individually addressable) is surfaced in the import preview so users understand the new semantics.

### 14.3 Bootstrapping existing usage

There is no persisted production data today (the app is stateless: CSV in, email out, in-memory jobs). Migration is therefore primarily **schema creation**, not data backfill: run the initial Alembic migration to create all tables; create a single bootstrap `Workspace` + an owner `User` for the existing operator; existing SMTP settings (previously a plaintext form field) are re-entered once through the encrypted `SendingIdentity` flow (they were never stored, so nothing to migrate — only to stop accepting as plaintext). Any saved CSVs are imported through the new wizard (§14.2).

### 14.4 Alembic policy (expand/contract, Postgres-swap, rollback)

- **All schema changes via Alembic**; no implicit `create_all` in production.
- **Down-migrations required** for every revision (tested in CI, §13).
- **Expand/contract for zero-downtime on Postgres:** additive change first (new nullable column / new table) → deploy code that writes both → backfill job → switch reads → a later contract migration drops the old column. Never rename-in-place a populated column on Postgres; add-new + backfill + drop.
- **SQLite caveat:** SQLite's limited `ALTER TABLE` means some migrations use Alembic's batch (copy-and-recreate) mode; the same logical migration runs both backends. The Postgres swap is itself an expand/contract exercise: stand up Postgres, run migrations, dual-write or one-shot copy, cut over reads, decommission SQLite — gated by the throughput boundary in §2.5 (Postgres mandatory before multi-worker / high volume / RLS reliance).

---

**Files this spec supersedes or builds on (absolute paths):**
- `/Users/arupanandaswain/PycharmProjects/web-scraping-info-of-authors-though-API-to-automate-the-mailing/app.py` — `SmtpSession` (~179–241; `CERT_NONE` at `_context`, swallowed `SMTPRecipientsRefused` ~282–283), `render_template` (~246, regex `\{(\w+)\}`), `send_email` (~253, HTML-only, no plaintext), `validate_email` (~297, three-state ladder), `_mx_cache` (~117), `process_csv_and_send_emails` (~308; required `name`/`emails`, semicolon split ~399), job/download endpoints.
- `/Users/arupanandaswain/PycharmProjects/web-scraping-info-of-authors-though-API-to-automate-the-mailing/jobs.py` — in-memory `JobManager` (states `queued/running/done/error`; fields `id/type/status/progress/message/result/files/error/created_at/updated_at`; retention window) evolving into the workspace-scoped DB-backed `Job` table + worker.
- `/Users/arupanandaswain/PycharmProjects/web-scraping-info-of-authors-though-API-to-automate-the-mailing/templates/` and `static/` — retired (replaced by the React SPA).
- `/Users/arupanandaswain/PycharmProjects/web-scraping-info-of-authors-though-API-to-automate-the-mailing/pyproject.toml` — add `google-genai` (via `uv`), `cryptography`, `argon2-cffi`, `alembic`, `sqlalchemy`, DKIM/DNS libs; wire `GEMINI_API_KEY`; remove Scraper-only deps.
