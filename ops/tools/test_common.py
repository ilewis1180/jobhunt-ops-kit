#!/usr/bin/env python3
"""Offline checks for tools/common.py: config fallbacks, run and job ids, keys and normalisers. Usage: python3 tools/test_common.py"""
import os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix='common-test-')
os.environ['JOBHUNT_OPS'] = os.path.join(TMP, 'ops')
os.environ['JOBHUNT_CONFIG'] = os.path.join(TMP, 'config.toml')
open(os.environ['JOBHUNT_CONFIG'], 'w').write('[sheets]\njob_queue_id = "QUEUE_ID_1"\n[run]\ntimezone = "UTC"\n[paths]\nmail_export_dir = "~/mail-x"\n')
sys.path.insert(0, HERE)
import common  # noqa: E402

fails = []


def check(name, cond):
    print(('ok   ' if cond else 'FAIL ') + name)
    if not cond:
        fails.append(name)


check('JOBHUNT_OPS wins for the data root', common.REPO == os.path.join(TMP, 'ops') and common.RUNS.endswith('/Runs'))
check('config.toml is read (minimal parser or tomllib)', common.sheet_id('job_queue') == 'QUEUE_ID_1')
check('unset sheet id is empty, not None', common.sheet_id('jd_archive') == '')
check('paths expand ~', common.mail_dir() == os.path.expanduser('~/mail-x'))
check('run id parse', common.run_date('R20260924-0905-apply1') == '2026-09-24' and common.run_match('R20260924-0905-apply1')
      and not common.run_match('R2026-apply') and common.run_day_dir('R20260924-0905-apply1').endswith('Runs/2026-09-24'))
check('job ids: numeric and JT-', common.is_job_id('4400000001') and common.is_job_id('JT-59de07b153')
      and not common.is_job_id('JT-zz') and not common.is_job_id('4.47E+09'))
check('attempt ids: numeric and JT-', common.ATTEMPT_RE.fullmatch('4400000001-a1') and common.ATTEMPT_RE.fullmatch('JT-59de07b153-a2'))
k = common.job_tools_key('Acme, Inc.', 'Account Executive', 'Houston, TX')
check('JT key is stable across case and punctuation', k.startswith('JT-') and len(k) == 13
      and k == common.job_tools_key('ACME Inc', 'account  executive', 'houston tx'))
check('company_key drops legal suffixes', common.company_key('Acme Corporation, Inc.') == 'acme-corporation' or common.company_key('Acme Inc.') == 'acme')
check('normalize_text', common.normalize_text('  Hello, World!! ') == 'hello world')
check('col_letter', common.col_letter(0) == 'A' and common.col_letter(26) == 'AA')
check('utc_iso ends with Z', common.utc_iso().endswith('Z'))
check('local_stamp has a zone', common.local_stamp().endswith('UTC'))
os.environ.pop('JOBHUNT_CONFIG')
print('\n' + ('ALL PASSED' if not fails else 'FAILURES:\n  ' + '\n  '.join(fails)))
sys.exit(1 if fails else 0)
