
# Author Outreach Automation (PubMed Scraper → Email Sender)

Automate academic outreach in two steps: **scrape authors + emails from PubMed** and **send personalized emails** using a configurable HTML template.  
The unified entry point is **`autoMailApp.py`** — it guides you through scraping, validating, and sending in an interactive flow.

> Ideal for research groups, editors, and collaborators who need **targeted**, **personalized**, and **logged** outreach.

---

## ✨ What this tool does

- **Scrape authors from PubMed** for a given topic/keyword
- **Extract & clean emails** (CSV output you can review)
- **Send personalized emails** via SMTP (Gmail/Outlook/Office365/Yahoo or custom)
- **Log results** (delivered / failed / error messages) to a separate CSV
- **Throttle safely** (configurable delays and per-run caps)

---

## 🧩 Repository structure


web-scraping-info-of-authors-though-API-to-automate-the-mailing/

├─ autoMailApp.py                        # ⭐ Main entry point (interactive end-to-end)

├─ scrapName.py                          # PubMed scraping → CSV

├─ automateEmailing.py                   # Legacy/alternate email sender

├─ emailFilter.py                        # Utility for filtering/cleaning emails from CSV

├─ for\_automate\_authentic\_email\_google\_yahoo\_office.py  # SMTP auth/provider helper

├─ templates/                            # HTML email templates (edit your outreach copy here)

├─ requirements.txt                      # Python deps

├─ try.csv                               # Example/placeholder CSV

└─ webscrap and email automation Process.txt  # Notes/process outline


## ✅ Prerequisites

- **Python** 3.8+ (3.10/3.11 recommended)
- An email account that supports SMTP (Gmail, Outlook/Office365, Yahoo, or custom SMTP)
  - For Gmail/Outlook, use an **App Password** (recommended) instead of your main password
- Network access to NCBI E-utilities (for PubMed search)

Install dependencies:

```bash
pip install -r requirements.txt
```

> If `requirements.txt` is minimal (e.g., just `requests`), that’s because the email stack uses Python’s standard library (`smtplib`, `email.mime`, etc.).

---

## ⚙️ Configuration

You can run fully **interactive** (prompts will ask everything), or prepare a small `.env` file in the project root to reduce typing:

```env
# .env (optional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@example.com
SMTP_PASSWORD=your_app_password

# Sending controls
MAX_EMAILS_PER_RUN=50
SEND_DELAY_SECONDS=8

# Defaults for scraping
SEARCH_TERM=cancer immunotherapy
YEARS_BACK=5
MAX_RECORDS=200
```

> If you don’t want a `.env`, just run interactively and paste values when prompted.

---

## 🏁 Quick Start (recommended path)

### 1) Run the end-to-end app

```bash
#to start the server locally
#recommended:
uvicorn autoMailApp:app --reload

#if you think the port is busy the try:
uvicorn autoMailApp:app --reload --port 8002 #(you can use port from 8000 - 8005) thats on you
```

You’ll typically be prompted to:

1. **Choose a mode**

   * `Scrape` authors → produce a CSV
   * `Send` emails from an existing CSV
   * `Pipeline` (scrape → send in one flow)
2. **Provide scraping inputs**

   * Topic/keyword (e.g., `"graph neural networks"`)
   * Years window (e.g., `5`)
   * Optional caps/limits
3. **Provide email inputs**

   * Path to CSV with emails (if you didn’t just scrape)
   * SMTP server (`smtp.gmail.com`, `smtp.office365.com`, `smtp.mail.yahoo.com`, or custom)
   * SMTP username & app password
   * Max emails per run & per-email delay (anti-spam/limits)
   * **Template selection** from `/templates`

The app will:

* Save **scraped authors** to CSV (e.g., `graph_neural_networks_authors_with_emails.csv`)
* Send emails (respecting your delay and cap)
* Create a **results log CSV** (e.g., `graph_neural_networks_authors_with_emails_results.csv`)

---

## 🧪 Alternate / Advanced scripts

* **`scrapName.py`** — Directly scrape PubMed into a CSV (run this if you only want data).
* **`automateEmailing.py`** — Standalone sender if you already have a CSV and want a focused CLI for sending.
* **`emailFilter.py`** — Clean up CSV emails (dedupe, simple validation, optional domain filters).
* **`for_automate_authentic_email_google_yahoo_office.py`** — Handy for testing SMTP provider logins and settings.

> You can use these utilities independently, but most users should stick with `autoMailApp.py`.

---

## 📨 Email templates

Templates live in **`templates/`**. They’re standard HTML (you can use simple placeholders, e.g., `{name}`, `{journal}`, `{article_title}` if the script supports string formatting).

**Tips**

* Keep it short and personal
* Mention the paper title and venue
* Add a **polite opt-out** line at the end
* Test send to yourself first

---

## 📄 CSV schemas

Your **scraped CSV** will typically contain columns like:

| Column          | Description                        |
| --------------- | ---------------------------------- |
| `name`          | Author’s full name                 |
| `email`         | Extracted/parsed email             |
| `journal`       | Journal/venue                      |
| `article_title` | Paper title                        |
| `affiliation`   | Author affiliation                 |
| `source_url`    | (If available) PubMed/article link |

Your **results CSV** (after sending) will typically add:

| Column    | Description                     |
| --------- | ------------------------------- |
| `status`  | `sent` / `failed`               |
| `error`   | SMTP / formatting errors if any |
| `sent_at` | Timestamp                       |

> Exact column names may vary slightly — open the generated CSV to confirm.

---

## 🔐 SMTP notes

* **Gmail:** `smtp.gmail.com:587` (TLS). Use an **App Password** (Google Account → Security → App Passwords).
* **Outlook/Office365:** `smtp.office365.com:587` (TLS). App password or Modern Auth as applicable.
* **Yahoo:** `smtp.mail.yahoo.com:587` (TLS). App password recommended.
* **Custom SMTP:** Ask your provider for host/port/TLS and limits.

**Respect provider limits** (Gmail \~500/day personal; Workspace/Office365 vary). Use `MAX_EMAILS_PER_RUN` and `SEND_DELAY_SECONDS` to avoid throttling.

---

## 🧯 Troubleshooting

**`[Errno 11001] getaddrinfo failed`**
DNS/host resolution issue. Double-check `SMTP_SERVER` (typo?), network, and port 587.

**`SMTPAuthenticationError`**
Wrong username/app password, or app-password not enabled. For Gmail/Outlook/Yahoo, create an **App Password**.

**No emails in scraped CSV**

* Try broader keywords
* Increase years window
* Some PubMed entries lack emails — adjust filters or add a secondary extraction approach

**Mangled accents/Unicode**
Open CSV with UTF-8. When sending, ensure `MIMEText(html, "html", "utf-8")`.

**HTML renders as plain text**
Send as `multipart/alternative` with HTML part; most of the included senders already do this.

---

## 🧼 Ethics & compliance

Use this for **legitimate** academic/professional outreach only.
Add an **opt-out** line and respect unsubscribe requests.
Comply with applicable anti-spam laws (CAN-SPAM, GDPR, etc.).
Throttle responsibly; respect PubMed/NCBI E-utilities policies.

---

## 🛠️ Development

* Python style: keep things straightforward and cross-platform
* Consider extracting constants (SMTP defaults, delays) to a `config.py` or `.env`
* Add tests around:

  * CSV read/write
  * Basic email rendering (template → filled HTML)
  * Dry-run mode (render-only, no send)

**Nice-to-haves / Roadmap**

* CLI flags for `autoMailApp.py` (non-interactive runs)
* Retry/backoff on transient SMTP errors
* Bounce handling + suppression list
* Provider-aware rate limits
* Parallel scraping with polite throttling

---

## 🤝 Contributing

PRs welcome:

1. Fork
2. Branch: `feat/<name>` or `fix/<name>`
3. Format & test
4. Open PR with a clear description and before/after

---

## 📜 License

Open use. If you adapt for production, add your preferred license file.

---

## 🙋 FAQ

**Can I run only the sender with my own CSV?**
Yes — point `autoMailApp.py` (or `automateEmailing.py`) to your CSV. Make sure there’s an `email` column.

**Where do I change the email copy?**
Edit the HTML in `templates/`. Keep variables consistent with what the sender fills (e.g., `{name}`, `{article_title}`).

**How do I slow it down to be safe?**
Increase `SEND_DELAY_SECONDS` and lower `MAX_EMAILS_PER_RUN`.

**Does this support SSL-only SMTP (port 465)?**
Yes, but prefer STARTTLS on 587 if your provider supports it. If you must, use `smtplib.SMTP_SSL` and adjust the port.
