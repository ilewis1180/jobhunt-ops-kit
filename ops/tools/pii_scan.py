#!/usr/bin/env python3
"""Scan files for personal values before they are committed, merged or reported (08 §1, §3).

The patterns come from the private pattern file (config paths.pii_patterns, default ~/.config/jobhunt/pii_patterns.json,
override JOBHUNT_PII_PATTERNS, or --patterns <file>), the same file tools/import-inbox.py and
tools/build-question-bank.py read, so the three can never drift apart. No personal value lives in the repo (00 hard
rule 8); the pattern file sits next to the Google token with mode 600. Two file shapes are accepted
(pii_patterns.example.json): `pii_regex`, one alternation whose top-level alternatives get a neutral name from their
shape (pii-phone-1, pii-email-2, pii-street-1, pii-zip-1, ...), and/or `patterns`, a list of {name, regex}. The matched
text is never printed.

Usage:
  python3 tools/pii_scan.py [--patterns <file>] <file|dir> [...]   files; directories are walked recursively
  python3 tools/pii_scan.py --attempt <RunID> <JobID>-a<N>   one attempt (JobID numeric or JT-): its trace, PAGE files,
                                                             Runs/*/ files (INTENT, findings, jd) and staging fragments
  python3 tools/pii_scan.py --canary                         print a harmless test token; a file holding it is a hit
                                                             ("test-canary"), which proves the scanner fires
  python3 tools/pii_scan.py --patterns tools/pii_patterns.public.json .   the public-safe gate CI runs on this repo

Output: `file:line: <pattern name>` per hit on stdout; a one-line summary on stderr.
Exit:   0 clean · 1 at least one hit · 2 usage error, missing path, nothing to scan, or patterns not loadable.
Matching is case-insensitive, and each line is also tried URL-decoded with "()" removed and spaces collapsed, so
"(NNN) NNN-NNNN" phones and %40 emails are caught. Binary files are skipped (counted on stderr).
"""
import functools, glob, json, os, re, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common  # noqa: E402

REPO = common.REPO
CANARY = re.compile(r'PIISCAN-CANARY-\d{4}')  # this source line does not match itself
SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', '.pytest_cache'}


PII_FILE = common.pii_patterns_path()
RUN = common.RUN_RE


def set_pattern_file(path):
    """Use another pattern file (--patterns). Clears the caches so the next scan loads it."""
    global PII_FILE
    PII_FILE = path
    pii_config.cache_clear()
    patterns.cache_clear()


@functools.lru_cache(maxsize=1)
def pii_config():
    """The pattern file's JSON. Any failure raises: the caller fails closed."""
    with open(PII_FILE, encoding='utf-8') as fh:
        cfg = json.load(fh)
    if 'pii_regex' not in cfg and not cfg.get('patterns'):
        raise ValueError('pattern file has neither pii_regex nor patterns')
    return cfg


def pii_regex():
    """One regex covering everything in the file: pii_regex plus every named pattern."""
    cfg = pii_config()
    parts = [cfg['pii_regex']] if cfg.get('pii_regex') else []
    parts += [f"(?:{p['regex']})" for p in cfg.get('patterns') or []]
    return '|'.join(parts)


def _alternatives(pattern):
    """Split a regex at its top-level '|' (not inside [...] or (...))."""
    parts, cur, depth, in_cls, esc = [], '', 0, False, False
    for ch in pattern:
        if esc:
            cur, esc = cur + ch, False
            continue
        if ch == '\\':
            cur, esc = cur + ch, True
            continue
        if in_cls:
            in_cls = ch != ']'
        elif ch == '[':
            in_cls = True
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == '|' and depth == 0:
            parts.append(cur)
            cur = ''
            continue
        cur += ch
    return parts + [cur]


def _kind(alt):
    """A neutral category for one alternative, from its shape only (never its text)."""
    lit = re.sub(r'\\[bBAZdDsSwW]', '', alt)
    lit = re.sub(r'\[(?:\\.|[^\]])*\]', '', lit)
    lit = re.sub(r'\{\d+(?:,\d*)?\}|[?*+()^$|]', '', lit).replace('\\', '')
    digits = sum(c.isdigit() for c in lit)
    letters = sum(c.isalpha() for c in lit)
    if '@' in lit:
        return 'email'
    if not letters and digits >= 7:
        return 'phone'
    if not letters and digits == 5:
        return 'zip'
    if letters and digits:
        return 'street'
    return 'name' if letters else 'value'


@functools.lru_cache(maxsize=1)
def patterns():
    """[(name, compiled)] for each alternative or named pattern, the whole regex, and the test canary."""
    cfg = pii_config()
    flags = re.IGNORECASE
    whole = re.compile(pii_regex(), flags)
    named, counts = [], {}
    if cfg.get('pii_regex'):
        try:
            for alt in _alternatives(cfg['pii_regex']):
                kind = _kind(alt)
                counts[kind] = counts.get(kind, 0) + 1
                named.append((f'pii-{kind}-{counts[kind]}', re.compile(alt, flags)))
        except re.error:
            named = []  # can't split cleanly: fall back to the whole regex under one name
    for p in cfg.get('patterns') or []:
        named.append((p['name'], re.compile(p['regex'], flags)))
    if not named:
        raise RuntimeError('no PII patterns')
    return named, whole


def _variants(line):
    yield line
    u = urllib.parse.unquote_plus(line)
    yield re.sub(r'\s+', ' ', u.replace('(', '').replace(')', ''))


def scan_text(text):
    """[(line_no, pattern_name)] for every hit in text. Never returns the matched text."""
    named, whole = patterns()
    hits = []
    for no, line in enumerate(text.splitlines(), 1):
        names = []
        for v in _variants(line):
            if CANARY.search(v) and 'test-canary' not in names:
                names.append('test-canary')
            if whole.search(v):
                found = [n for n, rx in named if rx.search(v)] or ['pii-value']
                names += [n for n in found if n not in names]
        hits += [(no, n) for n in names]
    return hits


def scan_file(path):
    """Hits for one file, or None if it looks binary."""
    with open(path, 'rb') as fh:
        data = fh.read()
    if b'\0' in data[:8192]:
        return None
    return scan_text(data.decode('utf-8', 'replace'))


def _same(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def expand(paths):
    """Every file under the given paths. The pattern file in use is skipped: it holds the patterns themselves."""
    files, missing = [], []
    for p in paths:
        if os.path.isfile(p):
            files.append(p)
        elif os.path.isdir(p):
            for d, subdirs, names in os.walk(p):
                subdirs[:] = sorted(s for s in subdirs if s not in SKIP_DIRS)
                files += [os.path.join(d, n) for n in sorted(names)]
        else:
            missing.append(p)
    return [f for f in files if not _same(f, PII_FILE)], missing


def attempt_files(run_id, attempt):
    """Every file one attempt wrote, as data-root-relative paths that exist."""
    if not RUN.fullmatch(run_id) or not common.ATTEMPT_RE.fullmatch(attempt):  # JT- ids carry a hyphen
        raise ValueError('expected <RunID> <JobID>-a<N>, e.g. R20260924-0900-apply1 4466598786-a1 or JT-59de07b153-a1')
    pats = [f'AppApply-Capture/traces/{run_id}/TRACE-{attempt}.jsonl',
            f'AppApply-Capture/pages/{run_id}/PAGE-{attempt}-p*.json',
            f'Runs/*/*-{attempt}-{run_id}.*',
            f'AppApply-Capture/staging/*-{attempt}-{run_id}.csv']
    found = {os.path.relpath(f, REPO) for p in pats for f in glob.glob(os.path.join(REPO, p))}
    return sorted(f for f in found if os.path.isfile(os.path.join(REPO, f)))


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 0 if argv else 2
    if argv[0] == '--canary':
        print('PIISCAN-CANARY-' + '0000')
        return 0
    if argv[0] == '--patterns':
        if len(argv) < 3:
            print('usage: pii_scan.py --patterns <file> <file|dir> [...]', file=sys.stderr)
            return 2
        set_pattern_file(argv[1])
        argv = argv[2:]
    try:
        patterns()
    except Exception as e:  # fail closed: never report "clean" without the patterns
        print(f'pii_scan: cannot load the PII patterns from {PII_FILE} ({type(e).__name__})', file=sys.stderr)
        return 2
    base = None
    if argv[0] == '--attempt':
        if len(argv) != 3:
            print('usage: pii_scan.py --attempt <RunID> <JobID>-a<N>', file=sys.stderr)
            return 2
        try:
            files, missing, base = attempt_files(argv[1], argv[2]), [], REPO
        except ValueError as e:
            print(f'pii_scan: {e}', file=sys.stderr)
            return 2
        for f in files:
            print(f'  scanning {f}', file=sys.stderr)
    else:
        files, missing = expand(argv)
    for m in missing:
        print(f'pii_scan: not found: {m}', file=sys.stderr)
    if missing or not files:
        if not files:
            print('pii_scan: nothing to scan', file=sys.stderr)
        return 2
    n_hits, binary = 0, 0
    for f in files:
        try:
            hits = scan_file(os.path.join(base, f) if base else f)
        except OSError as e:
            print(f'pii_scan: cannot read {f} ({e.strerror})', file=sys.stderr)
            return 2
        if hits is None:
            binary += 1
            continue
        for no, name in hits:
            print(f'{f}:{no}: {name}')
        n_hits += len(hits)
    note = f', {binary} binary skipped' if binary else ''
    print(f'pii_scan: {len(files)} file(s), {n_hits} hit(s){note}', file=sys.stderr)
    return 1 if n_hits else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
