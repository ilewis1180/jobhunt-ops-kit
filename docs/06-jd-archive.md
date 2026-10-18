# 06 — The JD Archive

A second Google Sheet holding the full job description of every job, by Job ID, **append-only**. Prep and apply
sessions capture the JD when they open the posting; the `jd` command backfills jobs that were never opened.

## The `jd-` file

`Runs/<date>/jd-<JobID>-<RunID>.md`, write-once:

```
# JD — <Company> — <Role> — <JobID>
Source URL: <origin + path> · Captured: <YYYY-MM-DD HH:MM> · Complete: Yes | No (<reason>) · Characters: <n>

<the job description text, as rendered, no markup>
```

A JD that will not render is **not** a reason to pause: mark it `Complete: No (<reason>)` and move on. Never open
aggregator redirect links to fetch a JD.

## Step C — the CSV

At session end, combine the session's new `jd-` files into `Runs/<date>/jd-<RunID>.csv`. Line 1 is exactly this
header, every row has 10 fields, RFC 4180 quoting, UTF-8:

```
LinkedIn Job ID,Company,Job Title,Source,Complete?,Captured Date,Source URL,Characters,Notes,Full Job Description
```

A cell is limited to 50,000 characters (Sheets); split a longer JD across two rows with `Notes` saying `part 1 of 2`.

## Step D — the append

```bash
python3 ops/tools/jd_archive_api.py check
python3 ops/tools/jd_archive_api.py append --run-id <RunID> Runs/<date>/jd-<RunID>.csv          # dry run
python3 ops/tools/jd_archive_api.py append --run-id <RunID> Runs/<date>/jd-<RunID>.csv --apply
```

The tool checks the sheet's header and the CSV's header, appends below the last row, reads every appended cell back,
and logs to `Runs/<date>/jd-archive-writes-<RunID>.jsonl`. It never edits or deletes a row. The same Job ID may appear
on several rows (a later capture); the latest `Complete? = Yes` wins. A read-back failure is a stop.

## The `jd` command (backfill)

Read 00 and this file only. For each Queue row with no `jd-` file: open the posting read-only, capture, write the
file; then Steps C and D. Run ID `…-jd`.
