#!/usr/bin/env python3
"""Shared helpers for ops/tools: configuration, paths, run and job ids, time, and the small functions every tool
used to carry its own copy of.

Configuration, first hit wins:
  1. environment variables: JOBHUNT_OPS (data root), JOBHUNT_CONFIG (config file), JOBHUNT_PII_PATTERNS,
     JOBHUNT_GOOGLE_TOKEN, JOBHUNT_MAIL_DIR, JOBHUNT_TZ
  2. config.toml (copy config.example.toml) at the repository root, or the file JOBHUNT_CONFIG names
  3. built-in defaults: the data root is the `ops/` folder that holds this `tools/` folder

Nothing personal lives in this file or in config.example.toml. The real config.toml, the token file and the private
PII pattern file stay outside git (.gitignore blocks config.toml, *token*, *credentials*).
"""
import csv
import datetime
import functools
import hashlib
import os
import re
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
OPS_DIR = os.path.dirname(TOOLS_DIR)
KIT_ROOT = os.path.dirname(OPS_DIR)

# A run id: R<YYYYMMDD>-<HHMM>-<kind>[N], e.g. R20260924-0900-orch, R20260924-0905-apply1
RUN_RE = re.compile(r'R(\d{4})(\d{2})(\d{2})-\d{4}-[a-z]+\d?')
# A job id: a LinkedIn posting number, or a job-tools key (JT- plus 10 hex) for jobs found by the search tools
JOB_ID_RE = r'\d{8,}|JT-[0-9a-f]{10}'
JOB_ID_FULL = re.compile(JOB_ID_RE)
ATTEMPT_RE = re.compile(r'(' + JOB_ID_RE + r'|[A-Za-z0-9_]+)-a(\d+)')


# ---------- config ----------

def _parse_toml_minimal(text):
    """A fallback for Python < 3.11 without tomllib: [section] headers and key = "string" | number | true/false lines.
    Enough for config.example.toml; anything fancier needs tomllib or tomli."""
    out, section = {}, None
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip() if not raw.strip().startswith('"') else raw.strip()
        if not line:
            continue
        m = re.fullmatch(r'\[([A-Za-z0-9_.-]+)\]', line)
        if m:
            section = out.setdefault(m.group(1), {})
            continue
        m = re.fullmatch(r'([A-Za-z0-9_-]+)\s*=\s*(.+)', line)
        if not m or section is None:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1].replace('\\"', '"')
        elif val in ('true', 'false'):
            val = val == 'true'
        elif re.fullmatch(r'-?\d+', val):
            val = int(val)
        elif re.fullmatch(r'-?\d+\.\d+', val):
            val = float(val)
        elif val.startswith('[') and val.endswith(']'):
            val = [v.strip().strip('"') for v in val[1:-1].split(',') if v.strip()]
        section[key] = val
    return out


def config_path():
    return os.environ.get('JOBHUNT_CONFIG') or os.path.join(KIT_ROOT, 'config.toml')


@functools.lru_cache(maxsize=1)
def load_config():
    """The parsed config.toml, or {} when there is none. Never raises on a missing file."""
    path = config_path()
    if not os.path.exists(path):
        return {}
    with open(path, 'rb') as fh:
        data = fh.read()
    try:
        import tomllib  # Python 3.11+
        return tomllib.loads(data.decode('utf-8'))
    except ImportError:
        pass
    try:
        import tomli  # type: ignore
        return tomli.loads(data.decode('utf-8'))
    except ImportError:
        return _parse_toml_minimal(data.decode('utf-8'))


def cfg(section, key, default=None):
    return load_config().get(section, {}).get(key, default)


def expand(path):
    return os.path.expanduser(os.path.expandvars(path)) if path else path


# ---------- paths ----------

def ops_root():
    """The data root: the folder that holds Runs/, AppApply-Capture/, Resume/ and the two .gsheet pointers."""
    return expand(os.environ.get('JOBHUNT_OPS') or cfg('paths', 'ops_root') or OPS_DIR)


REPO = ops_root()
RUNS = os.path.join(REPO, 'Runs')
CAPTURE = os.path.join(REPO, 'AppApply-Capture')


def pii_patterns_path():
    return expand(os.environ.get('JOBHUNT_PII_PATTERNS') or cfg('paths', 'pii_patterns')
                  or '~/.config/jobhunt/pii_patterns.json')


def google_token_path():
    return expand(os.environ.get('JOBHUNT_GOOGLE_TOKEN') or cfg('paths', 'google_token')
                  or '~/.config/jobhunt/google_token.json')


def mail_dir():
    return expand(os.environ.get('JOBHUNT_MAIL_DIR') or cfg('paths', 'mail_export_dir') or '~/Job-Mail-Export')


def transcripts_glob():
    return expand(os.environ.get('JOBHUNT_TRANSCRIPTS_GLOB') or cfg('paths', 'transcripts_glob')
                  or '~/.claude/projects/*/*.jsonl')


def sheet_id(which):
    """'job_queue' or 'jd_archive' -> the spreadsheet id from config, or '' when unset."""
    return os.environ.get(f'JOBHUNT_{which.upper()}_ID') or cfg('sheets', f'{which}_id') or ''


def queue_tab():
    return cfg('sheets', 'queue_tab') or 'Queue'


def browser_profile():
    return cfg('browser', 'profile_name') or 'App Apply'


def browser_device_id():
    return cfg('browser', 'profile_device_id') or ''


def lane_tab_url():
    return cfg('browser', 'lane_tab_url') or 'https://example.com/'


# ---------- time ----------

def local_tz():
    from zoneinfo import ZoneInfo
    name = os.environ.get('JOBHUNT_TZ') or cfg('run', 'timezone') or 'UTC'
    try:
        return ZoneInfo(name)
    except Exception:
        return datetime.timezone.utc


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def utc_iso(t=None, timespec='seconds'):
    return (t or now_utc()).isoformat(timespec=timespec).replace('+00:00', 'Z')


def local_stamp(t=None):
    """'YYYY-MM-DD HH:MM <zone abbreviation>' in the configured zone."""
    t = (t or now_utc()).astimezone(local_tz())
    return t.strftime('%Y-%m-%d %H:%M ') + (t.tzname() or 'UTC')


def today_local():
    return now_utc().astimezone(local_tz()).strftime('%Y-%m-%d')


# ---------- run and job ids ----------

def run_match(run_id):
    """The RUN_RE match for a full run id, or None."""
    return RUN_RE.fullmatch(run_id or '')


def run_date(run_id):
    """'YYYY-MM-DD' from a run id, or None."""
    m = RUN_RE.match(run_id or '')
    return f'{m.group(1)}-{m.group(2)}-{m.group(3)}' if m else None


def run_day_dir(run_id):
    """Runs/<YYYY-MM-DD>/ for a run id (not created)."""
    d = run_date(run_id)
    return os.path.join(RUNS, d) if d else None


def is_job_id(s):
    return bool(JOB_ID_FULL.fullmatch((s or '').strip()))


def normalize_text(text):
    """Lowercase, punctuation to spaces, whitespace collapsed. The one normaliser for keys and matching."""
    return re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).strip()


COMPANY_SUFFIXES = ('inc', 'llc', 'ltd', 'corp', 'co', 'company', 'corporation', 'plc', 'lp', 'group', 'holdings',
                    'technologies', 'technology', 'services', 'solutions', 'the')


def slug(s, limit=80):
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')[:limit] or 'unknown'


def company_key(name):
    """A company name reduced to a comparable key: lowercase slug with trailing legal suffixes removed."""
    words = slug(name).split('-')
    while len(words) > 1 and words[-1] in COMPANY_SUFFIXES:
        words.pop()
    return '-'.join(words)


def job_tools_key(company, title, location):
    """The JT- key for a job the search tools found: JT- plus the first 10 hex of SHA-1 over normalised
    company|title|location (lowercase, punctuation stripped, whitespace collapsed)."""
    raw = '|'.join(normalize_text(x) for x in (company, title, location))
    return 'JT-' + hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]


# ---------- small shared functions ----------

def die(msg, code=2):
    print('ERROR: ' + msg, file=sys.stderr)
    sys.exit(code)


def atomic_csv(path, header, rows):
    """Write header + rows to path via a temp file and a rename, so a reader never sees half a file."""
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    os.replace(tmp, path)


def col_letter(i):
    """0 -> 'A', 25 -> 'Z', 26 -> 'AA'."""
    s = ''
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--get':          # shell scripts: python3 common.py --get paths.backup_dir
        sec, _, key = sys.argv[2].partition('.')
        val = cfg(sec, key)
        print(expand(val) if isinstance(val, str) else ('' if val is None else val))
        sys.exit(0)
    print('config  :', config_path(), '(present)' if os.path.exists(config_path()) else '(absent, defaults in use)')
    print('ops root:', REPO)
    print('pii     :', pii_patterns_path())
    print('token   :', google_token_path())
    print('mail    :', mail_dir())
    print('tz      :', local_tz())
    print('queue id:', sheet_id('job_queue') or '(unset)')
