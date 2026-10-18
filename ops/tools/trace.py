#!/usr/bin/env python3
"""Append one 08 trace line: AppApply-Capture/traces/<RunID>/TRACE-<JobID>-a<N>.jsonl

Usage:
  python3 tools/trace.py <RunID> <JobID>-a<N> <action> [--page N] [--json '<extra fields>']
  python3 tools/trace.py <RunID> <JobID>-a<N> <action> [--page N] --json - <<'EOF'     (fields from stdin)
  {"target":{"label":"Email*","css":"#email","frame":"top"},"answer_key":"identity.email","result":"ok"}
  EOF

It sets ts (UTC, ms), run_id, attempt_id, job_id and step (0 for the first line, then last step + 1), plus
`action` and `page`. Everything else comes from --json (a JSON object; 08 §2 lists the fields). A top-level `url`
keeps origin + path only (query string and fragment dropped).
Refuses, writing nothing, any line tools/pii_scan.py would flag: exit 2, pattern names on stderr (never the value).
Exit 1 for usage errors. On success it prints `TRACE-<JobID>-a<N>.jsonl step <N> <action>`.
"""
import argparse, datetime, fcntl, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common, pii_scan  # noqa: E402  (tools/pii_scan.py loads the private PII patterns)

ACTIONS = ('start', 'navigate', 'read', 'click', 'type', 'select', 'check', 'upload', 'wait', 'next',
           'approval', 'intent', 'submit', 'confirm', 'halt', 'end')
RESERVED = ('ts', 'run_id', 'attempt_id', 'job_id', 'step', 'action')


class Parser(argparse.ArgumentParser):
    def error(self, message):  # exit 1, so exit 2 always means "refused by the PII check"
        self.print_usage(sys.stderr)
        print(f'trace.py: {message}', file=sys.stderr)
        sys.exit(1)


def fail(msg, code=1):
    print(f'trace.py: {msg}', file=sys.stderr)
    sys.exit(code)


def main():
    ap = Parser(description='Append one 08 trace line.', epilog='actions: ' + ' '.join(ACTIONS))
    ap.add_argument('run_id')
    ap.add_argument('attempt_id', help='<JobID>-a<N>')
    ap.add_argument('action', choices=ACTIONS, metavar='action')
    ap.add_argument('--page', type=int)
    ap.add_argument('--json', dest='extra', help="JSON object with the other fields, or '-' to read it from stdin")
    a = ap.parse_args()

    try:
        run_ok = pii_scan.RUN.fullmatch(a.run_id)
        pii_scan.patterns()
    except Exception as e:  # fail closed
        fail(f'cannot load the PII patterns from {pii_scan.PII_FILE} ({type(e).__name__})', 2)
    if not run_ok:
        fail(f'bad RunID {a.run_id!r} (expected R<YYYYMMDD>-<HHMM>-<kind>[N])')
    m = common.ATTEMPT_RE.fullmatch(a.attempt_id)  # JT- keys carry a hyphen (Phase 0)
    if not m:
        fail(f'bad attempt id {a.attempt_id!r} (expected <JobID>-a<N>)')
    if a.page is not None and a.page < 1:
        fail('--page must be 1 or more')

    extra = {}
    if a.extra is not None:
        raw = sys.stdin.read() if a.extra == '-' else a.extra
        try:
            extra = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as e:
            fail(f'--json is not valid JSON ({e.msg} at char {e.pos})')
        if not isinstance(extra, dict):
            fail('--json must be a JSON object')
    clash = [k for k in RESERVED if k in extra] + (['page'] if a.page is not None and 'page' in extra else [])
    if clash:
        fail(f'--json may not set {", ".join(clash)} (the script sets them)')
    if isinstance(extra.get('url'), str):
        bare = re.split(r'[?#]', extra['url'], 1)[0]
        if bare != extra['url']:
            print('trace.py: url query/fragment dropped (08 §1)', file=sys.stderr)
            extra['url'] = bare

    rec = {'ts': None, 'run_id': a.run_id, 'attempt_id': a.attempt_id, 'job_id': m.group(1), 'step': None,
           'action': a.action}
    if a.page is not None:
        rec['page'] = a.page
    rec.update(extra)

    # PII check before anything touches the disk (ts and step can't carry an personal value).
    hits = pii_scan.scan_text(json.dumps(rec))
    if hits:
        fail('REFUSED, nothing written: the line matches ' + ', '.join(sorted({n for _, n in hits}))
             + '. Use an answer key or value_ref instead of the value (08 §1).', 2)

    d = os.path.join(common.CAPTURE, 'traces', a.run_id)
    name = f'TRACE-{a.attempt_id}.jsonl'
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), 'a+', encoding='utf-8') as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        body = fh.read()
        lines = [ln for ln in body.splitlines() if ln.strip()]
        def field(ln, key):
            try:
                return json.loads(ln).get(key)
            except (ValueError, AttributeError):
                return None
        step = 0
        if lines:
            try:
                step = int(field(lines[-1], 'step')) + 1
            except (ValueError, TypeError):
                step = len(lines)
            if a.action == 'start':
                print('trace.py: warning: "start" but the trace already has lines', file=sys.stderr)
            elif field(lines[0], 'action') != 'start':
                print('trace.py: warning: the first line is not "start"', file=sys.stderr)
            if field(lines[-1], 'action') == 'end':
                print('trace.py: warning: appending after the "end" line', file=sys.stderr)
        elif a.action != 'start':
            print('trace.py: warning: first line of this trace is not "start"', file=sys.stderr)
        rec['ts'] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        rec['step'] = step
        fh.seek(0, os.SEEK_END)
        if body and not body.endswith('\n'):
            fh.write('\n')
        fh.write(json.dumps(rec) + '\n')
    print(f'{name} step {step} {a.action}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
