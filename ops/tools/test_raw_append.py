#!/usr/bin/env python3
"""Offline checks for tools/raw_append.py against an in-memory fake of the Job Queue (Raw + Queue with the real
UNIQUE / XLOOKUP behaviour, type-sensitive like Sheets). Never touches the Sheet or the real repo: JOBHUNT_OPS points
at a throwaway tree with its own jt-keys.csv.
Usage: python3 ops/tools/test_raw_append.py"""
import csv, datetime, io, json, os, sys, tempfile
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix='raw-append-test-')
os.environ['JOBHUNT_OPS'] = TMP
os.makedirs(os.path.join(TMP, 'AppApply-Capture'))
sys.path.insert(0, HERE)
import jobkey  # noqa: E402
import queue_api  # noqa: E402
import raw_append  # noqa: E402
fails = []
RUN = 'R20261020-1000-scrape'
HDR = queue_api.RAW_HEADER
SERIAL = lambda s: (datetime.date.fromisoformat(s) - datetime.date(1899, 12, 30)).days


def check(name, cond):
    print(('ok   ' if cond else 'FAIL ') + name)
    if not cond:
        fails.append(name)


class FakeQ:
    """Raw rows hold typed values like the Sheet (int ids, date serials). Queue A = UNIQUE(Raw!B), L = XLOOKUP last."""
    RAW_HEADER = HDR

    def __init__(self, raw, drop_on_append=False):
        self.raw = [list(HDR)] + [list(r) for r in raw]
        self.appends, self.formats, self.drop = [], [], drop_on_append

    def queue(self):
        seen, out = set(), []
        for r in self.raw[1:]:
            k = (type(r[1]), r[1])           # Sheets: 4400000001 and "4400000001" are different values
            if r[1] != '' and k not in seen:
                seen.add(k)
                out.append(r[1])
        last = {}
        for r in self.raw[1:]:
            last[(type(r[1]), r[1])] = r[4]
        return [[a] + [''] * 10 + [last[(type(a), a)]] for a in out]

    def values_get(self, rng, render='UNFORMATTED_VALUE', sid=None):
        tab, cells = rng.split('!')
        if tab == 'Queue':
            q = self.queue()
            return [[r[0]] for r in q] if cells == 'A2:A' else q
        if cells == 'A1:AA1':
            return [self.raw[0]]
        if cells == 'B2:B':
            return [[r[1]] for r in self.raw[1:]]
        if cells == 'A2:AA':
            return self.raw[1:]
        a, b = cells.split(':')
        return self.raw[int(a[1:]) - 1:int(b[2:])]

    def raw_append_rows(self, rows, sid=None):
        self.appends.append(rows)
        start = len(self.raw) + 1
        self.raw += [list(r) for r in (rows[:-1] if self.drop else rows)]
        return f'Raw!A{start}:AA{start + len(rows) - 1}'

    def raw_format_dates(self, first, last, cols, sid=None):
        self.formats.append((first, last, tuple(cols)))


def row(jid, co, title, loc='Houston, TX', url='', agg='', snap='2026-10-20', posted='', desc=''):
    r = [''] * 27
    r[0], r[1], r[2], r[3], r[4], r[6], r[7], r[13], r[24], r[25] = 'Saved', jid, url, title, co, agg, loc, posted, desc, snap
    return r


def existing():
    a = row(4400000001, 'Alpha', 'Account Executive', url='https://www.linkedin.com/jobs/view/4400000001/')
    a[25] = SERIAL('2026-10-15')
    b = row('JT-59de07b153', 'Affirm', 'Small Business Account Executive II', agg='jobtools:linkedin')
    return [a, b]


def write_jt_keys():
    with open(os.path.join(TMP, 'AppApply-Capture', 'jt-keys.csv'), 'w', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(jobkey.JT_KEYS_HEADER)
        w.writerow(['JT-59de07b153', 'linkedin', '4476880256', 'Affirm', 'Small Business Account Executive II',
                    'R20261012-1203-discover', ''])


def write_csv(rows, name='in.csv', header=HDR):
    p = os.path.join(TMP, name)
    with open(p, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return p


def go(fake, *args):
    raw_append.q = fake
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = raw_append.run(['--run', RUN] + [str(a) for a in args])
    return rc, out.getvalue() + err.getvalue()


JT = jobkey.jt_key('Legora', 'Account Executive Mid-Market', 'Houston, TX')
GOOD = [row('4400000002', 'Bravo', 'Sales Engineer', url='https://www.linkedin.com/jobs/view/4400000002/',
            posted='2026-10-18', desc='=HYPERLINK("http://evil","x")'),
        row(JT, 'Legora', 'Account Executive Mid-Market', agg='jobtools:indeed')]

write_jt_keys()
f = FakeQ(existing())
rc, out = go(f, '--csv', write_csv(GOOD))
check('dry run: gates pass, nothing written', rc == 0 and 'DRY RUN' in out and not f.appends)

f = FakeQ(existing())
rc, out = go(f, '--csv', write_csv(GOOD), '--expect-n', 3, '--expect-q', 2, '--apply')
check('apply: appended and read back', rc == 0 and 'appended and read back' in out or print(out))
p = f.appends[0] if f.appends else [[''] * 27, [''] * 27]
check('numeric Job ID goes in as a number (Queue UNIQUE/XLOOKUP keep matching)', p[0][1] == 4400000002 and p[1][1] == JT)
check('Snapshot and Posted Date go in as date serials, formatted yyyy-mm-dd',
      p[0][25] == SERIAL('2026-10-20') and p[0][13] == SERIAL('2026-10-18') and f.formats == [(4, 5, ('N', 'Z'))])
check('a "=..." cell stays text (RAW input)', p[0][24] == '=HYPERLINK("http://evil","x")')
check('Queue grew by exactly the new rows, lookups filled', len(f.queue()) == 4 and all(r[11] for r in f.queue()))
jt = list(csv.DictReader(open(os.path.join(TMP, 'AppApply-Capture', 'jt-keys.csv'))))
check('jt-keys.csv gets the job-tools row with board and location', jt[-1]['jt_key'] == JT and jt[-1]['board'] == 'indeed'
      and jt[-1]['location'] == 'Houston, TX' and jt[-1]['first_seen_run'] == RUN and len(jt) == 2)
log = os.path.join(TMP, 'Runs', '2026-10-20', f'raw-appends-{RUN}.jsonl')
check('append log written', os.path.exists(log) and len(open(log).read().splitlines()) == 2
      and json.loads(open(log).readline())['row'] == 4)


def refused(name, rows, *extra, header=HDR, fake=None):
    f = fake or FakeQ(existing())
    rc, out = go(f, '--csv', write_csv(rows, header=header), *extra, '--apply')
    check(f'refused: {name}', rc == 1 and 'GATE FAILED' in out and not f.appends or print(out))


refused('header differs', GOOD, header=HDR[:-1] + ['Flag'])
refused('row with 26 fields', [GOOD[0][:-1]])
refused('Job ID not a Queue id', [row('src-0123456789abcdef', 'X', 'Y')])
refused('Snapshot Date placeholder', [row('4400000003', 'C', 'T', snap='YYYY-MM-DD')])
refused('LinkedIn job keyed JT- (number-first rule)', [row(jobkey.jt_key('Bravo', 'SE', 'Houston, TX'), 'Bravo', 'SE',
        url='https://www.linkedin.com/jobs/view/4400000009/')])
refused('JT- key that is not jt_key(company, title, location)', [row('JT-0000000000', 'Legora', 'AE')])
refused('Job ID twice in the file', [GOOD[0], GOOD[0]])
refused('Job ID already in Raw (number stored as a number)', [row('4400000001', 'Alpha', 'AE',
        url='https://www.linkedin.com/jobs/view/4400000001/')])
refused('LinkedIn job already in Raw under a JT- alias', [row('4476880256', 'Affirm', 'SB AE II',
        url='https://www.linkedin.com/jobs/view/4476880256/')])
refused('--expect-n mismatch', GOOD, '--expect-n', 99)
refused('--expect-q mismatch', GOOD, '--expect-q', 99)
bad = FakeQ(existing())
bad.raw[0] = HDR[:-1] + ['Flag']
refused('live Raw header changed', GOOD, fake=bad)

f = FakeQ(existing())
rc, out = go(f, '--csv', write_csv([row('4400000004', 'Alpha', 'Account Executive', url='https://www.linkedin.com/jobs/view/4400000004/')]))
check('company + title + location repeat is a warning, not a refusal', rc == 0 and 'warning' in out and 'Raw 4400000001' in out)

write_jt_keys()
f = FakeQ(existing(), drop_on_append=True)
rc, out = go(f, '--csv', write_csv(GOOD), '--apply')
jt = list(csv.DictReader(open(os.path.join(TMP, 'AppApply-Capture', 'jt-keys.csv'))))
check('read-back mismatch: exit 1, READ-BACK FAILED, jt-keys untouched', rc == 1 and 'READ-BACK FAILED' in out and len(jt) == 1)

rc, out = go(FakeQ(existing()), '--csv', os.path.join(TMP, 'missing.csv'))
check('missing CSV is a usage error', rc == 2)

print('\n' + ('ALL PASSED' if not fails else 'FAILURES:\n  ' + '\n  '.join(fails)))
sys.exit(1 if fails else 0)
