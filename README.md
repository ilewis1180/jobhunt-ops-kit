# jobhunt-ops-kit

A job-application operations system run by an AI coding agent with a browser, under a human's per-application
approval. It grew out of one person's job hunt (about 250 applications in its first month) and is published here
**with nothing personal in it by construction**: every answer, résumé, hostname, spreadsheet id and run file lives
outside the repository; CI scans the tree with a public PII gate on every push.

## The four phases

| Phase | Session | What happens |
|---|---|---|
| **0 Discover** | `phase 0` | search tools (python-jobspy, a grader) find jobs; the operator ticks Apply/Skip; an agent finds the real apply link; rows go to the Raw tab with a `JT-` key |
| **1 Scrape** | `phase 1` | the LinkedIn Saved list is walked read-only into a 27-column CSV and appended to Raw through gates |
| **2 Prep** | `phase 2` | every Ready job gets a PREP card: the real ATS, every answer worked out from the private answers file, drafted text with sources, consents, open questions. Nothing is typed into a form |
| **3 Approve and submit** | `phase 3` | one **orchestrator** session runs a dispatch board, preflight, a decision sweep and the Queue writes; up to five **lanes** claim cards, ask the operator one question per card in their own chat, fill, write an INTENT, submit once, confirm, and record a trace, an outcome row and proof screenshots |

The playbooks in `docs/` are written for a coding agent (Claude Code with a browser extension) but are
tool-agnostic in their mechanics: write-once run files, read-back on every sheet write, a PII scan before every
record, approval recorded per card before any field is touched.

## The Mac/portal split

- **The applying machine** (a Mac in the original setup) holds the data root (`Runs/`, `AppApply-Capture/`,
  `Resume/`, the private answers file), runs the sessions and the `ops/tools`, and writes the two Google Sheets
  (Job Queue, JD Archive).
- **The dashboard host** receives a receive-only mirror of the data root and runs the read-only portal in
  `dashboard/` (FastAPI + HTMX + Postgres): Today, Applications, Outcomes, Stats, Questions, Library, Accounts.
  It never writes anything back.
- **The résumé workspace** (`resume/`) builds the upload PDFs from markdown and verifies them against an ATS screener.

## Layout

| Folder | Contents | Run it |
|---|---|---|
| `docs/` | the playbooks 00–11 and templates (answers file, account ledger, cards, summaries) | read `docs/00-start-here.md` first |
| `ops/tools/` | the tools (stdlib Python + two shell scripts), tests, PII patterns | `python3 ops/tools/test_*.py` |
| `discover/` | the Phase 0 search package and profiles | `python3 discover/scripts/run_search.py tech-sales` (after copying a profile) |
| `resume/` | build, lint and backup scripts, CSS, editor references, fictional examples, templates | `python3 resume/scripts/check_resume.py --shape ats resume/examples/ATS-Example.md` |
| `dashboard/` | the portal source, compose file, sample data | `cd dashboard && cp .env.example .env && python scripts/new-secrets.py && docker compose up -d --build` |
| `examples/` | synthetic CSVs in every file shape (`docs/11-data-model.md`) | — |
| `MANIFEST.md` | every file's source and what changed; what was left out and why | — |

## Setting it up for yourself

1. `cp config.example.toml config.toml` and fill in your data root, spreadsheet ids, browser profile and zone.
2. Write your private answers file from `docs/templates/ANSWERS-PRIVATE.template.md` (outside git), and your private
   PII pattern file from `ops/tools/pii_patterns.example.json` (outside the repo, mode 600). Install the pre-commit
   gate: `ops/tools/hooks/install.sh`.
3. Place a read-only copy of a Google OAuth token (drive scope) where `paths.google_token` points; share the two
   sheets with it. `python3 ops/tools/queue_api.py check`.
4. Build your résumés with `resume/` and put the PDFs in the data root's `Resume/`.
5. Open a session in this folder and type the phase word (`docs/00-start-here.md`).

## Safety properties

No credential or personal value is ever written to a file in the data root's shared parts: capture files carry
answer keys (`identity.email`) and references, `pii_scan.py` gates every terminal event and every commit, and the
dashboard serves files from an allowlist. The applier never types a password, never creates an account, never clicks
Submit without a recorded per-card approval and a written INTENT, and never re-submits to find out.

## Licence

MIT (see `LICENSE`). The résumé editor's base stylesheet is copyleft upstream code and is fetched, not shipped
(`resume/css/README.md`). The Phase 0 grader's upstream publishes no licence and is fetched by a script
(`discover/vendor/find_a_job_ai/SOURCE.md`).
