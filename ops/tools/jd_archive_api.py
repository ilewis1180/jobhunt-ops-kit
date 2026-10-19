#!/usr/bin/env python3
"""JD Archive through the Google Sheets API: **append only**, then read every appended cell back (06 Step D without the
Sheets UI). The same safeguards as queue_api.py, whose token handling it reuses.

  python3 tools/jd_archive_api.py check                              read-only: title, tab, header, last row
  python3 tools/jd_archive_api.py append --run-id <RunID> <jd-*.csv> [--apply]
                                                                     dry run unless --apply
  python3 tools/jd_archive_api.py fix-names --run-id <RunID> --csv <corrections.csv> [--apply]
                                                                     one-time in-place fix of Company (B) and Job Title (C)
                                                                     on the rows a corrections CSV lists; dry run unless --apply

What it will and won't do:
- It touches one spreadsheet, the JD Archive (config [sheets] jd_archive_id, checked against `JD Archive.gsheet` when
  that pointer file exists), and one tab, the first one.
- It never deletes a row. `append` only appends the CSV's data rows (not its header) below the last row.
- `fix-names` is the one exception to append-only: it writes **only columns B and C** of the rows a corrections CSV
  names (`sheet_row, job_id, batch, problem, company_now, title_now, company_fix, title_fix`). Before writing it checks
  that each row's Job ID (A) and current B/C still equal the CSV's `job_id`, `company_now`, `title_now` (so nothing
  moved) and that the fix values pass `name_problem`. After writing it reads the whole tab back: header, row count,
  every other cell of the fixed rows and every other row unchanged. Before/after values go to the same jsonl log.
- Before an append: the sheet's row 1 must equal the 06 header exactly; every CSV row must have 10 fields; the CSV's
  header must equal it too; and every row passes the Company/Title self-check (`name_problem`, compared with the
  Queue's L/M for the same Job ID), so a builder that mangles names is stopped before the append.
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


def name_problem(job_id, company, title, queue_company='', queue_title=''):
    """Why a row's Company/Title look mangled, or '' Catches three CSV-builder bugs seen in practice:
    the attempt id in Title, "Company, Title-part" split at a hyphen, and the company cut at its first comma so Title
    starts "Inc., ...". Queue values, when given, are
    the Queue's L (Company) and M (Job Title) for the same Job ID."""
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
    import jobkey
    N = jobkey.normalize
    if re.fullmatch(r'(?:\d{8,}|JT-[0-9a-f]{10})-a\d+', title.strip()):
        return 'Title holds the attempt id'
    if re.match(r'(?i)(?:inc|llc|ltd|corp|co|lp|plc)\b\.?,', title.strip()):
        return 'Title starts with the end of the company name'
    if queue_company:
        co, qco, qti = N(company), N(queue_company), N(queue_title)
        if co.startswith(qco) and len(co) > len(qco) and qti:
            rest = co[len(qco):].strip()
            if rest and (qti.startswith(rest) or rest.startswith(qti)):
                return 'Company holds the start of the job title'
        if qco.startswith(co) and len(qco) > len(co) and co:
            rest = qco[len(co):].strip()
            if rest and N(title).startswith(rest):
                return 'Title starts with the end of the company name'
        t = N(title)
        if t and qti and t != qti and qti.endswith(t) and not co == qco:
            return 'Title holds only the end of the job title'
        if not N(title) and qti:
            return 'Title is empty'
    return ''


FIX_COLS = ['sheet_row', 'job_id', 'batch', 'problem', 'company_now', 'title_now', 'company_fix', 'title_fix']


def plan_fixes(sheet, corrections):
    """[(row, job_id, company_now, title_now, company_fix, title_fix)] or a list of refusals (strings). Pure: no I/O.
    `sheet` is read_all()'s list (row 1 = header); `corrections` is a list of dicts with FIX_COLS."""
    plan, problems, seen = [], [], set()
    for c in corrections:
        try:
            n = int(c['sheet_row'])
        except (KeyError, ValueError):
            problems.append(f'bad sheet_row {c.get("sheet_row")!r}')
            continue
        if n < 2 or n > len(sheet):
            problems.append(f'row {n}: outside the sheet (last row {len(sheet)})')
            continue
        if n in seen:
            problems.append(f'row {n}: listed twice')
            continue
        seen.add(n)
        r = sheet[n - 1]
        if r[0] != c['job_id']:
            problems.append(f'row {n}: Job ID is {r[0]!r}, the CSV says {c["job_id"]!r} — rows moved, stop')
            continue
        if r[1] != c['company_now'] or r[2] != c['title_now']:
            problems.append(f'row {n} ({r[0]}): B/C are {r[1]!r}/{r[2]!r}, the CSV expected '
                            f'{c["company_now"]!r}/{c["title_now"]!r} — already changed, stop')
            continue
        if not c['company_fix'].strip() or not c['title_fix'].strip():
            problems.append(f'row {n} ({r[0]}): empty fix value')
            continue
        why = name_problem(r[0], c['company_fix'], c['title_fix'])
        if why:
            problems.append(f'row {n} ({r[0]}): the fix still fails the self-check: {why}')
            continue
        if (c['company_fix'], c['title_fix']) == (r[1], r[2]):
            problems.append(f'row {n} ({r[0]}): fix equals the current values, nothing to do')
            continue
        plan.append((n, r[0], r[1], r[2], c['company_fix'], c['title_fix']))
    return plan, problems


def fix_names(a, tname, sheet):
    run_id = a[a.index('--run-id') + 1] if '--run-id' in a else ''
    m = re.match(r'R(\d{4})(\d{2})(\d{2})-\d{4}-[a-z]+\d?$', run_id) or qa.die('--run-id must be a Run ID')
    path = a[a.index('--csv') + 1] if '--csv' in a and a.index('--csv') + 1 < len(a) else qa.die('give --csv <corrections.csv>')
    with open(path, encoding='utf-8-sig', newline='') as fh:
        rd = csv.DictReader(fh)
        if rd.fieldnames != FIX_COLS:
            qa.die(f'{os.path.basename(path)}: header must be {",".join(FIX_COLS)}')
        corrections = list(rd)
    if not sheet or sheet[0] != HEADER:
        qa.die('JD Archive row 1 is not the JD Archive header (07 Block 1) — stop (sheet integrity) and tell the operator')
    plan, problems = plan_fixes(sheet, corrections)
    if problems:
        qa.die('fix-names refused, nothing written:\n' + '\n'.join('  ' + p for p in problems[:30]))
    for n, job, b0, c0, b1, c1 in plan:
        print(f'  row {n} · {job} · B "{b0[:40]}" → "{b1[:40]}" · C "{c0[:40]}" → "{c1[:40]}"')
    if '--apply' not in a:
        print(f'DRY RUN: {len(plan)} row(s), columns B and C only. Re-run with --apply to write.')
        return
    data = [{'range': f"'{tname}'!B{n}:C{n}", 'values': [[b1, c1]]} for n, job, b0, c0, b1, c1 in plan]
    qa._call('POST', f'{base()}/values:batchUpdate', {'valueInputOption': 'RAW', 'data': data})
    after = read_all(tname)
    fixed = {n: (b1, c1) for n, job, b0, c0, b1, c1 in plan}
    problems = []
    if not after or after[0] != HEADER:
        problems.append('row 1 changed')
    if len(after) != len(sheet):
        problems.append(f'sheet has {len(after)} rows, expected {len(sheet)}')
    for i in range(1, min(len(after), len(sheet))):
        n = i + 1
        want = list(sheet[i])
        if n in fixed:
            want[1], want[2] = fixed[n]
        if after[i] != want:
            problems.append(f'row {n}: ' + ('read-back of the fix differs' if n in fixed else 'changed without being written'))
    log = os.path.join(REPO, 'Runs', f'{m.group(1)}-{m.group(2)}-{m.group(3)}', f'jd-archive-writes-{run_id}.jsonl')
    os.makedirs(os.path.dirname(log), exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    with open(log, 'a', encoding='utf-8') as fh:
        for n, job, b0, c0, b1, c1 in plan:
            fh.write(json.dumps({'ts': ts, 'run': run_id, 'sheet': sheet_id(), 'row': n, 'job': job, 'op': 'fix-names',
                                 'before': [b0, c0], 'after': [b1, c1], 'csv': os.path.basename(path),
                                 'ok': not problems}, ensure_ascii=False) + '\n')
    if problems:
        print('READ-BACK FAILED — stop and tell the operator (Sheets version history can restore):')
        for p in problems[:30]:
            print('  ' + p)
        sys.exit(1)
    print(f'fixed and read back: {len(plan)} row(s), columns B and C only; every other cell unchanged · '
          f'log {os.path.relpath(log, REPO)}')


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
    if a[0] == 'fix-names':
        fix_names(a, tname, sheet)
        return
    if a[0] != 'append' or '--run-id' not in a:
        qa.die('usage: append --run-id <RunID> <jd-*.csv> [--apply]  |  fix-names --run-id <RunID> --csv <file> [--apply]')
    run_id = a[a.index('--run-id') + 1]
    m = common.run_match(run_id) or qa.die('--run-id must be a Run ID')
    path = next((x for x in a[1:] if x.endswith('.csv')), None) or qa.die('give the jd-*.csv to append')
    rows = load_csv(path)
    if not sheet or sheet[0] != HEADER:
        qa.die('JD Archive row 1 is not the 06 header — stop (sheet integrity) and tell the operator')
    n = len(sheet)
    queue = qa.read_queue()   # read-only: L/M for the Company/Title self-check
    bad = [(r[0], why) for r in rows for why in [name_problem(r[0], r[1], r[2], queue.get(r[0], {}).get('L', ''),
                                                             queue.get(r[0], {}).get('M', ''))] if why]
    if bad:
        qa.die('Company/Title self-check failed — fix the CSV builder, nothing appended:\n' +
               '\n'.join(f'  {j}: {why}' for j, why in bad[:20]))
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
