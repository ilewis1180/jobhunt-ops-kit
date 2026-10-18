#!/usr/bin/env python3
"""Job Queue through the Google Sheets API: read the Queue tab, and write ONLY columns B, C, D, E, F, H, I, found by
Job ID, with an automatic read-back. It replaces typing into the Sheets UI (01 §1.4) and the Drive xlsx export.

Credential: a Google OAuth authorized-user token (client_id, client_secret, refresh_token; drive scope), as a read-only
copy at config paths.google_token (default ~/.config/jobhunt/google_token.json, override JOBHUNT_GOOGLE_TOKEN). This
tool refreshes the access token in memory only and never writes the file, never prints it, and never copies it. The
token must stay outside the repo (00 hard rule 8).

  python3 tools/queue_api.py check                       read-only: token, sheet title, Queue size
  python3 tools/queue_api.py read [--csv <out>]          the Queue tab (A–AA) as CSV
  python3 tools/queue_api.py write --run-id <RunID> <JobID> <col> <value> [<JobID> <col> <value> ...] [--apply]
                                                         dry run unless --apply; every write is read back and logged
                                                         to Runs/<date>/queue-writes-<RunID>.jsonl
Sheets API only, Job Queue only: the one spreadsheet ID comes from config.toml [sheets] job_queue_id, and any other
is refused. The token is refreshed with the drive scope alone, so the access token in use carries no Gmail, Calendar,
Contacts or Tasks access (a token granted only `drive` works; `spreadsheets` would be narrower if your token has it).
dispatch.py uses this for `--queue api` and `queue-plan --apply`.
"""
import datetime, json, os, re, stat, sys, time, urllib.error, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from common import die, col_letter  # noqa: E402,F401

REPO = common.REPO
TOKEN_FILE = common.google_token_path()
WRITABLE = set('BCDEFHI')          # 01 §1.1: the applier's columns. Never A, G, J, K, L–AA.
RAW_COLS = set('BDEFHI')           # stored literally, so text like "=…" or "+…" is never read as a formula
TAB = common.queue_tab()
JOB_QUEUE_ID = common.sheet_id('job_queue')   # config [sheets] job_queue_id; the only sheet this tool may touch
SCOPE = 'https://www.googleapis.com/auth/drive'
# A Job ID is a LinkedIn number or a job-tools key (10-DISCOVER.md): JT- plus 10 hex.
JOB_ID_RE = common.JOB_ID_RE
_access = {}


def sheet_id():
    if not JOB_QUEUE_ID:
        die('no Job Queue spreadsheet id: set [sheets] job_queue_id in config.toml (see config.example.toml)')
    try:
        pointer = json.load(open(os.path.join(REPO, 'Job Queue.gsheet')))['doc_id']
    except FileNotFoundError:
        return JOB_QUEUE_ID
    if pointer != JOB_QUEUE_ID:
        die('Job Queue.gsheet points at a different spreadsheet than config allows — stop and tell the operator')
    return JOB_QUEUE_ID


def _token():
    """A drive-scope access token, refreshed in memory on first use (the stored all-scope token is never used).
    The token file is only ever read."""
    if _access.get('exp', 0) > time.time() + 120:
        return _access['token']
    if not os.path.exists(TOKEN_FILE):
        die(f'no token at {TOKEN_FILE} — place a read-only copy of the Google token there (chmod 600)')
    if os.stat(TOKEN_FILE).st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        print(f'WARNING: {TOKEN_FILE} is readable by others; run: chmod 600 {TOKEN_FILE}', file=sys.stderr)
    if os.path.realpath(TOKEN_FILE).startswith(os.path.realpath(REPO) + os.sep):
        die('the token file is inside the ops repo — move it out (00 hard rule 8)')
    d = json.load(open(TOKEN_FILE))
    body = urllib.parse.urlencode({'client_id': d['client_id'], 'client_secret': d['client_secret'],
                                   'refresh_token': d['refresh_token'], 'grant_type': 'refresh_token',
                                   'scope': SCOPE}).encode()
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(
            d.get('token_uri') or 'https://oauth2.googleapis.com/token', data=body), timeout=30))
    except urllib.error.HTTPError as e:
        die(f'token refresh failed ({e.code}): {json.loads(e.read() or b"{}").get("error", "?")} — '
            'the token copy may be stale or revoked; re-authorize and re-copy it')
    if set(r.get('scope', SCOPE).split()) != {SCOPE}:
        die(f'refreshed token has scopes {r.get("scope")!r}, expected drive only — not using it')
    _access.update(token=r['access_token'], exp=time.time() + int(r.get('expires_in', 3000)))
    return _access['token']


def _call(method, url, body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': 'Bearer ' + _token(), 'Content-Type': 'application/json'})
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        err = json.loads(e.read() or b'{}').get('error', {})
        die(f'Sheets API {e.code} {err.get("status", "")}: {err.get("message", "")[:300]}')


def _base(sid):
    if sid != JOB_QUEUE_ID:
        die(f'spreadsheet {sid} refused: this tool only touches the Job Queue')
    return f'https://sheets.googleapis.com/v4/spreadsheets/{sid}'


def read_rows(sid=None, last_col='AA', render='UNFORMATTED_VALUE'):
    """{row number: {'A': str, 'B': str, …}} for the Queue tab, header row included."""
    sid = sid or sheet_id()
    q = urllib.parse.urlencode({'valueRenderOption': render, 'dateTimeRenderOption': 'FORMATTED_STRING'})
    rng = urllib.parse.quote(f'{TAB}!A1:{last_col}')
    vals = _call('GET', f'{_base(sid)}/values/{rng}?{q}').get('values', [])
    rows = {}
    for n, r in enumerate(vals, 1):
        rows[n] = {col_letter(i): ('' if v is None else str(int(v)) if isinstance(v, float) and v.is_integer() else str(v))
                   for i, v in enumerate(r)}
    return rows


def read_queue(sid=None):
    """Job ID -> {'row': n, 'A'..: value}: the same shape dispatch.read_queue returns for an export."""
    out = {}
    for n, r in read_rows(sid).items():
        a = r.get('A', '').strip()
        if n > 1 and re.fullmatch(JOB_ID_RE, a):
            if a in out:
                die(f'Job ID {a} appears twice in column A (rows {out[a]["row"]} and {n}) — stop, sheet integrity (01 §1.5)')
            out[a] = dict(r, row=n)
    return out


def write_cells(cells, run_id, apply=False, sid=None):
    """cells: [(job_id, col, value)]. Locates rows by Job ID, writes, reads back, checks neighbours. Returns ok."""
    sid = sid or sheet_id()
    m = common.run_match(run_id) or die('--run-id must be a Run ID')
    for job, col, val in cells:
        if col not in WRITABLE:
            die(f'column {col} is not writable (only {"".join(sorted(WRITABLE))}; 01 §1.1)')
        if '\n' in val:
            die(f'{job} {col}: one-line values only (01 §1.4)')
    before = read_rows(sid, 'K')
    rowmap = {}
    for n, r in before.items():
        jid = r.get('A', '').strip()
        if n > 1 and jid:
            if jid in rowmap:
                die(f'Job ID {jid} appears in rows {rowmap[jid]} and {n} — fix the sheet before writing (01 §1.5)')
            rowmap[jid] = n
    plan = []
    for job, col, val in cells:
        n = rowmap.get(job) or die(f'Job ID {job} not found in column A')
        plan.append((n, job, col, val, before[n].get(col, '')))
    for n, job, col, val, cur in plan:
        print(f'  row {n} · {job} · {col}: "{cur[:60]}" → "{val}"')
    if not apply:
        print(f'DRY RUN: {len(plan)} cell(s). Re-run with --apply to write.')
        return True
    for opt, cols in (('RAW', RAW_COLS), ('USER_ENTERED', {'C'})):
        data = [{'range': f'{TAB}!{col}{n}', 'values': [[val]]} for n, job, col, val, cur in plan if col in cols]
        if data:
            _call('POST', f'{_base(sid)}/values:batchUpdate', {'valueInputOption': opt, 'data': data})
    after = read_rows(sid, 'K')
    shown = read_rows(sid, 'K', render='FORMATTED_VALUE')
    targets = {(n, col) for n, job, col, val, cur in plan}
    problems = []
    for n, job, col, val, cur in plan:
        if after.get(n, {}).get('A', '').strip() != job:
            problems.append(f'row {n}: column A no longer {job} — rows shifted')
        got = after.get(n, {}).get(col, '') if col != 'C' else shown.get(n, {}).get(col, '')
        if col == 'C' and not got:
            problems.append(f'row {n} C: empty after write')
        elif col != 'C' and got != val:
            problems.append(f'row {n} {col}: read back "{got[:60]}", expected "{val[:60]}"')
    for n in sorted({p[0] for p in plan} | {p[0] - 1 for p in plan} | {p[0] + 1 for p in plan}):
        for col in 'ABCDEFGHIJK':
            if (n, col) not in targets and before.get(n, {}).get(col, '') != after.get(n, {}).get(col, ''):
                problems.append(f'row {n} {col}: changed without being written ("{before.get(n, {}).get(col, "")[:40]}" → '
                                f'"{after.get(n, {}).get(col, "")[:40]}")')
    log = os.path.join(REPO, 'Runs', f'{m.group(1)}-{m.group(2)}-{m.group(3)}', f'queue-writes-{run_id}.jsonl')
    os.makedirs(os.path.dirname(log), exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    with open(log, 'a', encoding='utf-8') as fh:
        for n, job, col, val, cur in plan:
            fh.write(json.dumps({'ts': ts, 'run': run_id, 'sheet': sid, 'row': n, 'job': job, 'col': col,
                                 'before': cur, 'after': val, 'ok': not problems}, ensure_ascii=False) + '\n')
    if problems:
        print('READ-BACK FAILED — stop and tell the operator (Sheets version history can restore):')
        for p in problems:
            print('  ' + p)
        return False
    print(f'written and read back: {len(plan)} cell(s), neighbours unchanged · log {os.path.relpath(log, REPO)}')
    return True


def main():
    a = sys.argv[1:]
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    sid = None
    if not a:
        print(__doc__)
        return
    if a[0] == 'check':
        meta = _call('GET', f'{_base(sid or sheet_id())}?fields=properties.title,sheets.properties.title')
        q = read_queue(sid)
        print(f'OK · "{meta["properties"]["title"]}" · tabs: {", ".join(s["properties"]["title"] for s in meta["sheets"])} · '
              f'Queue: {len(q)} Job IDs (last row {max((r["row"] for r in q.values()), default=0)})')
    elif a[0] == 'read':
        import csv
        rows = read_rows(sid)
        out = open(opt('--csv'), 'w', newline='', encoding='utf-8') if opt('--csv') else sys.stdout
        w = csv.writer(out)
        for n in range(1, max(rows) + 1):
            r = rows.get(n, {})
            w.writerow([r.get(col_letter(i), '') for i in range(27)])
    elif a[0] == 'write':
        rest = [x for i, x in enumerate(a[1:], 1) if x not in ('--apply', '--run-id') and a[i - 1] != '--run-id']
        if len(rest) % 3:
            die('write takes <JobID> <col> <value> triples')
        cells = [(rest[i], rest[i + 1].upper(), rest[i + 2]) for i in range(0, len(rest), 3)]
        sys.exit(0 if write_cells(cells, opt('--run-id'), '--apply' in a, sid) else 1)
    else:
        die(f'unknown command {a[0]}')


if __name__ == '__main__':
    main()
