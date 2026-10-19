# ROLE — Phase 0 discover (operating card)

Card 1.1. **No personal data.** For `phase 0` or `discover`. The operator is present for the review. Read **this
card**; open `10-discover.md` for the review-file format and the apply-link agent's method list, and
`discover/README.md` only if a search tool misbehaves. You don't need 01, the answers file, 04, 07–09. If this card and 10
disagree, 10 wins: follow it and note the mismatch in LEARNINGS.

## 1. What discover does, and what it never does

It runs the job search tools (find-a-job-ai / JobSpy), dedupes and pre-screens the results, lets the operator mark each job
**Apply** or **Skip**, finds the **real apply link** for every Apply, and appends those jobs to Raw so `phase 2` can
prep them.

**Never:** open an application form, sign in, create an account, submit, or save, follow or apply on the operator's LinkedIn
account. Search is guest-only. **Nothing is written to the Job Queue or Raw** until the operator marks a job Apply **and** its
apply link is found. Check the last `SESSION_LOG.md` entry first: only one applying session at a time.

Run ID `R<YYYYMMDD>-<HHMM>-discover` from `date`, on line 1. Model: a mid-tier model (the operator's standing choice). Machine: the apply host. Browser for the
pre-screen and link steps: the "App Apply" profile (the deviceId in config `[browser]`, signed in to LinkedIn).

## 2. Steps (10 "Steps")

1. **Start checks, read-only:** `tools/backup.sh --status`; `python3 tools/queue_api.py check` (stop if it
   fails); "App Apply" connected.
2. **Search**, one profile at a time, never in parallel. From `discover/`:
   `python scripts/run_search.py <profile> --hours-old 72` (a second profile only if the operator asks). LinkedIn answers HTTP 429 on bursts: wait, report the gap,
   never retry in a loop.
3. **Key and dedupe.** Key each job with
   `python3 tools/jobkey.py key "<company>" "<title>" "<location>" "<url>"`:
   - **a job with a LinkedIn job number is keyed by that number**, even when the tools found it;
   - only a job with no LinkedIn number gets `JT-<10 hex>` (SHA-1 of normalized `company|title|location`).
   Drop a job whose key is already in the Queue (read-only), company + title repeats of submitted cards, and a job
   whose company + normalized title + city (or requisition or apply URL) matches an existing Queue or Raw row, numeric
   or `JT-` (a job the tools found that the scrape later saved).
4. **Pre-screen the A and B grades.** The grader runs high and misreads seniority lines. Open each posting in
   "App Apply" (`get_page_text` with `max_chars`) and note fit, location, pay and "Responses managed off LinkedIn".
   Mark each `keep` or `drop` with a one-line reason.
5. **Review file:** `Runs/<date>/DISCOVER-<RunID>.md` in 10's format (an `id` of `<LinkedIn number or JT- key>`).
   Show the keep list in chat. The operator ticks **Apply** or **Skip** in the file or says it in chat. Neither ticked =
   undecided, not processed; both ticked = ask. Drops go under "## Dropped (not proposed)" with their reason.
6. **Find the apply link** for every Apply (§3). Skips are logged and never proposed again.
7. **Append:** for each job with a found link, a 27-column Raw row (05 Step C header) with `Real Apply URL`,
   `Apply Domain`, `ATS Guess` and `Location` filled, `Aggregator` = `jobtools:linkedin` or `jobtools:indeed`, Apply?
   blank (= Yes), into `Runs/<date>/discover-<RunID>.csv` (Python `csv`). Then
   `python3 tools/raw_append.py --run <RunID> --csv Runs/<date>/discover-<RunID>.csv` (dry run, every gate) and the
   same with `--apply` (RAW-mode append, read-back, Queue lookups checked, `jt-keys.csv` rows added with their
   location). A gate failure writes nothing; READ-BACK FAILED → stop and tell the operator. A job with no found link is
   **not** appended; it stays in the file as `no apply link` for the operator.
8. **Next command:** `phase 2` for the appended rows.

## 3. The apply-link agent (10 "Apply-link agent")

One subagent per Apply job, **serially or at most 3 at once** (one browser). Each stops at the first method that
verifies:
1. **The tool's direct link** (`job_url_direct`, Indeed): open it and verify.
2. **LinkedIn click-through:** open the LinkedIn job page in "App Apply", click **Apply** ("Apply on company
   website"); read the new tab's URL from the tab list, close that tab, and stop: type nothing, upload nothing, go no
   further than the landing page. An Easy Apply button → record `easy apply`, `Real Apply URL` blank.
3. **Web search** on company + title (+ requisition, location): the fallback and a cross-check. Accept only an
   employer or known-ATS domain whose title, requisition and location match; never an aggregator.
4. **Verify** the URL is a live posting with an apply path for that role (not a careers home or a search page).
   Record `Real Apply URL`, `Apply Domain`, `ATS Guess` (against `03-ATS/`), and `found`; else `no apply link` and why.
The agent never signs in, creates an account or submits. It reports one line per job.

## 4. Keys

- One key per job: the LinkedIn number when there is one, else `JT-` from `tools/jobkey.py`. The key goes in Raw
  column B; there is no new column and no header change.
- Older `JT-` rows that are really LinkedIn jobs keep their keys. `AppApply-Capture/jt-keys.csv`
  (`jt_key,board,board_id,company,title,first_seen_run,location`) holds their number in `board_id`;
  `jobkey.aliases()` and `raw_append.py` treat the two keys as one job.
- The discover package's `keys.py` emits the same `JT-` keys, so a search export goes straight into
  `raw_append.py`.

## 5. Hard rules for discover (00)

No password, account or SSO; never Apply or Submit. Never guess: an unverified link is `no apply link`. Never type into
any Sheet; the only Raw write is `raw_append.py`. Nothing personal in the DISCOVER file beyond job data. The DISCOVER
file is write-once once the run ends (tick boxes live while it's open). Never solve a CAPTCHA. Log every 429 or bot
signal.

## 6. Session end

`RUN-SUMMARY-<RunID>.md` (searched, found, after dedupe, kept, Apply / Skip / undecided, links found, rows appended,
Raw N and Queue Q before and after), `LEARNINGS-<RunID>.md` (doc changes as proposals), a `SESSION_LOG.md` entry,
`git commit`.

## 7. Where to look when…

| Situation | Read |
|---|---|
| Review-file layout | 10 "Review file format" |
| Apply-link methods and the tested examples | 10 "Apply-link agent" |
| A search tool error or a new profile | `discover/README.md` |
| Which ATS a link belongs to | the 03 quick reference |
| A `raw_append.py` or `jobkey.py` question | `python3 tools/raw_append.py -h`; `tools/jobkey.py` header |
| The Raw header and derived-field rules | 05 Step C |
