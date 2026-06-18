# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install deps (uv; see global instruction — never use pip directly)
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt        # requirements.txt and pyproject.toml are kept in sync

# Run the app (launcher finds a free port 8000-8100 and opens the browser)
python run.py
# or directly:
uvicorn app:app --reload --port 8002
```

There is **no test suite or linter configured**. The code was verified ad hoc with
`fastapi.testclient.TestClient` and live `curl` against a running server. When verifying
changes, stub the network (`app.validate_email`, `app.validate_email_filter`,
`app.SmtpSession`) to avoid real DNS/SMTP, then drive the endpoints through the job
lifecycle below.

## Architecture

iceReach is a single-file FastAPI app ([app.py](app.py)) exposing three tools — **Sender**,
**Filter**, **Scraper** — each as a web page + API. Requires Python 3.12+.

### Background-job model (the central pattern — read this first)

The three heavy operations do **not** run in the request cycle. Each POST endpoint
(`/email-sender/send`, `/email-filter/process`, `/email-scraper/scrape`) is thin: it does
fast synchronous validation, saves any upload to a temp file, then calls
`schedule_job(...)` and returns `202 {job_id, status_url}` immediately.

- `schedule_job` → `asyncio.create_task(_launch(...))` → `await run_in_threadpool(fn, ...)`.
  The job functions (`_run_send_job`, `_run_filter_job`, `_run_scrape_job`) are **blocking
  and run in a worker thread**, keeping the event loop responsive.
- [jobs.py](jobs.py) `JobManager` is the in-memory registry (thread-safe via a lock). Jobs
  carry `status / progress / message / result / files / error`. Artifacts are written to
  `generated_files/` and attached with `attach_file(job_id, key, path)`.
- Clients poll `GET /jobs/{id}` (returns `public_view` — hides server paths) and fetch
  results via `GET /jobs/{id}/download/{key}`. Download keys: `feedback` & `remaining`
  (sender), `result` (filter/scraper). Friendly download names come from
  `result["download_names"]`.
- Worker code reports progress through a `progress_cb(percent, message)` made by
  `make_progress_callback`; the core processing functions accept this callback.

**Consequences when editing:** job state is in-memory and single-process — it is wiped by
`--reload` and not shared across workers. `JobManager.cleanup_old()` (called on each launch)
drops jobs/files older than `retention_seconds` (6h).

### Frontend (Jinja + vanilla JS polling)

All pages extend [templates/universalLayout.html](templates/universalLayout.html), which
defines `window.iceReachJob` — the shared helper that POSTs a form, expects `202 + job_id`,
polls `/jobs/{id}` every 1.2s, drives a Bootstrap progress bar, and on completion renders
the JSON summary (sender) or triggers an artifact download (filter/scraper). Per-page
scripts (`upload_form.html`, `email_filter.html`, `email_scraper.html`) only supply the
`onProgress/onDone/onError` handlers. If you change the job result shape, update both the
job function in `app.py` and the page's handlers.

### Shared infrastructure in app.py

- **`SmtpSession`** — one authenticated SMTP connection reused across a whole send batch
  (transparent reconnect on drop). Opened once up front so auth/connection errors abort
  before the file is processed. Relaxes TLS verification only for non-major providers.
- **`resolve_mx_hosts(domain)`** — single shared DNS resolver + per-domain MX cache
  (negatives cached too). All MX checks (`has_mx_record`, `has_mx_record_filter`,
  `check_smtp_filter`) go through it.
- **NCBI Entrez** — `_ncbi_url` appends `NCBI_API_KEY` (env) and `_ncbi_throttle` rate-limits
  to 10 req/s with a key, 3/s without.
- **`render_template(content, row)`** — the substitution engine for both email bodies and
  subjects: `{column}` placeholders are filled from the CSV row dict; **missing/typo'd keys
  are left intact rather than raising** (do not switch this back to `str.format`).

### Data contracts

- Sender CSV requires `name` + `emails`; any other column is usable as `{column}` in the
  template/subject. Filter CSV requires only `emails`. Multiple emails are `;`-separated.
- Filter **resume** keys its checkpoint/output off the *stable original filename*
  (sanitized), never the random temp path — both endpoint and `process_csv_file_filter`
  must agree on `output_base_name`/`output_dir` for resume to find prior state.
- Scraper dedupes by email and stores author records under a collision-free key
  (`__author__::<first email>`), never `author_name` (names collide; many fall back to
  "Unknown Author").

### CLI_files/

`CLI_files/*.py` are standalone, legacy command-line variants that duplicate the app's
logic. They are **not** maintained alongside `app.py` — prefer changing the web app. Run
them from the repo root so their `templates/` paths resolve.
