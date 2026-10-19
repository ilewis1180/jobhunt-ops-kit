# 05 — Phase 1: the LinkedIn Saved-jobs scrape

Runs unattended in its own session. It reads the applicant's LinkedIn **Saved** tracker, writes one CSV row per new job
in the 27-column Raw format, and appends those rows to the **Raw** tab through the gated append. It never changes
anything on LinkedIn and never writes the Queue tab.

## When and how

- Run ID `R<YYYYMMDD>-<HHMM>-scrape` on line 1. One scraping session at a time.
- At most **one scrape per 6 hours**. A LinkedIn login wall, checkpoint or Google prompt is a stop (01 §8.1).
- **Read:** 00, this file, and the Queue tab columns A (Job ID), B (Status), P (Easy Apply), R (Real Apply URL),
  Y (Flags); plus every `JT-` row's company, title and city from Raw.
- **Write:** only `Runs/<date>/scrape-<RunID>.csv`, `cardstatus-<RunID>.csv`, `RUN-SUMMARY-<RunID>.md`,
  `LEARNINGS-<RunID>.md`, the Raw append, and these working files in the same day folder:
  - `scrape-<RunID>-CHECKPOINT.csv`: the scrape CSV so far, same header and rules, overwritten every ~10 rows. The
    only file here that may be overwritten.
  - `ids-<RunID>.csv`: the Pass 1 card list.
  - Any helper script or data file the run builds. Save them to the day folder, so a resumed run can use them.

## Step A — KNOWN_IDS and REOPEN_IDS (before opening LinkedIn)

- **KNOWN_IDS** = every Job ID in Queue column A.
- **JT- rows:** load company, title and city of every `JT-` row from Raw. A new LinkedIn row whose company + title +
  city matches one is flagged `duplicate of JT-<10 hex>`; Phase 2 then preps one of the pair (10 step 3 does the same
  check from the other side).
- **REOPEN_IDS** = known IDs that need a fresh full row: column Y contains `apply link missing`, **or** P = `No` with
  R blank, **and** B is blank, `Ready` or `Paused-Question`. Other statuses are never reopened. JD flags are not a
  reason to reopen.
- Post both counts.

## Step B — two passes

The Saved list reshuffles, drops and reposts jobs while you work, so never do detail work while paging.

**Pass 1 — card walk (IDs only, minutes).** Walk every tracker page. On each page read every card without clicking:
Job ID (from the title link's `href`), title, company, location text, status text, posting type, and whether the
button says Apply or Easy Apply. Write `ids-<RunID>.csv` as soon as the walk ends. Dedupe by Job ID: a repeated ID
means a missed page click, not a new job.

**Diff.** New IDs → Pass 2. REOPEN_IDS → Pass 2 whether or not they appeared in Pass 1. Every other known ID → the
card-status file only (Job ID, Status Raw, Posting Type, Easy Apply, Snapshot Date). **Never put a partial row in the
scrape CSV:** the Queue's lookups would blank that job's fields. Post the three counts.

**Pass 2 — detail rows, by URL.** For each Pass 2 ID open `https://www.linkedin.com/jobs/view/<id>/` directly in a new
tab and record the fields below. Never go back to the tracker to find a job. Card-only fields (Status Raw, Posting
Type) come from the Pass 1 list; for a REOPEN ID not seen in Pass 1 take them from the detail page's own posted line,
else leave blank and flag `card not seen`. Checkpoint every ~10 rows. Close each tab when done.

- **Resuming:** rebuild `have_ids` = KNOWN_IDS ∪ every ID in the checkpoint CSV and run Pass 2 for the rest.
- **Early stop (only if the operator says so):** end Pass 1 after a full page whose cards are all known and not in
  REOPEN_IDS (the tracker is most-recently-saved first).
- Closing a job is not the scrape's decision: a card reading "No longer accepting applications" goes into the
  card-status file; pre-triage decides (01 §2).
- **The JD is not the scrape's job.** If the "About the job" text is already on the page, you may copy it; otherwise
  leave the cell blank. Never wait, reload, click "See more" or flag a missing JD.
- **Tracker layout variants:** the list view sometimes snaps back to page 1. Reload the tracker once; if it still will
  not move, stop Pass 1, flag the run `pass 1 incomplete (list view pagination)`, and do Pass 2 for what you have.

### Per-job fields (Pass 2)

a. **LinkedIn Job ID:** the number in the URL. b. **LinkedIn Job URL:** `https://www.linkedin.com/jobs/view/<id>/`.
c. **Apply button:** read the "Apply on company website" link's `href` (never click it). It is a `safety/go` redirect:
   take its `url=` value, percent-decode, strip tracking parameters, keep job-identifying ones. **Real Apply URL** = the
   cleaned URL, **Apply Domain** = its host, Easy Apply = No. No decodable non-LinkedIn URL → flag `apply link missing`.
d. **Easy Apply button:** Easy Apply = Yes; Real Apply URL, Apply Domain, ATS Guess blank. A linked careers site goes
   in Company Careers URL.
e. "No longer accepting applications": still record the row, Posting Type = Closed.
f. **Company LinkedIn URL:** cut to `https://www.linkedin.com/company/<slug>/` (drop `/life/` and query strings).
g. **Location:** every listed location joined with ` | `. h. **Work Mode** exactly as labelled. i. **Employment Type**,
   **Seniority Level** from the criteria block. j. **Salary Raw** exactly as displayed, never an estimate.
k. **Applicant Count** as displayed. l. **Hiring Team** name, title and profile URL (href, query string removed, never
   opened; first person only). m. **Job Description** optional (above). n. Close the tab.

### Derived fields

- **Tracker Stage** from the URL. **Status Raw** word for word. **Posting Type:** Posted, Reposted or Closed.
- **Posted Date** = Snapshot Date minus the age in the status text (minutes/hours = same day; Nd, Nw = 7N, Nmo = 30N,
  Ny = 365N). Blank for Closed rows with no age.
- **Tracking parameters to strip:** `utm_*`, `gh_src`, `trk*`, `refId`, `trackingId`, `ref`, `src`, `source`,
  `lever-source`, `_atxs`, `ccd`, `v`, `r`, and bare fragments. **Keep** `gh_jid`, `jobId`, `req`, `id`, `jid`. After
  stripping, **no apply URL may contain "linkedin"**.
- **ATS Guess** from Apply Domain: greenhouse.io or `grnh.se` or a `gh_jid` parameter = Greenhouse; lever.co = Lever;
  ashbyhq.com = Ashby; myworkdayjobs.com = Workday; icims.com = iCIMS; taleo.net = Taleo; successfactors or sapsf =
  SuccessFactors; paylocity = Paylocity; adp = ADP; eightfold.ai = Eightfold; avature = Avature; jobvite = Jobvite;
  bamboohr = BambooHR; smartrecruiters.com = SmartRecruiters; oraclecloud.com = Oracle HCM; ultipro.com or ukg = UKG;
  hireology = Hireology; paycor = Paycor; rippling = Rippling; comeet = Comeet; zoho or zurl.to = Zoho Recruit;
  workable = Workable; jazzhr or applytojob = JazzHR; dayforce = Dayforce. Otherwise Other. Blank when Real Apply URL
  is blank.
- **Aggregator = Yes** if the company or the apply domain is a job aggregator or ad redirect (lensa, jobot, jooble,
  talent.com, ziprecruiter, dice, jobright, hiring cafe, jobgether, adzuna, appcast, joveo, jobs2careers, talentify,
  recruitics, ...) or the company is `(Company not listed)`.
- **Required on every row:** Job ID, Job URL, Title, Company, Location, Easy Apply, Snapshot Date, and (unless flagged
  `card not seen`) Status Raw and Posting Type. The build script fails the row, not the file, and lists what is missing.

### Flags — fixed codes only, in this order, `; `-separated

`company not listed` · `apply link missing` · `company mismatch` · `title mismatch` · `location mismatch` ·
`work mode mismatch` · `staffing firm` · `duplicate of <id>` · `card not seen` · `page verify retried`. Anything else
goes in LEARNINGS, not in the row.

## Step C — the files

`Runs/<date>/scrape-<RunID>.csv`: line 1 is exactly the header below, one row per new or REOPEN job, 27 fields, RFC
4180, UTF-8. `Runs/<date>/cardstatus-<RunID>.csv`: header
`LinkedIn Job ID,Status Raw,Posting Type,Easy Apply,Snapshot Date`.

```
Tracker Stage,LinkedIn Job ID,LinkedIn Job URL,Job Title,Company,Company LinkedIn URL,Aggregator,Location,Work Mode,Employment Type,Seniority Level,Status Raw,Posting Type,Posted Date,Easy Apply,Real Apply URL,Apply Domain,ATS Guess,Company Careers URL,Salary Raw,Applicant Count,Hiring Team Name,Hiring Team Title,Hiring Team URL,Job Description,Snapshot Date,Flags
```

## Step D — append to Raw, with the gates

The append goes through **`python3 ops/tools/raw_append.py`**, never by hand:

1. Dry run: `python3 ops/tools/raw_append.py --run <RunID> --csv Runs/<date>/scrape-<RunID>.csv`. Its gates: line 1
   equals the Raw header byte for byte, and so does live `Raw!A1:AA1`; every row has 27 fields; every Job ID is a
   LinkedIn number or `JT-<10 hex>`; Snapshot Date is a real date; the key rule (a row whose LinkedIn URL carries a
   job number uses that number; a `JT-` id equals `jt_key(Company, Title, Location)`); no Job ID twice in the file,
   none already in Raw, no LinkedIn number already in Raw under a `JT-` alias (`jt-keys.csv`). It prints **N**
   (Raw's last row) and **Q** (non-blank Job IDs in Queue A). Company + title + location repeats are warnings.
2. The same command with `--expect-n <N> --expect-q <Q> --apply`: one append in `RAW` input mode (no cell is ever
   read as a formula; numeric ids and dates typed so the Queue's lookups keep matching), then the read-back: header
   unchanged, range starts at N+1, Raw ends at N + rows, Queue count = Q + rows, each appended Job ID and Snapshot
   Date read back, every new Job ID in Queue A with Company filled. Log: `Runs/<date>/raw-appends-<RunID>.jsonl`.
   Job-tools rows are added to `AppApply-Capture/jt-keys.csv` with their location.
3. A gate failure writes nothing. **READ-BACK FAILED → stop, edit nothing further, tell the operator** (the sheet's
   version history can restore). Record N, rows and Q in the RUN-SUMMARY for the next session's integrity check.

## Step E — report

`RUN-SUMMARY-<RunID>.md`: pages visited, new rows, REOPEN rows, card-status rows, known jobs now closed, every flagged
row, Raw N → new last row, Queue Q → new count, what went wrong. `LEARNINGS-<RunID>.md`: new quirks, new ATS or
aggregator domains, per-job observations that fit no flag code.

## Gotchas

1. Pagination clicks fail silently; the highlighted page number is the only check. 2. The page bar is a sliding
window; Previous and Next reach pages outside it. 3. Two pages with the same jobs = a missed click; do not record the
repeat. 4. Never click Apply to get the URL (it can mark the job applied and trip bot detection); read the `href`.
5. The redirect URL is percent-encoded; decode `url=`. 6. Easy Apply jobs have no external URL. 7. Applicant counts
change daily; pair them with Snapshot Date. 8. Close each tab after extracting. 9. Some cards have no company name:
`(Company not listed)` plus the flag. 10. **The header is a contract**: a renamed column fails or silently blanks the
import. 11. Descriptions contain commas, quotes and line breaks: RFC 4180 quoting. 12. "Posted 3h ago" is relative to
Snapshot Date, not the import day. 13. Company cells can include a tagline after `|`; record as displayed. 14. A
LinkedIn URL in Real Apply URL is not an apply target. 15. Tracking parameters break URL dedupe. 16. Never click
"See more". 17. A tool result cut at ~1,000 characters: keep results in `window.*` and read them back in slices.
18. A tool result `[BLOCKED: query string data]`: encode `?`, `&`, `=` before returning them.

## Recipes (read-only page script for the tracker; test before relying on them)

- **Read one tracker page:** every card is an `a[href*="/jobs/view/<id>"]` holding two `<p>` (company · location;
  status); the Apply / Easy Apply button is a second link to the same ID; the highlighted page is
  `button[aria-label^="Page"][aria-current="true"]`. Store the parsed cards per page on `window.__store`.
- **Walk every page:** click only Next; after each click wait until both the highlighted page number and the first
  job ID changed (stop with `STUCK` after 10 s). Total cards must equal unique IDs must equal the Saved count.
- **Read results out in slices** of ~45 cards, encoded compactly (`page|id|P3d|A`), because tool output is cut.
- **Read a job detail page:** company link (cut to the slug), `safety/go` hrefs with `?` `&` `=` spelled out as
  placeholders so the tool does not block them, the apply button labels, the hiring-team block, the header lines
  (title, company, location · age · applicants, tags), and the "About the job" text up to the "more" marker.
- **One field for many jobs without opening tabs:** `fetch()` each job page from a linkedin.com tab, one at a time,
  1.5 s apart, stopping on a login or checkpoint redirect or an "unusual activity" page.
