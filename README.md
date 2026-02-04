# ICENews

ICENews is a **read-mostly social media monitoring dashboard** for collecting posts (currently X/Twitter via Scrapfly) into **SQLite**, then viewing them via a small **FastAPI + Jinja2 + Alpine.js + Tailwind (CDN)** web app.

This repo is being built for a **government monitoring context**. The guiding principle is: **predictable, testable, deployable**. If something is ambiguous, we prefer a safe default.

---

## What’s in this repo

- **Web app**: [`app/main.py`](app/main.py)
  - `GET /` renders the dashboard (server renders initial JSON payload)
  - `GET /api/posts` returns posts with **soft caps**
  - `GET /api/accounts` returns enabled accounts
- **DB access layer**: [`app/db.py`](app/db.py) (SQLite reads + clamping)
- **Models**: [`app/models.py`](app/models.py) (Pydantic response models)
- **Ingestion (X via Scrapfly)**: [`app/ingest/ingest_x_scrapfly.py`](app/ingest/ingest_x_scrapfly.py)
- **Scheduler**: [`app/scheduler.py`](app/scheduler.py) (runs ingestion periodically)
- **DB schema**: [`db`](db) (SQLite schema for `accounts`, `posts`)
- **Frontend**:
  - Template: [`app/templates/index.html`](app/templates/index.html)
  - JS: [`app/static/app.js`](app/static/app.js)

---

## Requirements

- macOS/Linux
- Python 3.10+ (recommended: 3.11)
- Scrapfly API key (test key is fine for dev)

Install dependencies:

```bash
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

---

## Environment configuration (`.env`)

Create a `.env` in the project root. At minimum you need a Scrapfly key.

Example keys used by the app:

- `SCRAPFLY_KEY` (live)
- `SCRAPFLY_USE_TEST=1` and `SCRAPFLY_TEST_KEY` (test)
- `ICENEWS_MAX_TWEETS_PER_ACCOUNT=4` (per-run cost control)
- `UMAMI_WEBSITE_ID` / `UMAMI_SCRIPT_URL` (optional analytics)

Security note: `.env` contains secrets and must not be committed.

---

## Initialize the database

Create the SQLite database file:

```bash
sqlite3 icenews_social.db < db
```

Import accounts (from `app/data/accounts.csv` if present, or your own CSV path if you adapt the importer):

```bash
. venv/bin/activate
python -m app.ingest.import_accounts
```

---

## Run ingestion (X via Scrapfly)

Run once:

```bash
. venv/bin/activate
python -m app.ingest.ingest_x_scrapfly
```

Cost control knob:
- **Per run** the ingestor fetches up to `ICENEWS_MAX_TWEETS_PER_ACCOUNT` newest posts per enabled account.
- Your current target is **4 per account per run**, every **6 hours**.

---

## Run the web app (FastAPI)

Start the server:

```bash
. venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open:
- `http://127.0.0.1:8000`

If you get **address already in use**:

```bash
lsof -i :8000
kill <PID>
```

---

## Run the scheduler

Run once:

```bash
. venv/bin/activate
python -m app.scheduler
```

Run as a daemon (every 6 hours = 21600 seconds):

```bash
. venv/bin/activate
python -m app.scheduler --daemon --interval 21600
```

---

## Tests

Run security tests:

```bash
. venv/bin/activate
pytest -q
```

---

## Safety posture (current)

This project is intentionally **read-only** for normal users (public dashboard view). Key safety choices so far:

- **SQL injection resistance**: parameterized queries in `app/db.py`
- **XSS reduction**: initial JSON is embedded in a `<script type="application/json">` tag and `<`/`>` are escaped server-side
- **Large-number attack mitigation**:
  - API layer accepts large values but **soft-caps**
  - DB layer also clamps (defense-in-depth)

**Important**: If you deploy to the public internet, you should add at least:
- HTTPS (Let’s Encrypt via Caddy)
- a read-only password gate (basic auth)
- rate limiting at the reverse proxy

See `DEPLOYMENT.md` for the VM + Docker path.

