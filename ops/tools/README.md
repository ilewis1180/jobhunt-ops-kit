# ops/tools — the command-line tools the playbooks call

Python 3.9+ standard library only (no pip installs). Every tool reads `config.toml` through `common.py`; the data
root is config `paths.ops_root` or `$JOBHUNT_OPS` (tests point it at a temp folder). Run `python3 ops/tools/common.py`
to see what it resolved.

| Tool | Role | Doc |
|---|---|---|
| `common.py` | config, paths, run and job ids, the JT key, normalisers, `die`, atomic CSV | — |
| `dispatch.py` | the parallel-run board: init, claim, event, board, queue-plan, needs, watch | 09 §3 |
| `preflight.py` | read-only HTTP check of every card before lanes start (Greenhouse, Lever, Ashby, Workday APIs; plain GET otherwise) | 09 §4 |
| `queue_api.py` | the Job Queue through the Sheets API: read, and write B–I by Job ID with read-back | 01 §1.4 |
| `jd_archive_api.py` | append-only JD Archive with read-back and a Company/Title self-check; `fix-names` for a one-time in-place name repair | 06 |
| `jobkey.py` | the one job key (LinkedIn number, else `JT-`), the company normaliser, `jt-keys.csv` aliases | 10, 11 |
| `raw_append.py` | the gated Raw append (header, ids, key rule, duplicates and aliases, N/Q, RAW-mode write, read-back, log) | 05 Step D |
| `intent_check.py` | INTENT coverage: every required field verified | 01 §4 step 8 |
| `trace.py` | append one trace line, refusing any personal value | 08 §2 |
| `pii_scan.py` | the PII gate (private patterns; `--patterns` for the public gate; `--attempt`; `--canary`) | 08 §1 |
| `import-inbox.py` | merge staging fragments / a cloud inbox into the capture CSVs, blocking PII and bad names | 08 §4.1 |
| `build-question-bank.py` | rebuild `question-bank.csv` from observations, redacting personal values | 08 §5 |
| `mail_track.py` | match mail threads to submitted jobs → `timeline.csv` and the orchestrator's brief | 09 §4 |
| `token_audit.py` | token use per session from the coding agent's transcripts; `--write-usage` writes the dashboard's USAGE feed | 11 |
| `lane-windows.sh` | macOS: which Chrome windows a lane can use; the one-lane-at-a-time start gate | 09 §2, §4 |
| `backup.sh`, `backup-watchdog.sh` | one-way backup of the data root to a folder, and the alarm when it stops | 09 §4 |
| `hooks/` | a pre-commit PII gate (`hooks/install.sh`) | — |

Tests (offline, no network, temp folders only): `python3 ops/tools/test_common.py`, `test_pii_scan.py`,
`test_import_inbox.py`, `test_dispatch.py` (includes the mandatory `--proof` on `submitted`), `test_jobkey.py`,
`test_raw_append.py` (an in-memory fake of the sheet), `test_token_audit.py`, `test_jd_archive_names.py`,
`test_jd_archive_fixnames.py`. CI runs them on Python 3.9 and 3.12.

Pattern files: `pii_patterns.example.json` is the shape of your private file (outside the repo);
`pii_patterns.public.json` is what CI scans this repository with.
