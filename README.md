# iceReach — Author Discovery & Outreach Toolkit

**One-line:** iceReach is a practical toolkit to discover authors from biomedical literature (via NCBI/PubMed), extract their contact details, validate email deliverability, and send personalized, templated outreach at scale — through a FastAPI web UI or standalone CLI scripts.

---

## Table of contents

* [Highlights](#highlights)
* [Tech stack & requirements](#tech-stack--requirements)
* [Repository layout](#repository-layout)
* [Installation](#installation)
* [Configuration (`.env`)](#configuration-env)
* [Running the app](#running-the-app)
* [How it works (high level)](#how-it-works-high-level)
* [Web UI & API endpoints](#web-ui--api-endpoints)
* [CSV format & templates](#csv-format--templates)
* [CLI scripts](#cli-scripts)
* [Operational notes & best practices](#operational-notes--best-practices)
* [Troubleshooting](#troubleshooting)
* [Known limitations & roadmap](#known-limitations--roadmap)
* [Security & privacy](#security--privacy)
* [License](#license)

---

## Highlights

* **API-first scraping** — uses NCBI Entrez (PubMed) APIs to locate articles and extract author information (no brittle HTML scraping).
* **Three tools, one app** — Scraper, Filter, and Sender, available both in a FastAPI web UI and as standalone CLI scripts.
* **Email validation pipeline** — syntax → DNS MX lookup → (filter only) SMTP-level probe to reduce bounces.
* **Templated personalization** — HTML email templates with `{placeholder}` substitution drawn from **any column** in your CSV. Missing/typo'd placeholders are left intact instead of crashing the run.
* **Multiple templates & subjects** — upload several HTML templates and several subjects; each recipient gets a random pick (useful for reducing spam-filter fingerprinting).
* **Resumable filtering** — large filter jobs checkpoint progress and can resume after interruption.
* **CSV-centric** — all inputs/outputs are CSV (Excel `.xlsx/.xls` accepted as input) for easy integration with spreadsheets and downstream tooling.

---

## Tech stack & requirements

* **Language:** Python **3.12+**
* **Web:** FastAPI + Jinja2 + uvicorn
* **Data:** pandas + openpyxl (CSV/Excel parsing)
* **Networking / mail:** requests, smtplib, dnspython
* **Validation / models:** pydantic (with the `email` extra)
* **Other:** python-dotenv, python-multipart, psutil

Dependencies are declared in both `pyproject.toml` and `requirements.txt` (kept in sync).

---

## Repository layout

```
.
├── app.py                  # FastAPI application — web UI + API (the main app)
├── jobs.py                 # In-memory background-job manager (status/progress/artifacts)
├── run.py                  # Launcher: finds a free port, starts uvicorn, opens the browser
├── runServer.bat           # Windows convenience launcher
├── pyproject.toml          # Project metadata + dependencies
├── requirements.txt        # Dependencies (mirror of pyproject.toml)
├── templates/              # Jinja2 UI templates (universalLayout, upload_form, email_filter, email_scraper)
├── newSampleTemplates/     # Example HTML email templates
├── fancyMails/             # More example HTML email templates
└── CLI_files/              # Standalone command-line variants (legacy / automation)
    ├── scrapName.py        # PubMed author/email scraper (CLI)
    ├── emailFilter.py      # Email validation/filter (CLI)
    ├── automateEmailing.py # Bulk sender with validation + logging (CLI)
    └── for_automate_authentic_email_google_yahoo_office.py  # Provider-specific sender variant
```

> **Note:** The CLI scripts in `CLI_files/` overlap with `app.py` and are kept for automation/cron use. The FastAPI app (`app.py`) is the primary, maintained interface.

---

## Installation

Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
# clone
git clone <repo-url>
cd web-scraping-info-of-authors-though-API-to-automate-the-mailing

# create & activate a virtual environment
uv venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# install dependencies
uv pip install -r requirements.txt
# or, from the project file:  uv pip install -e .
```

---

## Configuration (`.env`)

A `.env` file is **optional** — when you use the web UI you enter SMTP credentials directly in the form, so no `.env` is required. It is mainly useful for the CLI scripts or for an NCBI API key.

```ini
# NCBI / PubMed — raises Entrez rate limits (optional)
NCBI_API_KEY=your_ncbi_api_key_here

# SMTP / sending credentials (used by CLI scripts)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-sending@example.com
SMTP_PASS=your_smtp_password_or_app_password
FROM_NAME=Your Name or Organization
```

> Gmail/Outlook/Yahoo generally require an **app password** (or OAuth). A regular account password will usually be rejected. **Never commit `.env`.**

---

## Running the app

Easiest — the launcher picks a free port and opens your browser:

```bash
python run.py
```

Or run uvicorn directly:

```bash
uvicorn app:app --reload
# pick another port if 8000 is busy:
uvicorn app:app --reload --port 8002
```

Then open **http://127.0.0.1:8000/** (or the port shown in the console).

On Windows you can also double-click `runServer.bat`.

---

## How it works (high level)

1. **Discover** — the Scraper queries PubMed (Entrez `esearch` → `efetch`), parses the returned XML for article metadata and author blocks, and extracts emails from affiliation text via regex. Results are de-duplicated and exported to CSV.
2. **Validate** — the Filter checks each address: syntax → DNS MX record → live SMTP `RCPT` probe, and writes only deliverable rows to a filtered CSV. Progress is checkpointed so large files can resume.
3. **Send** — the Sender reads a CSV + one or more HTML templates, validates each address (syntax + MX), personalizes the message, and sends via SMTP with a configurable delay between rows. It returns a summary plus a per-recipient feedback CSV.

---

## Web UI & API endpoints

| Page (GET) | Purpose |
|---|---|
| `GET /` | Email Sender form |
| `GET /email-filter` | Email Filter form |
| `GET /email-scraper` | Email Scraper form |

All three heavy operations run as **background jobs**. The POST returns `202 Accepted`
with a `job_id` immediately; the client polls for progress and fetches artifacts when done.

| API (POST) | Purpose |
|---|---|
| `POST /email-sender/send` | Upload CSV + HTML template(s) and send personalized emails. Starts a job. |
| `POST /email-filter/process` | Upload a CSV/Excel of emails and filter to deliverable addresses. Starts a job. Supports `resume`. |
| `POST /email-scraper/scrape` | Provide a search term; scrapes authors+emails from PubMed (last 5 years). Starts a job. |

| Job API (GET) | Purpose |
|---|---|
| `GET /jobs/{id}` | Job status: `{status, progress, message, result, error, downloads}`. Poll until `status` is `done` or `error`. |
| `GET /jobs/{id}/download/{key}` | Download a generated artifact. Keys: `feedback` & `remaining` (sender), `result` (filter/scraper). |

The web UI does this polling for you and shows a live progress bar. Job state is
in-memory and expires after ~6 hours (artifacts are cleaned up with it).

> These endpoints have **no authentication** — intended for local use or behind an authenticated proxy, not direct public exposure.

---

## CSV format & templates

### Sender CSV — required columns

| Column | Required | Used for |
|---|---|---|
| `name` | ✅ | recipient display name + `{name}` placeholder |
| `emails` | ✅ | one or more addresses, **semicolon-separated** (`a@x.com;b@y.com`) |
| *(any other column)* | optional | available as `{column_name}` in the template/subject |

The Sender substitutes `{column}` placeholders from **any** column present in the row — both in the HTML body and in the subject line. A placeholder with no matching column is left as-is (it won't crash the job).

### Filter CSV — required columns

Only an **`emails`** column is required (one address per row).

### Email template

```html
<p>Dear Dr. {name},</p>
<p>I enjoyed your paper "{article_title}" in {journal}. ...</p>
```

Example templates live in `newSampleTemplates/` and `fancyMails/`.

### Example end-to-end workflow

1. **Scrape** authors from PubMed for a keyword (e.g. "machine learning in cardiology").
2. **Filter** the resulting CSV to keep only deliverable addresses.
3. **Send** personalized emails using an HTML template.

---

## CLI scripts

Run from the repo root (so the `templates/` path resolves):

```bash
# 1) Scrape authors → <search_term>_authors_with_emails.csv
python CLI_files/scrapName.py "machine learning in cardiology"

# 2) Validate / filter emails (prompts for the input CSV path)
python CLI_files/emailFilter.py

# 3) Bulk send (prompts for subject, template, SMTP credentials, etc.)
python CLI_files/automateEmailing.py
```

---

## Operational notes & best practices

* **Use a dedicated sending account or a transactional provider** (SES, SendGrid, Mailgun). Mass outreach from consumer mailboxes frequently triggers throttling or suspension.
* **App passwords / OAuth** for Gmail/Outlook/Yahoo — regular passwords are usually blocked.
* **Respect rate limits** — use the `delay` between sends and a sane `max_emails` per batch.
* **Compliance** — include unsubscribe instructions and follow anti-spam law (CAN-SPAM, GDPR consent where applicable).
* **Deliverability** — set up SPF/DKIM/DMARC on your sending domain; validate addresses (the Filter) before large sends.
* **Keep the feedback/results CSVs** for auditing.

---

## Troubleshooting

* **`SMTPAuthenticationError` / 535** — wrong credentials or provider block; use an app password.
* **MX lookup failures (`NXDOMAIN`)** — misspelled domain or DNS issue; check the address.
* **`ConnectionRefusedError` / blocked ports** — some networks block SMTP (25/465/587). Try another port or network (the UI hints at using a VPN / hotspot on restrictive LANs).
* **NCBI / Entrez rate limits** — set `NCBI_API_KEY` to raise your quota.
* **High bounce rates** — filter first, lower volume, and send from a trusted domain.

---

## Performance & architecture

Recent work addressed the main throughput/scale bottlenecks:

* **Background jobs** — send/filter/scrape run off the event loop in a worker thread. The server stays responsive (sub-millisecond) while a long job runs, and jobs are no longer bound by HTTP request timeouts. Clients poll `GET /jobs/{id}` for live progress.
* **SMTP connection reuse** — one authenticated SMTP connection is opened per send batch and reused across recipients (with transparent reconnect on drop), instead of reconnecting per email. Auth failures surface immediately, before the file is processed.
* **Per-domain DNS/MX caching** — a single shared resolver is used and MX results are memoized per domain (negatives included), so a list of thousands sharing a handful of domains resolves each domain once.
* **NCBI API key + rate limiting** — set `NCBI_API_KEY` to raise the Entrez limit to 10 req/s (3/s without). Requests are throttled to stay within the limit.
* **Managed output dir** — generated artifacts go to `generated_files/` and expire (~6h) along with their job records.

### Remaining / possible future work

* **SMTP `RCPT` probing (filter)** is inherently unreliable — many providers accept-all or block probes, and probing can harm sender reputation. Treat negatives as advisory.
* **In-memory job state** does not survive a process restart (e.g. `--reload`). For multi-process or durable needs, move to a real task queue (Celery/RQ/arq) + shared store.
* **No authentication** on the web endpoints.
* Possible additions: ESP transports (SES/SendGrid), OAuth2 for providers, a Dockerfile, and a DB for persistent job tracking and retries.

---

## Security & privacy

* Never commit `.env` or any credentials.
* Treat scraped personal contact data responsibly and follow institutional and legal rules for outreach and data privacy.

---

## License

Shared under the **MIT License**.

---

## Maintainer

Prepared for **Arupa Nanda Swain**.
