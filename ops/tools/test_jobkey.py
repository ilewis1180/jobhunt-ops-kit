#!/usr/bin/env python3
"""Offline checks for tools/jobkey.py: the JT- hash reproduces the docs/10 rule and every key in a fixture
jt-keys.csv, the company normaliser equals the mail-matching normaliser, dispatch and mail_track use it, the
LinkedIn-number-first rule, the jt-keys aliases, and agreement with discover/src/jobhunt_tools/keys.py.
Never touches a Sheet or the real data root (JOBHUNT_OPS points at a temp tree). Usage: python3 ops/tools/test_jobkey.py"""
import csv, hashlib, importlib.util, os, re, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix='jobkey-test-')
os.environ['JOBHUNT_OPS'] = TMP
os.makedirs(os.path.join(TMP, 'AppApply-Capture'))
REPO = TMP
sys.path.insert(0, HERE)
import jobkey  # noqa: E402

# Fixture: two jobs the search tools found that also have a LinkedIn number (board_id), one with none.
AF = jobkey.jt_key('Alpha Pay', 'Small Business Account Executive II', 'Houston, TX')
EZ = jobkey.jt_key('Ezee Fiber', 'Account Executive', 'Houston, TX')
with open(os.path.join(TMP, 'AppApply-Capture', 'jt-keys.csv'), 'w', newline='') as fh:
    csv.writer(fh, lineterminator='\n').writerows([
        ['jt_key', 'board', 'board_id', 'company', 'title', 'first_seen_run', 'location'],
        [AF, 'linkedin', '4476880256', 'Alpha Pay', 'Small Business Account Executive II', 'R20261012-1203-discover', 'Houston, TX'],
        [EZ, 'linkedin', '4450039300', 'Ezee Fiber', 'Account Executive', 'R20261012-1203-discover', 'Houston, TX'],
        ['JT-84948a8c54', 'indeed', '', 'Acme, Inc.', 'Account Executive', 'R20261012-1203-discover', 'Houston, TX']])
fails = []


def check(name, cond):
    print(('ok   ' if cond else 'FAIL ') + name)
    if not cond:
        fails.append(name)


# The rules as the discover docs first wrote them (copied verbatim), to prove nothing moved.
def old_discover_norm(s): return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s.lower())).strip()
def old_discover_key(co, t, loc): return 'JT-' + hashlib.sha1(f'{old_discover_norm(co)}|{old_discover_norm(t)}|{old_discover_norm(loc)}'.encode()).hexdigest()[:10]
OLD_SUFFIX = r'\b(inc|llc|ltd|corp|corporation|co|company|group|holdings|technologies|technology|services|solutions|the)\b'
def old_mail_norm(s): return re.sub(r'[^a-z0-9]+', ' ', re.sub(OLD_SUFFIX, ' ', (s or '').lower())).strip()


SAMPLES = ['Affirm', 'Acme, Inc.', 'SHI International Corp.', 'Tata Consultancy Services', 'The Home Depot',
           'KULR Technology Group, Inc (NYSE: KULR)', 'Mirum Pharmaceuticals, Inc.', 'Small Business Account Executive II',
           'Territory Account Executive, SMB - Houston, TX', 'Technical architect – Sales and Solutions Engineering',
           'Houston, TX', '  Remote,  US ', 'Re: Your application to Co-op Co.', 'Ernst & Young LLP', '', 'Café Résumé']

check('normalize == the docs/10 normaliser on samples', all(jobkey.normalize(s) == old_discover_norm(s) for s in SAMPLES))
check('jt_key == the original discover-append key on samples',
      all(jobkey.jt_key(a, b, c) == old_discover_key(a, b, c) for a in SAMPLES[:4] for b in SAMPLES[6:9] for c in SAMPLES[10:12]))
check('company_norm == the mail-matching normaliser on samples', all(jobkey.company_norm(s) == old_mail_norm(s) for s in SAMPLES))

rows = list(csv.DictReader(open(os.path.join(REPO, 'AppApply-Capture', 'jt-keys.csv'), encoding='utf-8')))
check('jt-keys.csv has the location column', rows and list(rows[0].keys()) == jobkey.JT_KEYS_HEADER)
bad = [r['jt_key'] for r in rows if jobkey.jt_key(r['company'], r['title'], r['location']) != r['jt_key']]
check(f'every jt-keys.csv key reproduces from company|title|location ({len(rows)} rows)', not bad or print(bad))

check('company_key strips filler', jobkey.company_key('Acme, Inc.') == 'acme'
      and jobkey.company_key('SHI International Corp.') == 'shi-international'
      and jobkey.company_key('Honeywell Technologies') == 'honeywell')
check('company_key falls back to the slug when only filler is left', jobkey.company_key('The Company') == 'the-company'
      and jobkey.company_key('') == 'unknown')

L = jobkey.linkedin_id
check('linkedin_id: view URL, slug URL, currentJobId, bare number, none',
      L('https://www.linkedin.com/jobs/view/4476880256/') == '4476880256'
      and L('https://www.linkedin.com/jobs/view/senior-ae-at-x-4012345678?x=1') == '4012345678'
      and L('https://www.linkedin.com/jobs/search/?currentJobId=4450039300&f=1') == '4450039300'
      and L('4479206600') == '4479206600' and L('https://jobs.ashbyhq.com/legora/251bbf9e') == ''
      and L('JT-59de07b153') == '')
check('job_key: the LinkedIn number wins when present', jobkey.job_key('Affirm', 'AE', 'Houston, TX',
      'https://www.linkedin.com/jobs/view/4476880256/') == '4476880256')
check('job_key: JT- only without a number', jobkey.job_key('Acme, Inc.', 'Account Executive', 'Houston, TX',
      'https://boards.greenhouse.io/acme/jobs/1') == 'JT-84948a8c54')
check('is_job_id', jobkey.is_job_id('4476880256') and jobkey.is_job_id('JT-59de07b153')
      and not jobkey.is_job_id('src-0123456789abcdef') and not jobkey.is_job_id('JT-XYZ'))

jt2n, n2jt = jobkey.aliases()
check('aliases: JT key <-> 4476880256 (a job found twice)', jt2n.get(AF) == '4476880256' and n2jt.get('4476880256') == AF)
check('same_job across the alias, not across strangers', jobkey.same_job(AF, '4476880256')
      and jobkey.same_job('4450039300', EZ) and not jobkey.same_job(AF, '4450039300'))

import queue_api  # noqa: E402
check('queue_api.JOB_ID_RE == jobkey.JOB_ID_RE', queue_api.JOB_ID_RE == jobkey.JOB_ID_RE)
import dispatch  # noqa: E402
check('dispatch.company_key is the shared one', all(dispatch.company_key(s) == jobkey.company_key(s) for s in SAMPLES))
import mail_track  # noqa: E402
check('mail_track.norm is the shared one', all(mail_track.norm(s) == jobkey.company_norm(s) for s in SAMPLES))

winnie = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'discover', 'src', 'jobhunt_tools', 'keys.py')
if os.path.exists(winnie):
    spec = importlib.util.spec_from_file_location('discover_keys', winnie)
    wk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wk)
    urls = ['', 'https://www.linkedin.com/jobs/view/4476880256/', 'https://www.linkedin.com/jobs/search/?currentJobId=4450039300',
            'https://www.indeed.com/viewjob?jk=abc123', 'https://boards.greenhouse.io/acme/jobs/1']
    check('discover keys.job_key == jobkey.job_key (one key scheme)',
          all(wk.job_key(a, b, c, u) == jobkey.job_key(a, b, c, u) for a in SAMPLES[:5] for b in SAMPLES[6:8]
              for c in SAMPLES[10:12] for u in urls))
    check('discover keys.normalize == jobkey.normalize', all(wk.normalize(s) == jobkey.normalize(s) for s in SAMPLES))
else:
    print('skip discover keys.py (not in this tree)')

print('\n' + ('ALL PASSED' if not fails else 'FAILURES:\n  ' + '\n  '.join(fails)))
sys.exit(1 if fails else 0)
