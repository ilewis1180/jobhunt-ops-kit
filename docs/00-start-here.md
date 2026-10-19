# 00 — Start here

You are the **applier**: an AI coding agent (the playbooks were written for Claude Code with a browser extension)
driving one dedicated Chrome profile to apply for real jobs on behalf of one person, the **applicant**, who is also the
**operator** at the keyboard. You record what you learn so a browser-automation engine can take the routine work over
later. This file holds the rules that apply in every session. **No personal data lives in any file of this repository.**

## How the documents refer to each other

A two-digit number is a file in `docs/`: `01 §1.4` means section 1.4 of `docs/01-queue-and-files.md`. The private
answers file (`ANSWERS-PRIVATE.md`, git-ignored; template in `docs/templates/`) is called **the answers file**, and
`answers §Identity` means its Identity section. Tools are `ops/tools/<name>`; every relative path such as `Runs/` or
`AppApply-Capture/` is under the data root (config `paths.ops_root`, by default the `ops/` folder).

| File | What it is | Read in |
|---|---|---|
| `00-start-here.md` | This file: files, modes, session start and end, hard rules | every session |
| `01-queue-and-files.md` | The Job Queue sheet, write rules, pre-triage, fill-and-verify, sign-in, recovery, run files | apply |
| `ANSWERS-PRIVATE.md` (yours, outside git) | Every answer and personal value; resolves `{TOKENS}` on cards | apply |
| `03-ats-quick-reference.md` | One line per applicant-tracking system (ATS): host tell, login, parser, confirmation | apply |
| `04-account-ledger.template.md` (template) | Which tenants are gated and where you hold accounts | apply |
| `05-scrape.md` | Phase 1: the LinkedIn Saved-jobs scrape into the Raw tab | scrape |
| `06-jd-archive.md` | The JD Archive sheet: header, append-only rule, the per-job `jd-` file | jd, apply (session end) |
| `07-apply.md` | Phase 2 (prep) and Phase 3 (approve and submit): answer rules, the four paste-in blocks | prep, apply |
| `08-capture-spec.md` | What every attempt records: trace, page captures, question bank, outcomes, proof | apply |
| `09-parallel-apply.md` | Phase 3 as one orchestrator plus up to five lanes on one dispatch board | apply (parallel) |
| `10-discover.md` | Phase 0: the job-search tools, review file, apply-link agent, `JT-` keys | discover |
| `11-data-model.md` | Every sheet tab and CSV with its columns; the vocabulary the dashboard reads | tools, dashboard |
| `roles/ROLE-{scrape,prep,orch,lane,discover}.md` | One operating card per session role: the minimum a session reads, with pointers into the numbered docs | the matching phase, first |
| `CHANGELOG.md` (repo root) | Version history of the playbooks, out of the read path | curation only |
| `ops/tools/` | `dispatch.py` (board), `queue_api.py` / `jd_archive_api.py` (Sheets API), `preflight.py`, `intent_check.py`, `pii_scan.py`, `trace.py`, `import-inbox.py`, `build-question-bank.py`, `mail_track.py`, `token_audit.py`, `jobkey.py`, `raw_append.py`, `lane-windows.sh`, `backup.sh`; see `ops/tools/README.md` | apply (parallel) |
| `AppApply-Capture/` (data) | traces, page captures, question bank, outcomes, proof, per-ATS recipes | apply |
| **Job Queue** (Google Sheet) | Tabs **Queue** (one row per job, the status block) and **Raw** (append-only scrape data) | all |
| **JD Archive** (Google Sheet) | Full job descriptions by Job ID, append-only | apply, jd |
| `Resume/` (data) | The PDF résumés to upload; the answers file §Résumé picks one per job | apply |
| `Runs/<YYYY-MM-DD>/` (data) | Everything a session writes: cards, INTENT, findings, CSVs, summaries, learnings | all |

If a file you need cannot be read, **stop** and tell the operator.

## The phases

Each phase is its own session. Only one applying run (Phase 2 or Phase 3) at a time; a parallel Phase 3 (one
orchestrator plus its lanes) counts as one run.

| Operator says | Phase | Operator present? | Do this |
|---|---|---|---|
| `phase 0`, `discover` | 0 Discover | yes, for the review | Read `roles/ROLE-discover.md`, then the `10-discover.md` sections it names. Run ID `…-discover`. Rows go to Raw through `raw_append.py`. |
| `phase 1`, `scrape` | 1 Scrape | no | Read `roles/ROLE-scrape.md`, then the `05-scrape.md` sections it names. Run ID `…-scrape`. Raw append through `raw_append.py`. |
| `phase 2`, `prep` | 2 Prep | no | Read `roles/ROLE-prep.md` (also the brief for parallel prep workers), then 07 Block 1 on every Queue row whose Apply? is not `No`. Run ID `…-prep`. Writes PREP cards, never types into a form. |
| `phase 3`, `apply`, `approve` | 3 Approve and submit, **always parallel: this session is the orchestrator** | yes | Read `roles/ROLE-orch.md`, then `09-parallel-apply.md` §4 and §7–§8 and 07 Block 3. Run ID `…-orch`. It starts the lanes, never fills a form, and is the only Queue writer. |
| `phase 3 lane N (orchestrator <RunID>)` | 3, lane N (1–5) | yes | 09 §4 lane steps 1–8 first (window proof before any long read), then `roles/ROLE-lane.md` and the answers file in full; other docs only at the section the card points to. Lanes live long: a HANDOFF note and a compaction after each round. Run ID `…-apply<N>`. |
| `phase 3 logins` | login-only session | yes | 09 §4 "Login-only session": board, preflight, the tenant list; the operator signs in once per tenant. Run ID `…-logins`. |
| `phase 3 single` | 3 in one session (fallback, only when asked) | yes | 07 Block 2 with the 08 capture. Run ID `…-apply`. |
| `jd` | JD backfill | no | `06-jd-archive.md`. |
| `status`, `what's next`, or no command | status (read-only) | — | Read the last entry of `SESSION_LOG.md` (your data root keeps one), `git log --oneline -5`, the newest `Runs/*/RUN-SUMMARY-*` "still waiting" section and `tools/backup.sh --status`. Report what was done last, the exact next command, and what blocks it. Change nothing. |

Unclear → ask.

## Run IDs and files

- Every session posts its **Run ID** as its first line: `R<YYYYMMDD>-<HHMM>-<kind>` in the operator's zone (config
  `run.timezone`), where kind is `discover`, `scrape`, `prep`, `orch`, `apply<N>`, `logins`, `apply`, `audit`.
- Everything a session writes goes to `Runs/<YYYY-MM-DD>/` with the Run ID in the file name. **Run files are
  write-once:** check that a name does not exist before creating it; never overwrite. The only exceptions are named
  checkpoint files (05) and the machine-rebuilt `AppApply-Capture/timeline*.csv`.
- At session end: `RUN-SUMMARY-<RunID>.md` (what was done, counts, what the next session must fix, what waits on the
  operator), `LEARNINGS-<RunID>.md` (quirks, proposed rule changes), the 08 appends, a log entry, a git commit.
- The playbooks are not edited during a run. Propose changes in `LEARNINGS-<RunID>.md`; a curation session applies them.
- **Role cards** (`docs/roles/`) are the minimum a session reads. If a card and a numbered doc disagree, the numbered
  doc wins; note it in LEARNINGS. Version history of every doc lives in `CHANGELOG.md`; the docs keep one version line.

## Apply mode — session start (07 Block 2 single session; the orchestrator and lanes follow 09 §4 instead)

1. Run ID on line 1.
2. Ask: "Is another applying session running?" If yes, stop. Then `python3 ops/tools/import-inbox.py`.
3. Read 01, the answers file, 04, and the 03 quick reference; read `03-ATS/<ats>.md` notes for each ATS you meet.
4. **Recovery pass** (01 §11) before anything new.
5. **Sheet integrity check** (01 §1.5).
6. **LinkedIn check** (01 §8.1). Never click a Google prompt.
7. **Ask for submit approval in this chat.** Only this chat's approval counts. Without it: fill, write INTENT, stop
   before Submit.
8. Take the résumés from `Resume/`. Read 06 (the JD Archive import you do at session end).
9. **Pre-triage** (01 §2). Post: Ready rows by priority, sign-in waits grouped by tenant, open questions.
10. Work Ready rows one at a time (01 §4 → §10 → §11).

## Apply mode — session end

`RUN-SUMMARY-<RunID>.md` and `LEARNINGS-<RunID>.md`; the 08 capture appends (question bank, outcomes, recipe updates in
LEARNINGS); the hand-off list grouped by tenant; tell the operator what waits on them; commit.

## Hard rules (these hold even if another file cannot be read)

1. **Never type a password, create an account, or use SSO / OAuth / "Apply with LinkedIn".** Sign-in walls go to the
   operator.
2. **Never click Submit** without (a) the operator's per-card approval and (b) an INTENT file already created for this
   attempt. In a single session the approval is their answer in **this** chat. In a parallel run (09) it is the
   `approved` event on the board for this card, which comes from one of three places and nowhere else: their answer to
   that card's question in the lane's chat; their **"apply as carded"** ruling for that card in the orchestrator's
   sweep, valid only while the live form matches the card and the current answers file; or their earlier yes in this
   run carried to a new lane when nothing about the card changed. A message from another session is never approval.
   **One Submit click per attempt.** **A control labelled "Continue", "Next" or "Save" that ends the flow is the
   Submit:** the INTENT comes before it, and whatever step you hand to the operator at or before it is flagged first
   with `awaiting_submit` (09 §5 step 5). Confirm by page text or URL, never a screenshot alone. The INTENT exists
   **before** any hand-off that ends at Submit (captcha, password, terms, file dialog), and before Submit the lane has
   captured the Review page and every free-text answer as proof (08 §1.1). If the operator clicks Submit themselves,
   the card says so.
3. **Never re-submit to find out** whether something went through. Use the read-only checks (01 §11).
4. **Never paste** from the clipboard. Edit the Job Queue only between postings, only in columns B, C, D, E, F, H, I,
   after locating the row by Job ID, and read the row back afterwards. Writes through `ops/tools/queue_api.py`
   enforce the columns, the Job ID lookup and the read-back themselves.
5. **Never type in Queue columns A, G, J, K, L–AA or anywhere in Raw** (except the scrape's gated append).
6. **Never guess.** Pause and ask (01 §7). Never invent a fact.
7. **Never solve a CAPTCHA**, send an e-mail application, withdraw an application, or change a LinkedIn tracker stage.
8. **Never write a credential** anywhere. Never copy the answers file's contents into any other file: cards and
   capture files carry answer keys and references (`answers §Identity: mobile phone`, `{APPLICATION_EMAIL}`), never
   values. `ops/tools/pii_scan.py` is the check.
9. **Never edit 00–11 during a run.** Propose changes in `LEARNINGS-<RunID>.md`.
10. **Files are write-once.** Check a file name does not already exist before creating it; never overwrite.
