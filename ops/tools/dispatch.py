#!/usr/bin/env python3
"""Phase 3 in parallel (09-PARALLEL-APPLY.md): one orchestrator and up to 5 apply lanes share one dispatch board.

State lives in Runs/<YYYY-MM-DD>/dispatch-<OrchRunID>/ and nothing in it is ever overwritten:
  board.csv             write-once snapshot from `init`: one row per PREP card, with its lane, lock and start state
  meta.json             write-once: run ID, lane count, Easy Apply lane and cap
  claims/<JobID>/       made with mkdir, so a claim is atomic; claim.json inside. A released claim moves to claims/_released/
  locks/<tenant>/       made with mkdir: one lane at a time per account-based tenant (01 §9); holder.json inside
  events/lane<N>.jsonl  append-only; only lane N writes it
  events/orch.jsonl     append-only; only the orchestrator writes it

Orchestrator: init <OrchRunID> --queue <export> · board · list [lane] · show <JobID> · needs [lane]
              queue-plan --queue <export> · open|hold|drop|reviewed|login|preapprove|full <JobID>... [--note]
              reopen <JobID>  (preapprove: the operator's "apply as carded" ruling from the sweep, 09 §4.5 — a lane that finds
              no difference between card, the current answers file and the live form posts `approved` from it and fills without a
              second ask; full: show this card's packet in full; packets are compact by default)
              external <JobID>... --note "<what the operator did>"  (the operator submitted it themselves outside a lane: the card leaves
              the board and can never be opened, held or dropped again; record it in the Queue by hand, 01 §1.4)
              confirm <JobID>... --note "<evidence>" [--findings <file>]  (a card the board holds as `unconfirmed` that a
              read-only check — mail receipt, ADP My Applications — shows was submitted: queue-plan then writes
              Submitted, not Submitted-unconfirmed, and never reverts a hand-corrected row)
              decisions <file> · watch (one line per lane event that needs the operator; for Monitor → phone push)
Lane N:       register <N> <LaneRunID> · window <N> ok|hidden [--note] · claim <N> [--ahead 3] [--hands-free]
              event <N> <JobID> <kind> [...] · retire <N>
              (`event <N> <JobID> external --note "<evidence>"`: the operator clicked Submit themselves in this lane's window and the
              lane read the confirmation; ends the card as externally submitted, no submit_clicked/intent needed;
              `event … submitted|unconfirmed|external` also writes the OUTCOME-/QB- staging fragments from the findings/INTENT
              when the lane has not, never over an existing one, after a pii_scan, and prints what is missing; a fragment
              the lane wrote itself is parsed first and the event is refused if a row has the wrong number of columns)
              (`event <N> <JobID> awaiting_submit --note "<what the operator must do>"`: the lane hands a step at or before
              Submit to the operator (captcha, blocked click, code, terms box, file dialog). INTENT must exist. It shows as
              SUBMIT HANDOFF first on `board`/`watch`. After the operator acts the lane posts `external` or `submitted`.
              `event <N> <JobID> retract --note "<why>"` voids a `submit_clicked` posted before any click happened;
              the lane must post `submit_clicked` again right before the real click)
              (event order: claimed → awaiting_yes → approved --approval "<reply>" → filling → intent → submit_clicked
              → submitted; `approved` writes the operator's yes down per card the moment it arrives)
              (window: the lane's window proof, 09 §4 lane step 3 — `claim` refuses until the latest window event is
              `ok`, and `filling`/`submit_clicked` refuse unless that `ok` is newer than the last hidden report;
              --ahead: hold up to 3 cards and ask about them in one round, 09 §5; --hands-free: skip login cards
              while the operator is away)
--queue api reads the sheet through tools/queue_api.py (preferred); an .xlsx, a .csv of the Queue tab, or the
Drive download tool's saved JSON also work. `queue-plan --queue api --apply` writes the pending cells and re-checks.
Every command after init uses the newest dispatch-* folder unless --run <OrchRunID> is given.
"""
import argparse, base64, csv, datetime, glob, io, json, os, re, shutil, sys, zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from common import die, slug, company_key  # noqa: E402,F401

REPO = common.REPO  # JOBHUNT_OPS overrides for tests
RUNS = common.RUNS
CT = common.local_tz()  # the operator's zone (config [run] timezone); run ids and board stamps use it
RUN_RE = common.RUN_RE
CARD_RE = re.compile(r'^PREP-(.+)-(' + common.JOB_ID_RE + r')-(R\d{8}-\d{4}-[a-z]+\d?)\.md$')
ATTEMPT_RE = re.compile(r'^(?:INTENT|submitted|unconfirmed|paused|skipped|closed|recovered)-.*?(' + common.JOB_ID_RE + r')-a(\d+)-')
DONE_OUTCOMES = ('submitted', 'unconfirmed', 'recovered')
TERMINAL = ('submitted', 'unconfirmed', 'paused', 'skipped', 'closed', 'released', 'external')
# A card in one of these board states is finished: never opened, held, dropped or handed out again.
FINISHED = ('done:submitted', 'done:unconfirmed', 'done:external', 'done:recovered')
WAITING = ('awaiting_yes', 'awaiting_login', 'awaiting_code', 'needs_user', 'awaiting_submit')
KINDS = WAITING + ('approved', 'filling', 'intent', 'submit_clicked', 'retract') + TERMINAL
# 09 §4 lane step 3: the lane proves its window (its tab alone in a window that shows on screen) before it claims.
WINDOW = ('window_ok', 'window_hidden')
# A needs_user note counts as a hidden report only when it clearly says so ("a hidden required input" must not).
HIDDEN_RE = re.compile(r"window\W+(is\W+)?hidden|visibilityState\W*[:=]?\W*['\"]?hidden|background tab|minimi[sz]ed"
                       r"|not (its )?own window|display (is )?(asleep|sleep)|screen (is )?locked|occluded|another space", re.I)
NEEDS_WINDOW = ('filling', 'submit_clicked')
WINDOW_FRESH_S = 600  # `submit_clicked` needs a `window ok` posted within this many seconds (09 §5 step 5)
# 09 §5: an event may only follow the step before it (lane 5 once posted `filling` during prepare). `approved` records
# the operator's per-card yes (--approval "<exact reply>") at the moment it arrives, so the card↔answer mapping of an
# ask-ahead round is written down before any field is touched.
NEEDS_BEFORE = {'approved': 'awaiting_yes', 'filling': 'approved', 'intent': 'filling', 'submit_clicked': 'intent',
                'submitted': 'submit_clicked', 'unconfirmed': 'submit_clicked',
                'awaiting_submit': 'intent', 'retract': 'submit_clicked'}
DECISIONS_RE = re.compile(r'((?:PREP-DECISIONS|DECISION)[\w.-]*\.md)')
MAX_AHEAD = 3
QUEUE_STATUS = {'submitted': 'Submitted', 'unconfirmed': 'Submitted-unconfirmed', 'skipped': 'Skipped', 'closed': 'Closed',
                'external': 'Submitted'}
# ATS families, checked in order. Account-based ATS keep one draft per account, so they take a tenant lock.
ATS = [('unknown', r'^unknown'), ('linkedin_easy_apply', r'linkedin|easy apply'), ('workday', r'workday'),
       ('greenhouse', r'greenhouse'), ('ashby', r'ashby'), ('lever', r'\blever\b'), ('workable', r'workable'),
       ('ultipro', r'ultipro|ukg'), ('adp', r'\badp\b'), ('oracle', r'oracle'), ('successfactors', r'successfactors'),
       ('icims', r'icims'), ('paycom', r'paycom'), ('paylocity', r'paylocity'), ('paycor', r'paycor'),
       ('phenom', r'phenom'), ('eightfold', r'eightfold'), ('smartrecruiters', r'smartrecruiters'),
       ('rippling', r'rippling'), ('hireology', r'hireology'), ('avature', r'avature'), ('talemetry', r'talemetry'),
       ('zoho', r'zoho'), ('teamtailor', r'teamtailor'), ('umantis', r'umantis'), ('bamboohr', r'bamboo'),
       ('jobvite', r'jobvite'), ('taleo', r'taleo')]
BOARD_COLS = ['order', 'lane', 'job_id', 'company', 'role', 'ats', 'ats_label', 'tenant', 'tenant_key', 'lock', 'ea', 'login',
              'priority', 'queue_row', 'state', 'card', 'card_run', 'resume', 'apply_url', 'jd']


def now():
    """(UTC ISO, local stamp). The local stamp is what board output and the Queue's I column carry."""
    t = common.now_utc()
    return common.utc_iso(t), common.local_stamp(t)


def tenant_key(site, url):
    """One key per account-holding tenant, however the card spelled it (a Workday tenant, an ADP cid, an UltiPro code)."""
    t = f'{site} {url}'.lower()
    for pat, pre in ((r'([a-z0-9-]+)\.wd\d+\.myworkday(?:jobs)?\.com', 'workday-'), (r'wd\d+\.myworkday\.com/([a-z0-9_-]+)', 'workday-'),
                     (r'cid[=: ]+([0-9a-f]{8}-[0-9a-f-]{27})', 'adp-'), (r'recruiting\d?\.ultipro\.com/([a-z0-9]+)', 'ultipro-'),
                     (r'([a-z0-9-]+\.fa\.[a-z0-9.]+)\.oraclecloud\.com', 'oracle-')):
        m = re.search(pat, t)
        if m:
            return pre + m.group(1)
    m = re.search(r'[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?:/[a-z0-9_-]+)?', re.sub(r'\(.*?\)', ' ', site.lower()))
    if m:
        return m.group(0)
    m = re.search(r'https?://([^/ ]+)', url.lower())
    return m.group(1) if m else slug(site)


def ats_family(label):
    t = label.lower()
    for fam, pat in ATS:
        if re.search(pat, t):
            return fam
    return 'other'


# ---------- Queue export ----------

def queue_api():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import queue_api as q
    return q


def read_queue(path):
    """Job ID -> {'row': n, 'A'..'M': value} from the Sheets API (`api`), an xlsx, a Drive-download JSON wrapper, or a CSV."""
    if path == 'api':
        return queue_api().read_queue()
    raw = open(path, 'rb').read()
    if raw[:1] == b'{':
        raw = base64.b64decode(json.loads(raw)['content'])
    if raw[:2] == b'PK':
        rows = _xlsx_rows(raw, 'Queue')
    else:
        rows = {i + 1: {chr(65 + j): v for j, v in enumerate(r[:26])}
                for i, r in enumerate(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))}
    out = {}
    for n, r in rows.items():
        a = (r.get('A') or '').strip()
        if n == 1 or not re.fullmatch(r'(\d{8,}(\.0+)?|JT-[0-9a-f]{10})', a):  # same rule as common.JOB_ID_RE
            continue  # same rule as queue_api.read_queue; '4.47E+09' must never become a Job ID
        out[a.split('.')[0]] = dict(r, row=n)
    return out


def _xlsx_rows(raw, sheet_name):
    M = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
    z = zipfile.ZipFile(io.BytesIO(raw))
    ss = []
    if 'xl/sharedStrings.xml' in z.namelist():
        ss = [''.join(t.text or '' for t in si.iter(M + 't'))
              for si in ET.fromstring(z.read('xl/sharedStrings.xml')).iter(M + 'si')]
    rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
    target = None
    for s in ET.fromstring(z.read('xl/workbook.xml')).iter(M + 'sheet'):
        if s.get('name') == sheet_name:
            target = rels[s.get(R + 'id')]
    if not target:
        die(f'no "{sheet_name}" tab in the export')
    target = target.lstrip('/')
    target = target if target.startswith('xl/') else 'xl/' + target
    rows = {}
    for r in ET.fromstring(z.read(target)).iter(M + 'row'):
        vals = {}
        for c in r.iter(M + 'c'):
            col = re.match(r'[A-Z]+', c.get('r')).group(0)
            v = c.find(M + 'v')
            if c.get('t') == 's' and v is not None:
                vals[col] = ss[int(v.text)]
            elif c.get('t') == 'inlineStr':
                vals[col] = ''.join(x.text or '' for x in c.iter(M + 't'))
            else:
                vals[col] = v.text if v is not None and v.text else ''
        rows[int(r.get('r'))] = vals
    return rows


# ---------- Cards and run files ----------

def read_card(path):
    head = open(path, encoding='utf-8').read().split('\n## ', 1)[0]
    title = head.split('\n', 1)[0].lstrip('# ').split(' — ')
    field = lambda name: (re.search(r'(?:^|· )' + name + r':\s*(.*?)\s*(?= · |$)', head, re.M) or [None, ''])[1]
    ats = field('ATS')
    login = field('Login needed').lower()
    return {
        'company': title[1] if len(title) > 1 else '', 'role': title[2] if len(title) > 2 else '',
        'apply_url': field('Apply URL'), 'ats': ats_family(ats) if ats else 'unknown',
        'ats_label': re.split(r'\s*[(—]', ats)[0].strip() if ats else '', 'tenant': field('Site'),
        'login': 'no' if login.startswith(('no', 'signed in')) else 'yes' if login.startswith('yes') else 'maybe',
        'resume': (re.search(r'^Résumé:\s*(\S+\.pdf)', head, re.M) or [None, ''])[1],
        'jd': (re.search(r'^JD:\s*(jd-\S+\.md)', head, re.M) or [None, ''])[1],
        'triage': (re.search(r'Pre-triage result:\s*([\w-]+)', head) or [None, ''])[1],
    }


def attempts_by_job():
    """Job ID -> {'n': highest attempt N, 'done': outcome of a submitted/unconfirmed/recovered file, 'intent_only': bool}."""
    idx = {}
    for p in glob.glob(os.path.join(RUNS, '*', '*.md')):
        m = ATTEMPT_RE.match(os.path.basename(p))
        if not m:
            continue
        d = idx.setdefault(m.group(1), {'n': 0, 'files': {}})
        n = int(m.group(2))
        d['n'] = max(d['n'], n)
        d['files'].setdefault(n, set()).add(os.path.basename(p).split('-', 1)[0])
    for p in glob.glob(os.path.join(REPO, 'AppApply-Capture', 'traces', '*', 'TRACE-*-a*.jsonl')):
        m = re.match(r'TRACE-(' + common.JOB_ID_RE + r')-a(\d+)\.jsonl$', os.path.basename(p))
        if m:
            d = idx.setdefault(m.group(1), {'n': 0, 'files': {}})
            d['n'] = max(d['n'], int(m.group(2)))
    for d in idx.values():
        kinds = set().union(*d['files'].values()) if d['files'] else set()
        d['done'] = next((k for k in DONE_OUTCOMES if k in kinds), '')
        top = d['files'].get(max(d['files'])) if d['files'] else set()
        d['intent_only'] = bool(top) and top == {'INTENT'}
    return idx


def find_run_file(name):
    return glob.glob(os.path.join(RUNS, '*', name))


# ---------- Dispatch state ----------

def run_dir(run):
    if run:
        m = RUN_RE.match(run) or die(f'bad Run ID {run}')
        return os.path.join(RUNS, f'{m.group(1)}-{m.group(2)}-{m.group(3)}', f'dispatch-{run}')
    dirs = sorted(glob.glob(os.path.join(RUNS, '*', 'dispatch-R*')), key=os.path.basename)
    return dirs[-1] if dirs else die('no dispatch run yet — the orchestrator runs `init` first')


def append(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + '\n')


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding='utf-8') if l.strip()]


class State:
    def __init__(self, d):
        self.d = d
        self.meta = json.load(open(os.path.join(d, 'meta.json')))
        self.rows = list(csv.DictReader(open(os.path.join(d, 'board.csv'), encoding='utf-8')))
        self.by_job = {r['job_id']: r for r in self.rows}
        self.orch = read_jsonl(os.path.join(d, 'events', 'orch.jsonl'))
        self.lane_events = {n: read_jsonl(os.path.join(d, 'events', f'lane{n}.jsonl'))
                            for n in range(1, self.meta['lanes'] + 1)}
        self.claims = {}
        for c in glob.glob(os.path.join(d, 'claims', '*', 'claim.json')):
            j = json.load(open(c))
            self.claims[j['job_id']] = j
        self.lane_run, self.retired = {}, set()
        # per lane: (ts, position in the lane's event file) of the last `window ok`, and of the last hidden report.
        # The position breaks ties: two events in the same second must still resolve in file order.
        self.win_ok, self.win_bad = {}, {}
        for n, evs in self.lane_events.items():
            for i, e in enumerate(evs):
                if e['kind'] == 'register':
                    self.lane_run[n] = e['run']
                    self.retired.discard(n)
                    self.win_ok.pop(n, None)
                    self.win_bad.pop(n, None)
                elif e['kind'] == 'retire':
                    self.retired.add(n)
                elif e['kind'] == 'window_ok':
                    self.win_ok[n] = (e['ts'], i)
                elif e['kind'] == 'window_hidden' or (e['kind'] == 'needs_user' and HIDDEN_RE.search(e.get('note') or '')):
                    self.win_bad[n] = (e['ts'], i)
        self.base, self.reviewed, self.decisions, self.login_override = {}, set(), [], {}
        self.preapproved, self.full = {}, set()
        self.confirmed = {}  # Job ID -> the orchestrator's `confirm` event (read-only evidence that an unconfirmed card went in)
        for r in self.rows:
            self.base[r['job_id']] = r['state']
        for e in self.orch:
            k = e['kind']
            for j in e.get('jobs', []):
                if k == 'preapprove':
                    self.preapproved[j] = e.get('note') or 'apply as carded (sweep)'
                elif k == 'full':
                    self.full.add(j)
                elif k == 'open':
                    self.base[j] = 'ready'
                elif k == 'hold':
                    self.base[j] = 'hold:' + (e.get('note') or 'orchestrator')
                elif k == 'drop':
                    self.base[j] = 'dropped:' + (e.get('note') or '')
                elif k == 'external':
                    self.base[j] = 'external:' + (e.get('note') or '')
                elif k == 'confirm':
                    self.confirmed[j] = e
                elif k == 'reviewed':
                    self.reviewed.add(j)
                elif k == 'login':
                    self.login_override[j] = 'yes'
            if k == 'decisions' and e['file'] not in self.decisions:
                self.decisions.append(e['file'])

    def prior_approval(self, job, claim_id=None):
        """the operator's latest `approved` for this job in THIS run from an earlier claim (09 §5: a same-run yes carries over
        when nothing about the card changed). None if the only approval belongs to the current claim."""
        best = None
        for evs in self.lane_events.values():
            for e in evs:
                if e['kind'] == 'approved' and e.get('job') == job and e.get('claim_id') != claim_id:
                    if not best or e['ts'] > best['ts']:
                        best = e
        return best and {'ct': best['ct'], 'lane_run': best['run'], 'approval': best.get('approval', '')}

    def window_ready(self, n):
        """True once the lane's latest window proof is `ok` and nothing since has reported the window hidden."""
        ok = self.win_ok.get(n)
        return bool(ok) and ok > (self.win_bad.get(n) or ('', -1))

    def login(self, job):
        """The board's login flag, or `yes` once the orchestrator marked a wall (preflight, a lane's report)."""
        return self.login_override.get(job) or self.by_job[job]['login']

    def open_claims(self, n):
        """This lane run's claims that aren't finished, oldest first."""
        run = self.lane_run.get(n)
        return sorted(((j, c) for j, c in self.claims.items()
                       if c['lane'] == n and c['lane_run'] == run and not self.status(j).startswith('done:')),
                      key=lambda jc: (jc[1]['at'], int(self.by_job[jc[0]]['order'])))

    def claim_events(self, job):
        c = self.claims.get(job)
        if not c:
            return []
        return [e for e in self.lane_events[c['lane']] if e.get('claim_id') == c['claim_id']]

    def status(self, job):
        """ready · hold:… · dropped:… · active:<kind> · waiting:<kind> · done:<kind> · orphaned:<kind>"""
        c = self.claims.get(job)
        if not c:
            return self.base.get(job, 'unknown')
        evs = self.claim_events(job)
        last = evs[-1]['kind'] if evs else 'claimed'
        if last in TERMINAL:
            return 'done:' + last
        if self.lane_run.get(c['lane']) != c['lane_run'] or c['lane'] in self.retired:
            return 'orphaned:' + last
        return ('waiting:' if last in WAITING else 'active:') + last

    def ea_submitted(self):
        return sum(1 for j, r in self.by_job.items()
                   if r['ea'] == '1' and self.status(j) in FINISHED)


def take_lock(d, lock, job, n, lane_run, ts):
    """mkdir = atomic lock. The lane run that holds a tenant may add more of its own cards (ask-ahead); nobody else may."""
    lock_dir = os.path.join(d, 'locks', lock)
    hp = os.path.join(lock_dir, 'holder.json')
    try:
        os.mkdir(lock_dir)
    except FileExistsError:
        try:
            h = json.load(open(hp))
        except (FileNotFoundError, ValueError):
            return False
        if h.get('lane') != n or h.get('lane_run') != lane_run:
            return False
        h['jobs'] = (h.get('jobs') or [h['job_id']]) + [job]
        json.dump(h, open(hp, 'w'))
        return True
    json.dump({'job_id': job, 'jobs': [job], 'lane': n, 'lane_run': lane_run, 'at': ts}, open(hp, 'w'))
    return True


def release_lock(d, c):
    """Take this claim off its tenant lock; remove the lock when no job of that lane run still holds it."""
    if not c.get('lock'):
        return
    lock_dir = os.path.join(d, 'locks', c['lock'])
    hp = os.path.join(lock_dir, 'holder.json')
    try:
        h = json.load(open(hp))
    except (FileNotFoundError, ValueError):
        if os.path.isdir(lock_dir):
            shutil.rmtree(lock_dir, ignore_errors=True)
        return
    jobs = h.get('jobs') or [h.get('job_id')]
    if c['job_id'] not in jobs:
        return
    jobs = [j for j in jobs if j != c['job_id']]
    if jobs:
        h.update(jobs=jobs, job_id=jobs[0])
        json.dump(h, open(hp, 'w'))
    else:
        shutil.rmtree(lock_dir, ignore_errors=True)


def lane_arg(st, n):
    str(n).isdigit() or die(f'lane must be a number 1..{st.meta["lanes"]}, not {n!r}')
    n = int(n)
    if not 1 <= n <= st.meta['lanes']:
        die(f'lane must be 1..{st.meta["lanes"]}')
    return n


# ---------- Commands ----------

def cmd_init(a):
    m = RUN_RE.fullmatch(a.run_id) or die('Run ID must look like R20260924-0900-orch')
    d = run_dir(a.run_id)
    if os.path.exists(d):
        die(f'{d} exists — dispatch folders are write-once; use a new orchestrator Run ID')
    if a.ea_lane > a.lanes:
        die(f'--ea-lane {a.ea_lane} is outside --lanes {a.lanes}: Easy Apply cards would be stranded on a lane nobody runs')
    # A second board while lanes still hold unfinished claims makes those cards claimable twice (the Queue never says
    # In progress during a parallel run). A replacement orchestrator resumes the old board with --run instead.
    live = []
    for od in glob.glob(os.path.join(RUNS, '*', 'dispatch-R*')):
        try:
            ost = State(od)
        except Exception:
            continue
        for n, run in ost.lane_run.items():
            if n in ost.retired:
                continue
            busy = [j for j, c in ost.claims.items() if c['lane'] == n and c['lane_run'] == run
                    and not ost.status(j).startswith('done:')]
            if busy:
                live.append(f'{os.path.basename(od)} lane {n} ({run}): {", ".join(busy)}')
    if live and not a.force:
        die('another board still has lanes holding unfinished claims:\n  ' + '\n  '.join(live) +
            '\nResume it with `--run <OrchRunID>` instead of a new `init`. If those lane chats are gone for good, recover '
            'each claim per 01 §11 on that board first (`reopen`, or a fresh `register` + `released`), then re-run; '
            '`--force "<why>"` overrides and is recorded.')
    queue = read_queue(a.queue)
    att = attempts_by_job()
    cards = {}
    for p in glob.glob(os.path.join(RUNS, '*', 'PREP-*.md')):
        cm = CARD_RE.match(os.path.basename(p))
        if cm and not os.path.basename(p).startswith(('PREP-SUMMARY', 'PREP-DECISIONS')):
            job, crun = cm.group(2), cm.group(3)
            if job not in cards or crun > cards[job][1]:
                cards[job] = (p, crun)
    rows, excluded = [], {}
    for job, (path, crun) in cards.items():
        q = queue.get(job)
        why = None
        if not q:
            why = 'not in Queue'
        elif (q.get('J') or '').strip().lower() == 'no':
            why = 'Apply? is No'  # a blank Apply? counts as Yes
        elif (q.get('B') or '').strip() in ('Submitted', 'Submitted-unconfirmed', 'Skipped', 'Closed'):
            why = 'Queue status ' + q['B'].strip()
        elif att.get(job, {}).get('done'):
            why = 'findings file says ' + att[job]['done']
        if why:
            excluded.setdefault(why, []).append(job)
            continue
        c = read_card(path)
        b = (q.get('B') or '').strip()
        if c['triage'] == 'Duplicate' or not c['apply_url']:
            state = 'hold:duplicate or no apply URL on card'
        elif att.get(job, {}).get('intent_only'):
            state = 'hold:recovery (INTENT without findings, 01 §11)'
        elif b in ('Ready', 'Paused-SignIn'):
            state = 'ready'
        elif b == 'In progress':
            state = 'hold:recovery (In progress, 01 §11)'
        elif b == 'Paused-Question':
            state = 'hold:question — ' + (q.get('F') or '')[:120]
        else:
            state = 'hold:' + (b or 'not triaged')
        ea = c['ats'] == 'linkedin_easy_apply'
        tenant = 'linkedin.com' if ea else (c['tenant'] or re.sub(r'^https?://([^/ ]+).*', r'\1', c['apply_url']))
        rows.append({
            'lane': '', 'job_id': job, 'company': c['company'], 'role': c['role'], 'ats': c['ats'],
            'ats_label': c['ats_label'], 'tenant': tenant,
            'tenant_key': 'linkedin' if ea else tenant_key(tenant, c['apply_url']), 'lock': '', 'ea': '1' if ea else '0',
            'login': 'yes' if b == 'Paused-SignIn' else ('no' if ea else c['login']),
            'priority': (q.get('K') or '3').strip() or '3', 'queue_row': str(q['row']), 'state': state,
            'card': os.path.basename(path), 'card_run': crun, 'resume': c['resume'],
            'apply_url': c['apply_url'], 'jd': c['jd']})
    lanes = a.lanes
    ea_lane = a.ea_lane if any(r['ea'] == '1' for r in rows) else 0
    for r in rows:
        if r['ea'] == '1':
            r['lane'] = str(ea_lane or 1)
    # One employer or one tenant = one group = one lane, and one lock, so two lanes never work it at once.
    parent = {}
    def find(x):
        while parent.setdefault(x, x) != x:
            x = parent[x]
        return x
    for r in rows:
        if r['ea'] != '1':
            parent[find('t:' + r['tenant_key'])] = find('c:' + company_key(r['company']))
    groups = {}
    for r in rows:
        if r['ea'] != '1':
            g = find('c:' + company_key(r['company']))
            r['lock'] = slug(g[2:])
            groups.setdefault(g, []).append(r)
    pool = [n for n in range(1, lanes + 1) if n != ea_lane] or [1]
    load = {n: 0 for n in pool}
    for key in sorted(groups, key=lambda k: (-len(groups[k]), k)):
        n = min(pool, key=lambda x: (load[x], x))
        for r in groups[key]:
            r['lane'] = str(n)
        load[n] += len(groups[key])
    rank = {'no': 0, 'maybe': 1, 'yes': 2}
    rows.sort(key=lambda r: (int(r['lane']), r['state'] != 'ready', r['priority'], rank[r['login']],
                             r['lock'], int(r['queue_row'])))
    for i, r in enumerate(rows, 1):
        r['order'] = str(i)
    os.makedirs(os.path.join(d, 'claims'))
    os.makedirs(os.path.join(d, 'locks'))
    os.makedirs(os.path.join(d, 'events'))
    with open(os.path.join(d, 'board.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=BOARD_COLS)
        w.writeheader()
        w.writerows(rows)
    ts, ct = now()
    json.dump({'run': a.run_id, 'created': ts, 'lanes': lanes, 'ea_lane': ea_lane, 'ea_cap': a.ea_cap,
               'queue_export': os.path.basename(a.queue), 'forced_over': live if a.force else [], 'force_note': a.force},
              open(os.path.join(d, 'meta.json'), 'w'), indent=1)
    # Every earlier decisions file that names a board Job ID is registered now, so lanes see it on every claim and
    # `needs` shows it (LEARNINGS-R20260924-0850-orch §4: the -2027-orch files had to be re-registered by hand).
    ids = {r['job_id'] for r in rows}
    auto = []
    for p in sorted(glob.glob(os.path.join(RUNS, '*', 'PREP-DECISIONS*.md')) + glob.glob(os.path.join(RUNS, '*', 'DECISION-*.md'))):
        if any(j in open(p, encoding='utf-8').read() for j in ids):
            append(os.path.join(d, 'events', 'orch.jsonl'),
                   {'ts': ts, 'ct': ct, 'kind': 'decisions', 'file': os.path.basename(p), 'auto': True})
            auto.append(os.path.basename(p))
    print(f'dispatch {a.run_id} · {ct} · {os.path.relpath(d, REPO)}')
    print(f'{len(rows)} cards on the board · Easy Apply lane {ea_lane or "—"} (cap {a.ea_cap} per run)')
    print(f'{len(auto)} decisions file(s) registered (they name board Job IDs): {", ".join(auto) or "none"}')
    for n in range(1, lanes + 1):
        mine = [r for r in rows if r['lane'] == str(n)]
        ready = [r for r in mine if r['state'] == 'ready']
        print(f'  lane {n}: {len(ready)} ready, {len(mine) - len(ready)} on hold · '
              f'{len({r["lock"] for r in mine})} employer groups · login needed/maybe on '
              f'{sum(1 for r in ready if r["login"] != "no")}')
    for why, jobs in sorted(excluded.items()):
        print(f'  not on board ({why}): {len(jobs)}')
    holds = [r for r in rows if r['state'] != 'ready']
    if holds:
        print('\nON HOLD (orchestrator: `open <JobID>` once resolved)')
        for r in holds:
            print(f'  {r["job_id"]} · {r["company"]} · lane {r["lane"]} · {r["state"][:110]}')
    logins = {}
    for r in rows:
        if r['state'] == 'ready' and r['login'] != 'no':
            logins.setdefault(r['tenant_key'], []).append(r)
    if logins:
        print('\nLOGINS (sign in once in the "App Apply" Chrome profile, 09 §2.1; every lane shares the cookies)')
        for k, rs in sorted(logins.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            tag = 'needed' if any(x['login'] == 'yes' for x in rs) else 'maybe'
            print(f'  {k} · {rs[0]["ats_label"]} · {rs[0]["company"]} · lane {rs[0]["lane"]} · {len(rs)} posting(s) · {tag}')


def cmd_register(a):
    st = State(run_dir(a.run))
    n = lane_arg(st, a.lane)
    RUN_RE.fullmatch(a.lane_run) or die('lane Run ID must look like R20260924-0905-apply1')
    old = st.lane_run.get(n)
    ts, ct = now()
    append(os.path.join(st.d, 'events', f'lane{n}.jsonl'), {'ts': ts, 'ct': ct, 'lane': n, 'run': a.lane_run,
                                                           'kind': 'register', 'previous_run': old})
    st = State(st.d)
    print(f'lane {n} registered as {a.lane_run} in dispatch {st.meta["run"]}' +
          (f' (replaces {old}; its unfinished claims are now orphaned for the orchestrator)' if old else ''))
    cmd_list(argparse.Namespace(run=a.run, lane=str(n)), st)
    lane_tab_report()


def lane_tab_report():
    """09 §4 lane step 4 (A6): say where this lane's example.com tab landed. Read-only; skipped when lane-windows.sh is absent
    (tests) or Chrome can't be read. A lane whose first tab lands in another window fails its window proof every time."""
    script = os.path.join(REPO, 'tools', 'lane-windows.sh')
    if not os.path.exists(script):
        return
    import subprocess
    try:
        r = subprocess.run(['zsh', script, '--lane-tab'], capture_output=True, text=True, timeout=25)
    except Exception:
        return
    out = (r.stdout or '').strip()
    if out:
        print(('WARNING ' if r.returncode else '') + out)


def cmd_window(a):
    """09 §4 lane step 3: the lane reports whether its tab is alone in a window that shows on screen."""
    st = State(run_dir(a.run))
    n = lane_arg(st, a.lane)
    if n not in st.lane_run or n in st.retired:
        die(f'lane {n} is not registered — run `register {n} <LaneRunID>` first')
    ts, ct = now()
    kind = 'window_ok' if a.state == 'ok' else 'window_hidden'
    rec = {'ts': ts, 'ct': ct, 'lane': n, 'run': st.lane_run[n], 'kind': kind}
    if a.note:
        rec['note'] = a.note
    append(os.path.join(st.d, 'events', f'lane{n}.jsonl'), rec)
    if kind == 'window_ok':
        print(f'lane {n} · window ok · {ct} · `claim {n} --ahead 3` may proceed')
    else:
        print(f'lane {n} · WINDOW HIDDEN · {ct} · the operator moves the tab group to its own window and puts it on screen '
              f'(09 §2 rule 2); then re-navigate the front tab, read visibilityState once, and `window {n} ok`. '
              f'No JS calls and no claims until then (09 §2, §4).')


def window_gate(st, n, what):
    if not st.window_ready(n):
        bad = st.win_bad.get(n)
        die(f'lane {n} has not proved its window — `{what}` is refused (09 §4 lane step 3). '
            + ('Its last report says the window is hidden' if bad and bad > (st.win_ok.get(n) or ('', -1))
               else 'No `window ok` yet for this lane run')
            + f'. After tabs_context_mcp: check the tab is alone in a window that shows on screen and visibilityState is '
              f'"visible", then `python3 tools/dispatch.py window {n} ok`.')


def next_attempt(job):
    return attempts_by_job().get(job, {}).get('n', 0) + 1


def try_claim(st, n, r):
    d, job = st.d, r['job_id']
    ts, ct = now()
    if r['lock'] and not take_lock(d, r['lock'], job, n, st.lane_run[n], ts):
        return None
    try:
        os.mkdir(os.path.join(d, 'claims', job))
    except FileExistsError:
        if r['lock']:
            release_lock(d, {'lock': r['lock'], 'job_id': job})
        return None
    attempt = next_attempt(job)
    claim = {'job_id': job, 'lane': n, 'lane_run': st.lane_run[n], 'attempt': attempt,
             'claim_id': f'{job}-L{n}-{ts}', 'at': ts, 'lock': r['lock']}
    json.dump(claim, open(os.path.join(d, 'claims', job, 'claim.json'), 'w'), indent=1)
    append(os.path.join(d, 'events', f'lane{n}.jsonl'),
           {'ts': ts, 'ct': ct, 'lane': n, 'run': st.lane_run[n], 'job': job, 'claim_id': claim['claim_id'],
            'kind': 'claimed', 'attempt': attempt, 'owner_lane': int(r['lane'])})
    return claim


def claim_brief(st, r, c):
    decisions = sorted({os.path.basename(p) for p in glob.glob(os.path.join(RUNS, '*', f'PREP-DECISIONS*{r["card_run"]}.md'))})
    decisions += [f for f in st.decisions if f not in decisions]
    out = {'job_id': r['job_id'], 'attempt_id': f'{r["job_id"]}-a{c["attempt"]}', 'company': r['company'],
           'role': r['role'], 'ats': r['ats'], 'ats_label': r['ats_label'], 'tenant': r['tenant'],
           'tenant_lock': r['lock'] or None, 'easy_apply': r['ea'] == '1', 'login': st.login(r['job_id']),
           'queue_row': int(r['queue_row']), 'card': r['card'], 'resume': r['resume'] or '(answers §Résumé)',
           'jd': r['jd'], 'apply_url': r['apply_url'], 'decisions': decisions,
           'reviewed_in_orchestrator': r['job_id'] in st.reviewed,
           'packet': 'full' if r['job_id'] in st.full else 'compact',
           'preapproved': st.preapproved.get(r['job_id']),
           'prior_approval': st.prior_approval(r['job_id'], c['claim_id'])}
    print(json.dumps(out, ensure_ascii=False, indent=1))


def claim_order(st, n):
    """Cards in the order `claim` offers them: this lane's own list, then the end of the other lanes' lists (never Easy Apply
    when there is an Easy Apply lane)."""
    mine = [r for r in st.rows if r['lane'] == str(n)]
    others = {}
    for r in st.rows:
        if r['lane'] != str(n) and not (r['ea'] == '1' and st.meta['ea_lane']):
            others.setdefault(r['lane'], []).append(r)
    order = list(mine)
    for lane in sorted(others, key=lambda k: -sum(1 for r in others[k] if st.status(r['job_id']) == 'ready')):
        order += list(reversed(others[lane]))
    return order


def claim_peek(st, n, ahead, held, hands_free):
    """`claim <N> --peek`: show what `claim` would hand out, claim nothing, post nothing, need no window proof. A lane that only
    wants to see its list used `claim` and took three cards by mistake (lane 2, 10-12)."""
    print(f'PEEK for lane {n} (nothing claimed): holds {len(held)} card(s)'
          + ''.join(f'\n  held  {j} · {st.by_job[j]["company"][:28]} · {st.status(j)}' for j, _ in held))
    ea_open = sum(1 for j, _ in held if st.by_job[j]['ea'] == '1')
    shown = 0
    for r in claim_order(st, n):
        if len(held) + shown >= ahead:
            break
        if st.status(r['job_id']) != 'ready':
            continue
        if r['ea'] == '1' and st.ea_submitted() + ea_open >= st.meta['ea_cap']:
            continue
        if hands_free and st.login(r['job_id']) != 'no':
            continue
        print(f'  next  {r["job_id"]} · {r["company"][:28]} ({r["ats"]}) · login {st.login(r["job_id"])} · lane {r["lane"]}')
        shown += 1
        ea_open += r['ea'] == '1'
    if not shown:
        print('  next  (nothing claimable)')


def cmd_claim(a):
    st = State(run_dir(a.run))
    n = lane_arg(st, a.lane)
    if n not in st.lane_run or n in st.retired:
        die(f'lane {n} is not registered — run `register {n} <LaneRunID>` first')
    ahead = max(1, min(MAX_AHEAD, a.ahead or 1))
    held = st.open_claims(n)
    if a.peek:
        return claim_peek(st, n, ahead, held, a.hands_free)
    window_gate(st, n, 'claim')
    if len(held) >= ahead:
        print(f'lane {n} already holds {len(held)} card(s): ' + ', '.join(f'{j} ({st.status(j)})' for j, _ in held)
              + ('; finish one with `event` first.' if ahead == 1 else f' (ask-ahead limit {ahead}).'))
        for j, c in held:
            claim_brief(st, st.by_job[j], c)
        return
    ea_open = sum(1 for j, _ in held if st.by_job[j]['ea'] == '1')
    order = claim_order(st, n)
    new, skipped_login = [], 0
    for r in order:
        if len(held) + len(new) >= ahead:
            break
        if st.status(r['job_id']) != 'ready':
            continue
        if r['ea'] == '1' and st.ea_submitted() + ea_open >= st.meta['ea_cap']:
            continue
        if a.hands_free and st.login(r['job_id']) != 'no':
            skipped_login += 1
            continue
        c = try_claim(st, n, r)
        if c:
            if r['lane'] != str(n):
                print(f'(taken from lane {r["lane"]}\'s list — nothing left in lane {n}\'s own list that it may work)')
            new.append(r['job_id'])
            ea_open += r['ea'] == '1'
            st = State(st.d)
    st = State(st.d)
    held = st.open_claims(n)
    if held:
        if ahead > 1:
            print(f'lane {n} holds {len(held)} card(s) (ask-ahead {ahead}; new: {", ".join(new) or "none"}). '
                  f'Prepare each read-only, then ask about all of them in one round, one question per card.')
        for j, c in held:
            claim_brief(st, st.by_job[j], c)
        return
    ready_left = sum(1 for r in st.rows if st.status(r['job_id']) == 'ready')
    print(f'NOTHING TO CLAIM for lane {n}. Ready cards left on the board: {ready_left}'
          + (f' · Easy Apply cap {st.meta["ea_cap"]} reached' if st.ea_submitted() >= st.meta['ea_cap'] else '')
          + (f' · {skipped_login} login card(s) skipped (--hands-free)' if skipped_login else '')
          + '. Write your lane summary and `retire`, or wait for the orchestrator to open held cards.')


def effective_prior(evs):
    """Event kinds posted so far for a claim, where `retract` voids the `submit_clicked` before it (a click posted before
    any click happened, LEARNINGS R20261012-1314-orch #2): `submitted` then needs a fresh `submit_clicked`."""
    prior = []
    for e in evs:
        if e['kind'] == 'retract':
            prior = [k for k in prior if k != 'submit_clicked']
        else:
            prior.append(e['kind'])
    return prior


def check_staged_fragments(job, attempt, run):
    """A fragment the lane wrote by hand can have unquoted commas that shift the columns (RingCentral QB, 10-07). Parse
    it with the csv module and refuse the terminal event before import-inbox.py has to block it."""
    stem = f'{job}-a{attempt}-{run}'
    for pre in ('OUTCOME', 'QB'):
        path = os.path.join(REPO, 'AppApply-Capture', 'staging', f'{pre}-{stem}.csv')
        if not os.path.exists(path):
            continue
        with open(path, newline='', encoding='utf-8') as fh:
            rows = list(csv.reader(fh))
        if not rows:
            die(f'{os.path.basename(path)} is empty — rewrite it with the csv module (08 §4)')
        want = len(rows[0])
        for i, row in enumerate(rows[1:], 2):
            if len(row) != want:
                die(f'{os.path.basename(path)} line {i} has {len(row)} columns, the header has {want}: a field with a comma '
                    f'is not quoted. Write the fragment with the csv module (RFC 4180), or delete it and let this command '
                    f'regenerate it from the findings and INTENT.')


def cmd_event(a):
    st = State(run_dir(a.run))
    n = lane_arg(st, a.lane)
    job, kind = a.job, a.kind
    c = st.claims.get(job)
    if not c or c['lane'] != n or c['lane_run'] != st.lane_run.get(n):
        die(f'lane {n} ({st.lane_run.get(n)}) does not hold a claim on {job}')
    s = st.status(job)
    if s.startswith('done:'):
        die(f'{job} is already {s}')
    if kind in ('submitted', 'unconfirmed', 'paused', 'skipped', 'closed') and not a.findings:
        die(f'`{kind}` needs --findings <findings file name>')
    if kind in ('submitted', 'unconfirmed') and not a.approval:
        die(f'`{kind}` needs --approval "<the operator\'s exact reply>"')
    if kind == 'approved' and not a.approval:
        die('`approved` needs --approval "<the operator\'s exact reply to this card\'s question>" (09 §5 step 3)')
    if kind == 'external' and not a.note:
        die('`external` needs --note "<what the operator did in this window and the confirmation you read, e.g. the page text>" '
            '(09 §5: read the confirmation yourself; the operator\'s own Submit click needs no submit_clicked)"')
    if kind == 'awaiting_submit' and not a.note:
        die('`awaiting_submit` needs --note "<what the operator must do, e.g. tick the hCaptcha in this window, click Submit>"')
    if kind == 'retract' and not a.note:
        die('`retract` needs --note "<why: no click happened, e.g. the Submit control was blocked or the form errored>"')
    if kind == 'paused' and not (a.status or '').startswith('Paused-'):
        die('`paused` needs --status Paused-SignIn|Paused-Question|Paused-Technical|Paused-CAPTCHA|Paused-Verify')
    if kind == 'paused' and a.status == 'Paused-Question' and not a.f:
        die('`paused --status Paused-Question` needs --f "Q1: …" — the question is the Queue\'s record (01 §1.3)')
    if a.findings and not find_run_file(a.findings):
        die(f'findings file {a.findings} not found in Runs/ — write it before the event')
    prior = effective_prior(st.claim_events(job))
    if kind in NEEDS_BEFORE and NEEDS_BEFORE[kind] not in prior:
        die(f'`{kind}` before `{NEEDS_BEFORE[kind]}` on {job} — post events in order (09 §5: claimed → awaiting_yes → '
            'filling → intent → submit_clicked → submitted; after a `retract`, post `submit_clicked` again)')
    if kind in NEEDS_WINDOW:
        window_gate(st, n, kind)
    if kind == 'submit_clicked':
        ok_at = datetime.datetime.fromisoformat(st.win_ok[n][0].replace('Z', '+00:00'))
        age = (datetime.datetime.now(datetime.timezone.utc) - ok_at).total_seconds()
        if age > WINDOW_FRESH_S:
            die(f'the last `window ok` for lane {n} is {int(age // 60)} min old — read visibilityState now and post '
                f'`window {n} ok` right before Submit (09 §5 step 5). A click into a hidden window is silently lost, and '
                f'a second click is never allowed.')
    if kind in ('submitted', 'unconfirmed', 'paused', 'skipped', 'closed', 'external'):
        pii_gate(job, c['attempt'], a.findings)
    ts, ct = now()
    if kind in ('submitted', 'unconfirmed', 'external'):
        check_staged_fragments(job, c['attempt'], st.lane_run[n])
    frag_msgs = (write_fragments(st, c, n, kind, a.findings, ts, a.note or '')
                 if kind in ('submitted', 'unconfirmed', 'external') else [])
    rec = {'ts': ts, 'ct': ct, 'lane': n, 'run': st.lane_run[n], 'job': job, 'claim_id': c['claim_id'],
           'kind': kind, 'attempt': c['attempt']}
    for k in ('findings', 'approval', 'status', 'f', 'note'):
        if getattr(a, k):
            rec[k] = getattr(a, k)
    append(os.path.join(st.d, 'events', f'lane{n}.jsonl'), rec)
    if kind in TERMINAL:
        release_lock(st.d, c)
    if kind == 'released':
        os.makedirs(os.path.join(st.d, 'claims', '_released'), exist_ok=True)
        shutil.move(os.path.join(st.d, 'claims', job), os.path.join(st.d, 'claims', '_released', f'{job}-{ts.replace(":", "")}'))
    print(f'lane {n} · {job} → {kind} · {ct}')
    for m in frag_msgs:
        print('  ' + m)
    if kind == 'external':
        print('  ended as externally submitted: queue-plan writes B Submitted' + (f', H {a.findings}' if a.findings else '')
              + '; no orchestrator `external` needed.')


# ---------- OUTCOME / QB staging fragments (08 §3.5, 09 §6) ----------

OUTCOME_COLS = ['run_id', 'attempt_id', 'job_id', 'company', 'ats', 'tenant', 'outcome', 'confirmation_method', 'started_at',
                'ended_at', 'duration_s', 'pages', 'fields', 'required_fields', 'human_interventions', 'halt_reason', 'trace_file']
QB_COLS = ['question_id', 'label_normalized', 'label_verbatim', 'answer_key', 'answer_planned', 'answer_source', 'control',
           'required', 'selector', 'ats', 'company', 'job_id', 'origin', 'file']
SAFE_ANSWER = re.compile(r'(?i)^(yes|no|decline[\w ,/-]*|company website|negotiable|n/?a|i am not a protected veteran|'
                         r'blank \(optional\)|left blank[\w ()-]*)$')


def md_rows(text, id_re):
    """Cells of every markdown table row whose first cell matches id_re."""
    rows = []
    for line in text.splitlines():
        if line.startswith('|'):
            cells = [x.strip() for x in line.strip().strip('|').split('|')]
            if cells and re.fullmatch(id_re, cells[0]):
                rows.append(cells)
    return rows


def confirmation_method(text):
    """Closest of the outcomes.csv vocabulary, read from the findings' own wording ('' when it says nothing usable)."""
    m = re.search(r'^## Confirmation method\s*\n(.*?)(?=^## |\Z)', text, re.S | re.M)
    t = (m.group(1) if m else '\n'.join(l for l in text.splitlines()[:8] if not l.startswith('#'))).lower()
    parts = []
    if 'redirect' in t:
        parts.append('redirect_confirmation')
    if 'modal' in t:
        parts.append('modal')
    if re.search(r'my applications|job page|candidate (home|portal)|status page', t):
        parts.append('job_page_status')
    if not parts and re.search(r'thank|confirmation (text|page|banner|message)|banner|received', t):
        parts.append('in_flow_text')
    return '+'.join(parts)


def source_kind(src):
    s = src.lower()
    if s.startswith(('02', 'answers')) or 'standing' in s:
        return 'standing_answers'
    if 'résumé' in s or 'resume' in s:
        return 'resume'
    if s.startswith(('07', 'rule', 'docs/07')):
        return 'rule_playbook'
    if 'chat' in s or 'user' in s or 'applicant' in s:
        return 'user_answer'
    return 'other'


def write_fragments(st, c, n, kind, findings, ts, note=''):
    """09 §6: the lane writes OUTCOME-/QB- fragments to AppApply-Capture/staging/. When it did not, build them from the
    attempt's findings and INTENT, scan them, and write each only if neither it nor an imported copy exists. A PII hit
    refuses the event (same as pii_gate). Returns the lines to print, including what the sources could not supply."""
    job, attempt, run = c['job_id'], c['attempt'], st.lane_run[n]
    stem = f'{job}-a{attempt}-{run}'
    staging = os.path.join(REPO, 'AppApply-Capture', 'staging')
    r = st.by_job[job]
    msgs, out = [], {}
    fnd = find_run_file(findings) if findings else []
    ftext = open(fnd[0], encoding='utf-8').read() if fnd else (note or '')
    intent = sorted(glob.glob(os.path.join(RUNS, '*', f'INTENT-{job}-a{attempt}-*.md')))
    itext = open(intent[-1], encoding='utf-8').read() if intent else ''
    evs = st.claim_events(job)
    first = lambda k: next((e for e in evs if e['kind'] == k), None)
    t0 = first('filling') or first('claimed')
    t1 = first('submit_clicked') or {'ts': ts}
    parse = lambda t: datetime.datetime.fromisoformat(t.replace('Z', '+00:00'))
    inv = md_rows(itext, r'P\d+\.F\d+')
    # inventory rows end Required (yes/no) then Options; ledger rows end with a State cell. Same ID pattern, told apart there.
    fields = {x[0]: x for x in inv if len(x) >= 6 and x[4].lower() in ('yes', 'no') and x[3].lower() != 'button'}
    ledg = {x[0]: x for x in inv if len(x) >= 5 and x[4].lower() not in ('yes', 'no')}
    trace = f'traces/{run}/TRACE-{job}-a{attempt}.jsonl'
    needs_k = {e['kind'] for e in evs}
    human = [h for h, k in (('approval', 'approved'), ('login', 'awaiting_login'), ('code', 'awaiting_code'),
                            ('needs_user', 'needs_user'), ('submit_handoff', 'awaiting_submit')) if k in needs_k]
    if kind == 'external':
        human.append('user_submit')
    req = sum(1 for x in fields.values() if x[4].lower() == 'yes')
    pages = max((int(x[1]) for x in fields.values() if x[1].isdigit()), default=0)
    ocsv = {'run_id': run, 'attempt_id': f'{job}-a{attempt}', 'job_id': job, 'company': r['company'], 'ats': r['ats'],
            'tenant': r['tenant'], 'outcome': 'submitted' if kind == 'external' else kind,
            'confirmation_method': confirmation_method(ftext),
            'started_at': t0['ts'], 'ended_at': t1['ts'],
            'duration_s': int((parse(t1['ts']) - parse(t0['ts'])).total_seconds()),
            'pages': pages or '', 'fields': len(fields) or '', 'required_fields': req if fields else '',
            'human_interventions': '+'.join(human), 'halt_reason': '',
            'trace_file': trace if os.path.exists(os.path.join(REPO, 'AppApply-Capture', trace)) else ''}
    out[f'OUTCOME-{stem}.csv'] = (OUTCOME_COLS, [ocsv])
    blanks = [k for k in OUTCOME_COLS if ocsv[k] == '' and k != 'halt_reason']
    if blanks:
        msgs.append(f'OUTCOME fragment: not in the sources, left blank: {", ".join(blanks)}')
    if fields:
        rows = []
        for fid, x in fields.items():
            lab, ctl, rq = x[2], x[3], x[4].lower()
            lg = ledg.get(fid)
            ans = lg[1] if lg else ''
            rows.append({'question_id': '', 'label_normalized': re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]+', ' ', lab.lower())).strip()[:60],
                         'label_verbatim': lab, 'answer_key': '', 'answer_planned': ans if SAFE_ANSWER.match(ans) else '',
                         'answer_source': source_kind(lg[2]) if lg else '', 'control': ctl, 'required': rq, 'selector': '',
                         'ats': r['ats'], 'company': r['company'].split(' (')[0], 'job_id': job, 'origin': 'lane',
                         'file': os.path.basename(intent[-1])})
        out[f'QB-{stem}.csv'] = (QB_COLS, rows)
        msgs.append('QB fragment: answer_key and selector are not in the INTENT (left blank); answer_planned is filled only '
                    'for non-personal choice answers')
    else:
        msgs.append('QB fragment NOT written: ' + (f'no inventory table in {os.path.basename(intent[-1])}' if intent
                                                    else f'no INTENT-{job}-a{attempt}-*.md found') + ' — the lane must write QB-' + stem + '.csv')
    os.makedirs(staging, exist_ok=True)
    done = []
    for name, (cols, rows) in out.items():
        dst = os.path.join(staging, name)
        if os.path.exists(dst) or glob.glob(os.path.join(staging, '_imported', '*', name)):
            msgs.append(f'{name}: already exists (staged or imported), kept as is')
            continue
        tmp = os.path.join(staging, '.tmp-' + name)
        with open(tmp, 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        done.append((name, tmp, dst))
    import subprocess
    scanner = os.path.join(REPO, 'tools', 'pii_scan.py')
    if done:
        res = subprocess.run([sys.executable, scanner] + [t for _, t, _ in done], capture_output=True, text=True)
        if res.returncode != 0:
            for _, t, _ in done:
                os.remove(t)
            die('PII scan hit in the generated fragments — nothing written, event refused (the scan prints where, never the value):\n'
                + (res.stdout or res.stderr).strip()[:600])
    for name, tmp, dst in done:
        try:
            os.link(tmp, dst)  # fails if a lane wrote it meanwhile: never overwrite
            msgs.append(f'wrote AppApply-Capture/staging/{name}')
        except FileExistsError:
            msgs.append(f'{name}: appeared meanwhile, kept as is')
        os.remove(tmp)
    return msgs


def pii_gate(job, attempt, findings):
    """08 §1 / 09 §5: an attempt's findings, INTENT and trace must hold no personal value before its terminal event."""
    scanner = os.path.join(REPO, 'tools', 'pii_scan.py')
    if not os.path.exists(scanner):
        die('tools/pii_scan.py is missing — the PII gate cannot run, so no terminal event is accepted (08 §1)')
    files = find_run_file(findings) if findings else []
    files += glob.glob(os.path.join(RUNS, '*', f'INTENT-{job}-a{attempt}-*.md'))
    files += glob.glob(os.path.join(REPO, 'AppApply-Capture', 'traces', '*', f'TRACE-{job}-a{attempt}.jsonl'))
    if not files:
        return
    import subprocess
    r = subprocess.run([sys.executable, scanner] + files, capture_output=True, text=True)
    if r.returncode == 1:
        die('PII scan hit — redact these before the event (the scan prints where, never the value):\n' + r.stdout.strip())
    if r.returncode not in (0, 1):
        die('tools/pii_scan.py failed: ' + (r.stderr or r.stdout).strip()[:300])


def cmd_retire(a):
    st = State(run_dir(a.run))
    n = lane_arg(st, a.lane)
    busy = [j for j, c in st.claims.items()
            if c['lane'] == n and c['lane_run'] == st.lane_run.get(n) and not st.status(j).startswith('done:')]
    if busy:
        die(f'lane {n} still holds {", ".join(busy)} — finish or `released` it first')
    ts, ct = now()
    append(os.path.join(st.d, 'events', f'lane{n}.jsonl'),
           {'ts': ts, 'ct': ct, 'lane': n, 'run': st.lane_run.get(n), 'kind': 'retire', 'note': a.note})
    print(f'lane {n} ({st.lane_run.get(n)}) retired · {ct}')


def orch_event(a, kind, jobs=None, **extra):
    st = State(run_dir(a.run))
    for j in jobs or []:
        if j not in st.by_job:
            die(f'{j} is not on the board')
    ts, ct = now()
    rec = {'ts': ts, 'ct': ct, 'kind': kind}
    if jobs is not None:
        rec['jobs'] = jobs
    if getattr(a, 'note', None):
        rec['note'] = a.note
    rec.update(extra)
    append(os.path.join(st.d, 'events', 'orch.jsonl'), rec)
    return st, ct


def cmd_simple(a):
    jobs = a.jobs
    if a.cmd == 'reviewed' and jobs == ['all-ready']:
        st = State(run_dir(a.run))
        jobs = [r['job_id'] for r in st.rows if st.status(r['job_id']) == 'ready']
    if a.cmd == 'drop' and not a.note:
        die('`drop` needs --note "<why>"')
    if a.cmd == 'preapprove' and not (a.note and DECISIONS_RE.search(a.note)):
        die('`preapprove` needs --note naming the PREP-DECISIONS file that records the operator\'s "apply as carded" ruling')
    if a.cmd in ('drop', 'hold', 'open', 'external'):
        st = State(run_dir(a.run))
        if a.cmd == 'external' and not a.note:
            die('`external` needs --note "<what the operator did and where the confirmation is>"')
        # A finished card stays finished: Submitted (by a lane, or by the operator's own click) is never reopened, held or dropped.
        fin = [j for j in jobs if (st.base.get(j) or '').startswith('external:') or st.status(j) in FINISHED]
        if fin:
            die(', '.join(fin) + f' already finished (submitted or recorded `external`) — `{a.cmd}` would overwrite it.')
        busy = [(j, st.claims[j]['lane']) for j in jobs if j in st.claims
                and st.status(j).split(':')[0] in ('active', 'waiting')]
        if busy:
            die('a lane is working ' + ', '.join(f'{j} (lane {n})' for j, n in busy) + f' — `{a.cmd}` only cards no lane '
                'holds. Message that lane instead: it posts `skipped`/`released` itself (09 §7).')
    if a.cmd == 'open':
        intent_guard(jobs, a.note)
    st, ct = orch_event(a, a.cmd, jobs)
    print(f'{a.cmd}: {len(jobs)} card(s) · {ct}')


def intent_guard(jobs, note):
    """01 §11: a job whose newest attempt has an INTENT but no findings may already be submitted. It goes back to
    ready only after the read-only check, and the note has to say so."""
    att = attempts_by_job()
    risky = [j for j in jobs if att.get(j, {}).get('intent_only')]
    if risky and not re.search(r'not sent|no submit|never submitted|nothing submitted', note or '', re.I):
        die(f'{", ".join(risky)}: an INTENT exists with no findings (01 §11 — the form may already be in). Do the read-only '
            f'confirmation first (candidate view, inbox, 03), then repeat with --note "not sent: <what you checked>". '
            f'If it WAS sent, write the recovered-/submitted- findings file instead; the board then excludes it.')


def cmd_confirm(a):
    """A card the board holds as `unconfirmed` that read-only evidence shows was submitted (mail receipt, ADP My
    Applications). `event` refuses a second terminal event and `external` refuses a finished card, so this is the path."""
    st = State(run_dir(a.run))
    if not a.note:
        die('`confirm` needs --note "<the read-only evidence: where you saw it and what it says>"')
    for j in a.jobs:
        if j not in st.by_job:
            die(f'{j} is not on the board')
        if st.status(j) != 'done:unconfirmed':
            die(f'{j} is {st.status(j)}; `confirm` is only for a card the board holds as done:unconfirmed')
        if j in st.confirmed:
            die(f'{j} was already confirmed ({st.confirmed[j]["ct"]})')
    if a.findings:
        find_run_file(a.findings) or die(f'findings file {a.findings} not found in Runs/')
        for j in a.jobs:
            pii_gate(j, st.claims[j]['attempt'], a.findings)
    st, ct = orch_event(a, 'confirm', a.jobs, **({'findings': a.findings} if a.findings else {}))
    print(f'confirm: {len(a.jobs)} card(s) · {ct} · queue-plan now writes Status Submitted'
          + (f', H {a.findings}' if a.findings else ''))


def cmd_reopen(a):
    st = State(run_dir(a.run))
    c = st.claims.get(a.job) or die(f'{a.job} has no claim')
    s = st.status(a.job)
    if not (s.startswith('orphaned') or s == 'done:paused'):
        die(f'{a.job} is {s}; only orphaned or paused claims can be reopened')
    if not a.note:
        die('`reopen` needs --note "<01 §11 finding, e.g. no INTENT → Ready>"')
    intent_guard([a.job], a.note)
    ts, ct = now()
    release_lock(st.d, c)
    os.makedirs(os.path.join(st.d, 'claims', '_released'), exist_ok=True)
    shutil.move(os.path.join(st.d, 'claims', a.job), os.path.join(st.d, 'claims', '_released', f'{a.job}-{ts.replace(":", "")}'))
    orch_event(a, 'open', [a.job], reopened_from=s)
    print(f'{a.job} reopened ({s}) → ready · {ct}')


def cmd_decisions(a):
    find_run_file(a.file) or die(f'{a.file} not found in Runs/')
    st, ct = orch_event(a, 'decisions', file=a.file)
    print(f'decisions file recorded: {a.file} · lanes see it on every claim')


def since(ts):
    t = datetime.datetime.fromisoformat(ts.replace('Z', '+00:00'))
    m = int((datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() // 60)
    return f'{m}m' if m < 60 else f'{m // 60}h{m % 60:02d}'


def cmd_board(a):
    st = State(run_dir(a.run))
    ts, ct = now()
    stat = {j: st.status(j) for j in st.by_job}
    count = lambda p: sum(1 for s in stat.values() if s.startswith(p))
    checks = [e for e in st.orch if e['kind'] == 'queue_check']
    def synced(j):
        done_ts = max(st.claim_events(j)[-1]['ts'], (st.confirmed.get(j) or {}).get('ts', ''))
        return any(e['ts'] >= done_ts and j in e.get('clean', []) for e in checks)
    pending = [j for j, s in stat.items() if s.startswith('done:') and s != 'done:released' and not synced(j)]
    conf = sum(1 for j in st.confirmed if stat.get(j) == 'done:unconfirmed')
    print(f'DISPATCH {st.meta["run"]} · {ct} · submitted {count("done:submitted") + conf + count("done:external")} · unconfirmed '
          f'{count("done:unconfirmed") - conf} · paused {count("done:paused")} · skipped/closed '
          f'{count("done:skipped") + count("done:closed")} · ready {count("ready")} · hold {count("hold")} · '
          f'Easy Apply {st.ea_submitted()}/{st.meta["ea_cap"]} · Queue writes pending {len(pending)}')
    print('\nLANE  RUN                      NOW')
    needs = []
    for n in range(1, st.meta['lanes'] + 1):
        run = st.lane_run.get(n, '—')
        cur = [(j, c) for j, c in st.claims.items() if c['lane'] == n and c['lane_run'] == run
               and not stat[j].startswith('done:')]
        left = sum(1 for r in st.rows if r['lane'] == str(n) and stat[r['job_id']] == 'ready')
        tag = ' (retired)' if n in st.retired else ''
        if n in st.lane_run and n not in st.retired and not st.window_ready(n):
            tag += ' · WINDOW HIDDEN' if st.win_bad.get(n) else ' · window not proved'
        if not cur:
            print(f'{n:<5} {run:<24} idle{tag} · {left} ready in its list')
        for j, c in cur:
            evs = st.claim_events(j) or [{'ts': c['at']}]
            r = st.by_job[j]
            note = evs[-1].get('note', '')
            hidden = ' · WINDOW HIDDEN' if (HIDDEN_RE.search(note) or not st.window_ready(n)) else ''
            print(f'{n:<5} {run:<24} {r["company"][:28]} {j} ({r["ats"]}) · {stat[j]} · {since(evs[-1]["ts"])} · '
                  f'{left} ready after{hidden}')
            if stat[j].startswith('waiting:'):
                needs.append((evs[-1]['ts'], n, j, stat[j].split(':')[1], note))
    if needs:
        print('\nNEEDS YOU (oldest first; go to that lane\'s chat)')
        for i, (t, n, j, k, note) in enumerate(sorted(needs, key=lambda x: (x[3] != 'awaiting_submit', x[0])), 1):
            label = 'SUBMIT HANDOFF' if k == 'awaiting_submit' else k
            print(f'  {i}. lane {n} · {label} · {st.by_job[j]["company"]} {j} · {since(t)}' + (f' · {note}' if note else ''))
    orph = [j for j, s in stat.items() if s.startswith('orphaned')]
    if orph:
        print('\nORPHANED (a lane chat ended mid-card): recover per 01 §11, then `reopen <JobID> --note …`')
        for j in orph:
            c = st.claims[j]
            has_intent = bool(glob.glob(os.path.join(RUNS, '*', f'INTENT-{j}-a{c["attempt"]}-*.md')))
            print(f'  {j} {st.by_job[j]["company"]} · lane {c["lane"]} ({c["lane_run"]}) · {stat[j]} · '
                  f'INTENT a{c["attempt"]}: {"YES → Paused-Verify, never re-submit" if has_intent else "no → safe to reopen"}')
    if pending:
        print(f'\nQUEUE WRITES PENDING ({len(pending)}): export the Queue, then `queue-plan --queue <export>`')
    if getattr(a, 'holds', False):
        print('\nON HOLD')
        for r in st.rows:
            if stat[r['job_id']].startswith('hold'):
                print(f'  {r["job_id"]} · {r["company"]} · lane {r["lane"]} · {stat[r["job_id"]][:110]}')


def cmd_list(a, st=None):
    st = st or State(run_dir(a.run))
    for r in st.rows:
        if a.lane and r['lane'] != str(a.lane):
            continue
        s = st.status(r['job_id'])
        print(f'{r["order"]:>4} L{r["lane"]} {r["job_id"]} · {r["company"][:30]} · {r["ats"]} · login {r["login"]} · '
              f'P{r["priority"]} · {s[:60]}' + (' · reviewed' if r['job_id'] in st.reviewed else ''))


def cmd_show(a):
    st = State(run_dir(a.run))
    r = st.by_job.get(a.job) or die(f'{a.job} is not on the board')
    print(json.dumps(r, ensure_ascii=False, indent=1))
    print('status:', st.status(a.job), '· reviewed' if a.job in st.reviewed else '')
    for e in st.claim_events(a.job):
        print(' ', e['ct'], e['kind'], {k: v for k, v in e.items() if k in ('findings', 'status', 'note', 'approval')})


def plan_cells(plan, q, j, want, ct):
    """Append the cells of row q that differ from `want`, plus C (the date) when anything changes. Returns True if any."""
    diff = [(col, (q.get(col) or '').strip(), v) for col, v in want.items() if (q.get(col) or '').strip() != v]
    for col, cur, v in diff + ([('C', '(date serial)', ct.rsplit(' ', 1)[0])] if diff else []):
        plan.append((str(q['row']), j, col, cur, v))
    return bool(diff)


def queue_plan(st, queue):
    """Cells the Queue still needs for every finished card: [(row, job, col, current, wanted)], and the clean jobs."""
    plan, clean = [], []
    for j, r in st.by_job.items():
        s = st.status(j)
        if not s.startswith('done:') or s == 'done:released':
            continue
        e = st.claim_events(j)[-1]
        kind = s.split(':')[1]
        cf = st.confirmed.get(j)
        if kind == 'unconfirmed' and cf:
            kind = 'submitted'  # `confirm`: read-only evidence after the lane's unconfirmed; the Queue must not revert to it
        want = {'B': e.get('status') if kind == 'paused' else QUEUE_STATUS[kind]}
        if (cf or {}).get('findings') or e.get('findings'):
            want['H'] = (cf or {}).get('findings') or e['findings']
        if kind == 'paused':
            if 'f' in e:
                want['F'] = e['f']      # a pause without --f leaves the sheet's F alone (the question is the record)
        else:
            want['F'] = ''
        appr = next((x for x in reversed(st.claim_events(j)) if x.get('approval')), None)
        if appr:
            want['I'] = f'{appr["ct"]} approved: "{appr["approval"]}" — chat {appr["run"]}'
        q = queue.get(j)
        if not q:
            plan.append((r['queue_row'], j, '?', 'row not found in export', ''))
            continue
        if not (q.get('D') or '').strip():
            want['D'] = r['ats_label']
        if not (q.get('E') or '').strip():
            want['E'] = r['tenant']
        if not plan_cells(plan, q, j, want, e['ct']):
            clean.append(j)
    # Cards the orchestrator dropped (the operator's skip in the sweep, preflight: closed) → B Skipped/Closed, H the decisions file.
    drops, opened = {}, {}
    for e in st.orch:
        for j in e.get('jobs', []):
            if e['kind'] == 'drop':
                drops[j] = e
                opened.pop(j, None)
            elif e['kind'] == 'open':
                drops.pop(j, None)
                opened[j] = e
            elif e['kind'] == 'hold':
                opened.pop(j, None)
    for j, e in drops.items():
        q = queue.get(j)
        if not q or not st.status(j).startswith('dropped'):
            continue
        note = e.get('note', '')
        want = {'B': 'Closed' if re.search(r'preflight:\s*closed', note, re.I) else 'Skipped'}
        m = DECISIONS_RE.search(note)
        if m:
            want['H'] = m.group(1)
        plan_cells(plan, q, j, want, e['ct'])
    # Released cards back on the board that left a findings file (inventory only, no INTENT): point H at it.
    rel = {}
    for evs in st.lane_events.values():
        for e in evs:
            if e['kind'] == 'released':
                rel[e['job']] = e
    for j, e in rel.items():
        q = queue.get(j)
        if not q or st.status(j) != 'ready':
            continue
        f = e.get('findings') or next((os.path.basename(p) for p in sorted(glob.glob(
            os.path.join(RUNS, '*', f'*-{j}-a{e["attempt"]}-*.md')))
            if re.match(r'(paused|skipped|closed)-', os.path.basename(p))), '')
        if f:
            plan_cells(plan, q, j, {'H': f}, e['ct'])
    # Holds the operator cleared in the sweep (`open`) whose Queue row still says Paused-Question or In progress: B → Ready, so
    # the next `init` doesn't hold them again (R20260924-0850: Southend, Strategy Engineering). Only while no lane holds
    # the card (a finished card's own write wins), and never over Paused-Verify/Technical/CAPTCHA: those move only on
    # the operator's G per 01 §1.3. F keeps the question as the record; H points at the decisions file when the note names one.
    for j, e in opened.items():
        q = queue.get(j)
        if not q or st.status(j) != 'ready' or (q.get('B') or '').strip() not in ('Paused-Question', 'In progress'):
            continue
        want = {'B': 'Ready'}
        m = DECISIONS_RE.search(e.get('note') or '')
        if m:
            want['H'] = m.group(1)
        plan_cells(plan, q, j, want, e['ct'])
    return plan, clean


def cmd_queue_plan(a):
    st = State(run_dir(a.run))
    if a.apply and a.queue != 'api':
        die('--apply needs --queue api (writes go through tools/queue_api.py)')
    plan, clean = queue_plan(st, read_queue(a.queue))
    src = 'the Sheets API' if a.queue == 'api' else os.path.basename(a.queue)
    print(f'Queue check vs {src}: {len(clean)} row(s) match, {len({p[1] for p in plan})} row(s) need writing')
    for row, j, col, cur, v in sorted(plan, key=lambda p: (int(p[0]) if p[0].isdigit() else 0, p[2])):
        print(f'  row {row} · {j} · {col}: "{cur[:60]}" → "{v}"')
    if a.apply and plan:
        if any(p[2] == '?' for p in plan):
            die('some finished cards have no Queue row — fix that first (sheet integrity, 01 §1.5)')
        if not queue_api().write_cells([(j, col, v) for row, j, col, cur, v in plan], st.meta['run'], apply=True):
            orch_event(a, 'queue_check', None, clean=[], dirty=sorted({p[1] for p in plan}))
            die('read-back failed — nothing is marked synced; see the lines above')
        plan, clean = queue_plan(st, read_queue('api'))
        print(f'after writing: {len(clean)} row(s) match, {len({p[1] for p in plan})} still differ')
    orch_event(a, 'queue_check', None, clean=clean, dirty=sorted({p[1] for p in plan}))
    if not plan:
        print('  nothing to write — the sheet matches every finished card.')
    elif not a.apply:
        print('  write them with `queue-plan --queue api --apply` (or by hand per 01 §1.4, then re-check)')


# ---------- needs (09 §4.5 sweep prep) and watch (09 §7 phone pushes) ----------

# A card's "Needs you" item that the current answers file already answers. Checked in order; the first match wins. Items that ask
# whether to apply at all (fit gaps, mismatches, "apply anyway?") are never auto-resolved: they stay the operator's.
NEEDS_RULES = [
    ('login', r'login needed|sign[ -]?in|account (creation|password)|create (an )?account|workday account|one-time code|code gate',
     'login list (not a sweep question)'),
    ('jd-missing', r"(jd|description)( text| body)?\b.{0,30}(did not|never|wouldn.t|won.t|wasn.t|unavailable|didn.t)", 'the lane re-reads the JD while preparing'),
    ('travel', r'travel|overnight', 'answers §Screening: travel'),
    ('relocation', r'relocat|on-site in|based in', 'answers §Screening: relocation'),
    ('salary', r'salary|compensation|numeric|pay range|base pay', 'answers §Compensation (figure and posted-range rules)'),
    ('presales', r'pre-?sales|solutions? architect|sales engineer', 'answers §Screening: years in the role family'),
    ('gov-official', r'government official|appointed official', 'answers §Attestations'),
    ('school', r'school\b|university|degree', 'answers §Education'),
    ('how-heard', r'how did you hear', 'answers §Screening: how heard'),
    ('recording', r'record(ing|ed)', 'answers §Consents: interview recording'),
    ('pay-structure', r'1099|commission|part-time|hours per week|h/wk', 'answers §Screening: pay structure'),
    ('on-call', r'on-call|weekend|lift(ing)? up to|physical', 'answers §Screening: on-call, weekend, physical requirements'),
    ('hours', r'extended hours|\b5\d[–-]\d\d ?h|cover lower', 'answers §Screening: extended hours'),
    ('citizen', r'citizen', 'answers §Work authorization'),
    ('acknowledgement', r'acknowledg|waiver|at-will', 'answers §Consents: standard acknowledgement'),
]
USERS_OWN = r'\bfit\b|apply anyway|\[apply/skip\]|mismatch|confirm this is|intended job|skip\?'


def card_needs(path):
    """The bullet items under a card's '## Needs you' heading (older cards: '## Needs <name>')."""
    t = open(path, encoding='utf-8').read()
    m = re.search(r'^## Needs [^\n]*\n(.*?)(?=^## |\Z)', t, re.S | re.M)
    items, cur = [], ''
    for line in (m.group(1) if m else '').splitlines():
        if re.match(r'\s*[-*] ', line):
            if cur:
                items.append(cur)
            cur = re.sub(r'^\s*[-*] ', '', line).strip()
        elif line.strip() and cur:
            cur += ' ' + line.strip()
    if cur:
        items.append(cur)
    return [i for i in items if not re.match(r'(?i)\(?none\b|nothing\b|n/a\b', i)]


def cmd_needs(a):
    st = State(run_dir(a.run))
    prior_files = sorted(glob.glob(os.path.join(RUNS, '*', 'PREP-DECISIONS*.md')) +
                         glob.glob(os.path.join(RUNS, '*', 'DECISION-*.md')))
    prior_text = {p: open(p, encoding='utf-8').read().splitlines() for p in prior_files}
    total = {'auto': 0, 'ask': 0, 'prior': 0, 'ruled': 0}
    for r in st.rows:
        s = st.status(r['job_id'])
        if (a.lane and r['lane'] != str(a.lane)) or not (s == 'ready' or s.startswith('hold')):
            continue
        cards = find_run_file(r['card'])
        items = card_needs(cards[0]) if cards else []
        prior = [(os.path.basename(p), l.strip()) for p, ls in prior_text.items() for l in ls if r['job_id'] in l]
        if not items and not prior and not s.startswith('hold'):
            continue
        print(f'\n{r["job_id"]} · {r["company"][:40]} · {r["role"][:50]} · lane {r["lane"]} · {s[:60]}')
        for p, l in prior:
            total['prior'] += 1
            print(f'   PRIOR   {p}: {l[:170]}')
        for it in items:
            rule = None if re.search(USERS_OWN, it, re.I) else next(
                ((nm, how) for nm, pat, how in NEEDS_RULES if re.search(pat, it, re.I)), None)
            if rule:
                total['auto'] += 1
                print(f'   ANSWERS {it[:120]}  →  {rule[1]}')
            elif prior:
                # A prior decisions line names this Job ID: read it before asking. On 09-24, 21 of 27 ASK items were
                # already ruled this way (LEARNINGS-R20260924-0850-orch §4).
                total['ruled'] += 1
                print(f'   RULED?  {it[:160]}  →  a PRIOR line above names this Job ID; ask only if it doesn\'t cover this item')
            else:
                total['ask'] += 1
                print(f'   ASK     {it[:200]}')
    print(f'\nneeds: {total["ask"] + total["ruled"]} item(s) still need a look — {total["ask"]} to ask the operator plus '
          f'{total["ruled"]} RULED? to check against the PRIOR lines first · {total["auto"]} answered by the current answers file · '
          f'{total["prior"]} prior ruling line(s) found (show them in the sweep question)')


def cmd_watch(a):
    """One line per lane event the operator should hear about. Built for the Monitor tool: each line becomes a notification."""
    import time
    d = run_dir(a.run)
    seen, first = {}, True
    while True:
        st = State(d)
        for n in range(1, st.meta['lanes'] + 1):
            evs = st.lane_events[n]
            start = seen.get(n, 0 if (a.replay or not first) else len(evs))
            for e in evs[start:]:
                k = e['kind']
                if k not in WAITING + ('window_hidden', 'submitted', 'unconfirmed', 'external', 'paused', 'released', 'retire', 'register'):
                    continue
                r = st.by_job.get(e.get('job', ''), {})
                tag = ('SUBMIT HANDOFF' if k == 'awaiting_submit' else 'NEEDS YOU' if k in WAITING + ('window_hidden',)
                       else 'LANE' if k in ('retire', 'register') else 'DONE')
                line = f'{tag} · lane {n} · {k} · {r.get("company", "")[:30]} {e.get("job", "")} · {e.get("note", "")}'
                print(line.strip(' ·')[:220], flush=True)
            seen[n] = len(evs)
        first = False
        if a.once:
            return
        if st.lane_run and all(n in st.retired for n in st.lane_run):
            print('ALL LANES RETIRED', flush=True)
            return
        time.sleep(a.interval)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--run', help='orchestrator Run ID (default: newest dispatch folder)')
    sp = p.add_subparsers(dest='cmd', required=True)
    x = sp.add_parser('init'); x.add_argument('run_id'); x.add_argument('--queue', required=True)
    x.add_argument('--lanes', type=int, default=5); x.add_argument('--ea-lane', type=int, default=5)
    x.add_argument('--ea-cap', type=int, default=15)
    x.add_argument('--force', metavar='WHY', help='start a new board although another board still has lanes holding claims (recorded in meta.json)')
    x = sp.add_parser('register'); x.add_argument('lane'); x.add_argument('lane_run')
    x = sp.add_parser('window'); x.add_argument('lane'); x.add_argument('state', choices=('ok', 'hidden'))
    x.add_argument('--note', help='what the lane saw (e.g. "tab 4 of 6 in a shared window", "JS timed out 45 s")')
    x = sp.add_parser('claim'); x.add_argument('lane')
    x.add_argument('--ahead', type=int, default=1, help=f'hold up to this many cards (max {MAX_AHEAD}) and ask in one round')
    x.add_argument('--hands-free', action='store_true', help='skip cards that need a login (the operator away)')
    x.add_argument('--peek', action='store_true', help='show what would be claimed; claim nothing, no window proof needed')
    x = sp.add_parser('event'); x.add_argument('lane'); x.add_argument('job'); x.add_argument('kind', choices=KINDS)
    for f in ('--findings', '--approval', '--status', '--f', '--note'):
        x.add_argument(f)
    x = sp.add_parser('retire'); x.add_argument('lane'); x.add_argument('--note')
    x = sp.add_parser('board'); x.add_argument('--holds', action='store_true')
    x = sp.add_parser('list'); x.add_argument('lane', nargs='?')
    x = sp.add_parser('show'); x.add_argument('job')
    x = sp.add_parser('queue-plan'); x.add_argument('--queue', required=True); x.add_argument('--apply', action='store_true')
    for name in ('open', 'hold', 'drop', 'reviewed', 'login', 'preapprove', 'full', 'external'):
        x = sp.add_parser(name); x.add_argument('jobs', nargs='+'); x.add_argument('--note')
    x = sp.add_parser('reopen'); x.add_argument('job'); x.add_argument('--note')
    x = sp.add_parser('confirm'); x.add_argument('jobs', nargs='+'); x.add_argument('--note')
    x.add_argument('--findings', help='the superseding findings file, if one was written; queue-plan then points H at it')
    x = sp.add_parser('decisions'); x.add_argument('file')
    x = sp.add_parser('needs'); x.add_argument('lane', nargs='?')
    x = sp.add_parser('watch'); x.add_argument('--interval', type=int, default=20)
    x.add_argument('--once', action='store_true'); x.add_argument('--replay', action='store_true')
    a = p.parse_args()
    {'init': cmd_init, 'register': cmd_register, 'window': cmd_window, 'claim': cmd_claim, 'event': cmd_event, 'retire': cmd_retire,
     'board': cmd_board, 'list': cmd_list, 'show': cmd_show, 'queue-plan': cmd_queue_plan, 'open': cmd_simple,
     'hold': cmd_simple, 'drop': cmd_simple, 'reviewed': cmd_simple, 'login': cmd_simple, 'preapprove': cmd_simple,
     'full': cmd_simple, 'external': cmd_simple, 'reopen': cmd_reopen, 'confirm': cmd_confirm,
     'decisions': cmd_decisions, 'needs': cmd_needs, 'watch': cmd_watch}[a.cmd](a)


if __name__ == '__main__':
    main()
