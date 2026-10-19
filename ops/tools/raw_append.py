#!/usr/bin/env python3
"""Append a Raw-format CSV to the Job Queue's Raw tab, with the 05 Step D gates built in.

Replaces the per-run Runs/*/raw_append_*.py and discover_append_*.py scripts. Phase 1 (scrape) and Phase 0 (discover)
both write a 27-column CSV with the Raw header and call this tool; it goes through tools/queue_api.py only.

  python3 tools/raw_append.py --run <RunID> --csv <file> [--expect-n N] [--expect-q Q]            dry run: every gate
  python3 tools/raw_append.py --run <RunID> --csv <file> [--expect-n N] [--expect-q Q] --apply    append + read-back

Gates before any write (exit 1 on the first failed gate, nothing written):
  1. CSV line 1 equals the Raw header byte for byte, and so does live Raw!A1:AA1; every row has 27 fields.
  2. Every Job ID (column B) is a Queue Job ID; Snapshot Date (Z) is a real YYYY-MM-DD date.
  3. Key rule (tools/jobkey.py): a row whose LinkedIn Job URL carries a job number must use that
     number; a JT- id must equal jt_key(Company, Title, Location).
  4. No Job ID twice in the file; none already in Raw; no LinkedIn number already in Raw (as an id or in column C);
     none already in Raw under a JT- alias from AppApply-Capture/jt-keys.csv (a job found by the search tools and later by the scrape).
  5. N (Raw's last row) and Q (non-blank Job IDs in Queue A) are read; --expect-n / --expect-q must match if given.
  Company + title + location repeats of existing Raw rows are listed as warnings, not refused (05 flags them).

Write (--apply): one append in valueInputOption=RAW, so no cell is ever read as a formula. Values are typed so the
Queue's UNIQUE and XLOOKUP still match earlier rows: a numeric Job ID goes in as a number, Posted Date (N) and
Snapshot Date (Z) as date serials formatted yyyy-mm-dd; everything else as text.
Read-back (exit 1 + "READ-BACK FAILED — stop and tell the operator" on any mismatch): header unchanged, appended range
starts at N+1, Raw ends at N + rows, Queue count = Q + rows, each appended row's Job ID and Snapshot Date read back,
and every new Job ID is in Queue A with Company (L) filled. Log: Runs/<date>/raw-appends-<RunID>.jsonl. Job-tools rows
(Aggregator jobtools:*, or a JT- id) are added to AppApply-Capture/jt-keys.csv with their location.
Exit: 0 ok · 1 gate or read-back failure · 2 usage.
"""
import csv, datetime, json, os, re, sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import common  # noqa: E402
import jobkey  # noqa: E402
import queue_api as q  # noqa: E402

REPO = common.REPO
RUN_RE = common.RUN_RE
B, C, D, E, G, H, N_COL, Z, AA = 1, 2, 3, 4, 6, 7, 13, 25, 26
DATE_COLS = (N_COL, Z)
EPOCH = datetime.date(1899, 12, 30)


class GateError(Exception):
    pass


def iso_date(s):
    try:
        return datetime.date.fromisoformat(s) if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s or '') else None
    except ValueError:
        return None


def cell_str(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return '' if v is None else str(v)


def typed(row):
    """The row as the API receives it: numeric id -> int, ISO dates in N/Z -> serial, the rest text."""
    out = list(row)
    if re.fullmatch(r'\d{8,}', row[B]):
        out[B] = int(row[B])
    for i in DATE_COLS:
        d = iso_date(row[i])
        if d:
            out[i] = (d - EPOCH).days
    return out


def load_csv(path):
    with open(path, encoding='utf-8', newline='') as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise GateError('CSV is empty')
    return rows[0], rows[1:]


def check_file(header, rows, jt_keys_path):
    """Gates 1-4 that need no Sheet. Returns warnings."""
    if header != q.RAW_HEADER:
        raise GateError('CSV header differs from the Raw header (05 Step D gate 1)')
    if not rows:
        raise GateError('CSV has no data rows')
    seen = set()
    jt2n, n2jt = jobkey.aliases(jt_keys_path)
    for i, r in enumerate(rows, 2):
        if len(r) != len(q.RAW_HEADER):
            raise GateError(f'CSV line {i}: {len(r)} fields, expected {len(q.RAW_HEADER)}')
        jid = r[B].strip()
        if not jobkey.is_job_id(jid):
            raise GateError(f'CSV line {i}: Job ID {jid!r} is neither a LinkedIn number nor JT-<10 hex>')
        if not iso_date(r[Z]):
            raise GateError(f'CSV line {i}: Snapshot Date {r[Z]!r} is not a YYYY-MM-DD date')
        lid = jobkey.linkedin_id(r[C])
        if lid and jid != lid:
            raise GateError(f'CSV line {i}: {jid} but the LinkedIn URL carries job {lid}; a LinkedIn job is keyed by its '
                            'number (tools/jobkey.py)')
        if jid.startswith('JT-') and jid != jobkey.jt_key(r[E], r[D], r[H]):
            raise GateError(f'CSV line {i}: {jid} is not jt_key(Company, Title, Location) = '
                            f'{jobkey.jt_key(r[E], r[D], r[H])}')
        if jid in seen:
            raise GateError(f'CSV line {i}: Job ID {jid} appears twice in the file')
        seen.add(jid)
        if jid in n2jt:
            raise GateError(f'CSV line {i}: LinkedIn job {jid} is already in Raw as {n2jt[jid]} (jt-keys.csv alias)')
        if jid in jt2n:
            raise GateError(f'CSV line {i}: {jid} is LinkedIn job {jt2n[jid]} (jt-keys.csv alias)')
    return []


def sheet_state():
    hdr = q.values_get('Raw!A1:AA1', 'FORMATTED_VALUE')
    raw = q.values_get('Raw!A2:AA')
    n = len(q.values_get('Raw!B2:B')) + 1
    queue_ids = [cell_str(x[0]).strip() for x in q.values_get('Queue!A2:A') if x]
    qn = sum(1 for x in queue_ids if jobkey.is_job_id(x))
    return (hdr[0] if hdr else []), raw, n, qn


def check_sheet(rows, raw, jt_keys_path):
    """Gate 4 against live Raw. Returns warnings (company/title/location repeats)."""
    jt2n, _ = jobkey.aliases(jt_keys_path)
    raw_ids, raw_lids, raw_ctl = set(), set(), {}
    for r in raw:
        r = [cell_str(x) for x in r] + [''] * (len(q.RAW_HEADER) - len(r))
        jid = r[B].strip()
        if not jid:
            continue
        raw_ids.add(jid)
        for n in (jobkey.linkedin_id(r[C]), jt2n.get(jid, ''), jid if jid.isdigit() else ''):
            if n:
                raw_lids.add(n)
        raw_ctl.setdefault((jobkey.company_norm(r[E]), jobkey.normalize(r[D]), jobkey.normalize(r[H])), jid)
    warnings = []
    for r in rows:
        jid = r[B].strip()
        if jid in raw_ids:
            raise GateError(f'{jid} is already in Raw')
        lid = jobkey.linkedin_id(r[C])
        if lid and lid in raw_lids:
            raise GateError(f'{jid}: LinkedIn job {lid} is already in Raw')
        other = raw_ctl.get((jobkey.company_norm(r[E]), jobkey.normalize(r[D]), jobkey.normalize(r[H])))
        if other:
            warnings.append(f'{jid}: same company + title + location as Raw {other} (flag it, 05 Step A)')
    return warnings


def jt_rows(rows, run_id, jt_keys_path):
    """jt-keys.csv rows to add: every job-tools row (Aggregator jobtools:*) or JT- id not yet recorded."""
    have = {r['jt_key'] for r in jobkey.read_jt_keys(jt_keys_path)}
    out = []
    for r in rows:
        if not (r[G].startswith('jobtools') or r[B].startswith('JT-')):
            continue
        k = jobkey.jt_key(r[E], r[D], r[H])
        if k in have:
            continue
        board = r[G].split(':', 1)[1] if ':' in r[G] else (r[G] or 'other')
        out.append([k, board, jobkey.linkedin_id(r[C]), r[E], r[D], run_id, r[H]])
        have.add(k)
    return out


def append_jt_keys(new, jt_keys_path):
    exists = os.path.exists(jt_keys_path)
    with open(jt_keys_path, 'a', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        if not exists:
            w.writerow(jobkey.JT_KEYS_HEADER)
        w.writerows(new)


def run(argv):
    opt = lambda k: argv[argv.index(k) + 1] if k in argv and argv.index(k) + 1 < len(argv) else None
    run_id, path, apply = opt('--run'), opt('--csv'), '--apply' in argv
    m = RUN_RE.fullmatch(run_id or '')
    if not m or not path:
        print(__doc__)
        return 2
    if not os.path.isfile(path):
        print(f'ERROR: no such CSV: {path}', file=sys.stderr)
        return 2
    jt_path = os.path.join(REPO, jobkey.JT_KEYS)
    try:
        header, rows = load_csv(path)
        check_file(header, rows, jt_path)
        live_hdr, raw, n, qn = sheet_state()
        if live_hdr != q.RAW_HEADER:
            raise GateError('live Raw!A1:AA1 differs from the Raw header — stop and tell the operator')
        warnings = check_sheet(rows, raw, jt_path)
        for flag, actual in (('--expect-n', n), ('--expect-q', qn)):
            if opt(flag) is not None and int(opt(flag)) != actual:
                raise GateError(f'{flag} {opt(flag)} but the Sheet has {actual}')
    except GateError as e:
        print(f'GATE FAILED: {e}. Nothing written.', file=sys.stderr)
        return 1
    print(f'gates ok · {len(rows)} row(s) · Raw N={n} · Queue Q={qn}')
    for w in warnings:
        print('  warning: ' + w)
    if not apply:
        print(f'DRY RUN: would append Raw rows {n + 1}-{n + len(rows)}. Re-run with --apply to write.')
        return 0

    payload = [typed(r) for r in rows]
    rng = q.raw_append_rows(payload)
    problems = []
    mr = re.search(r'!A(\d+):AA(\d+)$', rng or '')
    if not mr or (int(mr.group(1)), int(mr.group(2))) != (n + 1, n + len(rows)):
        problems.append(f'appended range {rng!r}, expected Raw!A{n + 1}:AA{n + len(rows)}')
    first, last = n + 1, n + len(rows)
    q.raw_format_dates(first, last, ['N', 'Z'])
    hdr2, raw2, n2, qn2 = sheet_state()
    if hdr2 != q.RAW_HEADER:
        problems.append('Raw header changed')
    if n2 != n + len(rows):
        problems.append(f'Raw ends at {n2}, expected {n + len(rows)}')
    if qn2 != qn + len(rows):
        problems.append(f'Queue has {qn2} Job IDs, expected {qn + len(rows)}')
    tail = q.values_get(f'Raw!A{first}:AA{last}')
    for want, got in zip(payload, tail + [[]] * (len(payload) - len(tail))):
        got = [cell_str(x) for x in got] + [''] * (len(q.RAW_HEADER) - len(got))
        if got[B] != cell_str(want[B]) or got[Z] != cell_str(want[Z]):
            problems.append(f'read back {got[B]!r}/{got[Z]!r}, expected {want[B]!r}/{want[Z]!r}')
    lookups = {cell_str(r[0]).strip(): (cell_str(r[11]) if len(r) > 11 else '') for r in q.values_get('Queue!A2:L') if r}
    for r in rows:
        if not lookups.get(r[B]):
            problems.append(f'{r[B]}: not in Queue A, or Company (L) blank')
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    log = os.path.join(REPO, 'Runs', f'{m.group(1)}-{m.group(2)}-{m.group(3)}', f'raw-appends-{run_id}.jsonl')
    os.makedirs(os.path.dirname(log), exist_ok=True)
    with open(log, 'a', encoding='utf-8') as fh:
        for i, r in enumerate(rows):
            fh.write(json.dumps({'ts': ts, 'run': run_id, 'csv': os.path.basename(path), 'row': first + i, 'job': r[B],
                                 'n_before': n, 'q_before': qn, 'n_after': n2, 'q_after': qn2, 'ok': not problems}) + '\n')
    new_jt = jt_rows(rows, run_id, jt_path)
    if new_jt and not problems:
        append_jt_keys(new_jt, jt_path)
    if problems:
        print('READ-BACK FAILED — stop and tell the operator (Sheets version history can restore):')
        for p in problems:
            print('  ' + p)
        return 1
    print(f'appended and read back: Raw {n} -> {n2}, Queue {qn} -> {qn2}, lookups filled · '
          f'jt-keys +{len(new_jt)} · log {os.path.relpath(log, REPO)}')
    return 0


if __name__ == '__main__':
    sys.exit(run(sys.argv[1:]))
