#!/usr/bin/env python3
"""Phase 3 preflight (runbook proposal T2 / O1): before the lanes start, the orchestrator checks every card on the
dispatch board with plain, read-only HTTP GETs, so dead postings and surprise login walls come off the board before a
lane spends a claim on them.

  python3 tools/preflight.py [--run <OrchRunID>] [--job <JobID> ...] [--no-write]

Board: the newest Runs/*/dispatch-*/board.csv, or the --run one (the same lookup as dispatch.py). Easy Apply rows (ea=1)
are skipped, and nothing is ever requested from linkedin.com or aplitrak.com (a plain page load there once recorded an
application): a card, redirect or Apply link that points there is left alone and marked skipped.

Per card (GET only, no cookies, redirects followed by hand so every hop is checked):
  Greenhouse  boards-api.greenhouse.io/v1/boards/<board>/jobs/<id>?questions=true   404 = closed; questions, JD length
  Lever       api.lever.co/v0/postings/<company>/<uuid>                            404 = closed
  Ashby       api.ashbyhq.com/posting-api/job-board/<org>                          job id (or title) on the board?
  Workday     <tenant>.wdN.myworkdayjobs.com/wday/cxs/<tenant>/<site>/job/<path>   404 = closed; live = login-wall
              (Workday is account-gated, 03/04). No job path on the card → the job page is read instead.
  anything    GET the apply URL: closed phrases, login-wall signals (final URL, sign-in form, "Create Account",
  else        SuccessFactors RMK ssoUrl, UltiPro opportunityApplyRedirectUrl → /Account/Login), and at most one hop
              to an Apply link on a known ATS host.
Status: ok · closed · login-wall · unknown (check by hand) · error · skipped.

Output (write-once; -2, -3 … when the name exists): Runs/<today>/preflight-<OrchRunID>.csv, plus a .jsonl with each
card's question list (label, required, type, options). Then a summary grouped by status, with the dispatch.py commands
the orchestrator may run. This tool never runs them, and never writes the board, the Job Queue or any sheet.
Polite: one request per second, a desktop User-Agent, a 15 s timeout, at most one retry (network error or 5xx).
"""
import argparse, csv, datetime, html, http.client, json, os, re, socket, ssl, sys, time, zlib
import urllib.error, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common, dispatch  # noqa: E402  (run_dir, State, RUNS, CT: the same board lookup as the orchestrator)

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/140.0.0.0 Safari/537.36')
HTML_ACCEPT = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
JSON_ACCEPT = 'application/json'
TIMEOUT, GAP, MAX_HOPS, MAX_BODY = 15, 1.0, 8, 4_000_000
BLOCKED = ('linkedin.com', 'aplitrak.com')          # never requested, not even through a redirect
OUT_COLS = ['job_id', 'company', 'ats', 'status', 'final_host', 'http_status', 'questions_count', 'required_count', 'note']
STATUSES = ['ok', 'closed', 'login-wall', 'unknown', 'error', 'skipped']

# Closed only on specific phrases. Never a bare "not accepting": one employer's page says "not accepting
# applications submitted through recruiting agencies".
CLOSED_PHRASES = ('no longer accepting applications', 'this job is no longer available', 'job is no longer available',
                  'position is no longer available', 'posting is no longer available',
                  'opportunity is no longer available', 'position has been filled', 'job not found',
                  'this job has expired', 'job posting has expired')
ATS_HOST = re.compile(r'(?:^|\.)(?:myworkdayjobs\.com|myworkday\.com|icims\.com|successfactors\.(?:com|eu)|taleo\.net|'
                      r'ultipro\.com|ukg\.net|adp\.com|oraclecloud\.com|greenhouse\.io|lever\.co|ashbyhq\.com|'
                      r'smartrecruiters\.com|workable\.com|jobvite\.com|paylocity\.com|paycomonline\.net|'
                      r'recruitingbypaycor\.com|hireology\.com|avature\.net|eightfold\.ai|talemetry\.com|'
                      r'zohorecruit\.com|bamboohr\.com|teamtailor\.com|umantis\.com|dayforcehcm\.com|'
                      r'applytojob\.com|breezy\.hr|brassring\.com)$', re.I)
LOGIN_PATH = re.compile(r'/account/login|/login\b|/signin\b|/sign-in\b|/logon\b|/register\b|createaccount', re.I)
URL_RE = re.compile(r'https?://[^\s<>"\'`]+', re.I)
UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
GH_PATH = re.compile(r'(?:job-boards|boards)\.greenhouse\.io/(?!embed/)([A-Za-z0-9_-]+)/jobs/(\d+)', re.I)
GH_EMBED = re.compile(r'greenhouse\.io/embed/job_app\?([^\s)]+)', re.I)
GH_BOARD = re.compile(r'(?:job-boards|boards)\.greenhouse\.io/(?!embed\b)([A-Za-z0-9_-]+)', re.I)
GH_JID = re.compile(r'gh_jid=(\d+)', re.I)
LEVER = re.compile(r'jobs\.(eu\.)?lever\.co/([^/\s?#]+)/(' + UUID + ')', re.I)
ASHBY = re.compile(r'jobs\.ashbyhq\.com/([^/\s?#)]+)(?:/(' + UUID + '))?', re.I)
ASHBY_JID = re.compile(r'ashby_jid=(' + UUID + ')', re.I)
WORKDAY = re.compile(r'https?://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/\s?#]+)/job/([^\s?#]+)',
                     re.I)


# ---------- HTTP ----------

def ascii_url(url):
    """Percent-encode non-ASCII characters and spaces (one apply link carried a Unicode ellipsis and the GET died with
    UnicodeEncodeError). Characters that are already URL syntax or %-escapes are left alone."""
    return urllib.parse.quote(url, safe="%:/?#[]@!$&'()*+,;=-._~")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None          # surface every 3xx, so each hop is checked against BLOCKED before it is requested


class Resp:
    def __init__(self, url, hops, status=None, body='', error=None, blocked=None):
        self.url, self.hops, self.status, self.body, self.error, self.blocked = url, hops, status, body, error, blocked

    @property
    def host(self):
        return host_of(self.url)


def host_of(url):
    return (urllib.parse.urlsplit(url).hostname or '').lower()


def blocked_host(url):
    h = host_of(url)
    return next((b for b in BLOCKED if h == b or h.endswith('.' + b)), None)


class Http:
    def __init__(self):
        self.opener = urllib.request.build_opener(NoRedirect)   # no HTTPCookieProcessor: no cookies kept or sent
        self.last, self.count = 0.0, 0

    def _once(self, url, accept):
        wait = self.last + GAP - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        self.count += 1
        req = urllib.request.Request(ascii_url(url), headers={'User-Agent': UA, 'Accept': accept, 'Accept-Encoding': 'gzip',
                                                   'Accept-Language': 'en-US,en;q=0.9'})
        try:
            with self.opener.open(req, timeout=TIMEOUT) as f:
                return f.status, f.headers, f.read(MAX_BODY)
        except urllib.error.HTTPError as e:
            try:
                body = e.read(MAX_BODY)
            except Exception:
                body = b''
            return e.code, e.headers, body
        finally:
            self.last = time.monotonic()

    def _fetch(self, url, accept):
        """One request, plus at most one retry on a network error or a 5xx."""
        for attempt in (0, 1):
            try:
                st, h, b = self._once(url, accept)
            except (urllib.error.URLError, socket.timeout, ConnectionError, ssl.SSLError,
                    http.client.HTTPException, OSError):
                if attempt:
                    raise
                continue
            if st >= 500 and not attempt:
                continue
            return st, h, b

    def get(self, url, accept=HTML_ACCEPT):
        hops = [url]
        for _ in range(MAX_HOPS):
            b = blocked_host(url)
            if b:
                return Resp(url, hops, blocked=b)
            try:
                st, h, raw = self._fetch(url, accept)
            except Exception as e:
                return Resp(url, hops, error=f'{type(e).__name__}: {str(e)[:80]}')
            loc = h.get('Location') if h else None
            if st in (301, 302, 303, 307, 308) and loc:
                nxt = urllib.parse.urljoin(url, loc.strip())
                if urllib.parse.urlsplit(nxt).scheme not in ('http', 'https'):
                    return Resp(url, hops, status=st, error='redirect to a non-http URL')
                url = nxt
                hops.append(url)
                continue
            return Resp(url, hops, status=st, body=decode(h, raw))
        return Resp(url, hops, error='too many redirects')


def decode(h, raw):
    if h is not None and 'gzip' in (h.get('Content-Encoding') or '').lower():
        try:
            raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw)
        except zlib.error:
            pass
    charset = 'utf-8'
    m = re.search(r'charset=([\w-]+)', (h.get('Content-Type') if h is not None else '') or '')
    if m:
        charset = m.group(1)
    try:
        return raw.decode(charset, 'replace')
    except LookupError:
        return raw.decode('utf-8', 'replace')


def get_json(http, url):
    r = http.get(url, JSON_ACCEPT)
    data = None
    if r.status == 200 and r.body:
        try:
            data = json.loads(r.body)
        except ValueError:
            pass
    return r, data


# ---------- Text helpers ----------

def visible_text(page):
    t = re.sub(r'(?is)<(script|style|noscript|template)\b.*?</\1>', ' ', page)
    t = re.sub(r'(?s)<!--.*?-->', ' ', t)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t))).strip().lower()


def jd_chars(fragment):
    return len(re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', html.unescape(fragment or '')))).strip())


def urls_in(text):
    out = []
    for m in URL_RE.finditer(text or ''):
        u = m.group(0).rstrip('.,;:')
        while u.endswith(')') and u.count(')') > u.count('('):
            u = u[:-1].rstrip('.,;:')
        out.append(u)
    return out


def norm_title(s):
    return re.sub(r'[^a-z0-9]+', ' ', re.sub(r'\(.*?\)', ' ', s.lower())).strip()


def result(status, resp=None, note='', **kw):
    r = {'status': status, 'final_host': resp.host if resp else '', 'http_status': (resp.status or '') if resp else '',
         'questions_count': '', 'required_count': '', 'note': note, 'questions': None}
    r.update(kw)
    return r


def fail(resp, what):
    """The verdict when a request did not come back with a usable answer."""
    if resp.blocked:
        return result('skipped', resp, f'skipped:{resp.blocked.split(".")[0]} (a hop pointed at {resp.blocked}; '
                                       f'not requested)')
    if resp.error:
        return result('error', resp, f'{what}: {resp.error}')
    return None


# ---------- ATS checks ----------

def find_greenhouse(text):
    m = GH_PATH.search(text)
    if m:
        return m.group(1), m.group(2), False
    m = GH_EMBED.search(text)
    if m:
        q = urllib.parse.parse_qs(html.unescape(m.group(1)))
        if q.get('for') and q.get('token'):
            return q['for'][0], q['token'][0], False
    m = GH_JID.search(text)
    if m:
        b = GH_BOARD.search(text)
        return (b.group(1) if b else None), m.group(1), not b
    return None


def gh_questions(data):
    qs = []
    for q in (data.get('questions') or []) + (data.get('location_questions') or []):
        fields = q.get('fields') or []
        types = [f.get('type', '') for f in fields]
        if types and all(t == 'input_hidden' for t in types):
            continue
        opts = [v.get('label', '') for f in fields for v in (f.get('values') or [])]
        qs.append({'label': re.sub(r'\s+', ' ', q.get('label') or '').strip(), 'required': bool(q.get('required')),
                   'type': '|'.join(t for t in types if t != 'input_hidden'), 'options': opts})
    return qs


def check_greenhouse(http, card, board, job, guessed):
    boards = [board] if board else []
    if guessed:
        ck = dispatch.company_key(card['company'])
        boards = list(dict.fromkeys([ck.replace('-', ''), ck]))
    for b in boards:
        api = f'https://boards-api.greenhouse.io/v1/boards/{urllib.parse.quote(b)}/jobs/{job}?questions=true'
        r, data = get_json(http, api)
        bad = fail(r, 'greenhouse api')
        if bad:
            return bad
        if r.status == 200 and data:
            qs = gh_questions(data)
            return result('ok', r, f'greenhouse api: live ({b}/{job}) · JD {jd_chars(data.get("content")):,} chars'
                          + (' · board guessed from company' if guessed else ''),
                          questions_count=len(qs), required_count=sum(q['required'] for q in qs), questions=qs,
                          source='greenhouse-api')
        if r.status == 404 and not guessed:
            return result('closed', r, f'greenhouse api 404: job {job} not on board "{b}"')
        if r.status == 404 and guessed:
            rb, _ = get_json(http, f'https://boards-api.greenhouse.io/v1/boards/{urllib.parse.quote(b)}')
            if rb.status == 200:
                return result('closed', r, f'greenhouse api 404: job {job} not on board "{b}" (board guessed from '
                                           f'company; it exists)')
            continue
        return result('unknown', r, f'greenhouse api HTTP {r.status}')
    return None       # board could not be found: fall back to the page


def check_lever(http, eu, company, uuid):
    api = f'https://api.{"eu." if eu else ""}lever.co/v0/postings/{company}/{uuid}'
    r, data = get_json(http, api)
    bad = fail(r, 'lever api')
    if bad:
        return bad
    if r.status == 200 and data:
        return result('ok', r, f'lever api: live · JD {len(data.get("descriptionPlain") or ""):,} chars '
                               f'(questions not in the public API)')
    if r.status == 404:
        return result('closed', r, 'lever api 404: posting not found')
    return result('unknown', r, f'lever api HTTP {r.status}')


def check_ashby(http, card, org, uuid):
    r, data = get_json(http, f'https://api.ashbyhq.com/posting-api/job-board/{org}')
    bad = fail(r, 'ashby api')
    if bad:
        return bad
    if r.status != 200 or data is None:
        return result('unknown', r, f'ashby api HTTP {r.status}: board "{org}" not found (renamed?)')
    jobs = data.get('jobs') or []
    if uuid:
        hit = next((j for j in jobs if (j.get('id') or '').lower() == uuid.lower()
                    or uuid.lower() in (j.get('jobUrl') or '').lower()), None)
        if hit:
            return result('ok', r, f'ashby api: live on "{org}" · JD {len(hit.get("descriptionPlain") or ""):,} chars '
                                   f'(questions not in the public API)')
    want = norm_title(card['role'])
    same = [j for j in jobs if norm_title(j.get('title') or '') == want]
    if same and uuid:
        return result('unknown', r, f'ashby: job id not on "{org}", but "{same[0].get("title")}" is live under '
                                    f'another id — update the apply URL')
    if same:
        return result('ok', r, f'ashby api: title live on "{org}" (no job id on the card)')
    if uuid:
        return result('closed', r, f'ashby api: job id not on board "{org}" ({len(jobs)} live jobs)')
    return result('unknown', r, f'ashby api: no job id on the card and no title match on "{org}"')


def workday_parts(url):
    m = WORKDAY.search(url)
    if not m:
        return None
    tenant, wd, site, path = m.groups()
    path = re.sub(r'/apply(?:/.*)?$', '', path.rstrip('/'))
    segs = ['x' if s in ('...', '…', '') else s for s in path.split('/')]
    if len(segs) == 1:
        segs = ['x'] + segs
    return tenant.lower(), wd, site, '/'.join(segs)


def check_workday(http, url):
    tenant, wd, site, path = workday_parts(url)
    api = f'https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/job/{path}'
    r, data = get_json(http, api)
    bad = fail(r, 'workday cxs')
    if bad:
        return bad
    if r.status == 200 and data and data.get('jobPostingInfo'):
        info = data['jobPostingInfo']
        if info.get('canApply') is False:
            return result('unknown', r, f'workday cxs: posting found but canApply=false ({tenant}/{site})')
        return result('login-wall', r, f'workday: live ({tenant}/{site}) · account-gated (03/04) · '
                                       f'JD {jd_chars(info.get("jobDescription")):,} chars')
    if r.status == 404:
        return result('closed', r, f'workday cxs 404: posting not found ({tenant}/{site})')
    return result('unknown', r, f'workday cxs HTTP {r.status} ({tenant}/{site})')


def api_route(http, card, url_or_text, text_for_board=''):
    """Greenhouse / Lever / Ashby / Workday check when the text names one of them; None otherwise."""
    gh = find_greenhouse(url_or_text + ' ' + text_for_board)
    if gh:
        res = check_greenhouse(http, card, *gh)
        if res:
            return res
    m = LEVER.search(url_or_text)
    if m:
        return check_lever(http, bool(m.group(1)), m.group(2), m.group(3))
    m = ASHBY.search(url_or_text)
    if m:
        uuid = m.group(2) or (ASHBY_JID.search(url_or_text).group(1) if ASHBY_JID.search(url_or_text) else None)
        return check_ashby(http, card, m.group(1), uuid)
    for u in urls_in(url_or_text):
        if workday_parts(u):
            return check_workday(http, u)
    return None


# ---------- Generic page ----------

def apply_links(page, base):
    """Apply-like anchors: (href, anchor text, is_apply_text)."""
    out = []
    for m in re.finditer(r'(?is)<a\b([^>]*)>(.*?)</a>', page):
        hm = re.search(r'''href\s*=\s*["']([^"']+)["']''', m.group(1))
        if not hm:
            continue
        href = html.unescape(hm.group(1)).strip()
        if href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            continue
        href = urllib.parse.urljoin(base, href)
        text = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', m.group(2)))).strip()
        is_apply = bool(re.search(r'\bapply\b', text, re.I)) or bool(re.search(r'/apply\b|mode=apply', href, re.I))
        if is_apply or ATS_HOST.search(host_of(href)):
            out.append((href, text, is_apply))
    out.sort(key=lambda x: not x[2])
    return out


def login_signals(resp):
    page, url = resp.body, resp.url
    path = urllib.parse.urlsplit(url).path + '?' + urllib.parse.urlsplit(url).query
    if re.search(r'^career\d*\.successfactors\.(com|eu)$', resp.host):
        return f'SuccessFactors career site ({resp.host}) sign-in'
    if LOGIN_PATH.search(path) and resp.host != '':
        return f'final URL is a sign-in page ({resp.host}{urllib.parse.urlsplit(url).path[:60]})'
    m = re.search(r'''opportunityApplyRedirectUrl\s*[:=]\s*["']([^"']*)''', page)
    if m and '/account/login' in m.group(1).lower():
        return 'UltiPro: Apply → /Account/Login (opportunityApplyRedirectUrl)'
    if re.search(r'''["']?ssoUrl["']?\s*:\s*['"]https://career\d*\.successfactors\.(?:com|eu)''', page) \
            and re.search(r'/talentcommunity/apply/', page):
        sso = re.search(r'https://(career\d*\.successfactors\.(?:com|eu))', page).group(1)
        return f'SuccessFactors RMK: Apply → {sso} sign-in (ssoUrl)'
    stripped = re.sub(r'(?is)<(script|style|noscript|template)\b.*?</\1>', ' ', page)
    if re.search(r'''<input\b[^>]*type\s*=\s*["']?password''', stripped, re.I):
        return 'sign-in form (password field) on the page'
    vis = visible_text(page)
    if re.search(r'\bcreate (?:an )?account\b', vis):
        return '"Create Account" on the page'
    if 'icims.com' in resp.host and re.search(r'\bsign in\b|\blog in\b', vis) and '/login' in url.lower():
        return 'iCIMS sign-in'
    return None


def closed_signals(resp):
    if re.search(r'"OpportunityIsClosed"\s*:\s*true', resp.body):
        return 'UltiPro: OpportunityIsClosed=true'
    vis = visible_text(resp.body)
    hit = next((p for p in CLOSED_PHRASES if p in vis), None)
    return f'page says "{hit}"' if hit else None


def check_page(http, card, url, hop_left=1):
    r = http.get(url)
    bad = fail(r, 'GET')
    if bad:
        return bad
    via = f' (redirected from {host_of(url)})' if host_of(url) != r.host else ''
    login_hop = next((h for h in r.hops if LOGIN_PATH.search(urllib.parse.urlsplit(h).path)
                      or re.match(r'(?:signin|login|auth|sso)[.-]', host_of(h))), None)
    if login_hop:
        return result('login-wall', r, f'redirects to sign-in ({host_of(login_hop)}'
                                       f'{urllib.parse.urlsplit(login_hop).path[:50]}){via}')
    if r.status == 410:
        return result('closed', r, f'HTTP 410 Gone{via}')
    if r.status == 404:
        return result('unknown', r, f'HTTP 404{via}: posting likely gone; confirm by hand')
    if r.status >= 400:
        sig = login_signals(r) if r.status in (401, 403) else None
        if sig:
            return result('login-wall', r, sig + via)
        return result('unknown', r, f'HTTP {r.status}{via}: blocked or bot wall; check by hand')
    if r.status != 200:
        return result('unknown', r, f'HTTP {r.status}{via}')
    sig = closed_signals(r)
    if sig:
        return result('closed', r, sig + via)
    sig = login_signals(r)
    if sig:
        return result('login-wall', r, sig + via)
    # one hop: the Apply link, when it leads to a known ATS host
    links = apply_links(r.body, r.url)
    for href, text, is_apply in links:
        if not is_apply:
            continue
        hpath = urllib.parse.urlsplit(href).path + '?' + urllib.parse.urlsplit(href).query
        if LOGIN_PATH.search(hpath):
            return result('login-wall', r, f'Apply link → sign-in ({host_of(href)}{urllib.parse.urlsplit(href).path[:60]})')
    for href, text, is_apply in links:
        b = blocked_host(href)
        if b and is_apply:
            return result('skipped', r, f'skipped:{b.split(".")[0]} (Apply link points at {b}; not requested)')
        if b:
            continue
        hh = host_of(href)
        if not hop_left or hh == r.host or not ATS_HOST.search(hh):
            continue
        if not (is_apply or '/job' in href.lower()):
            continue
        sub = api_route(http, card, href)
        if sub is None:
            sub = check_page(http, card, href, hop_left=0)
        sub['note'] = f'Apply → {hh}: ' + sub['note']
        return sub
    moved = urllib.parse.urlsplit(r.url).path.rstrip('/') in ('', '/search', '/jobs', '/careers') \
        and urllib.parse.urlsplit(url).path.rstrip('/') not in ('', '/search', '/jobs', '/careers')
    if moved:
        return result('unknown', r, f'redirected to {r.host}{urllib.parse.urlsplit(r.url).path or "/"}: posting may be '
                                    f'gone; check by hand')
    other = next((host_of(h) for h, t, a in links if a and host_of(h) != r.host), None)
    return result('ok', r, 'page live, no closed or login signal' + via + (f' · Apply → {other}' if other else ''))


# ---------- Per card ----------

def check_card(http, card):
    text = card['apply_url'] or ''
    full = text + ' ' + (card.get('tenant') or '')
    if 'aplitrak.com' in full.lower():
        return result('skipped', note='skipped:aplitrak (never requested)')
    res = api_route(http, card, text, card.get('tenant') or '')
    if res:
        return res
    urls = urls_in(text)
    usable = [u for u in urls if not blocked_host(u)]
    if not usable:
        if urls:
            return result('skipped', note=f'skipped:{blocked_host(urls[0]).split(".")[0]} (only URL is on '
                                          f'{blocked_host(urls[0])}; not requested)')
        return result('unknown', note='no apply URL on the card')
    res = check_page(http, card, usable[0])
    wd_tenant = card['ats'] == 'workday' or 'myworkday' in full.lower()
    if wd_tenant and res['status'] == 'ok':
        res['status'] = 'login-wall'
        res['note'] = 'Workday tenant (account-gated per 03/04); ' + res['note']
    return res


# ---------- Output ----------

def out_paths(run):
    day = datetime.datetime.now(dispatch.CT).strftime('%Y-%m-%d')
    d = os.path.join(dispatch.RUNS, day)
    os.makedirs(d, exist_ok=True)
    n = 1
    while True:
        base = os.path.join(d, f'preflight-{run}' + (f'-{n}' if n > 1 else ''))
        if not os.path.exists(base + '.csv') and not os.path.exists(base + '.jsonl'):
            return base + '.csv', base + '.jsonl'
        n += 1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--run', help='orchestrator Run ID (default: newest dispatch folder)')
    p.add_argument('--job', action='append', help='check only this Job ID (repeatable)')
    p.add_argument('--no-write', action='store_true', help='print only; write no files')
    a = p.parse_args()

    d = dispatch.run_dir(a.run)
    board = os.path.join(d, 'board.csv')
    if not os.path.exists(board):
        dispatch.die(f'{board} not found')
    rows = list(csv.DictReader(open(board, encoding='utf-8')))
    run = os.path.basename(d)[len('dispatch-'):]
    try:
        st = dispatch.State(d)
        state = {r['job_id']: st.status(r['job_id']) for r in rows}
    except Exception:
        state = {r['job_id']: r['state'] for r in rows}
    if a.job:
        missing = set(a.job) - {r['job_id'] for r in rows}
        if missing:
            dispatch.die(f'not on the board: {" ".join(sorted(missing))}')
        rows = [r for r in rows if r['job_id'] in a.job]
    ea = [r for r in rows if r['ea'] == '1']
    todo = [r for r in rows if r['ea'] != '1']

    http = Http()
    t0 = time.monotonic()
    print(f'PREFLIGHT {run} · {len(todo)} cards to check ({len(ea)} Easy Apply skipped, no LinkedIn requests)',
          file=sys.stderr)
    results = []
    for i, card in enumerate(todo, 1):
        try:
            res = check_card(http, card)
        except Exception as e:           # one bad card never stops the sweep
            res = result('error', note=f'{type(e).__name__}: {str(e)[:100]}')
        res['card'] = card
        results.append(res)
        print(f'  [{i}/{len(todo)}] {card["job_id"]} {card["company"][:28]} · {res["status"]} · {res["note"][:110]}',
              file=sys.stderr)

    if not a.no_write:
        csv_path, jsonl_path = out_paths(run)
        with open(csv_path, 'x', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(OUT_COLS)
            for res in results:
                c = res['card']
                w.writerow([c['job_id'], c['company'], c['ats'], res['status'], res['final_host'], res['http_status'],
                            res['questions_count'], res['required_count'], res['note']])
        nq = 0
        with open(jsonl_path, 'x', encoding='utf-8') as fh:
            for res in results:
                if res['questions'] is not None:
                    c = res['card']
                    fh.write(json.dumps({'job_id': c['job_id'], 'company': c['company'], 'ats': c['ats'],
                                         'source': res.get('source', ''), 'questions': res['questions']},
                                        ensure_ascii=False) + '\n')
                    nq += 1

    by = {s: [r for r in results if r['status'] == s] for s in STATUSES}
    ct = common.local_stamp()
    print(f'\nPREFLIGHT {run} · {ct} · {len(results)} cards · {http.count} requests in '
          f'{int(time.monotonic() - t0)} s · Easy Apply skipped {len(ea)}')
    print(' · '.join(f'{s} {len(by[s])}' for s in STATUSES))
    if not a.no_write:
        print(f'wrote {os.path.relpath(csv_path, dispatch.REPO)} and .jsonl ({nq} question lists)')

    def line(res, extra=''):
        c = res['card']
        return f'  {c["job_id"]} {c["company"][:30]} · {c["ats"]} · {res["note"][:120]}{extra}'

    rid = f'--run {run} '
    if by['closed']:
        print(f'\nCLOSED ({len(by["closed"])})')
        live = []
        for res in by['closed']:
            s = state.get(res['card']['job_id'], '')
            open_now = s == 'ready' or s.startswith('hold')
            if open_now:
                live.append(res['card']['job_id'])
            print(line(res, '' if open_now else f' · board: {s[:40]}'))
        if live:
            print(f'  → python3 tools/dispatch.py {rid}drop {" ".join(live)} --note "preflight: closed"')
        else:
            print('  → nothing to drop: every closed card is already finished or claimed')
    if by['login-wall']:
        new = [r for r in by['login-wall'] if r['card']['login'] != 'yes']
        known = [r for r in by['login-wall'] if r['card']['login'] == 'yes']
        print(f'\nLOGIN WALLS ({len(by["login-wall"])}; {len(new)} new = board login is not "yes")')
        for res in new:
            s = state.get(res['card']['job_id'], '')
            print(line(res, f' · board login {res["card"]["login"]}' + ('' if s == 'ready' else f' · board: {s[:40]}')))
        if known:
            print(f'  already login=yes: {" ".join(r["card"]["job_id"] for r in known)}')
        if new:
            print('  → sign in before the lanes start (04 ledger), or `hold` these until the operator is at the keyboard')
    for s, title in (('unknown', 'UNKNOWN (check by hand)'), ('error', 'ERROR'), ('skipped', 'SKIPPED')):
        if by[s]:
            print(f'\n{title} ({len(by[s])})')
            for res in by[s]:
                print(line(res))
    if by['ok']:
        gh = [r for r in by['ok'] if r['questions'] is not None]
        print(f'\nOK ({len(by["ok"])}): {" ".join(r["card"]["job_id"] for r in by["ok"])}')
        if gh:
            print('  Greenhouse question lists: ' + ' · '.join(
                f'{r["card"]["company"][:18]} {r["questions_count"]}q/{r["required_count"]} req' for r in gh))


if __name__ == '__main__':
    main()
