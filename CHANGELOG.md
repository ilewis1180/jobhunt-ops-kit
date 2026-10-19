# CHANGELOG — jobhunt-ops-kit

The playbooks in `docs/` keep one version line each; their history lives here, out of every session's read path.
Curation adds a row at the top. **No personal data.**

## 0.2 — stage-2 sync (branch `stage2-sync`)

Folds in the operations changes made after the first public copy was taken (the "to fold in" list of `MANIFEST.md`):

- **One job key.** `ops/tools/jobkey.py`: a job's key is its LinkedIn number whenever one is known, else `JT-<10 hex>`;
  `linkedin_id()`, `company_norm()` / `company_key()` (one normaliser for the board, mail matching and the JD
  guard), `aliases()` and `same_job()` from `jt-keys.csv` (now with a `location` column). `common.company_key` and
  `common.job_tools_key` delegate to it. `docs/10`, `docs/11`.
- **Gated Raw append.** `ops/tools/raw_append.py` replaces per-run append scripts: header, 27 fields, id and date
  checks, the key rule, duplicates in the file, in Raw and through aliases, `--expect-n/--expect-q`, RAW-mode typed
  write, full read-back, jsonl log, `jt-keys.csv` upkeep. `queue_api.py` gained the Raw helpers. `docs/05` Step D and
  `docs/10` step 7 call it.
- **Capture is mandatory.** `dispatch.py event … submitted` needs `--proof <AppApply-Capture/proof/<RunID>/<JobID>-a<N>-…>`
  of this attempt (`proof_gate`) and refuses when no OUTCOME fragment ends up staged (`outcome_gate`). `docs/08` §1.1,
  `docs/09` §5 step 6, `test_dispatch.py`.
- **Token feed.** `token_audit.py --write-usage <OrchRunID>` writes the 16-column `USAGE-<OrchRunID>.csv` the dashboard
  reads (sessions named `orch`, `orch-<HHMM>`, `lane<N>-<HHMM>`; job counts from the outcomes CSVs; `--weekly-*`
  typed in by the operator; write-once after the run day). It replaces `usage_report.py`, which is removed. `docs/09`
  §8 and `docs/11`; `RUN-SUMMARY` carries `tokens_per_submit`.
- **JD Archive guard.** `jd_archive_api.name_problem` stops an append whose Company/Title were mangled by the CSV
  builder (checked against the Queue's own columns); `fix-names --csv <corrections>` repairs columns B and C in place,
  once, with the same read-back. Tests `test_jd_archive_names.py`, `test_jd_archive_fixnames.py`.
- **Role cards.** `docs/roles/ROLE-{scrape,prep,orch,lane,discover}.md`: the minimum each session reads, with pointers
  into the numbered docs (a lane starts on its card plus the answers file instead of six playbooks). `docs/00` routes
  every phase through its card; a numbered doc wins over a card when they disagree. Lanes live long: a HANDOFF note
  and a compaction after every round rather than retiring after a few cards.
- **This file.** Version history out of the read path.
- CI runs the five new tests; `config.example.toml` gained `[capture] proof_format`.

## 0.1 — first public copy

Playbooks `docs/00`–`11`, `ops/tools` with tests, the discover package, résumé build tools with fictional examples,
the dashboard port with sample data, synthetic example CSVs, the public PII gate. See `MANIFEST.md` for every file's
source and what was changed.
