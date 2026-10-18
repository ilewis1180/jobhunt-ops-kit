#!/usr/bin/env python3
"""Import capture files from an inbox folder into the ops data tree. The inbox is either a cloud-drive folder a remote
(browser-only) session wrote to (config paths.inbox_dir) or, in a parallel run, `AppApply-Capture/staging/`
(`--from`). Run at the start of every session (00 session start) and after any remote session. Idempotent and write-once:

  TRACE-<JobID>-a<N>-<RunID>.jsonl   -> AppApply-Capture/traces/<RunID>/TRACE-<JobID>-a<N>.jsonl
  PAGE-<JobID>-a<N>-p<k>-<RunID>.json -> AppApply-Capture/pages/<RunID>/PAGE-<JobID>-a<N>-p<k>.json
  DOM-<ats>-<slug>-<JobID>.html       -> AppApply-Capture/dom/<ats>/<slug>-<JobID>.html
  OUTCOME-<JobID>-a<N>-<RunID>.csv    -> appended (minus header) to AppApply-Capture/outcomes.csv
  QB-<RunID>.csv                      -> appended (minus header) to AppApply-Capture/question-bank-observations.csv
  OUTCOME-JT-<10 hex>-a<N>-<RunID>.csv, QB-JT-…  (Phase 0 jobs, no LinkedIn number) -> AppApply-Capture/outcomes-jt.csv and
                                         question-bank-observations-jt.csv, header written on first use. The numeric guard
                                         stays for the main files: the dashboard keys on a number, so a JT- row there would
                                         match no job. The dashboard ignores the -jt files until it learns JT- keys.
  anything else containing R<YYYYMMDD>-  -> Runs/<YYYY-MM-DD>/<name>
Every imported file is scanned for personal values first (the private PII patterns, common.pii_patterns_path()); a
hit blocks that file. After import, the source moves to inbox/_imported/<YYYY-MM-DD>/. An existing destination is
never overwritten (reported instead).
Parallel Phase 3 (09): lanes write OUTCOME-/QB- fragments to AppApply-Capture/staging/ instead of appending to the
shared CSVs; the orchestrator merges them with --from AppApply-Capture/staging (same checks, archived to staging/_imported/).
Usage: python3 tools/import-inbox.py [--dry-run] [--from <dir>]
"""
import csv, glob, io, json, os, re, shutil, sys, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common, pii_scan  # noqa: E402

REPO = common.REPO  # JOBHUNT_OPS overrides for tests
INBOX = common.expand(common.cfg('paths', 'inbox_dir') or '') or os.path.join(common.CAPTURE, 'staging')
PII_FILE = pii_scan.PII_FILE


def load_pii():
    """The personal-value regex lives outside the repo (00 hard rule 8), next to the Google token. Fail closed."""
    try:
        return re.compile(pii_scan.pii_regex(), re.I), pii_scan.pii_config()
    except Exception as e:
        sys.exit(f'ERROR: PII pattern file {PII_FILE} not loadable ({type(e).__name__}); nothing is imported or scanned')


PII, PII_CFG = load_pii()
RUN = common.RUN_RE

# Cross-platform guard. The ops tree is mirrored to the dashboard host, which may be Windows,
# and Windows silently refuses names containing these. Once, five OUTCOME files were written with ISO
# timestamps (colons) glued into the job id: they never reached the dashboard, the portal never saw
# those applications, and nothing reported an error for three days.
# The same fault also corrupted job_id itself, so both the name and the field are checked.
WIN_BAD = re.compile(r'[:"*?<>|\x00-\x1f]')
WIN_RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}


def portability_problem(name):
    """Reject a staging name Windows cannot hold, before it becomes a file nobody notices is missing."""
    hit = WIN_BAD.search(name)
    if hit:
        return f'filename contains {hit.group(0)!r}, which Windows cannot store (it would never sync to the dashboard)'
    if name != name.strip() or name.endswith('.'):
        return 'filename has a leading/trailing space or a trailing dot; Windows cannot store it'
    if name.split('.')[0].upper() in WIN_RESERVED:
        return f'filename uses the Windows reserved name {name.split(".")[0]!r}'
    return None


JT_RE = re.compile(r'JT-[0-9a-f]{10}')


def bad_job_id(name, text):
    """OUTCOME-/QB- rows are keyed on job_id. A non-numeric one matches no job in the portal."""
    if not name.startswith(('OUTCOME-', 'QB-')):
        return None
    try:
        row = next(iter(csv.DictReader(io.StringIO(text))), None)
    except Exception as e:
        return f'unreadable CSV ({type(e).__name__})'
    if not row:
        return 'no data row'
    jid = (row.get('job_id') or '').strip()
    if not jid:
        return 'job_id is empty'
    if name.startswith(('OUTCOME-JT-', 'QB-JT-')):
        if not JT_RE.fullmatch(jid) or f'-{jid}-' not in name:
            return f'job_id {jid!r} is not a JT-<10 hex> key that matches the file name'
        return None
    if not jid.isdigit():
        return f'job_id {jid!r} is not numeric (the dashboard keys on it; this row would match no job)'
    return None
dry = '--dry-run' in sys.argv
if '--from' in sys.argv:
    INBOX = os.path.abspath(os.path.join(REPO, sys.argv[sys.argv.index('--from') + 1]))

def dest_for(name):
    m = RUN.search(name)
    run = m.group(0) if m else None
    date = f'{m.group(1)}-{m.group(2)}-{m.group(3)}' if m else None
    base = name
    if run:
        base = name.replace('-' + run, '')
    if name.startswith('TRACE-') and run:
        return ('file', f'AppApply-Capture/traces/{run}/{base}')
    if name.startswith('PAGE-') and run:
        return ('file', f'AppApply-Capture/pages/{run}/{base}')
    if name.startswith('DOM-'):
        parts = name[4:].split('-', 1)
        return ('file', f'AppApply-Capture/dom/{parts[0]}/{parts[1] if len(parts) > 1 else name}')
    if name.startswith('OUTCOME-JT-'):
        return ('append', 'AppApply-Capture/outcomes-jt.csv')
    if name.startswith('QB-JT-'):
        return ('append', 'AppApply-Capture/question-bank-observations-jt.csv')
    if name.startswith('OUTCOME-'):
        return ('append', 'AppApply-Capture/outcomes.csv')
    if name.startswith('QB-'):
        return ('append', 'AppApply-Capture/question-bank-observations.csv')
    if date:
        return ('file', f'Runs/{date}/{name}')
    return (None, None)

def main():
    if not os.path.isdir(INBOX):
        print('inbox missing:', INBOX); return 1
    names = sorted(n for n in os.listdir(INBOX) if not n.startswith(('.', '_')) and os.path.isfile(os.path.join(INBOX, n)))
    if not names:
        print('inbox empty'); return 0
    today = datetime.date.today().isoformat()
    done, skipped = [], []
    for n in names:
        src = os.path.join(INBOX, n)
        kind, rel = dest_for(n)
        if not kind:
            skipped.append((n, 'no RunID / unknown type')); continue
        bad = portability_problem(n)
        if bad:
            skipped.append((n, f'BLOCKED: {bad}')); continue
        data = open(src, 'rb').read()
        text = data.decode('utf-8', 'replace')
        if PII.search(text):
            skipped.append((n, 'BLOCKED: contains a personal value')); continue
        bad = bad_job_id(n, text)
        if bad:
            skipped.append((n, f'BLOCKED: {bad}')); continue
        dst = os.path.join(REPO, rel)
        if kind == 'file':
            if os.path.exists(dst):
                skipped.append((n, f'exists: {rel}')); continue
            if not dry:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                open(dst, 'wb').write(data)
        else:
            rows = list(csv.reader(io.StringIO(text)))
            body = rows[1:] if rows and rows[0] and rows[0][0] in ('run_id', 'question_id') else rows
            if not dry:
                if rel.endswith('-jt.csv') and not (os.path.exists(dst) and os.path.getsize(dst)) and rows:
                    body = rows  # a new -jt file has no header yet: the first fragment's own header starts it
                if os.path.exists(dst) and os.path.getsize(dst) and open(dst, 'rb').read()[-1:] != b'\n':
                    open(dst, 'a').write('\n')  # never glue the first new row onto the last old one
                with open(dst, 'a', newline='', encoding='utf-8') as fh:
                    csv.writer(fh).writerows(body)
        if not dry:
            arch = os.path.join(INBOX, '_imported', today)
            os.makedirs(arch, exist_ok=True)
            shutil.move(src, os.path.join(arch, n))
        done.append((n, rel))
    for n, r in done: print(('WOULD IMPORT ' if dry else 'imported ') + f'{n} -> {r}')
    for n, why in skipped: print(f'skipped {n}: {why}')
    print(f'{len(done)} imported, {len(skipped)} skipped' + (' (dry run)' if dry else ''))
    return 0

if __name__ == '__main__':
    sys.exit(main())
