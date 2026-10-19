# MANIFEST — where every file came from and what changed

Sources are the private repositories on the applying machine: **ops** = the operations repo (`AppApply/ops`, at its
commit after the stage-2 history rewrite), **tools** = the job-tools folder (`Tools/winnie-jobhunt-tools`,
`Tools/find-a-job-ai`), **résumé** = the résumé workspace (`Job Hunt 2026`) and the `mdresume` skill folder,
**portal** = the dashboard source zip sent by the dashboard host (2026-10-17). "New" = written for this kit.
Every file was de-personalised the same way: names, hostnames, Tailscale addresses, home-directory paths, spreadsheet
ids, device ids, run ids, dates of specific incidents, company rulings and the person's answers removed or moved to
`config.example.toml` / `.env.example`; the protocol tokens that carried a name were renamed (`needs_manny` →
`needs_user`, `manny_submit` → `user_submit`, `manny_answer` → `user_answer`, `standing_02` → `standing_answers`,
`rule_07` → `rule_playbook`); the private answers file is "the answers file" / `ANSWERS-PRIVATE.md`.

## Root

| File | Source | Change |
|---|---|---|
| `README.md` | new | what the system is, the four phases, the Mac/portal split, how to run each piece |
| `LICENSE` | new | MIT; notes the two fetched (not shipped) third-party pieces |
| `MANIFEST.md` | new | this file |
| `config.example.toml` | new | every path, id and name the tools used to hard-code |
| `.gitignore` | ops `.stignore` + ops `.gitignore` | plus `*token*`, `*credentials*`, `.env*`, `config.toml`, run data, build outputs, fetched files |
| `.github/workflows/ci.yml` | new | public PII gate (`pii_scan --patterns`) + literal grep, tests on Python 3.9 and 3.12 |

## docs/ (rewritten generically from the ops playbooks)

| File | Source | Change |
|---|---|---|
| `00-start-here.md` | ops `00-START-HERE.md` + ops `CLAUDE.md` routing table | files table, phase routing, run ids, session start/end, the ten hard rules; Project/Drive-era text dropped; the person's name → the operator |
| `01-queue-and-files.md` | new, from the parts of ops `01-PLAYBOOK.md` the other files reference (§1.4, §1.5, §2, §4, §7, §8, §11, §12) as described in 00/07/08/09 and the tools | written so the `01 §n` references in docs and tools resolve; 01-PLAYBOOK itself was not copied (it carries personal rulings) |
| `03-ats-quick-reference.md` | ops `03-ATS-KNOWLEDGE.md` quick-reference table | one row per ATS; tenant-specific account notes dropped |
| `05-scrape.md` | ops `05-SCRAPE-PROMPT.md` | steps A–E, derived fields, flags, header, gates, gotchas kept; the pasted prompt block folded into the field list; page-script recipes summarised |
| `06-jd-archive.md` | ops `06-JD-BACKFILL.md` header and steps (via `jd_archive_api.py`) | the `jd-` file, the 10-column CSV, the append |
| `07-apply.md` | ops `07-APPLY-PROMPT.md` | answer rules, free-text sources, live-form and parser checks, Blocks 1–4; résumé file names, salary figures, employer names and dated rulings removed; change log dropped |
| `08-capture-spec.md` | ops `08-CAPTURE-SPEC.md` | §1–§5 kept; tenant example in the sample JSON made generic; dated incident narrative shortened |
| `09-parallel-apply.md` | ops `09-PARALLEL-APPLY.md` | §1–§8 kept with the same numbering; deviceId, profile names and dated incidents moved to config or generalised; model rulings generalised; change log dropped |
| `10-discover.md` | ops `10-DISCOVER.md` | steps, review format, apply-link agent, JT key rule; the stage-2 "LinkedIn number wins" rule noted |
| `11-data-model.md` | new, from the ops CSV headers, `queue_api.py`, `mail_track.py`, `dispatch.py`, `usage_report.py` and the audit's appendix E | every tab and CSV with columns and vocabularies |
| `templates/ANSWERS-PRIVATE.template.md` | new (section names inferred from the tools' answer-key vocabulary, never from the private file) | headings and key names only |
| `templates/04-account-ledger.template.md` | ops `04-ACCOUNT-LEDGER.md` table shape (as read by the portal parser) | header and states only |
| `templates/PREP-card.template.md`, `RUN-SUMMARY.template.md`, `LEARNINGS.template.md`, `DISCOVER.template.md` | the formats in ops 07, 00, 10 | fictional example values |

## ops/tools/

| File | Source | Change |
|---|---|---|
| `common.py` | new | config loading (tomllib, tomli or a minimal parser), data-root and path resolution, `RUN_RE`, `JOB_ID_RE`, `ATTEMPT_RE`, `run_date`, `job_tools_key`, `company_key`, `normalize_text`, `die`, `atomic_csv`, `col_letter`, local zone; replaces the 7 `REPO` fallbacks, 3 run-id regexes, 5 job-id regexes and 3 `die()`s |
| `dispatch.py` | ops `tools/dispatch.py` | imports from `common`; zone from config; `NEEDS_RULES` generalised to answers-file sections (one school name and one years figure removed); card heading `## Needs <anything>`; token renames; the person's name → the operator |
| `queue_api.py` | ops | spreadsheet id and token path from config; `die`/`col_letter`/`JOB_ID_RE` from `common`; token-provenance docstring generalised |
| `jd_archive_api.py` | ops | spreadsheet id from config |
| `preflight.py` | ops | imports `common`; two employer names in comments removed; local stamp from config |
| `import-inbox.py` | ops | inbox from config (`paths.inbox_dir`, default `AppApply-Capture/staging`); patterns through `pii_scan`; cloud-drive folder names removed |
| `mail_track.py` | ops | mail dir from config; `ERA_START` from config (`run.queue_era_start`); reads `outcomes-jt.csv` too (folded in from stage 2); normaliser from `common` |
| `pii_scan.py` | ops | `--patterns <file>`; named-pattern file shape; the pattern file in use is skipped when scanning; `--attempt` accepts `JT-` ids (folded in from stage 2); neutral names `pii-<kind>-n` |
| `trace.py` | ops | attempt regex and capture path from `common` |
| `intent_check.py` | ops | unchanged |
| `build-question-bank.py` | ops | reformatted; pattern file through `pii_scan`; `Archive/First Run` glob dropped; dead `try: pass` blocks removed; vocabulary renamed |
| `token_audit.py` | ops | transcripts glob from config; `--check-0929` (a comparison against one private run) removed; private run-id lookup removed; zone from config |
| `usage_report.py` | ops | transcripts glob from config (the dashboard's USAGE feed writer) |
| `lane-windows.sh` | ops | lane-tab host configurable (`JOBHUNT_LANE_TAB_HOST`); incident dates removed; the person's name → the operator |
| `backup.sh` | ops `backup-to-drive.sh` | target, log and source from env/config; cloud-drive account glob and the publish step removed; résumé snapshot optional |
| `backup-watchdog.sh` | ops | decision number and dated incident removed |
| `hooks/pre-commit`, `hooks/install.sh` | ops `tools/hooks/` (stage 2) | paths under `ops/tools`; `JOBHUNT_HOOK_PATTERNS` for the public patterns |
| `pii_patterns.public.json` | new | shapes (e-mail, phone, street, spreadsheet id, tailnet address) plus the literal strings this repo must never carry, written so a plain grep does not match them |
| `pii_patterns.example.json` | new | the shape of the private pattern file |
| `test_dispatch.py`, `test_import_inbox.py` | ops | symlink `common.py`; fictional names |
| `test_common.py`, `test_pii_scan.py` | new | |
| `README.md` | new | |

Not copied from ops `tools/`: `tile-lanes.sh`, `launch-browser1.sh`, `publish-live.sh`, `timeline-refresh.sh`,
`run_active.sh`, `post-commit.hook`, `PROJECT-INSTRUCTIONS.md` (dead, host-specific, or Drive-era).

## discover/

| File | Source | Change |
|---|---|---|
| `src/jobhunt_tools/{keys,grade,fajai_grade,discover,resolve,db,export}.py` | tools `winnie-jobhunt-tools/src/jobhunt_tools/` | `keys.py` emits `JT-` keys (the stage-2 rule), `db.py` container/user/db from env, `fajai_grade.py` errors clearly when the vendored grader is absent; host-governance wording removed |
| `scripts/run_search.py`, `run_discovery.py`, `run_export.py` | tools | docstrings generalised |
| `config/profiles/tech-sales.example.json`, `healthcare-sales.example.json` | tools `config/profiles/*.json` | candidate name, location, years and the note replaced with example values; skill lists kept (generic sales terms) |
| `tests/test_jobhunt_tools.py` | tools | neutral location, `operator` as decided_by; JT key test |
| `requirements.txt` | tools | one JobSpy version (1.3.0) |
| `schema.sql` | new | the `job_approvals` table the pipeline assumes |
| `vendor/find_a_job_ai/SOURCE.md`, `fetch.sh`, `sales-grading.patch` | tools (the local patch to `find-a-job-ai`) | the upstream file is fetched, not shipped (no upstream licence); the patch is the kit's own change |

Not copied: `AGENT.md`, `WINNEREAD-*.md`, `winnie.yaml`, `CHANGELOG.md`, `workflows/cronicle-events.md`, `system/`
(host governance), `state/` (data), the `find-a-job-ai` and `jobspy-mcp-server` clones (upstream repos; the MCP
server is unrelated to the phases).

## resume/

| File | Source | Change |
|---|---|---|
| `scripts/build_ats_pdf.py` | résumé `1-Resumes/scripts/build_ats_pdf.py` | browser auto-detect / `--chrome`, temp file, `--css-dir` and css names, `--max-pages`, `--expect-name`, `--html-only`, non-ASCII report, exit codes |
| `scripts/build_backup.py` | mdresume skill `scripts/build_backup.py` | record ids and display names moved to a `--records` JSON; every style knob an option |
| `scripts/check_resume.py` | mdresume skill `scripts/check_resume.py` | `--shape ats|display|any`, `--max-skills`, `--skills-sep`, `--forbid`; the retired 15-skill pipe rule is now the display shape's option; ATS-shape checks added (entry line, dates, headings, one skill per line) |
| `css/ohmycv-theme.css`, `css/ohmycv-ats.css` | résumé `1-Resumes/` | header rewritten; employer names in comments replaced |
| `css/minimal-base.css`, `css/fetch_base_css.sh`, `css/README.md` | new | the editor's base stylesheet is GPL-3.0/AGPL-3.0 upstream (not MIT as first assumed), so it is fetched, and a small original stand-in ships |
| `references/{markdown-dialect,css-and-layout,storage-and-export,browser}.md` | mdresume skill `references/` | hostname → `<editor-host>`; example identity → fictional; corpus-specific sentences generalised |
| `examples/ATS-Example.md`, `Display-Example.md` | new (fictional) | the two shapes |
| `examples/records.example.json`, `example_backup.json` | new; built by `build_backup.py` from the examples with `minimal-base.css` | |
| `templates/applicant-profile.example.yml` | new (shape only; the private `applicant-profile.yml` was not read beyond its key names) | |
| `templates/Facts-Source-of-Truth.template.md` | résumé `3-Bullet-Bank/Facts-Source-of-Truth.md` headings + `00-README.md` evidence tags | headings and rules only, no content |
| `templates/approved-bullets.schema.json`, `approved-bullets.example.json` | new, from `approved-bullets/README.md`'s description of the JSON | |
| `docs/ats-screener-guide.md` | résumé `4-ATS/ATS-Screener-and-mdresume-Guide.md` §1–§6 generic parts | scan history, record ids, hostnames, session evidence dropped |
| `docs/per-application-checklist.md` | résumé `4-ATS/Per-Application-Checklist.md` | sales-specific keyword list and Facts line references dropped |
| `README.md` | new | |

Not copied: every real résumé `.md`/`.pdf`/`.notes.md`, `ats_variants_data.json`, the bullet banks and
`Approved-Bullets.md`, `evidence/`, `Targeting/`, `_Archive/`, `applicant-profile.yml`,
`Application-Field-Inventory.md`, `AGENT-BRIEF-Resume-and-ATS.md`, `Decisions-Log.md`, gap files.

## dashboard/

| File | Source | Change |
|---|---|---|
| `src/jobhunt/**` (app, data, outcomes, parsers, sheets, sync, db, schema.sql, templates, static) | portal zip `web-jobhunt/src/jobhunt/` | bind address, scanner URL, zone and résumé prefix from env; `is_private` is now an allowlist (`SERVED_ROOT_FILES`, `SERVED_DIRS`) plus the `private` rule; "Chrome on <host>" → "Browser on the apply host"; `answer_source` styles use the kit vocabulary; names and dated notes in comments removed |
| `tests/*.py` | portal zip | fictional résumé prefix via env; answers-file names; two extra blocked paths in the allowlist test (23 tests) |
| `compose.yaml` | portal zip | every host path, address, id and name is a `${VAR}` from `.env`; container and volume names generic; defaults run `sample-data/` |
| `.env.example` | new | |
| `Dockerfile`, `requirements*.txt`, `.dockerignore`, `.gitattributes`, `db/init/01-roles.sh`, `scripts/new-secrets.py` | portal zip | names in comments |
| `sample-data/` | new, assembled from `examples/` | a synthetic data root and résumé workspace so `docker compose up` shows every page |
| `README.md` | new | stack, run, what it reads, counting rules, privacy, known issues |

Not copied: `AGENT.md`, `CHANGELOG.md`, `WINNEREAD-web-jobhunt.md`, `winnie.yaml`, `system/`,
`scripts/start-chrome.ps1`, `scripts/start-chrome-hidden.vbs` (host governance and Windows launcher scripts holding
tailnet addresses, drive paths, hostnames and names). The repository history is fresh: nothing was cloned from the
host's private git, whose staging branch holds an encrypted key.

## examples/

All new and synthetic: `raw`, `queue`, `outcomes`, `outcomes-jt`, `timeline`, `followups`, `question-bank-observations`,
`question-bank`, `jt-keys`, `USAGE-…`, `board` CSVs, with a README.

## Deliberately left out, and why

| Left out | Why |
|---|---|
| ops `01-PLAYBOOK.md`, `02-ANSWERS-PRIVATE.md`, `03-ATS/*.md`, `04-ACCOUNT-LEDGER.md` | 02 is the person's answers (never opened by this session); 01 and the 03 per-ATS notes carry personal rulings, tenant accounts and dated incidents interleaved with mechanics, so 01 was rewritten as `docs/01` and 03 reduced to the quick reference; 04 is tenant account state |
| ops `Runs/`, `AppApply-Capture/`, `Resume/`, `scratch/`, `Archive/`, `SESSION_LOG.md`, `PLAN-MAIL-TRACKER.md`, `AUDIT-*.md`, the `.gsheet` pointers | run history, captured application data, real PDFs, Queue exports, the audit and planning notes: personal by nature |
| the real PII pattern file, the Google token, `config.toml`, `.env`, `secrets/` | credentials and personal values; `.gitignore` blocks them by name |
| `find-a-job-ai/daily_job_search.py` (vendored copy) | no upstream licence; fetched by `discover/vendor/find_a_job_ai/fetch.sh` |
| `ohmycv-base.css` (the editor's stylesheet) | GPL-3.0 / AGPL-3.0 upstream, incompatible with shipping inside an MIT kit; fetched by `resume/css/fetch_base_css.sh` |
| `jobspy-mcp-server` | an upstream MCP server with local patches, unrelated to the phases; its one JobSpy version is pinned in `discover/requirements.txt` instead |
| the Winnie governance files in the tools and portal trees | host-specific, full of addresses, paths and names |
| ops `tools/tile-lanes.sh`, `launch-browser1.sh`, `publish-live.sh`, `timeline-refresh.sh`, `run_active.sh`, `post-commit.hook` | retired or Drive/launchd-specific; the backup script covers the live need |
| the `Winnie-Macky-Notes` exchange files | correspondence |

## Stage-2 changes (folded in on branch `stage2-sync`; see `CHANGELOG.md` 0.2)

| File | Source | Change |
|---|---|---|
| `ops/tools/jobkey.py`, `test_jobkey.py` | ops `tools/jobkey.py`, `test_jobkey.py` | data root and run regex from `common`; the test builds its own `jt-keys.csv` fixture (fictional company names) and compares with `discover/src/jobhunt_tools/keys.py` instead of the host's copy; incident dates and the person's name removed |
| `ops/tools/raw_append.py`, `test_raw_append.py` | ops | `common` for the data root and run regex; "tell the operator"; the duplicate case described generically |
| `ops/tools/queue_api.py` (Raw helpers) | ops `queue_api.py` `RAW_HEADER`, `values_get`, `raw_append_rows`, `raw_format_dates` | copied as is |
| `ops/tools/common.py` | kit | `company_key` and `job_tools_key` now delegate to `jobkey` so there is one rule |
| `ops/tools/dispatch.py` (`proof_gate`, `outcome_gate`, `--proof`) | ops | dates and the person's name removed from the messages |
| `ops/tools/test_dispatch.py` | ops (stage-2 version) | fictional first name, `answers §` sources, `user_submit`, the operator |
| `ops/tools/token_audit.py` (`--write-usage`) | ops | session-name hour in the configured zone (`common.local_tz`); "dashboard" for "portal"; the one-run comparison check (`--check-0929`) not carried |
| `ops/tools/test_token_audit.py` | ops | project folder name and zone from config/env, not the host's |
| `ops/tools/usage_report.py` | removed | replaced by `token_audit.py --write-usage` (same 16 columns) |
| `ops/tools/jd_archive_api.py` (`name_problem`, `fix-names`), `test_jd_archive_names.py`, `test_jd_archive_fixnames.py` | ops | incident counts and dates removed; "tell the operator" |
| `docs/roles/ROLE-{scrape,prep,orch,lane,discover}.md` | ops `ROLE-*.md` cards 1.0/1.1 | the person → the operator (they/them); `02` → the answers file; the browser deviceId and profile → config `[browser]`; host paths → the kit's folders (`discover/`, the ops folder); résumé file names → "the file the answers file names"; the side-business exception generalised; dated pilots and worker timings generalised; `tile-lanes.sh` → "a window-tiling script"; model names → "the lane model" / "a mid-tier model"; `03-ATS/<ats>.md` noted as the reader's own per-ATS notes; 07 Block 1 JD section → 06 Steps C–D; card dates dropped |
| `CHANGELOG.md` | new (the ops repo keeps its own, which quotes dated incidents) | the kit's version history, out of the read path |
| `docs/00`, `05`, `08`, `09`, `10`, `11`, `README.md`, `ops/tools/README.md`, `.github/workflows/ci.yml`, `config.example.toml` | kit | routing through the cards, `raw_append.py` in 05 D / 10 step 7, proof mandatory in 08 §1.1 and 09 §5, `--write-usage` and `tokens_per_submit` in 09 §8, one key in 11, new tests in CI, `[capture] proof_format` |

Already here before this sync: `pii_scan --attempt` with `JT-` ids; `mail_track` reading `outcomes-jt.csv`; ops
`.gitignore scratch/` (`ops/scratch/` is ignored here).
