#!/usr/bin/env python3
"""One job key and one company/title normaliser for every ops tool.

Key rule: a job's key is its **LinkedIn job number** whenever one is known (from the job URL or
given directly); only a job with no LinkedIn number gets `JT-<10 hex>` = the first 10 hex of SHA-1 of
`normalize(company)|normalize(title)|normalize(location)`. The hash is the one docs/10 defines, so every
existing JT- key reproduces. Existing JT- rows that are really LinkedIn jobs are NOT rekeyed: their number
sits in `AppApply-Capture/jt-keys.csv` (`board_id`), and `aliases()` maps one to the other for dedupe.

  normalize(text)        lowercase, every run of non [a-z0-9] -> one space, trimmed. Used for the JT hash and titles.
  company_norm(text)     normalize() after dropping corporate filler words (inc, llc, corp, group, services, the, ...).
                         Identical to the old mail_track.norm, so mail matching does not move.
  company_key(name)      company_norm() joined with '-', for lock / group names (dispatch board).
  linkedin_id(text)      the LinkedIn job number in a URL (jobs/view/<slug->N, currentJobId=N) or a bare number, else ''.
  jt_key(co, title, loc) the JT- key.
  job_key(co, title, loc, url='', linkedin='')   the key under the rule above.
  is_job_id(s)           s is a Queue Job ID (8+ digits or JT- + 10 hex); same pattern as queue_api.JOB_ID_RE.
  aliases(path=None)     {JT key: LinkedIn number} and {number: JT key} from jt-keys.csv, for "same job?" checks.

  python3 tools/jobkey.py key "<company>" "<title>" "<location>" [<url>]     print the key
  python3 tools/jobkey.py norm "<text>"                                      print normalize / company_norm / company_key
Stdlib only. A copy of the key rule lives in discover/src/jobhunt_tools/keys.py (the search tools run without
this folder); tools/test_jobkey.py checks the two agree.
"""
import csv, hashlib, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

REPO = common.REPO
JT_KEYS = os.path.join('AppApply-Capture', 'jt-keys.csv')
JT_KEYS_HEADER = ['jt_key', 'board', 'board_id', 'company', 'title', 'first_seen_run', 'location']
JOB_ID_RE = r'\d{8,}|JT-[0-9a-f]{10}'
FILLER = r'\b(inc|llc|ltd|corp|corporation|co|company|group|holdings|technologies|technology|services|solutions|the)\b'
_LINKEDIN = (re.compile(r'linkedin\.com/(?:comm/)?jobs/view/(?:[^/?#\s]*?-)?(\d{6,})', re.I),
             re.compile(r'[?&](?:currentJobId|jobId)=(\d{6,})', re.I))


def normalize(text):
    return re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).strip()


def company_norm(text):
    return normalize(re.sub(FILLER, ' ', (text or '').lower()))


def company_key(name):
    k = '-'.join(company_norm(name).split())[:80]
    return k or (re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')[:80] or 'unknown')


def linkedin_id(text):
    s = (text or '').strip()
    if re.fullmatch(r'\d{6,}', s):
        return s
    for rx in _LINKEDIN:
        m = rx.search(s)
        if m:
            return m.group(1)
    return ''


def jt_key(company, title, location):
    raw = '|'.join(normalize(x) for x in (company, title, location))
    return 'JT-' + hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]


def job_key(company, title, location, url='', linkedin=''):
    return linkedin_id(linkedin) or linkedin_id(url) or jt_key(company, title, location)


def is_job_id(s):
    return bool(re.fullmatch(JOB_ID_RE, (s or '').strip()))


def read_jt_keys(path=None):
    path = path or os.path.join(REPO, JT_KEYS)
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8', newline='') as fh:
        return list(csv.DictReader(fh))


def aliases(path=None):
    """(jt_to_number, number_to_jt) from jt-keys.csv rows whose board_id is a LinkedIn number."""
    jt2n, n2jt = {}, {}
    for r in read_jt_keys(path):
        n = linkedin_id(r.get('board_id', ''))
        if n and r.get('jt_key'):
            jt2n[r['jt_key']] = n
            n2jt.setdefault(n, r['jt_key'])
    return jt2n, n2jt


def same_job(a, b, path=None):
    """True when two Job IDs are one job: equal, or a JT- key whose recorded LinkedIn number is the other."""
    if a == b:
        return True
    jt2n, _ = aliases(path)
    return jt2n.get(a) == b or jt2n.get(b) == a


def main(argv):
    if len(argv) >= 4 and argv[0] == 'key':
        print(job_key(argv[1], argv[2], argv[3], argv[4] if len(argv) > 4 else ''))
        return 0
    if len(argv) == 2 and argv[0] == 'norm':
        print(f'normalize:    {normalize(argv[1])}\ncompany_norm: {company_norm(argv[1])}\ncompany_key:  {company_key(argv[1])}')
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
