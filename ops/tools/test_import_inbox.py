#!/usr/bin/env python3
"""Offline checks for tools/import-inbox.py routing: numeric fragments go to the main CSVs, JT- (Phase 0) fragments go to the
-jt CSVs with a header, and a non-numeric / mismatched job_id is still blocked. Throwaway tree (JOBHUNT_OPS); never touches real data.
Usage: python3 tools/test_import_inbox.py"""
import csv, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix='import-test-')
ENV = dict(os.environ, JOBHUNT_OPS=TMP, JOBHUNT_PII_PATTERNS=os.path.join(TMP, 'pii.json'), JOBHUNT_CONFIG=os.path.join(TMP, 'none.toml'))
open(ENV['JOBHUNT_PII_PATTERNS'], 'w').write('{"pii_regex": "ZZPIIZZ"}')
STG = os.path.join(TMP, 'AppApply-Capture', 'staging')
os.makedirs(STG)
CAP = os.path.join(TMP, 'AppApply-Capture')
RUN = 'R20261012-1344-apply1'
fails = []


def check(name, cond):
    print(('ok   ' if cond else 'FAIL ') + name)
    if not cond:
        fails.append(name)


def frag(name, header, rows):
    with open(os.path.join(STG, name), 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


OH = ['run_id', 'attempt_id', 'job_id', 'company']
QH = ['question_id', 'label_verbatim', 'job_id']
frag(f'OUTCOME-4477851824-a1-{RUN}.csv', OH, [[RUN, '4477851824-a1', '4477851824', 'Alpha']])
frag(f'OUTCOME-JT-2b9bf7e17e-a1-{RUN}.csv', OH, [[RUN, 'JT-2b9bf7e17e-a1', 'JT-2b9bf7e17e', 'Bravo']])
frag(f'OUTCOME-JT-59de07b153-a1-{RUN}.csv', OH, [[RUN, 'JT-59de07b153-a1', 'JT-59de07b153', 'Charlie']])
frag(f'QB-JT-2b9bf7e17e-a1-{RUN}.csv', QH, [['q1', 'Worked here, as employee?', 'JT-2b9bf7e17e']])
frag(f'QB-JT-aaaaaaaaaa-a1-{RUN}.csv', QH, [['q1', 'x', 'JT-bbbbbbbbbb']])          # key does not match the name
frag(f'QB-4474602920-a1-{RUN}.csv', QH, [['q1', 'x', 'Delta']])                  # still blocked
r = subprocess.run([sys.executable, os.path.join(HERE, 'import-inbox.py'), '--from', 'AppApply-Capture/staging'],
                   capture_output=True, text=True, env=ENV, cwd=TMP)
out = r.stdout + r.stderr
rd = lambda f: list(csv.reader(open(os.path.join(CAP, f)))) if os.path.exists(os.path.join(CAP, f)) else []
check('numeric OUTCOME goes to outcomes.csv (no JT row)', [x[2] for x in rd('outcomes.csv')] == ['4477851824'])
check('JT- OUTCOMEs go to outcomes-jt.csv with one header', [x[2] for x in rd('outcomes-jt.csv')] == ['job_id', 'JT-2b9bf7e17e', 'JT-59de07b153'])
check('JT- QB goes to question-bank-observations-jt.csv with a header', len(rd('question-bank-observations-jt.csv')) == 2
      and rd('question-bank-observations-jt.csv')[0][0] == 'question_id')
check('JT- key not matching the file name is blocked', f'QB-JT-aaaaaaaaaa-a1-{RUN}.csv' in out and 'not a JT-' in out)
check('non-numeric job_id still blocked', 'Delta' in out and 'not numeric' in out)
check('blocked files stay in staging', os.path.exists(os.path.join(STG, f'QB-4474602920-a1-{RUN}.csv')))
print('\n' + ('ALL PASSED' if not fails else 'FAILURES:\n  ' + '\n  '.join(fails)))
sys.exit(1 if fails else 0)
