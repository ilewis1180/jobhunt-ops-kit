# ROLE — Phase 1 scrape (operating card)

Card 1.1. **No personal data.** For `phase 1`, `scrape`, and the first half of `phase 1+2`. Unattended.
Read **this card**, then from `05-scrape.md`: **Step B**, **the prompt block** ("The prompt (v2.1, unchanged)"),
**Gotchas** and **Recipes** (the walk depends on them), and Step C's **Flags** and **Derived fields** tables. You don't
need 01–04, 07–10. If this card and 05 disagree, 05 wins: follow it and note the mismatch in LEARNINGS.

## 1. What the scrape does, and what it never does

It walks the operator's LinkedIn **Saved jobs** tracker, builds one 27-column Raw row per **new** job (and per REOPEN job),
appends them to the Job Queue's **Raw** tab through `tools/raw_append.py`, and records card status for every known
job. The Queue tab then grows new rows by formula.

**Never:** write to the Queue tab, type into any Sheet cell, change anything on LinkedIn (no save, unsave, stage
change, apply, follow), click a Google prompt, or open more than one detail tab at a time. **At most one scrape per
6 hours.** A login wall, checkpoint or "unusual activity" → stop and tell the operator (01 §8.1). Check the last
`SESSION_LOG.md` entry first: only one applying session at a time.

Run ID `R<YYYYMMDD>-<HHMM>-scrape` from `date`, on line 1. Model: a mid-tier model (the operator's standing choice). Browser: the "App Apply" profile
(the deviceId in config `[browser]`, signed in to LinkedIn).

## 2. Steps

**A. Known and reopen lists (before LinkedIn).** Read Queue columns A, B, P, R, Y with
`python3 tools/queue_api.py read --csv <file>`.
- `KNOWN_IDS` = every Job ID in Queue A.
- Load every `JT-` row's company, title and city from Raw. After the scrape, a new LinkedIn row whose company + title
  + city matches a `JT-` row gets the flag `duplicate of JT-<10 hex>`; Phase 2 preps only one of the pair.
  (`raw_append.py` also refuses a LinkedIn number already in Raw under a `JT-` alias from `jt-keys.csv`.)
- `REOPEN_IDS` = known IDs with Y containing `apply link missing`, or P = `No` with R blank, **and** B blank, `Ready` or
  `Paused-Question`. JD flags are never a reason to reopen.
- Post both counts.

**B. Two passes** (05 Step B in full).
- **Pass 1, card walk:** every tracker page, `read_page` only, no clicks into cards, no detail tabs. Record Job ID,
  title, company, location, Status Raw, Posting Type, Easy Apply. Write `ids-<RunID>.csv` when the walk ends. A
  repeated ID is a missed page click, not a new job.
- **Diff:** new IDs and every REOPEN ID → Pass 2; every other known ID → the card-status file only. Post the three
  counts. Never put a partial row in the scrape CSV (it would blank that job's Queue lookups).
- **Pass 2, detail rows by URL:** open `https://www.linkedin.com/jobs/view/<id>/` for each, do prompt STEP 2 (a–n),
  one tab at a time, closed immediately. Write `scrape-<RunID>-CHECKPOINT.csv` every ~10 rows (the only file that may
  be overwritten).
- **Job descriptions are not the scrape's job:** take the text only if it is already on the page; never wait, reload
  or flag a JD. Never click "See more".
- **List-view pagination** that snaps back: reload `…/jobs-tracker/?stage=saved` once; still stuck → flag
  `pass 1 incomplete (list view pagination)` and do Pass 2 for what you have.
- Closing a job is not the scrape's decision: "No longer accepting" goes only to the card-status file.
- **Resuming** in a new session: `have_ids` = KNOWN_IDS ∪ the checkpoint's IDs; Pass 2 only for the rest.

**C. Files** (written with the Write tool; check each name doesn't exist first).
- `Runs/<date>/scrape-<RunID>.csv`: line 1 exactly the 27-column header (05 Step C), one row per new or REOPEN job,
  RFC-4180 quoting (write it with Python `csv`), UTF-8. One file, not split.
- `Runs/<date>/cardstatus-<RunID>.csv`: `LinkedIn Job ID,Status Raw,Posting Type,Easy Apply,Snapshot Date`.
- **Flags:** only the fixed codes of 05 Step C, `; `-separated, in table order. Everything else goes to LEARNINGS.
- **Derived fields:** strip tracking parameters (no apply URL may contain "linkedin"); Aggregator and ATS Guess by
  the 05 maps; Company LinkedIn URL cut to `https://www.linkedin.com/company/<slug>/`; every required field present;
  Snapshot Date is today, never the placeholder.
- Helper scripts and data (`build_csv.py`, `rows.jsonl`) live in the day folder, so a resume can use them.

**D. Append to Raw** (05 Step D).
1. Dry run: `python3 tools/raw_append.py --run <RunID> --csv Runs/<date>/scrape-<RunID>.csv`. It checks the header
   against the file and live Raw, 27 fields, a valid Job ID, a real Snapshot Date, the key rule (the LinkedIn number),
   and duplicates in the file, in Raw and through `jt-keys.csv` aliases; it prints N (Raw's last row) and Q
   (non-blank Job IDs in Queue A).
2. The same command with `--expect-n <N> --expect-q <Q> --apply`: appends in RAW mode, reads back range, N, Q, ids and
   dates, checks the Queue lookups are filled, logs to `Runs/<date>/raw-appends-<RunID>.jsonl`.
3. A gate failure writes nothing. To skip a refused row (for example a LinkedIn job already in Raw under a `JT-`
   alias), remove it from the CSV, run again, and flag it in RUN-SUMMARY. **READ-BACK FAILED → stop and tell the operator**
   (Sheets version history can restore). In `phase 1+2`, don't start Phase 2 after a failed read-back.

**E. Report.**
- `RUN-SUMMARY-<RunID>.md`: pages visited; new, REOPEN and card-status rows; known jobs now "No longer accepting";
  every flagged row (table); Raw N → new last row; Queue Q → new count; anything that went wrong. Counts and
  problems only: a resuming session reads it first.
- `LEARNINGS-<RunID>.md`: new quirks or LinkedIn signals, new ATS or aggregator domains, observations that don't fit
  a flag code, and doc changes as proposals (never edit 00–10 or the cards during a run).
- A `SESSION_LOG.md` entry, `git commit`. Next command for the operator: `phase 2` (or the prep half of `phase 1+2` runs now).

## 3. Hard rules for the scrape (00)

No password, account or SSO. Never guess, never invent a row value. Never type in Queue columns or Raw (the only Raw
write is `raw_append.py`). Never write a credential or any the answers file value. Files are write-once except the checkpoint. Never
solve a CAPTCHA. Pacing (01 §12): one scrape per 6 hours, one detail tab at a time; log every bot signal.

## 4. Browser limits that bite here

- `javascript_tool` output is cut at ~1,000 characters: keep results on `window.*` and read them in slices
  (05 Recipe 3).
- Output containing `?`, `&` or `=` comes back `[BLOCKED…]`: encode before returning (Recipe 4).
- A full page navigation clears page JavaScript: paste the helper again on every job page.
- No `setTimeout` or `await` inside `javascript_tool`; wait with `computer wait`.

## 5. Where to look when…

| Situation | Read |
|---|---|
| The walk, the diff, pagination | 05 Step B; Gotchas 1–5 |
| Detail-row fields a–n | 05 "The prompt" STEP 2 |
| JS helpers for reading cards and links | 05 Recipes |
| A symptom (field count, blank lookups, truncated output) | 05 Troubleshooting |
| A `raw_append.py` refusal | `python3 tools/raw_append.py -h` (gates listed in its header) |
| LinkedIn sign-in or checkpoint | 01 §8.1 |
