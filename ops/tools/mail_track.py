#!/usr/bin/env python3
"""Mail → job timeline, Phase 0: a READ-ONLY match report (PLAN-MAIL-TRACKER.md).

Reads <mail_export_dir>/job-threads.csv (never writes there; the folder is config paths.mail_export_dir), the Queue
through queue_api.py (read only) and AppApply-Capture/outcomes.csv + outcomes-jt.csv, then matches each mail thread to a
Queue job and reports the match rate. The mail exporter's contract is in docs/11-data-model.md (job-threads.csv,
export-status.json).
Writes ONLY the two report files below. No email bodies, no addresses: company, status, dates, thread id.

  python3 tools/mail_track.py report   --run-id <RunID> [--mail <dir>]   Phase 0 match report
  python3 tools/mail_track.py timeline --run-id <RunID> [--mail <dir>]   Phase 1: rebuild AppApply-Capture/timeline.csv

timeline writes AppApply-Capture/timeline.csv (machine-rebuilt, safe to overwrite) and AppApply-Capture/timeline-review.csv.
It creates AppApply-Capture/followups.csv only if absent and NEVER rewrites it (the applicant's columns: followed_up_at,
followup_days, snooze_until, note). followup_due = action needed: the date of the newest mail that needs the applicant
(assessment or survey, more_info, recruiter reply, interview, offer); blank once rejected, or once followed_up_at is on/after
that mail (the applicant's "handled" date). Waiting with no reply is never a follow-up. action_type names the kind.

report outputs (Runs/<date>/): mail-report-<RunID>.csv (one row per matched or reviewable thread) and
mail-report-<RunID>.md (counts, match tiers, per-job dates, review list).
Exit: 0 ok, 1 usage, 2 checked failure (stale export, Queue read failed).
"""
import collections, csv, datetime, io, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from common import die  # noqa: E402

REPO = common.REPO
MAIL = common.mail_dir()
STALE_HOURS = 2
SUFFIX = r'\b(' + '|'.join(common.COMPANY_SUFFIXES) + r')\b'
GENERIC = {'', 'us', 'usa', 'global', 'america', 'americas'}
# Threads first received before this date are history, never listed for review (config [run] queue_era_start).
ERA_START = datetime.datetime.strptime(common.cfg('run', 'queue_era_start') or '2000-01-01', '%Y-%m-%d')


def norm(s):
    s = re.sub(SUFFIX, ' ', (s or '').lower())
    return common.normalize_text(s)


def pdate(s):
    s = (s or '').strip().replace('T', ' ').rstrip('Z')
    for fmt, n in (('%Y-%m-%d %H:%M', 16), ('%Y-%m-%d', 10)):   # migrated Queue rows carry a date only
        try:
            return datetime.datetime.strptime(s[:n], fmt)
        except ValueError:
            pass
    return None


def read_queue():
    p = subprocess.run([sys.executable, os.path.join(REPO, 'tools', 'queue_api.py'), 'read'],
                       capture_output=True, text=True)
    if p.returncode != 0:
        die('Queue read failed: ' + p.stderr.strip()[:300])
    rows = list(csv.DictReader(io.StringIO(p.stdout)))
    if not rows or 'Job ID' not in rows[0]:
        die('Queue read returned no Job ID column')
    return rows


def apply_dates():
    """Job ID -> latest submit time from outcomes.csv and outcomes-jt.csv (both, so JT- jobs get a real apply date)."""
    out = {}
    for name in ('outcomes.csv', 'outcomes-jt.csv'):
        path = os.path.join(REPO, 'AppApply-Capture', name)
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r.get('outcome') in ('submitted', 'unconfirmed'):
                    d = pdate(r.get('ended_at')) or pdate(r.get('started_at'))
                    if d and (r['job_id'] not in out or d > out[r['job_id']]):
                        out[r['job_id']] = d
    return out


TITLE_STOP = {'and', 'of', 'for', 'to', 'in', 'at', 'a', 'the', 'ii', 'iii', 'i'}
ACTION = {'assessment': 'assessment', 'more_info': 'more_info', 'interview': 'interview', 'recruiter': 'reply',
          'offer': 'offer'}   # mail statuses that need the applicant to act (survey, reply, interview)
CAPTURE = os.path.join(REPO, 'AppApply-Capture')


def add_bdays(d, n):
    while n > 0:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def atomic_csv(path, header, rows):
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    os.replace(tmp, path)


def read_followups():
    path = os.path.join(CAPTURE, 'followups.csv')
    head = ['job_id', 'followed_up_at', 'followup_days', 'snooze_until', 'note']
    if not os.path.exists(path):
        with open(path, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(head)
        return {}
    return {r['job_id']: r for r in csv.DictReader(open(path, encoding='utf-8')) if r.get('job_id')}


def write_timeline(jobs, results, stale, exported_at, run_id):
    fu = read_followups()
    slack = datetime.timedelta(days=1)
    per = collections.defaultdict(list)
    for t, j, m, note in results:
        if j:
            per[j['id']].append((t, m, note))
    rows = []
    for j in sorted(jobs, key=lambda j: str(j['apply_at'])):
        ts = per.get(j['id'], [])
        conf = [pdate(t['first_received_at']) for t, m, n in ts if t['status'] == 'received'
                and (j['apply_at'] is None or pdate(t['first_received_at']) >= j['apply_at'] - slack)]
        rej = [pdate(t['last_received_at']) for t, m, n in ts if t['status'] == 'rejected']
        itv = [pdate(t['first_received_at']) for t, m, n in ts if t['status'] == 'interview']
        last = max([pdate(t['last_received_at']) for t, m, n in ts], default=None)
        methods = sorted({m for t, m, n in ts})
        if not ts:
            confidence = ''
        elif any(n.startswith('ambiguous') for t, m, n in ts):
            confidence = 'low'
        elif any(m.startswith('a:') for t, m, n in ts):
            confidence = 'high'
        else:
            confidence = 'medium'
        confirmation, rejection, interview = min(conf, default=None), max(rej, default=None), min(itv, default=None)
        state = 'rejected' if rejection else 'interview' if interview else 'confirmed' if confirmation else 'applied'
        f = fu.get(j['id'], {})
        # follow-up and action-needed are one tag: set only when mail needs the applicant (assessment/survey, more info, reply,
        # interview, offer) and nothing newer has cleared it. Silence after applying is NOT a follow-up.
        acts = sorted((pdate(t['last_received_at']), ACTION[t['status']]) for t, m, n in ts
                      if t['status'] in ACTION and pdate(t['last_received_at']))
        due, atype = '', ''
        if acts and not rejection:
            when, atype = acts[-1]
            done = (f.get('followed_up_at') or '').strip()
            snooze = (f.get('snooze_until') or '').strip()
            if done and done >= when.date().isoformat():
                atype = ''
            else:
                due = when.date().isoformat()
                if snooze and snooze > due:
                    due = snooze
        rows.append([j['id'], j['company'], j['title'], j['apply_at'] or '', j['src'], confirmation or '', rejection or '',
                     interview or '', last or '', len(ts), ';'.join(methods), confidence, state, due, exported_at, atype])
    head = ['job_id', 'company', 'title', 'apply_at', 'apply_src', 'confirmation_at', 'rejection_at', 'interview_at',
            'last_mail_at', 'thread_count', 'match_methods', 'match_confidence', 'state', 'followup_due', 'mail_export_at', 'action_type']
    atomic_csv(os.path.join(CAPTURE, 'timeline.csv'), head, rows)
    rev = []
    for t, j, m, note in results:
        era = (pdate(t['first_received_at']) or datetime.datetime.min) >= ERA_START
        if (not j and era) or note.startswith('ambiguous'):
            rev.append([t['thread_id'], t['status'], t['sender_domain'], t['first_received_at'][:10],
                        j['id'] if j else '', note if j else 'no-match', t['last_subject'][:80]])
    atomic_csv(os.path.join(CAPTURE, 'timeline-review.csv'),
               ['thread_id', 'mail_status', 'sender_domain', 'first_received', 'guessed_job_id', 'why', 'subject'], rev)
    c = collections.Counter(r[12] for r in rows)
    print('timeline.csv: %d jobs %s; mail export %.1f h old%s' % (len(rows), dict(c), stale,
          ' (STALE: dates may be missing)' if stale > STALE_HOURS else ''))
    print('timeline-review.csv: %d threads; followups.csv entries read: %d' % (len(rev), len(fu)))
    today = datetime.date.today().isoformat()
    due = [r for r in rows if r[13] and r[13] <= today]
    print('action needed (the follow-up tag): %d' % len(due))
    # the brief the Phase 3 orchestrator reads to the operator (09 §4 step 1, §8 step 2)
    recent = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    print('BRIEF')
    for r in sorted(due, key=lambda r: r[13])[:15]:
        print('  action needed (%s): %s (%s), mail %s, applied %s' % (r[15], r[1], r[0], r[13], str(r[3])[:10]))
    if len(due) > 15:
        print('  ... and %d more in timeline.csv' % (len(due) - 15))
    for r in rows:
        if r[6] and str(r[6])[:10] >= recent:
            print('  new rejection: %s (%s) %s' % (r[1], r[0], str(r[6])[:10]))
        if r[7] and str(r[7])[:10] >= recent:
            print('  interview mail: %s (%s) %s' % (r[1], r[0], str(r[7])[:10]))


def main(argv):
    if len(argv) < 3 or argv[0] not in ('report', 'timeline') or argv[1] != '--run-id':
        die(__doc__, 1)
    cmd = argv[0]
    run_id = argv[2]
    mail = MAIL
    if '--mail' in argv:
        mail = os.path.expanduser(argv[argv.index('--mail') + 1])
    try:
        import json
        st = json.load(open(os.path.join(mail, 'export-status.json')))
        age = (datetime.datetime.utcnow() - datetime.datetime.strptime(st['exported_at'], '%Y-%m-%dT%H:%M:%SZ'))
        stale = age.total_seconds() / 3600
        exported_at = st['exported_at']
    except Exception as e:
        die('cannot read export-status.json: %s' % e)
    threads = list(csv.DictReader(open(os.path.join(mail, 'job-threads.csv'), encoding='utf-8-sig')))

    queue = [r for r in read_queue() if r['Status'].startswith('Submitted')]
    applied = apply_dates()
    jobs = []
    for r in queue:
        at = applied.get(r['Job ID']) or pdate(r['Last touched'])
        src = 'outcomes.csv' if r['Job ID'] in applied else 'Queue last-touched'
        jobs.append({'id': r['Job ID'], 'company': r['Company'], 'n': norm(r['Company']), 'apply_at': at,
                     'src': src, 'title': r['Job Title'], 'tn': norm(r['Job Title'])})
    jobs = [j for j in jobs if len(j['n']) >= 3]
    by_name = collections.defaultdict(list)
    for j in jobs:
        by_name[j['n']].append(j)

    results = []
    for t in threads:
        if t['status'] == 'alert':
            continue
        first, last = pdate(t['first_received_at']), pdate(t['last_received_at'])
        text = norm(t['last_subject'] + ' ' + re.sub(r'<.*?>|@.*', '', t['last_from']))
        cname = norm(t['company'])
        cand, method = [], ''
        if cname and cname in by_name:
            cand, method = by_name[cname], 'a:company-field'
        else:
            hit = [n for n in by_name if n not in GENERIC and re.search(r'\b%s\b' % re.escape(n), text)]
            if hit:
                cand = [j for n in hit for j in by_name[n]]
                method = 'b:subject-or-sender'
        # same company can be applied for twice; keep applications made on or before the mail
        if not cand:
            body = norm(re.sub(r'<[^>]*>|\{[^}]*\}|[a-z-]+:[^;]*;', ' ', t['last_body'])[:6000])
            hit = [n for n in by_name if n not in GENERIC and len(n) >= 4 and re.search(r'\b%s\b' % re.escape(n), body)]
            if len(hit) == 1:
                cand, method = by_name[hit[0]], 'c:body-text'
        # mail can land before the lane's recorded end time (and clocks differ by zone): allow one day
        slack = datetime.timedelta(days=1)
        cand = [j for j in cand if j['apply_at'] is None or last is None or j['apply_at'] - slack <= last]
        if len(cand) > 1:   # same company applied for twice: the job title in the mail picks the right one
            sub = set(norm(t['last_subject']).split())
            bod = set(norm(re.sub(r'<[^>]*>|\{[^}]*\}|[a-z-]+:[^;]*;', ' ', t['last_body'])[:6000]).split())
            def tscore(j):
                tt = [w for w in j['tn'].split() if w not in TITLE_STOP]
                return (sum(2 for w in tt if w in sub) + sum(1 for w in tt if w in bod)) / float(max(1, len(tt)))
            sc = sorted(((tscore(j), j) for j in cand), key=lambda x: -x[0])
            if sc[0][0] > 0 and (len(sc) == 1 or sc[0][0] > sc[1][0]):
                cand, method = [sc[0][1]], method + '+title'
        if len(cand) == 1:
            results.append((t, cand[0], method, 'ok'))
        elif len(cand) > 1:
            cand.sort(key=lambda j: j['apply_at'] or datetime.datetime.min)
            results.append((t, cand[-1], method, 'ambiguous:%d' % len(cand)))
        else:
            results.append((t, None, 'none', 'no-match'))

    if cmd == 'timeline':
        return write_timeline(jobs, results, stale, exported_at, run_id)
    matched = [r for r in results if r[1]]
    day = datetime.date.today().isoformat()
    outdir = os.path.join(REPO, 'Runs', day)
    os.makedirs(outdir, exist_ok=True)
    csvp = os.path.join(outdir, 'mail-report-%s.csv' % run_id)
    with open(csvp, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['thread_id', 'mail_status', 'sender_domain', 'job_id', 'company', 'method', 'note',
                    'apply_at', 'first_mail_at', 'last_mail_at'])
        for t, j, m, note in results:
            if j:
                w.writerow([t['thread_id'], t['status'], t['sender_domain'], j['id'], j['company'], m, note,
                            j['apply_at'], t['first_received_at'], t['last_received_at']])

    # per-job summary
    per = collections.defaultdict(lambda: {'received': None, 'rejected': None, 'interview': None, 'n': 0})
    for t, j, m, note in matched:
        d = per[j['id']]
        d['n'] += 1
        k = t['status']
        key = {'received': 'received', 'rejected': 'rejected', 'interview': 'interview'}.get(k)
        if key:
            when = t['first_received_at'] if key == 'received' else t['last_received_at']
            if d[key] is None or when < d[key]:
                d[key] = when
    withmail = [j for j in jobs if j['id'] in per]
    nomail = [j for j in jobs if j['id'] not in per]
    tiers = collections.Counter(m for _, j, m, _ in results if j)
    unmatched = [r for r in results if not r[1]]
    inera = [r for r in unmatched if (pdate(r[0]['first_received_at']) or datetime.datetime.min) >= ERA_START]
    sts = collections.Counter(r[0]['status'] for r in unmatched)

    md = []
    md.append('# Mail match report %s (Phase 0, read-only)\n' % run_id)
    md.append('Export age %.1f h%s. Threads read %d (alerts skipped). Submitted jobs in Queue %d (name usable: %d).\n'
              % (stale, ' **STALE (> %d h)**' % STALE_HOURS if stale > STALE_HOURS else '', len(threads), len(queue), len(jobs)))
    md.append('## Thread → job\n')
    md.append('- Matched: %d of %d non-alert threads (%.0f%%). Tiers: %s'
              % (len(matched), len(results), 100.0 * len(matched) / max(1, len(results)), dict(tiers)))
    md.append('- Ambiguous (same company applied twice; newest application chosen): %d'
              % sum(1 for r in results if r[3].startswith('ambiguous')))
    md.append('- Unmatched: %d (by status: %s). Of those, received since %s (the Queue era): %d'
              % (len(unmatched), dict(sts), ERA_START.date().isoformat(), len(inera)))
    md.append('\n## Job → mail\n')
    md.append('- Submitted jobs with at least one matched thread: %d of %d (%.0f%%)'
              % (len(withmail), len(jobs), 100.0 * len(withmail) / max(1, len(jobs))))
    md.append('- With a `received` (confirmation) thread: %d; `rejected`: %d; `interview`: %d'
              % (sum(1 for d in per.values() if d['received']), sum(1 for d in per.values() if d['rejected']),
                 sum(1 for d in per.values() if d['interview'])))
    md.append('- Apply date source: outcomes.csv %d, Queue last-touched %d' %
              (sum(1 for j in jobs if j['src'] == 'outcomes.csv'), sum(1 for j in jobs if j['src'] != 'outcomes.csv')))
    md.append('\n## Submitted jobs with no mail found (%d)\n' % len(nomail))
    for j in sorted(nomail, key=lambda j: str(j['apply_at'])):
        md.append('- %s — %s (%s)' % (j['id'], j['company'], str(j['apply_at'])[:10]))
    md.append('\n## Unmatched threads since %s (%d) — review list\n' % (ERA_START.date().isoformat(), len(inera)))
    for t, _, _, _ in sorted(inera, key=lambda r: r[0]['first_received_at']):
        md.append('- %s %s — %s — %s' % (t['first_received_at'][:10], t['status'], t['sender_domain'], t['last_subject'][:60]))
    mdp = os.path.join(outdir, 'mail-report-%s.md' % run_id)
    open(mdp, 'w', encoding='utf-8').write('\n'.join(md) + '\n')
    print('\n'.join(md[:12]))
    print('\nwrote', csvp, mdp)


if __name__ == '__main__':
    main(sys.argv[1:])
