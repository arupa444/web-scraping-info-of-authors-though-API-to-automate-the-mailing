# iceReach — End-to-End Guide (with Zoho Mail)

This walks you through **every feature**, from a fresh clone to sending tracked campaigns,
automations, forms, and the API — using your Zoho mailbox as the sender.

> **Your sending account**
> - SMTP host: `smtp.zoho.in`  •  port: `587` (STARTTLS)
> - Username: `team@influenceai.in`
> - Password: **use a Zoho App Password** (Zoho Mail → Settings → Security → App Passwords), not your login password — required if 2FA is on. Put it only in `.env` (gitignored). Never commit it.
> - **From address must be `team@influenceai.in`** (or a verified alias on `influenceai.in`). Zoho rejects mail "from" addresses you don't own.

---

## 0. One-time prerequisites

- Python **3.12+**, Node **18+**, and [`uv`](https://docs.astral.sh/uv/).
- **Authenticate your domain in Zoho** (so mail isn't spam-foldered): in Zoho Mail Admin, finish **SPF + DKIM + DMARC** for `influenceai.in`. Zoho signs your outbound mail with *its* DKIM — you do **not** need iceReach's DKIM for Zoho relay (leave the iceReach sending-domain unverified; see §4).
- Zoho has **daily send limits** (often ~50–250/day on smaller plans). Keep test batches tiny and set a workspace quota (§13).

---

## 1. Install

```bash
git clone <repo-url>
cd web-scraping-info-of-authors-though-API-to-automate-the-mailing

uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

cd frontend && npm install && npm run build && cd ..
```

## 2. Configure `.env` (repo root)

Create `.env` (it's gitignored). Fill in your **app password**:

```ini
# Security — change for anything beyond local
SECRET_KEY=please-change-this-to-a-long-random-string

# Public base URL used to build open/click/unsubscribe links.
# Localhost is fine for testing on your own machine. For real recipients this
# MUST be a public URL (your server/tunnel), or tracking + unsubscribe won't work.
BASE_URL=http://127.0.0.1:8000

# AI (optional but powering subjects/body/critique/sequences/narratives)
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=gemini-3-flash-preview

# CORS origin for the SPA dev server (only needed when running Vite separately)
FRONTEND_ORIGIN=http://127.0.0.1:5173
```

> The Zoho SMTP host/port/user/password are **not** global env vars — you enter them per
> *sending domain* inside the app (§4), so different workspaces can use different senders.

## 3. Run

**Single process (serves the API + the built SPA):**

```bash
python run.py          # picks a free port, opens your browser
```

Open the printed URL (e.g. `http://127.0.0.1:8000`). The UI is the easiest way to use everything.

**Background worker** (required for campaign sends, imports, automations, bounce polling) — run in a second terminal:

```bash
source .venv/bin/activate
PYTHONPATH=backend python -m icereach.services.queue
```

> Long work (sending, importing) runs as **background jobs**. Without the worker, jobs stay
> "queued" forever. The UI shows live progress; the API returns a `job_id` you poll.

**Two-process dev mode** (hot reload) instead of `run.py`:

```bash
uvicorn icereach.main:app --reload --app-dir backend --port 8000   # terminal 1
cd frontend && npm run dev                                          # terminal 2 (proxies /api)
```

Interactive API docs are always at `/docs`.

---

## How auth works (for API/curl users)

The SPA handles this for you. If you script against the API with cookies:
- Log in → server sets an **httpOnly session cookie** + a readable **`ice_csrf`** cookie.
- On every **POST/PATCH/PUT/DELETE** send header **`X-CSRF-Token: <value of ice_csrf cookie>`**.
- Programmatic integrations should instead use an **API key** (§12) via `Authorization: Bearer ice_...` (no CSRF needed).

A reusable curl setup (used in examples below):

```bash
BASE=http://127.0.0.1:8000
J=/tmp/ice.cookies
csrf() { awk '/ice_csrf/{print $7}' "$J"; }   # reads the CSRF token from the jar
# after signup/login, mutations use:  -b $J -H "X-CSRF-Token: $(csrf)"
```

---

## 4. Create your account & workspace

**UI:** open the app → **Sign up** (email, password, workspace name). You're now the workspace **owner**.

**API:**
```bash
curl -s -c $J -X POST $BASE/api/auth/signup -H "Content-Type: application/json" \
  -d '{"email":"you@influenceai.in","password":"a-strong-password","workspace_name":"InfluenceAI"}'
```

## 5. Add your Zoho sending domain

This is the transport every campaign/automation uses.

**UI:** **Settings → Sending domains → Add**:
- Domain: `influenceai.in`
- Provider: **SMTP**
- SMTP host: `smtp.zoho.in`  •  port: `587`
- SMTP username: `team@influenceai.in`
- SMTP password: *(your Zoho app password)*

**API:**
```bash
curl -s -b $J -H "X-CSRF-Token: $(csrf)" -H "Content-Type: application/json" \
  -X POST $BASE/api/sending-domains -d '{
    "domain":"influenceai.in","provider":"smtp",
    "smtp_host":"smtp.zoho.in","smtp_port":587,
    "smtp_username":"team@influenceai.in","smtp_password":"YOUR_ZOHO_APP_PASSWORD"
  }'
```
The response includes its `id` (you'll reference it when sending) and a set of DNS records
for *iceReach's own* DKIM. **With Zoho you can ignore those** and rely on Zoho's domain
auth — leave the sending domain "unverified", and iceReach will send via Zoho without
adding its own DKIM signature (Zoho adds theirs).

> Want iceReach to DKIM-sign too? Publish the shown TXT records in `influenceai.in` DNS,
> then **Verify**. Only do this if you understand double-signing; for Zoho it's unnecessary.

> **TLS:** iceReach verifies the relay's TLS certificate for **every** provider (Zoho, SES,
> Mailgun, custom — there's no provider allowlist). Leave `verify_tls` on. Only set it to
> `false` for a trusted **self-signed/internal** relay.

## 6. Add contacts

Required field: `emails`/`email`; optional `name`; anything else becomes a **custom attribute** usable as a `{merge}` tag.

**UI:** **Contacts → Add contact**, or **Import** a CSV/Excel.

**CSV import** (background job, validates + skips suppressed):
- CSV needs an `email` column (plus `name` and any custom columns).
- **UI:** Contacts → Import → choose file → optionally a target list → watch progress.
- **API:**
```bash
curl -s -b $J -H "X-CSRF-Token: $(csrf)" -X POST $BASE/api/contacts/import \
  -F "file=@contacts.csv" -F "list_id=1" -F "validate_emails=true"
# -> {"job_id": N}; poll:  curl -s -b $J $BASE/api/jobs/N
```

Single contact via API:
```bash
curl -s -b $J -H "X-CSRF-Token: $(csrf)" -H "Content-Type: application/json" \
  -X POST $BASE/api/contacts -d '{"email":"lead@example.com","name":"Lead","attributes":{"city":"Pune"}}'
```

## 7. Lists & segments

**Lists** are static groups; **segments** are dynamic rules.

- **List:** Contacts/Lists → create a list → add contacts to it.
- **Segment:** Segments → New → build rules (e.g. `attributes.city = Pune` AND `status = subscribed`).
  Operators: `eq, neq, contains, gt, lt, in, exists`; fields: `email, name, status, attributes.<key>`;
  combine with `all` / `any` / `not`. **Preview** shows the matching count + sample.

```bash
curl -s -b $J -H "X-CSRF-Token: $(csrf)" -H "Content-Type: application/json" -X POST $BASE/api/segments \
  -d '{"name":"Pune subs","rules":{"all":[{"field":"attributes.city","op":"eq","value":"Pune"},{"field":"status","op":"eq","value":"subscribed"}]}}'
```

## 8. Build an email template (block builder)

**UI:** **Templates → New**. Add blocks (heading, text, button, image, divider, spacer, 2-column),
reorder/edit them, and watch the **live preview** (it's exactly what gets sent). Put `{name}` (or any
contact attribute) anywhere for personalization. **Save**, then **Send test** to your own inbox
(pick the Zoho sending domain).

The template's HTML is generated email-safe (inline styles, 600px table) — good for Outlook/Gmail.

## 9. Create & send a campaign

**UI:** **Campaigns → New campaign**:
1. Name it; **From name** = e.g. `InfluenceAI`; **From email** = `team@influenceai.in` (must be your Zoho address).
2. Pick the **sending domain** (your Zoho one) and an **audience** (a list *or* a segment).
3. Compose the body, or **Start from template**. Use the **AI** buttons:
   - *Generate subjects* → pick one (needs `GEMINI_API_KEY`).
   - *Check deliverability* → spam-risk + fixes before you send.
4. **A/B test:** add a second variant with its own subject/HTML and a weight; recipients are split by weight, and the **Analytics → A/B** table shows the winner.
5. **Send** → a background job runs; watch the progress bar.

**API:**
```bash
# create
CID=$(curl -s -b $J -H "X-CSRF-Token: $(csrf)" -H "Content-Type: application/json" -X POST $BASE/api/campaigns -d '{
  "name":"Launch","from_name":"InfluenceAI","from_email":"team@influenceai.in",
  "sending_domain_id":1,"list_id":1,
  "variants":[{"subject":"Hi {name}","html":"<p>Hello {name}!</p>","weight":1}]
}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
# send (enqueues the job; the worker delivers it)
curl -s -b $J -H "X-CSRF-Token: $(csrf)" -X POST $BASE/api/campaigns/$CID/send
```

> Sending inserts open-pixel + click-redirect links and a one-click `List-Unsubscribe` header.
> Those links use `BASE_URL` — on localhost only you can open them; for real recipients set
> `BASE_URL` to a public address before sending.

## 10. Track results & analytics

**UI:** open the campaign → **Analytics**: sent, opens (unique/total), clicks, CTR/CTOR, unsubscribes,
hard/soft bounces. **`delivered` and `complaints` show `—`** unless an ESP webhook feeds them (§14) —
over plain Zoho SMTP they aren't truthfully knowable, so we don't fake them.

- **A/B breakdown:** per-variant rates + winner.
- **AI summary:** "Generate AI summary" → plain-language narrative + suggestions.
- **Bounces:** if you configure a bounce mailbox (`BOUNCE_IMAP_*` in `.env`) and run the `poll_dsn`
  job, hard bounces auto-suppress the address.

## 11. Automations (drip journeys)

**UI:** **Automations → New**:
- **Trigger:** *Manual* (you enroll people) or *List subscribe* (auto-enroll when a contact joins a list).
- **Steps (ordered):** `Send` (subject + HTML, or a template), `Wait` (N days), `Condition` (segment rule — continue if matched, else exit).
- Set the **sending domain** = Zoho and **From email** = `team@influenceai.in`.
- **AI: draft sequence** turns a goal into a ready send→wait→send journey.
- **Activate**, then **Enroll** contacts (or let list-subscribe do it). The worker advances due steps (~every 30s). **Runs** shows each contact's position/status.

Example: *Welcome series* = Send "Welcome {name}" → Wait 2 days → Condition `status = subscribed` → Send "Getting started".

## 12. Signup forms (grow your list)

**UI:** **Forms → New**: name, target **list**, **sending domain** (for the confirmation email), and
**double opt-in** on/off.
- Hosted form URL: `BASE_URL/f/{id}` — share it or embed it.
- With **double opt-in**, a confirmation email is sent (via your Zoho domain) and the contact only
  subscribes after clicking — required for clean lists. Without a usable sending domain configured,
  the contact stays *pending* (it won't silently subscribe).
- **Public newsletter archive:** `BASE_URL/a/<workspace-slug>` lists your sent campaigns.

## 13. Public REST API (`/v1`) for developers

**UI:** **Settings → API keys → Create** (shown **once** — copy it). Use it as `Authorization: Bearer ice_...`.

```bash
KEY=ice_xxx_yyy
# add a contact
curl -s -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -X POST $BASE/v1/contacts -d '{"email":"api@example.com","name":"API"}'
# send a one-off transactional email through Zoho
curl -s -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -X POST $BASE/v1/emails -d '{
    "to":"someone@example.com","subject":"Hi {name}","html":"<p>Welcome!</p>",
    "sending_domain_id":1,"from_email":"team@influenceai.in","from_name":"InfluenceAI"}'
```

## 14. Webhooks

- **Outbound (you receive events):** Settings → Outbound webhooks → add a URL + events (e.g. `open,click`).
  iceReach POSTs `{event, data}` to your URL.
- **Inbound (ESP → iceReach):** only relevant if you switch the sending domain's provider to
  **Resend/SendGrid** (Settings → provider + API key). Point that ESP's webhook at
  `BASE_URL/webhooks/resend` or `/webhooks/sendgrid`; delivered/bounce/complaint events then populate
  `delivered`/`complaints` and auto-suppress complaints. (Set `WEBHOOK_SECRET` in `.env` and append
  `?secret=...` to the webhook URL to authenticate them.) **Zoho SMTP has no such webhook** — that's
  why delivered/complaints stay `—` on Zoho.

## 15. Team, quotas, billing, audit (SaaS console)

All under **Settings**:
- **Team/Members:** invite users (owner can grant *admin*; admins add *members*). Members can't see audit logs or change billing.
- **Billing (preview):** pick a plan — this sets your monthly **send quota** (scaffold; no real Stripe charge).
- **Quota:** once the monthly send count hits the limit, campaign sends skip the rest and `/v1/emails` returns `429`.
- **Audit log:** owner/admin see who did what (sends, member changes, plan changes).
- **Rate limiting:** the API throttles abusive clients (HTTP 429 + `Retry-After`).

---

## A quick full run-through (copy/paste)

1. `python run.py` + (2nd terminal) the worker.
2. Sign up → **Settings → Sending domains** → add Zoho (`smtp.zoho.in:587`, `team@influenceai.in`, app password).
3. **Contacts** → add yourself (use a real inbox you control).
4. **Templates** → build one → **Send test** to yourself → confirm it arrives from `team@influenceai.in`.
5. **Lists** → create "Test" → add yourself.
6. **Campaigns** → New → from `team@influenceai.in`, domain = Zoho, audience = "Test", use the template → **Send**.
7. Open the email, click a link → **Analytics** shows your open + click.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Job stuck on "queued" | The **worker isn't running**. Start `PYTHONPATH=backend python -m icereach.services.queue`. |
| SMTP auth fails / `535` | Use a **Zoho App Password** (not login password); ensure IMAP/SMTP access is enabled in Zoho; username is the full `team@influenceai.in`. |
| Mail rejected / "from not allowed" | **From email must be `team@influenceai.in`** (or a verified Zoho alias on the domain). |
| Lands in spam | Finish **SPF/DKIM/DMARC for `influenceai.in` in Zoho admin**; warm up volume; avoid spammy copy (use the AI *deliverability check*). |
| Opens/clicks/unsubscribe links broken for recipients | `BASE_URL` is localhost. Set it to a **public URL** (deployed server or a tunnel) and resend. |
| AI buttons return 503 | `GEMINI_API_KEY` not set in `.env` (restart after adding). |
| `delivered`/`complaints` show `—` | Expected on SMTP. Switch the domain to an ESP (Resend/SendGrid) + wire its webhook (§14). |
| Hitting Zoho's daily limit | Set a workspace **quota** below Zoho's cap and send in smaller batches. |

## Production checklist (before real volume)

- Set a strong `SECRET_KEY` and a **public HTTPS** `BASE_URL`; serve behind TLS.
- Encrypt secrets at rest (SMTP/DKIM/API keys are stored plaintext today).
- Move the rate limiter/queue to Redis if you run more than one process.
- Configure a bounce mailbox (`BOUNCE_IMAP_*`) + schedule the `poll_dsn` job.
- Keep your Zoho app password only in `.env`; rotate it if it ever leaks.
