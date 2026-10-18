# 01 — The Job Queue, the files, and how to work

The rules every applying session follows. Section numbers are referenced from the other playbooks and from the tools
(`01 §1.4`, `01 §11`), so they are stable.

## §1 The Job Queue sheet

### §1.1 Columns

One Google Sheet, two tabs. **Raw** is append-only scrape data (27 columns, 05 Step C header; several rows per job over
time, the newest wins). **Queue** has one row per job; column A is a `UNIQUE()` of Raw's Job IDs, L–AA are lookups
into Raw, and B–K is the status block.

| Col | Header | Written by |
|---|---|---|
| A | Job ID | formula (never typed) |
| B | Status | applier (and the operator) |
| C | Last touched | applier (a date; the one `USER_ENTERED` cell) |
| D | ATS | applier |
| E | Tenant key | applier |
| F | Open questions (agent) | applier: the question a `Paused-Question` row waits on |
| G | Applicant's answers | **operator only** |
| H | Findings file | applier: the PREP card, findings or decisions file name |
| I | Chat approval record | applier: time, the exact reply, the chat's run id |
| J | Apply? | **operator only**; blank counts as Yes, `No` means never send |
| K | Priority | **operator only**; blank = 3 |
| L–AA | Company, Job Title, Location, Work Mode, Easy Apply, LinkedIn Job URL, Real Apply URL, Apply Domain, ATS Guess, Company Careers URL, Salary Raw, Posting Type, Posted Date, Flags, Tracker Stage, Snapshot Date | formulas (never typed) |

Never sort the Queue: tools locate rows by Job ID, never by position.

### §1.2 Job IDs

A Job ID is the LinkedIn posting number (8 or more digits) or, for a job the search tools found with no LinkedIn
number, `JT-<10 hex>` (10 §Rules). A Job ID is never anything else: never a timestamp, never a company name.

### §1.3 Statuses (column B)

`New` (blank) · `Ready` · `In progress` · `Submitted` · `Submitted-unconfirmed` · `Skipped` · `Closed` ·
`Paused-SignIn` · `Paused-Question` (the question is in F; the operator answers in G) · `Paused-Technical` ·
`Paused-CAPTCHA` · `Paused-Verify` (an INTENT exists with no findings; read-only checks only, never re-submit).
A Paused-Verify, -Technical or -CAPTCHA row moves only when the operator writes in G.

### §1.4 Writing the Queue

- Only B, C, D, E, F, H, I. Locate the row by Job ID. One-line values. Write between postings, never while a form is
  open in the same browser profile. Read the row back after every write and compare.
- `ops/tools/queue_api.py write --run-id <RunID> <JobID> <col> <value> ... --apply` does all of that: it refuses other
  columns and other spreadsheets, writes B/D/E/F/H/I `RAW` (text is never a formula), reads every cell and its
  neighbours back, and logs to `Runs/<date>/queue-writes-<RunID>.jsonl`. A read-back failure is a stop.
- In a parallel run only the orchestrator writes the Queue (`dispatch.py queue-plan --queue api --apply`).
- A `Submitted` row is never changed back by a tool; a hand correction is kept.

### §1.5 Sheet integrity check (every session start)

No Job ID twice in Queue column A; Raw's header row `A1:AA1` unchanged; Raw's last row and the Queue's non-blank Job ID
count match what the last `RUN-SUMMARY` recorded (05 Step D). Any mismatch: stop, change nothing, tell the operator
(Sheets version history restores).

## §2 Pre-triage (before any card is worked)

For every Ready row, read-only:
1. Duplicate: same company + title (+ city) as another row, or the same apply URL → keep one, flag the other.
2. Already applied: a `submitted-` findings file or an outcomes row exists → do not work it.
3. Closed: the posting says no longer accepting, 404, 410 → `Closed`.
4. Aggregator or staffing repost with no employer → ask.
5. Fit flag: the posting requires a license, clearance, degree or named product the résumé does not show → a fit
   question for the operator (`Paused-Question`, question in F), never a silent skip.
6. Login wall at the posting → `Paused-SignIn`, add the tenant to the login list.
7. Never open the apply flow to triage; read the posting page only.

## §3 Reading the answers file

Every answer comes from, in order: the answers file → the résumé that job gets → earlier findings files in `Runs/`
→ the applicant's public profile. 07 "Shared answer rules" says how to pick when sources disagree. Cards and capture
files reference the answers file by section and key (`answers §Identity: mobile phone`), never by value.

## §4 Fill and verify (one card)

1. **Inventory the form before writing anything** (one read per page): every field, exact label, control type,
   required or not, options. On a tenant with a public API (Greenhouse, Lever, Ashby) take the question list from
   the API instead of rendering the page.
2. Compare the inventory to the card and to the current answers file. Anything the card did not predict is a
   `REVIEW:` flag before any typing.
3. Capture the JD if the card has none (06, `jd-<JobID>-<RunID>.md`).
4. Fill one page at a time. After the first keystroke on a new host, read the value back before typing more (the
   first input is often swallowed). Verify every field after filling: read the value, not the keystrokes.
5. After a résumé upload, autofill or saved-profile restore, re-read the work history and the personal fields
   against the résumé and the answers file (07 "Live form and parser checks").
6. Uploads: the exact file the card names, from `Resume/`.
7. **Sweep before Next or Submit:** required fields with no value = 0, invalid fields = 0, mismatches = 0.
8. **Pre-submit gate:** the sweep is clean; every required field is `verified` in the INTENT ledger and every optional
   field is `verified` or `optional-left-blank` (`ops/tools/intent_check.py <draft>` must say `coverage OK`); the
   Review page and every free-text answer are captured as proof (08 §1.1); the operator's approval for this card is
   recorded. Then the INTENT file, then one Submit click as its own tool call, then confirmation by page text or URL.

## §5 The INTENT file

`INTENT-<JobID>-a<N>-<RunID>.md`, written **before** Submit, write-once:

```
# INTENT — <Company> — <Role> — <JobID>-a<N>
Card: <PREP file> · Decisions: <PREP-DECISIONS file or none> · Approval: <time> "<exact reply>"
## Inventory
| ID | Page | Label (verbatim) | Control | Required | Options / conditional on |
| P1.F01 | 1 | Email | email | yes | |
## Ledger
| ID | Answer used | Source | Verified how | State |
| P1.F01 | {identity.email} | answers §Identity | re-read after blur | verified |
## Consents ticked (exact wording)
## Work history on Review/last page: verified
## Coverage
Required in inventory: N · verified required in ledger: N · optional left blank: N
```

One row per field ID (no ranges). Values are answer keys or references, never personal values (00 rule 8).

## §6 The findings file

`<outcome>-<ats>-<company-slug>-<JobID>-a<N>-<RunID>.md` where outcome is `submitted`, `unconfirmed`, `paused`,
`skipped`, `closed` or `recovered`. Sections: `## Outcome` (what happened, in one or two lines), `## Confirmation
method` (redirect, modal, in-flow text, job-page status; quote the page text), `## Fields` (the inventory with
answers used, by key), `## Best-effort answers`, `## Quirks` (for 03), `## Proof` (the 08 §1.1 file names). The
findings file is what `dispatch.py event` reads to build the outcomes row.

## §7 Pause, don't guess

A fact that is in no source, a "willing to" outside the answers file, a required numeric pay field with no figure, a
demographic question with no decline option → ask the operator (single session: in this chat; lane: `needs_user`).
Never invent. Never pick "the most likely" option on a legal statement.

## §8 Sign-in

- §8.1 **LinkedIn check** at session start: open the jobs tracker; a login wall, checkpoint or Google prompt is a stop
  (the operator signs in; never click a Google prompt).
- §8.2 Never create an account, never type a password, never use SSO. The operator signs in, in the browser window
  the session uses, and says `done`.
- §8.3 A sign-in in one window does not follow into another lane's window on many tenants: each lane confirms the
  account menu in its own window.
- §8.4 **Verify** a sign-in by the tenant's account menu on one posting, then record the tenant in 04.

## §9 Tenant locks

Account-based tenants (Workday, SuccessFactors, ADP, UltiPro, Oracle) keep one draft per account. Only one lane works
such a tenant at a time; `dispatch.py` takes a tenant lock per employer group.

## §10 Files and run ids

- §10.1 Run ID `R<YYYYMMDD>-<HHMM>-<kind>` in the configured zone.
- §10.2 One day folder `Runs/<YYYY-MM-DD>/`.
- §10.3 Names carry the Job ID, the attempt (`-a<N>`) and the Run ID: `PREP-<Company>-<JobID>-<RunID>.md`,
  `INTENT-<JobID>-a<N>-<RunID>.md`, `jd-<JobID>-<RunID>.md`, `preflight-<RunID>.csv`.
- §10.4 **Collision guard:** check the name does not exist, then create. Never overwrite. If it exists, use a new
  attempt number or a new Run ID.
- §10.5 Names must survive a trip to Windows: no `:` `"` `*` `?` `<` `>` `|`, no trailing dot or space (08 §4.1).

## §11 Recovery pass (session start, and for orphaned claims)

For every row `In progress`, every `Paused-Verify`, and every attempt with an INTENT but no findings file:
1. **Read-only checks first:** the tenant's candidate home or "my applications", the confirmation mail, the job page
   status. Never click Submit to find out.
2. Was submitted → write a `recovered-` findings file; the Queue row becomes `Submitted`.
3. Was not submitted (no application in the candidate view, form never reached Submit) → note what you checked, and
   the row goes back to `Ready` (`dispatch.py reopen <JobID> --note "not sent: <what you checked>"`).
4. Cannot tell → `Paused-Verify`, with what you checked in F. Never re-submit.

## §12 Pacing

One posting at a time per window. On LinkedIn: at most one scrape per 6 hours; Easy Apply submissions capped per run
(`dispatch.py init --ea-cap`, default 15); never a burst of tabs. On any host: one request per second for the
read-only preflight; the applier never fetches from a page to localhost.

## §13 The PREP card

The card format is in 07 Block 1. A card references answers by key, lists best-effort answers separately, carries the
drafted free text word for word with a `Sources:` line per claim, lists the consents it will tick with their exact
wording, and lists the open questions under `## Needs you`.
