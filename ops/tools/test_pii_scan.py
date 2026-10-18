#!/usr/bin/env python3
"""Offline checks for tools/pii_scan.py: both pattern-file shapes, the canary, the URL-decoded variant, fail-closed, and the
public gate on this tools folder. Usage: python3 tools/test_pii_scan.py"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix='pii-test-')
PY = sys.executable
fails = []


def check(name, cond):
    print(('ok   ' if cond else 'FAIL ') + name)
    if not cond:
        fails.append(name)


def scan(patterns, *paths):
    env = dict(os.environ, JOBHUNT_PII_PATTERNS=patterns, JOBHUNT_OPS=TMP, JOBHUNT_CONFIG=os.path.join(TMP, 'none.toml'))
    r = subprocess.run([PY, os.path.join(HERE, 'pii_scan.py')] + list(paths), capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


legacy = os.path.join(TMP, 'legacy.json')
json.dump({'pii_regex': r'Pat\s+Example|pat\.example(?:@|%40)example\.org|\(?555\)?[\s.-]?0100[\s.-]?0000|\b12345\b|\b12 Sample Street\b'}, open(legacy, 'w'))
named = os.path.join(TMP, 'named.json')
json.dump({'patterns': [{'name': 'email', 'regex': r'[\w.+-]+(?:@|%40)[\w-]+\.\w+'}, {'name': 'secret-word', 'regex': r'xyzzy'}]}, open(named, 'w'))
clean = os.path.join(TMP, 'clean.txt'); open(clean, 'w').write('job 4466598786 submitted at 14:03, answer_key identity.email\n')
dirty = os.path.join(TMP, 'dirty.txt'); open(dirty, 'w').write('contact pat.example' + '%40' + 'example.org or (555) 0100-0000 today\n')  # built from parts: this file must pass the gate
canary = os.path.join(TMP, 'canary.txt'); open(canary, 'w').write('token PIISCAN-CANARY-' + '0000\n')

rc, out = scan(legacy, clean)
check('legacy shape: clean file passes (a bare job id is not a phone)', rc == 0 and '0 hit(s)' in out)
rc, out = scan(legacy, dirty)
check('legacy shape: URL-decoded email and bracketed phone are caught, named by kind', rc == 1 and 'pii-email-1' in out and 'pii-phone-1' in out
      and 'example.org' not in out.split('pii_scan:')[0])
rc, out = scan(named, dirty)
check('named shape: hit reported under its own name', rc == 1 and 'dirty.txt:1: email' in out)
rc, out = scan(named, canary)
check('canary fires', rc == 1 and 'test-canary' in out)
rc, out = scan(os.path.join(TMP, 'missing.json'), clean)
check('fails closed without a pattern file (exit 2)', rc == 2 and 'cannot load' in out)
rc, out = scan(legacy, '--patterns', named, dirty)
check('--patterns overrides the configured file', rc == 1 and 'dirty.txt:1: email' in out and 'pii-phone' not in out)
rc, out = scan(legacy, '--patterns', os.path.join(HERE, 'pii_patterns.public.json'), HERE)
check('public gate: this tools folder is clean', rc == 0, )
if rc != 0:
    print(out)
# --attempt accepts a JT- id
os.makedirs(os.path.join(TMP, 'Runs', '2026-10-06'))
open(os.path.join(TMP, 'Runs', '2026-10-06', 'INTENT-JT-59de07b153-a1-R20261006-0905-apply1.md'), 'w').write('# INTENT\nclean\n')
rc, out = scan(legacy, '--attempt', 'R20261006-0905-apply1', 'JT-59de07b153-a1')
check('--attempt accepts a JT- attempt id and finds its files', rc == 0 and 'INTENT-JT-59de07b153-a1' in out)
print('\n' + ('ALL PASSED' if not fails else 'FAILURES:\n  ' + '\n  '.join(fails)))
sys.exit(1 if fails else 0)
