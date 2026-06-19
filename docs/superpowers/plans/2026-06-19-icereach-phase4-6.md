# iceReach Phases 4–6 Implementation Plan (condensed)

> Built in one push as tested backend cores + key UI. Billing is an explicit scaffold (no live Stripe). References spec §12 P4–P6.

## P4 — Deliverability / ESP
- **ESP adapter layer** (`services/esp.py`): `EmailProvider` base + `SmtpProvider` (wraps `SmtpSession`), `ResendProvider`, `SendGridProvider` (httpx). `SendingDomain` gets `provider` + `api_key`. `sender`/`automation` send via `get_provider(domain)`. Tests mock httpx.
- **Inbound webhooks** (`routers/webhooks.py`): `POST /api/webhooks/{provider}` parses delivered/bounce/complaint → updates `Message.status`, records `Event`, suppresses on complaint/hard-bounce. **Unlocks** `delivered`/`complaints` in analytics (counted from events when present, else `None`).
- **A/B**: `analytics.variant_breakdown(campaign)` (per-variant sent/opens/clicks + `pick_winner`); `GET /api/campaigns/{id}/variants`.
- **Send-time** (`services/sendtime.py`): `best_hour(db, contact)` from past opens (fallback default).

## P5 — Growth / API
- **Signup forms** (`models/forms.py` SignupForm; `routers/forms.py` authed CRUD; public `GET /f/{id}`, `POST /f/{id}/submit` → pending contact + double-opt-in email, `GET /f/confirm/{token}` → subscribe + enroll).
- **Public archive**: `GET /a/{slug}` lists sent campaigns; `GET /a/{slug}/{id}` renders one.
- **Public REST API** (`routers/v1.py`, API-key auth): `POST/GET /v1/contacts`, `POST /v1/emails` (transactional send).
- **Outbound webhooks** (`models` Webhook + `services/webhooks_out.py`): dispatch on open/click/bounce; CRUD.
- **AI narrative**: `ai.service.summarize_analytics(metrics)` + `POST /api/campaigns/{id}/analytics/narrative`.

## P6 — SaaS hardening
- **Quotas**: `Workspace.monthly_send_limit` + `_sent_this_month`; enforce in `sender`/`v1 emails` (block 402/429).
- **Rate limiting**: in-memory token-bucket middleware → 429 + `Retry-After` for `/api/*` and public tracking.
- **Audit logs**: write on key mutations; `GET /api/audit-logs` (admin).
- **RBAC**: `require_role("owner","admin")` on destructive/admin endpoints; members API.
- **Billing (SCAFFOLD)**: `routers/billing.py` — plans list + `create-checkout` stub returning a placeholder URL; no live Stripe calls.

## DoD
`pytest backend/tests -q` green incl. new tests + one combined migration roundtrip; webhooks make `delivered`/`complaints` real; SPA builds. Scaffolded items (billing) clearly labeled in code + UI.
