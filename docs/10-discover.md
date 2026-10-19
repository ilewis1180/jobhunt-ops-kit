# 10 — Phase 0: Discover (job-search tools)

Command: `phase 0` or `discover`. Run ID `…-discover`. The operator is present for the review.

Purpose: find new jobs with the search tools, rank and pre-screen them, let the operator mark each one Apply or Skip,
find the **real apply link** for every Apply, and hand those jobs to Phase 2. It never opens an application form and
never submits. It writes nothing to the Job Queue until a job is marked Apply and its apply link is found.

## Where it runs

- The search tools are the `discover/` package (python-jobspy under the hood) with one profile per role family
  (`discover/config/profiles/*.json`, examples provided). A separate, signed-in browser profile may be used for the
  pre-screen and the apply-link step; guest searches need no login.
- Later (optional): a scheduler on another host runs the same searches daily and posts cards to a chat channel; the
  Mac does the pre-screen, the link finding and the Phase 2 hand-off (`discover/README.md`).

## Steps

1. **Start checks (read-only).** `backup.sh --status`; `queue_api.py check`; the browser profile connected. Stop if the
   Queue check fails.
2. **Search.** `python3 discover/scripts/run_search.py <profile> --hours-old 72` (one profile at a time, never in
   parallel). LinkedIn answers HTTP 429 on bursts: wait, report the gap, never retry in a loop. Output:
   `discover/state/staging/discover-candidates-<timestamp>.csv`.
3. **Dedupe.** Drop any job whose LinkedIn Job ID is already in the Queue (read-only), company + title repeats of
   submitted cards, and any job whose company + normalised title + city (or requisition or apply URL) matches an
   existing Queue or Raw row, `JT-` or numbered (05 Step A flags the other direction).
4. **Pre-screen the A and B grades.** The grader runs high and misreads seniority lines. Open each posting
   (read-only) and note fit, location, pay and "responses managed off LinkedIn". Mark each `keep` or `drop` with a
   one-line reason.
5. **Review file.** Write `Runs/<date>/DISCOVER-<RunID>.md` (format below) and show the keep list in chat. The operator
   ticks **Apply** or **Skip** in the file or says it in chat. Neither ticked = undecided, not processed. Both = ask.
6. **Find the apply link** for every Apply (agent step below). Skips are logged and never proposed again.
7. **Hand off to Phase 2.** For each job with a found link, build a Raw-format row (the 27 columns of 05 Step C, with
   `Real Apply URL`, `Apply Domain`, `ATS Guess` and `Location` filled; `Aggregator` = `jobtools:<board>`; `Apply?`
   blank = Yes) into `Runs/<date>/discover-<RunID>.csv`, then `python3 ops/tools/raw_append.py --run <RunID> --csv
   <that file>` (dry run) and again with `--apply` (05 Step D). A job with no found link is **not** appended; it
   stays in the file as `no apply link`.
8. **Next command:** `phase 2` for the appended rows.

## Review file format

```
# DISCOVER <RunID> — <date>
Searched: <profiles>, hours-old <n>. Found <n>, after dedupe <n>, kept <n>.

## Review (tick one box per job)
- [ ] Apply   [ ] Skip   **<Company> — <Title>** · grade <A/B> · <board> · <location> · id <job id or JT- key>
  Verdict: keep — <reason>. Pay: <…>. Link: <job page URL>
  Apply link: <filled by the link agent>   Status: <found / easy apply / no apply link>

## Dropped (not proposed)
- <Company> — <Title> · <reason>
```

## Apply-link agent (step 6)

One subagent per Apply job, serially or at most 3 at once (one browser). Methods, stop at the first that verifies:
1. **Direct link from the tool** (`job_url_direct`, Indeed): open and verify.
2. **LinkedIn click-through:** open the LinkedIn job page in the signed-in profile and click **Apply** ("Apply on
   company website"). The employer page opens in a new tab: read that tab's URL, close it, stop. Type nothing, upload
   nothing. An Easy Apply button → record `easy apply`, leave the Real Apply URL blank. (Reading the button's `href`
   with page script is blocked by the browser tool on query-string data, so click through instead.)
3. **Web search on company + title (+ requisition, location)** as the fallback and cross-check. Accept only an
   employer or known-ATS domain whose title, requisition and location match; never an aggregator.
4. **Verify** the URL is a live posting with an apply path for that role (not a careers home or a search page). Record
   `Real Apply URL`, `Apply Domain`, `ATS Guess` (03) and `found`; otherwise `no apply link` and why.
Never sign in, create an account or submit. One-line result per job.

## Rules

- Guest search only; the applicant's own LinkedIn session is not used for bulk scraping, and nothing is saved,
  followed or applied on their account.
- 00 hard rules apply. Nothing personal in the DISCOVER file beyond job data. The file is write-once once the run ends.
- **Job-tools key:** every job the tools find gets its own key in the existing Job ID column of Raw:
  `JT-<10 hex>` = the first 10 hex of SHA-1 of normalised `company|title|location` (lowercase, punctuation stripped,
  whitespace collapsed; `ops/tools/jobkey.py jt_key`). `Aggregator` = `jobtools:<board>`; the board's own job
  id or URL goes in `LinkedIn Job URL` / `Flags`. `raw_append.py` keeps `AppApply-Capture/jt-keys.csv`
  (`jt_key,board,board_id,company,title,first_seen_run,location`) to catch the same job found twice, and refuses a
  LinkedIn number already in Raw under a `JT-` alias, so one job never gets two rows.
  **A job that carries a LinkedIn number keeps that number as its key** (`python3 ops/tools/jobkey.py key "<company>"
  "<title>" "<location>" [<url>]`); only a job with no number gets a `JT-` key.
- **Test before the first append:** confirm the Queue lookup formulas accept a `JT-` id by appending one approved
  row through the gates and reading Queue back; stop if any lookup column is blank.
- Commit at session end.
