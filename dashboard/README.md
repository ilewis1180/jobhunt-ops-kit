# dashboard/ — the read-only portal

A FastAPI + Jinja + HTMX web app over a receive-only mirror of the ops data root, with its own Postgres read model
rebuilt from the files on every sync. Pages: Today (funnel, needs-you list, recent submits, health), Applications
(search, status and ATS filters, CSV export, token-use card), one application (trail, answers by key, proof
screenshots, JD, run files), Outcomes (from `timeline.csv`), Stats (funnel, skip reasons, submits by ATS and day),
Questions (the question bank), Library (résumés, approved bullets, docs viewer), Accounts (tenant ledger, health).
There is no POST route and no login: bind it to loopback or a private network address only.

Ported from a private deployment with a fresh history; the host-specific files were dropped and every hostname,
path, spreadsheet id and name was moved to `.env`.

## Stack

Python 3.14 image, FastAPI 0.141, uvicorn, Jinja2, psycopg 3, markdown-it-py, google-auth (sync only), Postgres 16,
HTMX 2.0.10 vendored in `src/jobhunt/web/static/`. Three containers (`compose.yaml`):

| Service | Role | DB role | Mounts |
|---|---|---|---|
| `db` | Postgres on loopback | `jobhunt_admin` | volume |
| `sync` | `python -m jobhunt.sync`: every `JOBHUNT_SYNC_INTERVAL` s fingerprints the mirrored folders and the sheets; when anything changed it parses everything and replaces 13 read-model tables in one transaction (TRUNCATE + refill). `sync_runs` is the only portal-held state. Run mode: while a run is live (fresh dispatch events or a RUN-ACTIVE flag) a light sync every 30 s refreshes the board, attempts, traces, run files and the Queue tab | `jobhunt_sync` (schema owner) | ops `:ro`, content `:ro`, the service-account key `:ro` |
| `app` | the portal | `jobhunt_app` (SELECT only, `default_transaction_read_only`) | ops `:ro`, content `:ro` |

`db/init/01-roles.sh` creates the roles on the first start of an empty volume; `scripts/new-secrets.py` writes the
three `secrets/*.env` files with random passwords (never printed, git-ignored).

## Run it

```bash
cd dashboard
cp .env.example .env                 # defaults point at ./sample-data: a synthetic data root
python scripts/new-secrets.py
docker compose up -d --build
open http://127.0.0.1:4110/
```

For your own data, set `JOBHUNT_OPS_HOST_DIR` and `JOBHUNT_CONTENT_HOST_DIR` in `.env` to the mirrored folders,
`JOBHUNT_TZ` to the applying machine's zone, `JOBHUNT_RESUME_PREFIX` to any file-name prefix your résumés share, and
(optionally) the two spreadsheet ids plus a read-only Google service-account key at `JOBHUNT_GOOGLE_SA_HOST_FILE`
(viewer on the two sheets, `spreadsheets.readonly`). Without the sheets the portal runs from files alone.

Tests (no database needed): `pip install -r requirements-dev.txt && python -m pytest -q tests` (23 tests).

## What it reads (all under the mirrored data root; schemas in `docs/11-data-model.md`)

`Runs/*/scrape-*.csv` → `jobs` · `Runs/*/jd-*.csv` → `jds` · `Runs/*/dispatch-*/board.csv` → `board` ·
`AppApply-Capture/outcomes.csv`, `outcomes-jt.csv` and `staging/OUTCOME-*.csv` (17 columns) → `attempts` ·
`AppApply-Capture/traces/**/*.jsonl` → `trace_steps` (answer keys and `value_safe`/`value_ref` only) ·
`question-bank.csv` → `questions` · `04-ACCOUNT-LEDGER.md` → `tenants` (the Notes column is never stored) ·
`Resume/*.pdf` → `resumes` · the résumé workspace's `Approved-Bullets.md` → `bullets` · `0*.md`, `SESSION_LOG.md` →
`docs` · `Runs/*/PREP-*`, `INTENT-*`, summaries → `run_files` · `Runs/*/USAGE-*.csv` (16 columns) → `token_usage` ·
the Queue, Raw and JD Archive sheets → `sheet_rows` (credential-looking columns dropped). Outcomes reads
`AppApply-Capture/timeline.csv` (16 columns) and `followups.csv` directly. Proof screenshots are served from
`AppApply-Capture/proof/<RunID>/<JobID>-a<N>-{review,text<K>,confirm}.png`.

## Counting rules (why three "submitted" numbers can differ)

Stats "Submitted" and the Applications status filter take the **Queue Status** first (the orchestrator's record), and
fall back to the latest attempt, then the board. Outcomes "Applied" is the row count of **`timeline.csv`** (built by
`mail_track.py` from the Queue's Submitted rows). The Applications count of attempts comes from **`outcomes*.csv`**.
Three sources, three join keys: reconcile on the ops side before trusting any one of them.

## Privacy

The file routes serve only an allowlist: top-level `0N-*.md` and `SESSION_LOG.md`, and the `Runs/`,
`AppApply-Capture/`, `Resume/`, `1-Resumes/`, `3-Bullet-Bank/`, `4-ATS/` folders, never any path with `private` in
it (`parsers.is_private`; `tests/test_proof.py`). Sheet columns whose header looks like a credential are dropped at
sync. Trace values are keys and references, never personal values (08 §1).

## Known issues (carried over, open)

- Outcomes tiles are not mutually exclusive: Open + Confirmed + Rejected + Interview can exceed Applied.
- `/outcomes?state=open` and `?state=interview` return 422 (the `state` pattern allows only applied, confirmed,
  rejected).
- The token card's weekly-limit % is taken from whichever run last reported one.
- The "browser on the apply host" health tile is a TCP probe of a CDP port; irrelevant when the browser runs elsewhere.
- Older private data may still carry the pre-kit vocabulary (`standing_02`, `needs_manny`); the public version reads
  only the kit vocabulary (`docs/11-data-model.md`).
