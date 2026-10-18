#!/usr/bin/env python3
"""JD Archive through the Google Sheets API: **append only**, then read every appended cell back (06 Step D without the
Sheets UI). The same safeguards as queue_api.py, whose token handling it reuses.

  python3 tools/jd_archive_api.py check                              read-only: title, tab, header, last row
  python3 tools/jd_archive_api.py append --run-id <RunID> <jd-*.csv> [--apply]
                                                                     dry run unless --apply

What it will and won't do:
- It touches one spreadsheet, the JD Archive (config [sheets] jd_archive_id, checked against `JD Archive.gsheet` when
  that pointer file exists), and one tab, the first one.
- It never edits or deletes a row. It only appends the CSV's data rows (not its header) below the last row.
- Before: the sheet's row 1 must equal the 06 header exactly; every CSV row must have 10 fields; the CSV's header must
  equal it too.
- After: row 1 unchanged, the sheet ends at N + rows, every appended cell reads back equal to the CSV (values are sent
  RAW, so text like "=…" is never a formula), and a Job ID + Captured Date already in the sheet is reported (JD Archive
  may hold several rows per job; 06 says the latest `Yes` wins, so this is a note, not a stop).
- Every append is logged to Runs/<date>/jd-archive-writes-<RunID>.jsonl (row numbers and Job IDs, never the text).
- A read-back failure → stop and tell the operator (Sheets version history can restore).
"""
import csv, datetime, json, os, re, sys, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import queue_api as qa  # noqa: E402  (token refresh with the drive scope only, _call, die)

REPO = qa.REPO
JD_ARCHIVE_ID = common.sheet_id('jd_archive')   # config [sheets] jd_archive_id; the only sheet this tool may touch
HEADER = ['LinkedIn Job ID', 'Company', 'Job Title', 'Source', 'Complete?', 'Captured Date', 'Source URL', 'Characters',
          'Notes', 'Full Job Description']
CELL_MAX = 50000   # Sheets' per-cell limit


def sheet_id():
    if not JD_ARCHIVE_ID:
        qa.die('no JD Archive spreadsheet id: set [sheets] jd_archive_id in config.toml (see config.example.toml)')
    try:
        pointer = json.load(open(os.path.join(REPO, 'JD Archive.gsheet')))['doc_id']
    except FileNotFoundError:
        return JD_ARCHIVE_ID
    if pointer != JD_ARCHIVE_ID:
        qa.die('JD Archive.gsheet points at a different spreadsheet than config allows — stop and tell the operator')
    return JD_ARCHIVE_ID


def base():
    return f'https://sheets.googleapis.com/v4/spreadsheets/{sheet_id()}'


def tab():
    meta = qa._call('GET', f'{base()}?fields=properties.title,sheets.properties.title')
    return meta['properties']['title'], meta['sheets'][0]['properties']['title']


def read_all(tab_name):
    rng = urllib.parse.quote(f"'{tab_name}'!A1:J")
    q = urllib.parse.urlencode({'valueRenderOption': 'UNFORMATTED_VALUE'})
    vals = qa._call('GET', f'{base()}/values/{rng}?{q}').get('values', [])
    norm = lambda v: str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)
    return [[norm(v) for v in r] + [''] * (10 - len(r)) for r in vals]


def load_csv(path):
    rows = list(csv.reader(open(path, encoding='utf-8-sig', newline='')))
    if not rows or rows[0] != HEADER:
        qa.die(f'{os.path.basename(path)}: line 1 is not the 06 header exactly')
    bad = [i for i, r in enumerate(rows[1:], 2) if len(r) != 10]
    if bad:
        qa.die(f'{os.path.basename(path)}: lines {bad[:5]} do not have 10 fields')
    big = [r[0] for r in rows[1:] if any(len(c) > CELL_MAX for c in r)]
    if big:
        qa.die(f'Job ID(s) {big} have a cell over {CELL_MAX} characters (Sheets limit) — split per 06 Step C')
    return rows[1:]


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    title, tname = tab()
    sheet = read_all(tname)
    if a[0] == 'check':
        print(f'OK · "{title}" · tab "{tname}" · header {"OK" if sheet and sheet[0] == HEADER else "MISMATCH"} · '
              f'last row {len(sheet)}')
        return
    if a[0] != 'append' or '--run-id' not in a:
        qa.die('usage: append --run-id <RunID> <jd-*.csv> [--apply]')
    run_id = a[a.index('--run-id') + 1]
    m = common.run_match(run_id) or qa.die('--run-id must be a Run ID')
    path = next((x for x in a[1:] if x.endswith('.csv')), None) or qa.die('give the jd-*.csv to append')
    rows = load_csv(path)
    if not sheet or sheet[0] != HEADER:
        qa.die('JD Archive row 1 is not the 06 header — stop (sheet integrity) and tell the operator')
    n = len(sheet)
    seen = {(r[0], r[5]) for r in sheet[1:]}
    for r in rows:
        dup = ' · note: same Job ID + date already in the sheet' if (r[0], r[5]) in seen else ''
        print(f'  + row {n + 1 + rows.index(r)} · {r[0]} · {r[1][:30]} · Complete? {r[4]} · {len(r[9])} chars{dup}')
    if '--apply' not in a:
        print(f'DRY RUN: {len(rows)} row(s) would be appended after row {n}. Re-run with --apply to write.')
        return
    rng = urllib.parse.quote(f"'{tname}'!A{n + 1}")
    q = urllib.parse.urlencode({'valueInputOption': 'RAW', 'insertDataOption': 'INSERT_ROWS'})
    qa._call('POST', f'{base()}/values/{rng}:append?{q}', {'values': rows})
    after = read_all(tname)
    problems = []
    if after[0] != HEADER:
        problems.append('row 1 changed')
    if len(after) != n + len(rows):
        problems.append(f'sheet ends at {len(after)}, expected {n + len(rows)}')
    if after[:n] != sheet:
        problems.append('an existing row changed')
    for i, r in enumerate(rows):
        got = after[n + i] if n + i < len(after) else []
        if got[:10] != r:
            problems.append(f'row {n + 1 + i} ({r[0]}): read-back differs')
    log = os.path.join(REPO, 'Runs', f'{m.group(1)}-{m.group(2)}-{m.group(3)}', f'jd-archive-writes-{run_id}.jsonl')
    os.makedirs(os.path.dirname(log), exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    with open(log, 'a', encoding='utf-8') as fh:
        for i, r in enumerate(rows):
            fh.write(json.dumps({'ts': ts, 'run': run_id, 'sheet': sheet_id(), 'row': n + 1 + i, 'job': r[0],
                                 'complete': r[4], 'csv': os.path.basename(path), 'ok': not problems}) + '\n')
    if problems:
        print('READ-BACK FAILED — stop and tell the operator (Sheets version history can restore):')
        for p in problems:
            print('  ' + p)
        sys.exit(1)
    print(f'appended and read back: {len(rows)} row(s), rows {n + 1}–{n + len(rows)}, existing rows unchanged · '
          f'log {os.path.relpath(log, REPO)}')


if __name__ == '__main__':
    main()
