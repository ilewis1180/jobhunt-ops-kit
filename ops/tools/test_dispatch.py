#!/usr/bin/env python3
"""Offline checks for tools/dispatch.py: `confirm`, lane `external`, the OUTCOME/QB fragments, `awaiting_submit`/`retract`, fragment quoting, and trace.py JT- ids. Builds a throwaway ops
tree (JOBHUNT_OPS) with a fake Queue CSV and a harmless PII pattern file; never touches the Sheet, Chrome or real data.
Usage: python3 tools/test_dispatch.py"""
import csv, glob, io, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix='dispatch-test-')
ENV = dict(os.environ, JOBHUNT_OPS=TMP, JOBHUNT_PII_PATTERNS=os.path.join(TMP, 'pii.json'), JOBHUNT_CONFIG=os.path.join(TMP, 'none.toml'))
json.dump({'pii_regex': r'ZZPIIZZ'}, open(ENV['JOBHUNT_PII_PATTERNS'], 'w'))
os.makedirs(os.path.join(TMP, 'tools'))
for f in ('common.py', 'dispatch.py', 'pii_scan.py'):
    os.symlink(os.path.join(HERE, f), os.path.join(TMP, 'tools', f))
RUNS = os.path.join(TMP, 'Runs', '2026-10-06')
os.makedirs(RUNS)
ORCH = 'R20261006-0900-orch'
fails = []


def d(*args, ok=True):
    r = subprocess.run([sys.executable, os.path.join(TMP, 'tools', 'dispatch.py'), '--run', ORCH] + [str(x) for x in args],
                       capture_output=True, text=True, env=ENV, cwd=TMP)
    if (r.returncode == 0) != ok:
        fails.append(f'{args}: rc={r.returncode} {r.stdout[-300:]} {r.stderr[-300:]}')
    return r.stdout + r.stderr


def check(name, cond):
    print(('ok   ' if cond else 'FAIL ') + name)
    if not cond:
        fails.append(name)


JOBS = {'4400000001': 'Alpha', '4400000002': 'Bravo', '4400000003': 'Charlie', '4400000004': 'Delta'}
for j, co in JOBS.items():
    open(os.path.join(RUNS, f'PREP-{co}-{j}-R20261006-0800-prep.md'), 'w').write(
        f'# PREP — {co} — Engineer — {j}\nATS: Greenhouse · Site: boards.example.com/{co.lower()} · Login needed: no · '
        f'Apply URL: https://boards.example.com/{co.lower()}/{j}\nRésumé: R.pdf\nJD: jd-{j}.md\n')
rows = ['Job ID,Status'] + [f'{j},Ready' for j in JOBS]
q = os.path.join(TMP, 'queue.csv')
open(q, 'w').write('A,B,C,D,E,F,G,H,I,J,K\n' + ''.join(f'{j},Ready,,,,,,,,Yes,3\n' for j in JOBS))
out = subprocess.run([sys.executable, os.path.join(TMP, 'tools', 'dispatch.py'), 'init', ORCH, '--queue', q, '--lanes', '2', '--ea-lane', '2'],
                     capture_output=True, text=True, env=ENV, cwd=TMP)
check('init', out.returncode == 0 or print(out.stdout, out.stderr))
d('register', 1, 'R20261006-0905-apply1')
d('window', 1, 'ok')
pk = d('claim', 1, '--ahead', 3, '--peek')
check('claim --peek lists next cards and claims nothing (A7)', 'PEEK' in pk and 'next' in pk and 'held' not in pk
      and 'ready' in d('show', '4400000001'))
d('claim', 1, '--ahead', 3)
d('claim', 2, ok=False)  # lane 2 not registered


def findings(j, kind, text='Submitted. Redirect to a confirmation page: "Thank you for applying."'):
    n = f'{kind}-greenhouse-x-{j}-a1-R20261006-0905-apply1.md'
    open(os.path.join(RUNS, n), 'w').write(f'# x — {j}\n\n## Outcome\n{text}\n\n## Confirmation method\n{text}\n')
    return n


INTENT = """# INTENT — x
## Inventory
| ID | Page | Label (verbatim) | Control | Required | Options / conditional on |
| P1.F01 | 1 | First Name | text | yes | |
| P1.F02 | 1 | How did you hear about this job? | text | no | |
| P1.F03 | 1 | Will you require sponsorship? | select | yes | Yes/No |
| P1.F04 | 1 | Autofill | button | no | never used |
## Ledger
| ID | Answer used | Source | Verified how | State |
| P1.F01 | Alex | answers §Identity | JS value | verified |
| P1.F02 | Company Website | answers §Screening | JS value | verified |
| P1.F03 | No | answers §Work authorization | read | verified |
"""
STAGING = os.path.join(TMP, 'AppApply-Capture', 'staging')
os.makedirs(STAGING)


def lane_to_submit_clicked(j):
    d('claim', 1, '--ahead', 3)
    d('event', 1, j, 'awaiting_yes')
    d('event', 1, j, 'approved', '--approval', 'yes')
    d('event', 1, j, 'filling')
    d('event', 1, j, 'intent')
    d('window', 1, 'ok')
    d('event', 1, j, 'submit_clicked')


# --- 3. fragments from the findings file
a, b, c, e = list(JOBS)
lane_to_submit_clicked(a)
open(os.path.join(RUNS, f'INTENT-{a}-a1-R20261006-0905-apply1.md'), 'w').write(INTENT)

# --- A1: awaiting_submit (SUBMIT HANDOFF) and retract, on the card that just posted submit_clicked
d('event', 1, a, 'awaiting_submit', ok=False)                           # note required
d('event', 1, a, 'awaiting_submit', '--note', 'tick the hCaptcha in lane 1 window, then click Submit')
board = d('board')
check('board shows SUBMIT HANDOFF in NEEDS YOU (A1)', 'SUBMIT HANDOFF' in board and 'waiting:awaiting_submit' in board)
check('watch prints SUBMIT HANDOFF (A1)', 'SUBMIT HANDOFF' in subprocess.run(
    [sys.executable, os.path.join(TMP, 'tools', 'dispatch.py'), '--run', ORCH, 'watch', '--once', '--replay'],
    capture_output=True, text=True, env=ENV, cwd=TMP).stdout)
d('event', 1, a, 'retract', ok=False)                                   # note required
d('event', 1, a, 'retract', '--note', 'no click happened; the control was blocked')
d('event', 1, a, 'retract', '--note', 'twice', ok=False)               # nothing left to void
out = d('event', 1, a, 'submitted', '--findings', findings(a, 'submitted'), '--approval', 'yes', ok=False)
check('after retract, submitted needs a fresh submit_clicked (A1)', 'before `submit_clicked`' in out)
d('window', 1, 'ok'); d('event', 1, a, 'submit_clicked')

# --- A5: a lane-written fragment with an unquoted comma is refused before the event
bad = os.path.join(STAGING, f'QB-{a}-a1-R20261006-0905-apply1.csv')
open(bad, 'w').write('question_id,label_verbatim,answer_planned\nq1,Worked here, as employee or contractor?,No\n')
out = d('event', 1, a, 'submitted', '--findings', findings(a, 'submitted'), '--approval', 'yes', ok=False)
check('unquoted fragment refuses the event (A5)', 'columns' in out and 'csv module' in out and 'done:' not in d('show', a))
os.remove(bad)
out = d('event', 1, a, 'submitted', '--findings', findings(a, 'submitted'), '--approval', 'yes')
fo = os.path.join(STAGING, f'OUTCOME-{a}-a1-R20261006-0905-apply1.csv')
fq = os.path.join(STAGING, f'QB-{a}-a1-R20261006-0905-apply1.csv')
check('submitted writes OUTCOME fragment', os.path.exists(fo))
check('submitted writes QB fragment', os.path.exists(fq))
if os.path.exists(fo):
    r = list(csv.DictReader(open(fo)))[0]
    check('OUTCOME row content', r['outcome'] == 'submitted' and r['fields'] == '3' and r['required_fields'] == '2'
          and r['confirmation_method'] == 'redirect_confirmation' and r['company'] == 'Alpha')
if os.path.exists(fq):
    qr = list(csv.DictReader(open(fq)))
    check('QB rows skip buttons, keep safe answers only', len(qr) == 3 and
          {x['label_verbatim']: x['answer_planned'] for x in qr}['How did you hear about this job?'] == 'Company Website'
          and {x['label_verbatim']: x['answer_planned'] for x in qr}['First Name'] == '')
check('missing data is printed', 'answer_key' in out and 'left blank' in out)

# existing fragment is never overwritten
lane_to_submit_clicked(b)
open(os.path.join(RUNS, f'INTENT-{b}-a1-R20261006-0905-apply1.md'), 'w').write(INTENT)
pre = os.path.join(STAGING, f'OUTCOME-{b}-a1-R20261006-0905-apply1.csv')
open(pre, 'w').write('lane wrote this\n')
out = d('event', 1, b, 'unconfirmed', '--findings', findings(b, 'unconfirmed', 'Clicked; page unclear.'), '--approval', 'yes')
check('existing fragment kept', open(pre).read() == 'lane wrote this\n' and 'kept as is' in out)
check('unconfirmed writes the QB fragment', os.path.exists(os.path.join(STAGING, f'QB-{b}-a1-R20261006-0905-apply1.csv')))

# no INTENT -> OUTCOME only, and says QB is missing
lane_to_submit_clicked(c)
out = d('event', 1, c, 'submitted', '--findings', findings(c, 'submitted'), '--approval', 'yes')
check('no INTENT: OUTCOME written, QB reported missing', os.path.exists(os.path.join(STAGING, f'OUTCOME-{c}-a1-R20261006-0905-apply1.csv'))
      and not os.path.exists(os.path.join(STAGING, f'QB-{c}-a1-R20261006-0905-apply1.csv')) and 'QB fragment NOT written' in out)

# --- 1. confirm
queue = lambda status: open(q, 'w').write('A,B,C,D,E,F,G,H,I,J,K\n' + ''.join(
    f'{j},{status if j == b else "Submitted"},,,,,,x,,Yes,3\n' for j in (a, b, c)))
d('confirm', a, '--note', 'x', ok=False)               # submitted, not unconfirmed
d('confirm', b, ok=False)                              # note required
queue('Submitted')                                     # hand-corrected row for the unconfirmed card
plan = d('queue-plan', '--queue', q)
check('before confirm, queue-plan reverts the hand-corrected row', f'{b} · B: "Submitted" → "Submitted-unconfirmed"' in plan)
d('confirm', b, '--note', 'mail receipt 12:14 CT')
plan = d('queue-plan', '--queue', q)
check('after confirm, queue-plan keeps Submitted', f'{b} · B:' not in plan)
d('confirm', b, '--note', 'again', ok=False)
board = d('board')
check('board counts confirmed as submitted', 'submitted 3 · unconfirmed 0' in board)

# --- 2. lane external
d('event', 1, e, 'external', ok=False)                 # note required
d('claim', 1, '--ahead', 3)
d('event', 1, e, 'awaiting_yes')
out = d('event', 1, e, 'external', '--note', 'the operator clicked Submit in this window; page says Application received')
check('lane external ends the card', 'externally submitted' in out and 'done:external' in d('show', e))
fe = os.path.join(STAGING, f'OUTCOME-{e}-a1-R20261006-0905-apply1.csv')
check('external writes the OUTCOME fragment (A4)', os.path.exists(fe) and
      (lambda r: r['outcome'] == 'submitted' and 'user_submit' in r['human_interventions'])(list(csv.DictReader(open(fe)))[0]))
check('finished card cannot be claimed or reopened', 'NOTHING TO CLAIM' in d('claim', 1)
      and 'already finished' in d('open', e, ok=False) and 'already finished' in d('hold', e, ok=False)
      and 'already finished' in d('external', e, '--note', 'x', ok=False))
d('event', 1, e, 'released', ok=False)
q2 = open(q).read() + f'{e},Ready,,,,,,,,Yes,3\n'
open(q, 'w').write(q2)
plan = d('queue-plan', '--queue', q)
check('queue-plan writes Submitted for external', f'{e} · B: "Ready" → "Submitted"' in plan)

# --- A3: trace.py takes a JT- attempt id
for f in ('trace.py', 'import-inbox.py'):
    if not os.path.exists(os.path.join(TMP, 'tools', f)):
        os.symlink(os.path.join(HERE, f), os.path.join(TMP, 'tools', f))
tr = lambda att: subprocess.run([sys.executable, os.path.join(TMP, 'tools', 'trace.py'), 'R20261006-0905-apply1', att, 'start'],
                                capture_output=True, text=True, env=ENV, cwd=TMP)
check('trace.py accepts a JT- attempt id (A3)', tr('JT-59de07b153-a1').returncode == 0 and os.path.exists(
    os.path.join(TMP, 'AppApply-Capture', 'traces', 'R20261006-0905-apply1', 'TRACE-JT-59de07b153-a1.jsonl')))
check('trace.py still rejects a malformed id', tr('JT-zz-a1').returncode != 0)

# --- A8: preflight percent-encodes non-ASCII URLs
sys.path.insert(0, HERE)
import preflight
check('preflight ascii_url encodes a Unicode ellipsis and keeps %-escapes (A8)',
      preflight.ascii_url('https://x.com/a%20b?q=1&r=\u2026') == 'https://x.com/a%20b?q=1&r=%E2%80%A6')

# --- PII hit in fragments' sources is refused
print('\n' + ('ALL PASSED' if not fails else 'FAILURES:\n  ' + '\n  '.join(fails)))
sys.exit(1 if fails else 0)
