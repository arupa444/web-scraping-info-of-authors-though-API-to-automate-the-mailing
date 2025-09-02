# Web Scraper + Author Outreach — Automated Mailing Toolkit

**One-line:** A practical, production-oriented toolkit to discover authors from biomedical literature (via NCBI/PubMed), extract contact details, validate email deliverability, and send personalized, templated outreach at scale — with both a FastAPI web UI and standalone CLI scripts.

---

## Table of contents

* [Highlights](#highlights)
* [Tech stack & requirements](#tech-stack--requirements)
* [Repository layout](#repository-layout)
* [Installation](#installation)
* [Configuration (`.env`)](#configuration-env)
* [How it works (high level)](#how-it-works-high-level)
* [Usage — quick start](#usage--quick-start)

  * [1) FastAPI (Web UI)](#1-fastapi-web-ui)
  * [2) Scrape authors (CLI)](#2-scrape-authors-cli)
  * [3) Validate / filter emails (CLI or UI)](#3-validate--filter-emails-cli-or-ui)
  * [4) Send emails (CLI or UI)](#4-send-emails-cli-or-ui)
* [CSV format & templates](#csv-format--templates)
* [Web UI endpoints (FastAPI)](#web-ui-endpoints-fastapi)
* [Operational notes & best practices](#operational-notes--best-practices)
* [Troubleshooting](#troubleshooting)
* [Extending / contribution guide](#extending--contribution-guide)
* [License & attribution](#license--attribution)

---

## Highlights

* **API-first scraping**: Uses NCBI Entrez (PubMed) APIs to locate articles and extract author information (no brittle HTML scraping).
* **Two interfaces**: FastAPI web UI for interactive workflows and standalone CLI scripts for automation/cron jobs.
* **Email validation pipeline**: Syntax checks → MX lookups → optional SMTP-level verification to reduce bounces.
* **Templated personalization**: HTML email templates with Python-style placeholders (`{name}`, `{article_title}`, `{journal}`) for safe, repeatable personalization.
* **CSV-centric**: All inputs/outputs are CSV files for easy integration with spreadsheets, databases, or downstream tooling.

---

## Tech stack & requirements

* **Language:** Python 3.8+
* **Web:** FastAPI + Jinja2 templates + uvicorn
* **Networking / mail:** requests, smtplib, dnspython
* **Validation / models:** pydantic
* **Other:** python-dotenv, python-multipart

Install with:

```bash
pip install -r requirements.txt
```

`requirements.txt` contains the full list used by this project (e.g. `fastapi`, `uvicorn`, `jinja2`, `requests`, `dnspython`, `pydantic`, `python-dotenv`).

---

## Repository layout (important files)

* `app.py` — FastAPI application that provides the web UI and API endpoints.
* `automateEmailing.py` — CLI script that loads a CSV + HTML template and performs bulk sending with validation and logging.
* `emailFilter.py` — Standalone utility to validate and filter emails (syntax, MX, optional SMTP verification).
* `for_automate_authentic_email_google_yahoo_office.py` — Provider-specific helper / variant for sending via common providers (prompts for credentials / app passwords).
* `scrapName.py` — Command-line tool that queries PubMed/Entrez (NCBI) for a search term and extracts author names, affiliations and email addresses.
* `templates/` — Jinja2 HTML templates used by the web UI **and** example email templates used by the mailing scripts.
* `.env` — Environment file (NOT committed in normal workflows). Used for API keys and SMTP credentials.
* `requirements.txt` — Python dependencies.
* `try.csv`, `try_results.csv` — Example input/output CSVs to test functionality.

---

## Installation

1. Clone the repository:

```bash
git clone <repo-url>
cd web-scraping-info-of-authors-though-API-to-automate-the-mailing-main
```

2. Create & activate a virtual environment:

```bash
python -m venv venv
# macOS / Linux
source venv/bin/activate
# Windows (cmd)
venv/Scripts/activate
```

3. Install requirements:

```bash
pip install -r requirements.txt
```

4. Create a `.env` file at the repo root (see next section for recommended keys).

---

## Configuration (`.env`)

Create a `.env` file with the credentials and keys your workflow requires. **Never** commit `.env` to source control.

Example `.env` entries (adapt to your SMTP provider & API keys):

```ini
# NCBI / PubMed (for scrapName.py)
NCBI_API_KEY=your_ncbi_api_key_here

# SMTP / sending credentials (used by CLI scripts or the web UI)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-sending@example.com
SMTP_PASS=your_smtp_password_or_app_password

# Optional: From display name used in emails
FROM_NAME=Your Name or Organization
```

> Note: Gmail/Outlook/Yahoo often require an **app password** or OAuth flow. Using your regular account password may be blocked or result in authentication errors. Provider-specific helper scripts are included (`for_automate_authentic_email_google_yahoo_office.py`) but using app passwords and dedicated sending accounts is strongly recommended.

---

## How it works (high level)

1. **Discovery** — `scrapName.py` queries PubMed (Entrez) for a search term, parses returned XML for article metadata and author blocks, and extracts email addresses via regex from author/affiliation text.
2. **Validation** — `emailFilter.py` performs a three-phase validation (syntax → DNS MX lookup → SMTP probe) to reduce invalid addresses.
3. **Delivery** — `automateEmailing.py` and the FastAPI app read a CSV + HTML template, personalize each message, and send in batches with configurable delays. Results are written to a results CSV for auditing.

---

## Usage — quick start


## 1) FastAPI (Web UI)
****

Start the app and use the browser-based interface to upload CSVs and templates, preview personalized messages, and send in controlled batches.
And if you are using this then you don't have to set a .env file.

### Running the Application

```bash
uvicorn app:app --reload
```
```bash
# if you think your default port is busy the use:
uvicorn app:app --reload --port 8002 # you can use any port inbetween 8000 to 8005 recommended
```

Then open: **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**


### app (Auto Mail App) – Email Tools Application for Pulsus

app (Auto Mail App) is a **FastAPI-based application** designed to simplify email-related workflows for research communication and outreach. It provides a **web interface and APIs** to:

* 📤 Send personalized emails in bulk from CSV + HTML templates.
* 🔍 Scrape author contact details from **PubMed**.
* 🛠️ Filter and validate email addresses for deliverability.

This tool is built to automate mailing for journals, publishers, and research organizations.

---

### Features

* **Email Sender**

  * Upload a CSV file of authors.
  * Use an HTML email template with placeholders (`{name}`, `{journal}`, `{article_title}`).
  * Configurable SMTP server (Gmail, Outlook, Yahoo, Universal, Custom).
  * Supports sending limits and delays between messages.
  * Provides a full summary (success, failed, validation breakdown).

* **Email Filter**

  * Upload CSV with email addresses.
  * Validates syntax, MX records, and SMTP acceptance.
  * Generates a **filtered CSV** with only deliverable emails.
  * Supports resuming from last checkpoint for large files.

* **Email Scraper**

  * Scrapes author emails from **PubMed articles (last 5 years)**.
  * Extracts names, affiliations, journals, article titles, and emails.
  * Removes duplicates and ensures unique results.
  * Exports author details into a structured CSV.

---


---

### API Endpoints

### 1. **Email Sender**

* `POST /email-sender/send`
  Upload CSV + HTML template and send personalized emails.

### 2. **Email Filter**

* `POST /email-filter/process`
  Upload CSV of emails and filter out invalid/non-deliverable ones.

### 3. **Email Scraper**

* `POST /email-scraper/scrape`
  Provide a **search term** and fetch authors’ emails from PubMed.

---

### CSV Format Requirements

### For Email Sending:

```csv
name,emails,journal,article_title
John Doe,john@example.com,Journal of AI,Deep Learning in Practice
Jane Roe,jane@university.edu,Medical Journal,AI in Healthcare
```

* **name** → Author name
* **emails** → Single or multiple emails (semicolon `;` separated)
* **journal** → Journal name
* **article\_title** → Article title

---

### Example Workflow

1. Scrape author emails from PubMed with a keyword (e.g., "machine learning").
2. Filter the extracted CSV to keep only **deliverable** emails.
3. Send personalized emails using an HTML template.



## 2) Scrape authors (CLI)

```bash
python scrapName.py "machine learning in cardiology"
```

* Output: `<search_term>_authors_with_emails.csv` with columns such as `name`, `journal`, `article_title`, `emails`, `affiliations`.
* Notes: The script uses NCBI Entrez `esearch`/`efetch`. If you have a `NCBI_API_KEY` in `.env` the script will use it to increase rate limits.

## 3) Validate / filter emails (CLI or UI)

**CLI:**

```bash
python emailFilter.py
# It will prompt for the input CSV path and produce a filtered output CSV (e.g. input_filtered.csv)
```

**UI:** Start the FastAPI UI (below) and go to the **Email Filter** page to upload CSVs and run validations.

## 4) Send emails (CLI or UI)

**CLI (example)**

```bash
python automateEmailing.py
```

`automateEmailing.py` will prompt for parameters (subject, template file, SMTP credentials if not provided in `.env`, etc.) and will create a `<input>_results.csv` containing per-recipient status and messages.

---
## CSV format & templates

### Required CSV columns (recommended)

The web UI and the scripts expect CSVs with at least the following columns (case-insensitive):

* `name` — recipient name (used to personalize `Dear {name}`)
* `emails` — one or more emails for the author (can be a single email or a delimited string)
* `journal` — article journal (used for context in personalization)
* `article_title` — article title (used in personalization)

> The repo includes `try.csv` as an example. `scrapName.py` produces files with a compatible format.

### Email template format

* Use an **HTML** file for richer formatting.
* Placeholders use Python \[`str.format()`] style: `{name}`, `{article_title}`, `{journal}`. Example:

```html
<p>Dear Dr. {name},</p>
<p>I am writing about your paper titled "{article_title}" published in {journal}...</p>
```

* The FastAPI UI accepts uploaded templates (or uses templates in `/templates/`). The mailing scripts call `template.format(...)` to substitute values before sending.

---

## Web UI endpoints (FastAPI)

The FastAPI app exposes these key routes (see `app.py`):

* `GET /` — Landing / dashboard page.
* `GET /email-filter` — Upload CSV & run validation.
* `GET /email-scraper` — Simple interface to run `scrapName`-style searches from the browser.
* `POST /email-sender/send` — Send emails using uploaded CSV + template (invoked by the UI form).
* `POST /email-filter/process` — Process an uploaded CSV and return filtered results.
* `POST /email-scraper/scrape` — Trigger a PubMed search and download results.

These endpoints are intended for local use or behind an authenticated proxy — they are **not** hardened for public exposure without authentication.

---

## Operational notes & best practices

* **Use a dedicated sending account or transactional provider.** Mass outreach with consumer mailboxes frequently triggers throttling and account suspension.
* **App passwords / OAuth:** For Gmail/Outlook, prefer app passwords or OAuth tokens. Manage credentials carefully.
* **Rate limits:** Respect provider rate limits — use the `delay` parameter between sends and limit `max_emails` in a batch.
* **Unsubscribe & compliance:** Include unsubscribe instructions and abide by anti-spam laws (CAN-SPAM, GDPR consent rules where applicable).
* **IP reputation & deliverability:** If you plan to send large volumes, use a proper ESP, warmed-up IPs, DKIM/SPF, and monitoring for bounces and complaints.
* **Backups / logging:** Results CSVs are important for auditing. Keep copies and rotate logs.

---

## Troubleshooting — common issues

* **`smtplib.SMTPAuthenticationError` / 535** — Wrong credentials or provider blocks. Try app passwords or provider-specific settings (e.g., `Allow less secure apps` is no longer supported by many providers).
* **MX lookup failures (dns.resolver.NXDOMAIN)** — Domain misspelled or DNS issues. Check the domain in the CSV.
* **`ConnectionRefusedError` / blocked ports** — Some networks block SMTP ports (25/465/587). Try an alternate port or run from a different network.
* **NCBI / Entrez rate limits** — If you plan many queries, set `NCBI_API_KEY` to raise your request quota.
* **High bounce rates** — Reduce sending volume, validate addresses first, and use a trusted sending domain.

---

## Extending / contribution guide

* Add provider-specific transports (Amazon SES, SendGrid, Mailgun) to improve deliverability and remove SMTP-based fragility.
* Add OAuth2 for common providers to avoid storing plain-text passwords.
* Dockerize the app for consistent deployment: a `Dockerfile` and `docker-compose.yml` would be ideal additions.
* Add a small database (SQLite or Postgres) for persistent job tracking, recipient state, and retries.

If you want, I can scaffold a Dockerfile + compose, add SES integration, or change the web UI to require authentication.

---

## Security & privacy

* Do **not** commit `.env` or any credentials to the repository.
* Treat scraped personal contact data responsibly. Follow institutional and legal rules for outreach and data privacy.

---

## License

This repository is shared under the **MIT License** (feel free to update to a different license if required).

---

## Maintainer

Prepared for: **Arupa Nanda Swain** — please review and tell me if you want the README tuned for a specific audience (developers vs non-technical users) or want additional docs (API reference, architecture diagram, Dockerfile).
