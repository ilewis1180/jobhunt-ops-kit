#!/usr/bin/env python3
"""Token use per session for one orchestrator run -> Runs/<date>/USAGE-<OrchRunID>.csv (portal "Token use" card).

  python3 tools/usage_report.py <OrchRunID> [--phase 3] [--date YYYY-MM-DD] [--since HH:MM] [--weekly-start N] [--weekly-now N]

Source: Claude Code transcripts (config paths.transcripts_glob). Every assistant entry has
message.usage (input, output, cache_creation, cache_read); one message can repeat on several lines, so each message.id is
counted once. A transcript belongs to the run when it was written since --since (default: the orchestrator's start) and its
first user message names this orchestrator ("phase 3", a lane line with the OrchRunID, or the RunID itself). The session
name is `orch`, or `lane<N>-<HHMM>` from the lane's own Run ID (R<date>-<HHMM>-apply<N>), so it is unique in the run.
Only token counts and names are written: no message text. Weekly-limit columns stay blank unless given on the command line
(nothing reads that percentage reliably). The whole file is rewritten via a temp file and a rename, so a file sync
never ships half a file. Re-run at each checkpoint and at session end.
"""
import argparse, csv, datetime, glob, json, os, re, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

REPO = common.REPO
GLOB = common.transcripts_glob()
FIELDS = ['run_id', 'phase', 'session', 'session_run_id', 'model', 'started_at', 'updated_at', 'input_tokens', 'output_tokens',
          'cache_creation_tokens', 'cache_read_tokens', 'jobs_attempted', 'jobs_submitted', 'weekly_pct_start',
          'weekly_pct_now', 'weekly_resets_at']
LANE_RUN = re.compile(r'R\d{8}-(\d{4})-apply(\d)')


def first_user_text(path):
    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get('type') != 'user':
                continue
            c = (o.get('message') or {}).get('content')
            if isinstance(c, list):
                c = ' '.join(x.get('text', '') for x in c if isinstance(x, dict))
            if isinstance(c, str) and c.strip() and not c.lstrip().startswith('<'):
                return c
    return ''


def scan(path):
    """Token totals for one transcript (each message.id once) plus first/last timestamp, model, lane run id."""
    seen, tot, model, first, last, lane_run, lane_texts = set(), [0, 0, 0, 0], '', None, None, None, []
    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            ts = o.get('timestamp')
            if ts:
                first = first or ts
                last = ts
            m = o.get('message')
            if not isinstance(m, dict):
                continue
            if o.get('type') == 'user':
                lane_texts.append(json.dumps(m)[:6000])
            u = m.get('usage')
            if o.get('type') != 'assistant' or not u:
                continue
            mid = m.get('id') or o.get('uuid')
            if mid in seen:
                continue
            seen.add(mid)
            model = m.get('model') or model
            tot[0] += u.get('input_tokens') or 0
            tot[1] += u.get('output_tokens') or 0
            tot[2] += u.get('cache_creation_input_tokens') or 0
            tot[3] += u.get('cache_read_input_tokens') or 0
    return tot, model, first, last, lane_texts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run_id')
    ap.add_argument('--phase', default='3')
    ap.add_argument('--date')
    ap.add_argument('--since', help='HH:MM local; default = time in the RunID')
    ap.add_argument('--weekly-start')
    ap.add_argument('--weekly-now')
    a = ap.parse_args()
    m = re.fullmatch(r'R(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})-orch', a.run_id)
    if not m:
        sys.exit('bad orchestrator RunID')
    date = a.date or f'{m[1]}-{m[2]}-{m[3]}'
    start = datetime.datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]))
    since = start.timestamp() - 60
    rows = []
    for p in glob.glob(GLOB):
        if os.path.getmtime(p) < since:
            continue
        head = first_user_text(p)
        low = head.lower()
        is_orch = a.run_id in head or (low.strip().startswith('phase 3') and 'lane' not in low.split('\n')[0])
        lane = re.search(r'phase 3 lane (\d)', low)
        if not (is_orch or (lane and a.run_id in head)):
            continue
        tot, model, first, last, lane_texts = scan(p)
        if not first:
            continue
        # a stray older session that merely mentions the run is skipped: it must have started after the run did
        t0 = datetime.datetime.fromisoformat(first.replace('Z', '+00:00')).timestamp()
        if t0 < since:
            if not is_orch:
                continue
        name = 'orch' if (is_orch and not lane) else None
        run_of = ''
        if name is None:
            n = lane.group(1)
            own = re.compile(r'R\d{8}-(\d{4})-apply' + n + r'\b')
            mm = next((own.search(t) for t in lane_texts if own.search(t)), None)
            hhmm = mm.group(1) if mm else first[11:13] + first[14:16]
            name, run_of = f'lane{n}-{hhmm}', (mm.group(0) if mm else '')
        rows.append({'run_id': a.run_id, 'phase': a.phase, 'session': name, 'session_run_id': run_of, 'model': model,
                     'started_at': first[:19] + 'Z', 'updated_at': last[:19] + 'Z', 'input_tokens': tot[0],
                     'output_tokens': tot[1], 'cache_creation_tokens': tot[2], 'cache_read_tokens': tot[3],
                     'weekly_pct_start': a.weekly_start if name == 'orch' and a.weekly_start else '',
                     'weekly_pct_now': a.weekly_now if name == 'orch' and a.weekly_now else ''})
    rows.sort(key=lambda r: (r['session'] != 'orch', r['started_at']))
    outdir = os.path.join(REPO, 'Runs', date)
    os.makedirs(outdir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=outdir, prefix='.USAGE-', suffix='.tmp')
    with os.fdopen(fd, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, restval='')
        w.writeheader()
        w.writerows(rows)
    dest = os.path.join(outdir, f'USAGE-{a.run_id}.csv')
    os.replace(tmp, dest)
    tot = sum(int(r[k]) for r in rows for k in ('input_tokens', 'output_tokens', 'cache_creation_tokens', 'cache_read_tokens'))
    print(f'{dest}: {len(rows)} session(s), {tot:,} tokens')


if __name__ == '__main__':
    main()
