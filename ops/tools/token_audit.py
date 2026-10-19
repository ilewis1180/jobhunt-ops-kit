#!/usr/bin/env python3
"""Token audit over every Claude Code transcript of the job hunt -> Runs/<date>/TOKEN-AUDIT-*-<RunID>.csv.

  python3 tools/token_audit.py [--run-id R20261017-HHMM-audit] [--since YYYY-MM-DD] [--projects-glob GLOB]
                               [--rates IN,OUT,CW5M,CW1H,CR] [--out-dir DIR] [--dry-run]
  python3 tools/token_audit.py --spot-check 10
  python3 tools/token_audit.py --write-usage <OrchRunID> [--weekly-start N] [--weekly-now N] [--weekly-resets ISO]
                               [--dry-run]                                dashboard feed Runs/<date>/USAGE-<OrchRunID>.csv

--write-usage <OrchRunID> (replaces usage_report.py): one row per session of that Phase 3 run in the 16-column
dashboard contract (USAGE_FIELDS): the orchestrator (`orch`, later hand-off sessions `orch-<HHMM>`) and its lanes
(`lane<N>-<HHMM>` from the lane's own run id). jobs_attempted / jobs_submitted per lane come from outcomes.csv +
outcomes-jt.csv rows whose run_id is the lane's own id (orch row blank). weekly_pct_start / weekly_pct_now /
weekly_resets_at are not readable from the transcripts: pass what the operator reads off their usage page with
--weekly-start N, --weekly-now N and --weekly-resets <ISO time> (orch row only); left out, they stay blank. Run it at
each orchestrator checkpoint and at session end (09 §7–§8). The file is the run's live feed: it is rewritten atomically
(temp + rename, so a file sync never ships half a file) while its date is today, and refused after that, so it is
write-once history once the run day is over.

Read-only over its inputs: the Claude Code transcripts (config paths.transcripts_glob, e.g.
~/.claude/projects/-Users-<you>-<project>*/<session>.jsonl, streamed line by line, never json-loaded whole) and
AppApply-Capture/outcomes.csv + outcomes-jt.csv. It writes only new files; an existing
output file is never overwritten (Runs/ is write-once), the tool exits instead. No message text is written except
`first_user_line`, the first 120 chars of the first user message with emails, phone numbers, street addresses, URLs and
long digit runs blanked, kept for classification spot-checks.

Outputs (RunID = --run-id, else R<today>-audit):
  TOKEN-AUDIT-sessions-<RunID>.csv  one row per top-level transcript, sorted by started_at
  TOKEN-AUDIT-by-phase-<RunID>.csv  per phase: sessions, turns, screenshots, token sums, median/p90 cache_read, share
  TOKEN-AUDIT-by-run-<RunID>.csv    per calendar day (level=day) and per orchestrator run (level=orch_run)
  TOKEN-AUDIT-by-tool-<RunID>.csv   per tool name: calls, sessions, result chars, result images

How each column is counted (approximate, by design):
- Tokens: lifted from usage_report.scan(): every assistant entry carries message.usage; one API response is split over
  several JSONL lines that repeat the same usage, so each message.id is counted once (falling back to the entry uuid).
  cache_creation is split by TTL from usage.cache_creation.ephemeral_5m/1h_input_tokens (cache_write_5m/1h columns).
- turns = distinct assistant message ids, i.e. API calls. Each call re-reads the cached prefix, so cache_read/turn is
  roughly the context size. user_prompts = real user messages (text that does not start with '<', not tool results).
- model = most common message.model over those distinct responses ('<synthetic>' entries ignored).
- Tool stats come from assistant tool_use blocks, de-duplicated by tool_use id. computer_calls = names ending in
  'computer' (claude-in-chrome and Claude_Browser); screenshots = those with input.action == 'screenshot';
  batch_screenshots = screenshot actions inside browser_batch inputs (not in `screenshots`); read_calls = Read;
  batch_calls = any name ending in browser_batch. read_chars / page_text_chars = total length of the text of the
  matching tool_result (tool_use_id -> tool name map; content may be a string or a list of text blocks; images are not
  counted as chars). result_chars = text length of every tool_result; result_images = image blocks in tool results
  (the real screenshot payload, whichever tool returned it).
- phase: from the first real user message, lifted from usage_report.first_user_text() (first 'user' entry whose text
  does not start with '<'). Case-insensitive, in this order: lane, logins, single, scrape+prep, discover, scrape,
  prep, orch (phase 3 / apply / approve), jd, status; else other (the routing words of docs/00). Tier 1: the routing
  word starts the message (after an optional start/run/let's/please). Tier 2: an explicit "phase N ..." anywhere in the
  first 200 chars. Bare words (apply, prep, status...) count only at the start, because free-text questions use them
  too. A session handed off from another session ("Background (from the session that started this one)...") is
  always other.
- run_id_guess: first R\\d{8}-\\d{4}-[a-z0-9]+ in the first user message, else in the first three assistant messages
  (text + tool inputs). For a lane, run_id_guess is the lane's own R<start date>-HHMM-apply<N> id: the first one in
  the transcript (first 6000 chars of each of the first 400 entries). Same-date only, and first rather than
  most-mentioned, because a restarted lane quotes its predecessor's id more often than its own. orch_run_id is the
  orchestrator id named in the lane line. For an orch row, orch_run_id is its own id: the most-mentioned
  R<start date>-HHMM-orch in the transcript (same date as the session start, so an older run id quoted from a file is
  not picked up).
- handoff = 1 when the first prompt is a session hand-off brief. Its phase stays other (per the brief), but when its
  transcript names a same-date orchestrator id it gets that orch_run_id, so by-run counts it with its run and the
  p3_* columns count it as Phase 3.
- first_user_line falls back to the first queue-operation prompt when no user entry has real text, and a leading
  @"<file>" attachment is skipped for classification (an attached 05-SCRAPE / 06-JD / 10-DISCOVER / 09-PARALLEL doc
  sets the phase).
- subagent_* columns: transcripts under <session>/subagents/*.jsonl, summed the same way. They are NOT in the four main
  token columns (usage_report never counted them either), so the 09-29 check compares like with like.
- Dates: started_at/ended_at are UTC ISO. The by-run `date` is the local date of started_at (config [run] timezone),
  which matches the date in the run ids.
- submitted (by-run): rows with outcome == submitted in outcomes.csv + outcomes-jt.csv. Day rows count by the 8-digit
  date in the outcome's run_id. Orch-run rows count outcomes whose run_id is the orch id or one of its lanes' own ids;
  if none match and it is the only orchestrator run that day, the day's count is used (submitted_basis says which).
- api_equiv_usd: only when --rates is given (prices per million tokens, from the claude-api skill, never typed from
  memory). Every session is priced at those rates whatever its model, so it is a Sonnet-5.5-list-price equivalent.

"""
import argparse, collections, csv, datetime, glob, json, os, re, statistics, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

REPO = common.REPO
DEFAULT_GLOB = common.transcripts_glob()
RUN_RE = re.compile(r'R\d{8}-\d{4}-[a-z0-9]+')
ORCH_RE = re.compile(r'R\d{8}-\d{4}-orch\b')
TOKS = ['input_tokens', 'output_tokens', 'cache_creation_tokens', 'cache_read_tokens']

SESSION_FIELDS = ['session_id', 'project_dir', 'started_at', 'ended_at', 'duration_min', 'model', 'phase', 'run_id_guess',
                  'turns', 'tool_calls', 'computer_calls', 'screenshots', 'read_calls', 'read_chars', 'page_text_chars',
                  'batch_calls', *TOKS, 'first_user_line',
                  # extra columns beyond the brief
                  'orch_run_id', 'handoff', 'date', 'user_prompts', 'batch_screenshots', 'result_chars', 'result_images',
                  'cache_write_5m', 'cache_write_1h', 'cache_read_per_turn', 'subagents', 'subagent_input_tokens',
                  'subagent_output_tokens', 'subagent_cache_creation_tokens', 'subagent_cache_read_tokens']

# ---- phase routing (CLAUDE.md lines 7-18) -------------------------------------------------------------------------
PHASES = [
    ('lane', r'phase\s*3\s*lane\s*\d'),
    ('logins', r'phase\s*3\s*logins?\b'),
    ('single', r'phase\s*3\s*single\b'),
    ('scrape+prep', r'phase\s*1\s*\+\s*2\b|scrape\s+and\s+prep\b'),
    ('discover', r'phase\s*0\b|\bdiscover\b'),
    ('scrape', r'phase\s*1\b|\bscrape\b'),
    ('prep', r'phase\s*2\b|\bprep\b'),
    ('orch', r'phase\s*3\b|\bapply\b|\bapprove\b'),
    ('jd', r'\bjd\b'),
    ('status', r'\bstatus\b|what\'?s next|where are we'),
]
PHASES = [(n, re.compile(p)) for n, p in PHASES]


LEAD = re.compile(r"^(?:(?:please|ok(?:ay)?|let'?s|start|run|begin|do|go|now|next)[\s,:]+)*")
HANDOFF = re.compile(r'^background \(from the session')


def classify(text):
    """Tier 1: a routing word at the very start (after start/run/let's...). Tier 2: an explicit `phase N` anywhere in
    the first 200 chars (bare words like apply/prep are too common in free text to match there). Session hand-off
    briefs ("Background (from the session ...") are always other: they mention phases while asking for other work."""
    for rx, name in DOC_PHASE:             # a prompt that attaches a phase doc (@".../05-SCRAPE-PROMPT.md")
        if AT_REF.match(text) and rx.search(AT_REF.match(text).group(0)):
            return name
    while AT_REF.match(text):
        text = AT_REF.sub('', text, count=1)
    low = ' '.join(text.lower().split())[:200]
    if HANDOFF.match(low):
        return 'other'
    head = low[LEAD.match(low).end():]
    for name, rx in PHASES:
        m = rx.search(head)
        if m and m.start() == 0:
            return name
    for name, rx in PHASES:
        m = re.search(r'phase\s*[0-3]', rx.pattern) and rx.search(low)
        if m and m.group(0).startswith('phase'):
            return name
    return 'other'


# ---- scrubbing for first_user_line --------------------------------------------------------------------------------
SCRUB = [
    re.compile(r'\S+@\S+'),
    re.compile(r'https?://\S+'),
    re.compile(r'\+?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}'),
    re.compile(r'\b\d{1,6}\s+(?:[A-Z][a-z]+\s+){1,3}(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Dr|Drive|Ln|Lane|Way|Ct|Court|'
               r'Pkwy|Parkway|Hwy|Pl|Place|Cir|Trl)\b\.?', re.I),
    re.compile(r'\b\d{5,}\b'),
]


def scrub(text):
    s = ' '.join(text.split())[:160]
    keep = RUN_RE.findall(s)                       # run ids look like phone numbers / long digit runs: protect them
    s = RUN_RE.sub('\x00', s)
    for rx in SCRUB:
        s = rx.sub('[x]', s)
    for rid in keep:
        s = s.replace('\x00', rid, 1)
    return s[:120]


# ---- helpers lifted from usage_report.py ---------------------------------------------------------------------------
LEAD_TAGS = re.compile(r'^\s*(?:<([a-z][a-z_-]*)\b[^>]*>.*?</\1>\s*)+', re.S)
AT_REF = re.compile(r'^\s*(?:@"[^"]*"|@\S+)\s*')
DOC_PHASE = [(re.compile(r'05-SCRAPE'), 'scrape'), (re.compile(r'06-JD'), 'jd'), (re.compile(r'10-DISCOVER'), 'discover'),
             (re.compile(r'09-PARALLEL'), 'orch')]


def user_text(o):
    """usage_report.first_user_text() applied to one entry, with one change: leading tag blocks
    (<system-reminder>...</system-reminder>, <command-name>...) are stripped from each text block first, so a prompt
    that the app delivered behind a reminder still counts. Returns '' when nothing real is left."""
    if o.get('type') != 'user':
        return ''
    c = (o.get('message') or {}).get('content')
    parts = [x.get('text', '') for x in c if isinstance(x, dict)] if isinstance(c, list) else [c]
    keep = []
    for t in parts:
        if not isinstance(t, str):
            continue
        t = LEAD_TAGS.sub('', t)
        if t.strip() and not t.lstrip().startswith('<'):
            keep.append(t)
    return ' '.join(keep)


def add_usage(u, acc):
    """usage_report.scan() summation for one distinct message: input, output, cache_creation, cache_read (+ TTL split)."""
    acc['input_tokens'] += u.get('input_tokens') or 0
    acc['output_tokens'] += u.get('output_tokens') or 0
    acc['cache_creation_tokens'] += u.get('cache_creation_input_tokens') or 0
    acc['cache_read_tokens'] += u.get('cache_read_input_tokens') or 0
    cc = u.get('cache_creation') or {}
    acc['cache_write_5m'] += cc.get('ephemeral_5m_input_tokens') or 0
    acc['cache_write_1h'] += cc.get('ephemeral_1h_input_tokens') or 0


def result_len(content):
    """(text chars, image blocks) of a tool_result content (string or list of blocks)."""
    if isinstance(content, str):
        return len(content), 0
    chars = imgs = 0
    if isinstance(content, list):
        for x in content:
            if not isinstance(x, dict):
                continue
            if x.get('type') == 'image':
                imgs += 1
            elif isinstance(x.get('text'), str):
                chars += len(x['text'])
    return chars, imgs


def tokens_only(path, until=None):
    """Token sums for one transcript; with `until` (ISO UTC) only entries stamped at or before it."""
    acc = collections.Counter()
    seen = set()
    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            if '"usage"' not in line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            m = o.get('message')
            if o.get('type') != 'assistant' or not isinstance(m, dict) or not m.get('usage'):
                continue
            if until and (o.get('timestamp') or '')[:19] > until[:19]:
                continue
            mid = m.get('id') or o.get('uuid')
            if mid in seen:
                continue
            seen.add(mid)
            add_usage(m['usage'], acc)
    return acc


def scan(path, tool_totals=None):
    acc = collections.Counter()
    seen, models = set(), collections.Counter()
    first = last = None
    first_user = queued = ''
    asst_texts = []                       # first three distinct assistant messages, text + tool inputs
    lane_own_texts = []
    tools_seen, tool_names = set(), {}
    tool_sessions = set()
    st = collections.Counter()
    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            ts = o.get('timestamp')
            if ts:
                first = first or ts
                last = ts
            if o.get('type') == 'queue-operation' and not queued and isinstance(o.get('content'), str):
                q = LEAD_TAGS.sub('', o['content'])
                if q.strip() and not q.lstrip().startswith('<'):
                    queued = q
            m = o.get('message')
            if not isinstance(m, dict):
                continue
            typ = o.get('type')
            content = m.get('content')
            if typ == 'user':
                t = user_text(o)
                if t:
                    st['user_prompts'] += 1
                    if not first_user:
                        first_user = t
                if len(lane_own_texts) < 400:
                    lane_own_texts.append(line[:6000])
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get('type') == 'tool_result':
                            name = tool_names.get(b.get('tool_use_id'), '?')
                            ch, im = result_len(b.get('content'))
                            st['result_chars'] += ch
                            st['result_images'] += im
                            if name == 'Read':
                                st['read_chars'] += ch
                            elif name.endswith('get_page_text'):
                                st['page_text_chars'] += ch
                            if tool_totals is not None:
                                tool_totals[name]['result_chars'] += ch
                                tool_totals[name]['result_images'] += im
                continue
            if typ != 'assistant':
                continue
            mid = m.get('id') or o.get('uuid')
            u = m.get('usage')
            if u and mid not in seen:
                seen.add(mid)
                add_usage(u, acc)
                if m.get('model') and m['model'] != '<synthetic>':
                    models[m['model']] += 1
            if isinstance(content, list):
                bits = []
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get('type') == 'text':
                        bits.append(b.get('text') or '')
                    elif b.get('type') == 'tool_use':
                        inp = b.get('input') if isinstance(b.get('input'), dict) else {}
                        bits.append(json.dumps(inp)[:2000])
                        bid = b.get('id')
                        if bid in tools_seen:
                            continue
                        tools_seen.add(bid)
                        name = b.get('name') or '?'
                        tool_names[bid] = name
                        st['tool_calls'] += 1
                        if tool_totals is not None:
                            tool_totals[name]['calls'] += 1
                            tool_sessions.add(name)
                        if name.endswith('computer'):
                            st['computer_calls'] += 1
                            if inp.get('action') == 'screenshot':
                                st['screenshots'] += 1
                        elif name == 'Read':
                            st['read_calls'] += 1
                        elif name.endswith('browser_batch'):
                            st['batch_calls'] += 1
                            for a in inp.get('actions') or []:
                                if isinstance(a, dict) and str(a.get('name', '')).endswith('computer') and \
                                        isinstance(a.get('input'), dict) and a['input'].get('action') == 'screenshot':
                                    st['batch_screenshots'] += 1
                if bits and len(asst_texts) < 3 and (not asst_texts or asst_texts[-1][0] != mid):
                    asst_texts.append((mid, ' '.join(bits)))
                elif bits and asst_texts and asst_texts[-1][0] == mid and len(asst_texts) <= 3:
                    asst_texts[-1] = (mid, asst_texts[-1][1] + ' ' + ' '.join(bits))
                if len(lane_own_texts) < 400:
                    lane_own_texts.append(' '.join(bits)[:6000])
    if tool_totals is not None:
        for n in tool_sessions:
            tool_totals[n]['sessions'] += 1
    return dict(acc=acc, st=st, models=models, first=first, last=last, first_user=first_user or queued,
                asst_texts=[t for _, t in asst_texts], lane_texts=lane_own_texts, turns=len(seen))


def parse_ts(ts):
    return datetime.datetime.fromisoformat(ts.replace('Z', '+00:00'))


def session_row(path, tool_totals=None):
    r = scan(path, tool_totals)
    if not r['first']:
        return None
    t0, t1 = parse_ts(r['first']), parse_ts(r['last'])
    fu = r['first_user']
    phase = classify(fu)
    m = RUN_RE.search(fu)
    run_id = m.group(0) if m else ''
    if not run_id:
        for t in r['asst_texts']:
            m = RUN_RE.search(t)
            if m:
                run_id = m.group(0)
                break
    orch = ''
    handoff = 1 if HANDOFF.match(' '.join(fu.lower().split())) else 0
    if phase == 'orch' or handoff:         # own orchestrator id: the most-mentioned R<startdate>-HHMM-orch
        day = t0.astimezone(common.local_tz()).strftime('%Y%m%d')
        own = re.compile(r'R' + day + r'-\d{4}-orch\b')
        ids = collections.Counter(x for t in r['lane_texts'] for x in own.findall(t))
        orch = ids.most_common(1)[0][0] if ids else ''
    if phase == 'lane':
        mo = ORCH_RE.search(fu)
        orch = mo.group(0) if mo else ''
        n = re.search(r'phase\s*3\s*lane\s*(\d)', fu.lower()).group(1)
        day = t0.astimezone(common.local_tz()).strftime('%Y%m%d')   # same date as the lane start: older lane ids get quoted too
        own = re.compile(r'R' + day + r'-\d{4}-apply' + n + r'\b')
        mm = next((own.search(t) for t in r['lane_texts'] if own.search(t)), None)
        if mm:                                     # first, not most-mentioned: a restarted lane quotes its predecessor
            run_id = mm.group(0)
    sub = collections.Counter()
    subs = glob.glob(os.path.join(path[:-6], 'subagents', '*.jsonl'))
    for sp in subs:
        sub.update(tokens_only(sp))
    acc, st = r['acc'], r['st']
    row = {
        'session_id': os.path.basename(path)[:-6],
        'project_dir': os.path.basename(os.path.dirname(path)),
        'started_at': t0.strftime('%Y-%m-%dT%H:%M:%SZ'), 'ended_at': t1.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'duration_min': round((t1 - t0).total_seconds() / 60, 1),
        'model': r['models'].most_common(1)[0][0] if r['models'] else '',
        'phase': phase, 'run_id_guess': run_id, 'turns': r['turns'],
        **{k: st[k] for k in ('tool_calls', 'computer_calls', 'screenshots', 'read_calls', 'read_chars',
                              'page_text_chars', 'batch_calls', 'user_prompts', 'batch_screenshots', 'result_chars',
                              'result_images')},
        **{k: acc[k] for k in TOKS + ['cache_write_5m', 'cache_write_1h']},
        'first_user_line': scrub(fu),
        'orch_run_id': orch, 'handoff': handoff,
        'date': t0.astimezone(common.local_tz()).strftime('%Y-%m-%d'),
        'cache_read_per_turn': round(acc['cache_read_tokens'] / r['turns']) if r['turns'] else 0,
        'subagents': len(subs),
        'subagent_input_tokens': sub['input_tokens'], 'subagent_output_tokens': sub['output_tokens'],
        'subagent_cache_creation_tokens': sub['cache_creation_tokens'],
        'subagent_cache_read_tokens': sub['cache_read_tokens'],
    }
    return row


# ---- aggregation ---------------------------------------------------------------------------------------------------
def pct(vals, q):
    if not vals:
        return 0
    s = sorted(vals)
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo))


def fresh(r):
    return int(r['input_tokens']) + int(r['output_tokens']) + int(r['cache_creation_tokens'])


def by_phase(rows):
    total_cr = sum(r['cache_read_tokens'] for r in rows) or 1
    out = []
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r['phase']].append(r)
    for ph, rs in sorted(groups.items(), key=lambda kv: -sum(r['cache_read_tokens'] for r in kv[1])):
        crs = [r['cache_read_tokens'] for r in rs]
        out.append({'phase': ph, 'sessions': len(rs), 'turns': sum(r['turns'] for r in rs),
                    'screenshots': sum(r['screenshots'] for r in rs),
                    'batch_screenshots': sum(r['batch_screenshots'] for r in rs),
                    'result_images': sum(r['result_images'] for r in rs),
                    **{k: sum(r[k] for r in rs) for k in TOKS},
                    'median_cache_read': round(statistics.median(crs)), 'p90_cache_read': pct(crs, 0.9),
                    'cache_read_share': round(sum(crs) / total_cr, 4),
                    'cache_read_per_turn': round(sum(crs) / (sum(r['turns'] for r in rs) or 1))})
    return out


def load_outcomes():
    subs = []
    for name in ('outcomes.csv', 'outcomes-jt.csv'):
        p = os.path.join(REPO, 'AppApply-Capture', name)
        if not os.path.exists(p):
            continue
        with open(p, newline='', encoding='utf-8') as fh:
            for row in csv.DictReader(fh):
                if (row.get('outcome') or '').strip() == 'submitted':
                    subs.append(row.get('run_id') or '')
    return subs


def is_p3(r):
    return r['phase'] in ('orch', 'lane', 'single', 'logins') or bool(r['handoff'] and r['orch_run_id'])


def usd(r, rates):
    if not rates:
        return ''
    ri, ro, cw5, cw1, cr = rates
    cw_other = r['cache_creation_tokens'] - r['cache_write_5m'] - r['cache_write_1h']  # untagged writes -> 5m price
    return round((r['input_tokens'] * ri + r['output_tokens'] * ro + (r['cache_write_5m'] + cw_other) * cw5 +
                  r['cache_write_1h'] * cw1 + r['cache_read_tokens'] * cr) / 1e6, 2)


def by_run(rows, rates):
    subs = load_outcomes()
    sub_by_date = collections.Counter(re.match(r'R(\d{8})', s).group(1) for s in subs if re.match(r'R\d{8}', s))
    sub_by_run = collections.Counter(subs)
    keys = ['input_tokens', 'output_tokens', 'cache_creation_tokens', 'cache_read_tokens', 'cache_write_5m',
            'cache_write_1h']

    def agg(level, group, date, rs, submitted, basis):
        d = {'level': level, 'group': group, 'date': date, 'sessions': len(rs),
             'lane_sessions': sum(r['phase'] == 'lane' for r in rs),
             'handoff_sessions': sum(r['handoff'] for r in rs), 'turns': sum(r['turns'] for r in rs),
             'screenshots': sum(r['screenshots'] for r in rs),
             'result_images': sum(r['result_images'] for r in rs),
             **{k: sum(r[k] for r in rs) for k in keys},
             'p3_fresh_tokens': sum(fresh(r) for r in rs if is_p3(r)),
             'p3_cache_read_tokens': sum(r['cache_read_tokens'] for r in rs if is_p3(r)),
             'submitted': submitted, 'submitted_basis': basis}
        f = d['input_tokens'] + d['output_tokens'] + d['cache_creation_tokens']
        d['fresh_tokens_per_submit'] = round(f / submitted) if submitted else ''
        d['cache_read_per_submit'] = round(d['cache_read_tokens'] / submitted) if submitted else ''
        d['api_equiv_usd'] = usd(d, rates)
        d['api_usd_per_submit'] = round(d['api_equiv_usd'] / submitted, 2) if rates and submitted else ''
        return d

    out = []
    days = collections.defaultdict(list)
    for r in rows:
        days[r['date']].append(r)
    for date, rs in sorted(days.items()):
        n = sub_by_date.get(date.replace('-', ''), 0)
        out.append(agg('day', date, date, rs, n, 'run_id date'))
    runs = collections.defaultdict(list)
    for r in rows:
        k = r['orch_run_id']
        if k:
            runs[k].append(r)
    orch_per_day = collections.Counter(k[1:9] for k in runs)
    for k, rs in sorted(runs.items()):
        ids = {k} | {r['run_id_guess'] for r in rs}
        n = sum(sub_by_run[i] for i in ids if i)
        basis = 'lane run ids'
        if not n and orch_per_day[k[1:9]] == 1:
            n, basis = sub_by_date.get(k[1:9], 0), 'run_id date (only orch that day)'
        date = f'{k[1:5]}-{k[5:7]}-{k[7:9]}'
        out.append(agg('orch_run', k, date, rs, n, basis))
    return out


def by_tool(tool_totals):
    return [{'tool': n, 'calls': t['calls'], 'sessions': t['sessions'], 'result_chars': t['result_chars'],
             'result_images': t['result_images']}
            for n, t in sorted(tool_totals.items(), key=lambda kv: -kv[1]['calls'])]


# ---- io ------------------------------------------------------------------------------------------------------------
def audit_run_id(today):
    return f'R{today.replace("-", "")}-audit'


def write_csv(path, rows, fields=None):
    if os.path.exists(path):
        sys.exit(f'refusing to overwrite {path} (Runs/ files are write-once)')
    fields = fields or (list(rows[0].keys()) if rows else [])
    with open(path, 'x', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    print(f'wrote {os.path.relpath(path, REPO)} ({len(rows)} rows)')


def collect(a, tool_totals=None):
    paths = sorted(glob.glob(os.path.expanduser(a.projects_glob)))
    rows = []
    for p in paths:
        row = session_row(p, tool_totals)
        if row and (not a.since or row['date'] >= a.since):
            rows.append(row)
    rows.sort(key=lambda r: r['started_at'])
    return rows, len(paths)


def fmt(n):
    n = float(n)
    for unit, d in (('B', 1e9), ('M', 1e6), ('k', 1e3)):
        if abs(n) >= d:
            return f'{n / d:.2f}{unit}'
    return f'{n:.0f}'


def spot_check(a, n):
    rows, _ = collect(a)
    by = collections.defaultdict(list)
    for r in rows:
        by[r['phase']].append(r)
    picks = []
    while len(picks) < n and any(by.values()):
        for ph in sorted(by):
            if by[ph] and len(picks) < n:
                picks.append(by[ph].pop(len(by[ph]) // 2))
    for r in picks:
        print(f'{r["started_at"][:16]}  {r["phase"]:12} {r["run_id_guess"]:22} | {r["first_user_line"]}')


# ---- portal usage feed -------------------------------------------------------------------------------------------
USAGE_FIELDS = ['run_id', 'phase', 'session', 'session_run_id', 'model', 'started_at', 'updated_at', 'input_tokens',
                'output_tokens', 'cache_creation_tokens', 'cache_read_tokens', 'jobs_attempted', 'jobs_submitted',
                'weekly_pct_start', 'weekly_pct_now', 'weekly_resets_at']
ORCH_ID = re.compile(r'R(\d{4})(\d{2})(\d{2})-\d{4}-orch')


def outcome_counts():
    """(attempted, submitted) Counters by outcome run_id over outcomes.csv + outcomes-jt.csv (distinct attempt_id)."""
    att, sub, seen = collections.Counter(), collections.Counter(), set()
    for name in ('outcomes.csv', 'outcomes-jt.csv'):
        p = os.path.join(REPO, 'AppApply-Capture', name)
        if not os.path.exists(p):
            continue
        with open(p, newline='', encoding='utf-8') as fh:
            for row in csv.DictReader(fh):
                key = (row.get('run_id') or '', row.get('attempt_id') or '')
                if key in seen or not (row.get('outcome') or '').strip():
                    continue
                seen.add(key)
                att[key[0]] += 1
                if row['outcome'].strip() == 'submitted':
                    sub[key[0]] += 1
    return att, sub


def usage_rows(rows, orch_id, weekly=None):
    att, sub = outcome_counts()
    sel = [r for r in rows if r['orch_run_id'] == orch_id and (r['phase'] in ('orch', 'lane') or r['handoff'])]
    out, orch_named = [], False
    for r in sorted(sel, key=lambda r: r['started_at']):
        hhmm = parse_ts(r['started_at']).astimezone(common.local_tz()).strftime('%H%M')
        own = r['run_id_guess'] if r['phase'] == 'lane' and re.fullmatch(r'R\d{8}-\d{4}-apply\d', r['run_id_guess']) else ''
        if r['phase'] == 'lane':
            n = own[-1] if own else (re.search(r'lane\s*(\d)', r['first_user_line'].lower()) or [None, '?'])[1]
            name = f'lane{n}-{own[10:14] if own else hhmm}'
        else:
            name = 'orch' if not orch_named else f'orch-{hhmm}'
            orch_named = True
        out.append({'run_id': orch_id, 'phase': '3', 'session': name, 'session_run_id': own, 'model': r['model'],
                    'started_at': r['started_at'], 'updated_at': r['ended_at'],
                    **{k: r[k] for k in TOKS},
                    'jobs_attempted': att[own] if own else '', 'jobs_submitted': sub[own] if own else '',
                    'weekly_pct_start': '', 'weekly_pct_now': '', 'weekly_resets_at': ''})
        if name == 'orch' and weekly:
            out[-1].update({k: v for k, v in weekly.items() if v not in (None, '')})
    out.sort(key=lambda x: (not x['session'].startswith('orch'), x['started_at']))
    return out


def write_usage(a, orch_id):
    m = ORCH_ID.fullmatch(orch_id or '')
    if not m:
        sys.exit('--write-usage needs an orchestrator run id, R<YYYYMMDD>-<HHMM>-orch')
    date = f'{m[1]}-{m[2]}-{m[3]}'
    a.since = a.since or date
    rows, _ = collect(a)
    for flag, v in (('--weekly-start', a.weekly_start), ('--weekly-now', a.weekly_now)):
        if v not in (None, '') and not re.fullmatch(r'\d{1,3}(\.\d+)?', str(v)):
            sys.exit(f'{flag} takes a percentage number, e.g. 42')
    out = usage_rows(rows, orch_id, {'weekly_pct_start': a.weekly_start, 'weekly_pct_now': a.weekly_now,
                                     'weekly_resets_at': a.weekly_resets})
    total = sum(int(r[k]) for r in out for k in TOKS)
    for r in out:
        print(f'{r["session"]:14} {r["session_run_id"]:24} {fmt(r["cache_read_tokens"]):>9} cache_read · '
              f'submitted {r["jobs_submitted"]}')
    print(f'{orch_id}: {len(out)} session(s), {fmt(total)} tokens')
    if a.dry_run:
        return 0
    if not out:
        print('no sessions found for that run; nothing written', file=sys.stderr)
        return 1
    d = os.path.join(a.out_dir or os.path.join(REPO, 'Runs', date))
    dest = os.path.join(d, f'USAGE-{orch_id}.csv')
    if os.path.exists(dest) and date != datetime.date.today().isoformat():
        sys.exit(f'refusing to rewrite {os.path.relpath(dest, REPO)}: its run day is over (Runs/ is write-once)')
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f'.USAGE-{orch_id}.tmp')
    with open(tmp, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=USAGE_FIELDS)
        w.writeheader()
        w.writerows(out)
    os.replace(tmp, dest)
    print(f'wrote {os.path.relpath(dest, REPO)}')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog='See the module docstring (head -60 tools/token_audit.py) for column rules.')
    ap.add_argument('--run-id', help='audit run id used in the file names (default: R<today>-audit)')
    ap.add_argument('--since', help='only sessions whose local start date is on/after YYYY-MM-DD')
    ap.add_argument('--projects-glob', default=DEFAULT_GLOB, help=f'transcript glob (default {DEFAULT_GLOB})')
    ap.add_argument('--rates', help='USD per million tokens: input,output,cache_write_5m,cache_write_1h,cache_read '
                                    '(take them from the claude-api skill, not memory)')
    ap.add_argument('--out-dir', help='output folder (default Runs/<today>)')
    ap.add_argument('--dry-run', action='store_true', help='scan and print the summary, write nothing')
    ap.add_argument('--write-usage', metavar='ORCH_RUN_ID', help='write Runs/<date>/USAGE-<OrchRunID>.csv for the dashboard '
                                                                  "token card (16 columns; see the docstring)")
    ap.add_argument('--weekly-start', help='--write-usage: weekly limit %% used at the run start (orch row)')
    ap.add_argument('--weekly-now', help='--write-usage: weekly limit %% used now (orch row)')
    ap.add_argument('--weekly-resets', help='--write-usage: when the weekly limit resets, ISO time (orch row)')
    ap.add_argument('--spot-check', type=int, metavar='N', help='print N sessions (spread over phases) with their '
                                                                 'scrubbed first_user_line, write nothing')
    a = ap.parse_args()
    if a.write_usage:
        sys.exit(write_usage(a, a.write_usage))
    if a.spot_check:
        spot_check(a, a.spot_check)
        return
    rates = None
    if a.rates:
        rates = [float(x) for x in a.rates.split(',')]
        if len(rates) != 5:
            sys.exit('--rates needs 5 numbers: input,output,cache_write_5m,cache_write_1h,cache_read')
    today = datetime.date.today().isoformat()
    run_id = a.run_id or audit_run_id(today)
    out_dir = a.out_dir or os.path.join(REPO, 'Runs', today)
    tool_totals = collections.defaultdict(collections.Counter)
    rows, nfiles = collect(a, tool_totals)
    phases = by_phase(rows)
    runs = by_run(rows, rates)
    tools = by_tool(tool_totals)

    tf = sum(fresh(r) for r in rows)
    tcr = sum(r['cache_read_tokens'] for r in rows)
    print(f'{nfiles} transcripts, {len(rows)} sessions, fresh {fmt(tf)}, cache_read {fmt(tcr)}, run id {run_id}')
    print(f'{"phase":12} {"sess":>5} {"turns":>7} {"shots":>6} {"fresh":>9} {"cache_read":>11} {"share":>6} '
          f'{"cr/turn":>8}')
    for p in phases:
        f = p['input_tokens'] + p['output_tokens'] + p['cache_creation_tokens']
        print(f'{p["phase"]:12} {p["sessions"]:>5} {p["turns"]:>7} {p["screenshots"]:>6} {fmt(f):>9} '
              f'{fmt(p["cache_read_tokens"]):>11} {p["cache_read_share"]:>6.1%} {fmt(p["cache_read_per_turn"]):>8}')
    if a.dry_run:
        return
    os.makedirs(out_dir, exist_ok=True)
    write_csv(os.path.join(out_dir, f'TOKEN-AUDIT-sessions-{run_id}.csv'), rows, SESSION_FIELDS)
    write_csv(os.path.join(out_dir, f'TOKEN-AUDIT-by-phase-{run_id}.csv'), phases)
    write_csv(os.path.join(out_dir, f'TOKEN-AUDIT-by-run-{run_id}.csv'), runs)
    write_csv(os.path.join(out_dir, f'TOKEN-AUDIT-by-tool-{run_id}.csv'), tools)


if __name__ == '__main__':
    main()
