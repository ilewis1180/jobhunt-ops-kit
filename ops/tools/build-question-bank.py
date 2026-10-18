#!/usr/bin/env python3
"""Question bank (08 §2.4). Default: read AppApply-Capture/question-bank-observations.csv (lanes append live-form rows
to it) and rebuild AppApply-Capture/question-bank.csv from it. The observations file is never rewritten by default.
  --rebuild-observations   also re-derive rows from every PREP card and findings file under Runs/ and
                           APPEND only rows not already present (origin + file + label); nothing is dropped.
Personal values are redacted with the replacement list in the private PII pattern file (config paths.pii_patterns; 00
hard rule 8). answer_source vocabulary: standing_answers (from the private answers file) · resume · rule_playbook (an
answer rule in docs/07) · best_effort · needs_user · other.
"""
import collections
import csv
import glob
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

REPO = common.REPO
os.chdir(REPO)
REBUILD = '--rebuild-observations' in sys.argv
PII_FILE = common.pii_patterns_path()
try:
    import pii_scan
    cfg = pii_scan.pii_config()
    pat = [(re.compile(r['regex'], re.I), r['label']) for r in cfg.get('replacements', [])]
    # Fallback: every alternative of the scan regex itself, labelled by kind, so nothing the scanner would flag survives.
    KIND_LABEL = {'phone': '{answers.identity.mobile_phone}', 'zip': '{answers.address.zip}',
                  'street': '{answers.address.street}', 'email': '{answers.email}', 'name': '{answers.name}',
                  'value': '{answers.value}'}
    scan_alts = [(re.compile(alt, re.I), KIND_LABEL[pii_scan._kind(alt)], pii_scan._kind(alt))
                 for alt in pii_scan._alternatives(cfg.get('pii_regex', '')) if alt]
    scan_alts += [(re.compile(p['regex'], re.I), KIND_LABEL['value'], 'value') for p in cfg.get('patterns') or []]
    # A value the scanner would flag only after its normalisation ("(NNN) NNN-NNNN", %40 emails) gets the whole
    # phone/email/zip-shaped substring replaced, so the file ends up clean under the very scan that gates commits.
    GENERIC = {'phone': re.compile(r'\(?\d{3}\)?[\s.\-]*\d{3}[\s.\-]*\d{4}'), 'zip': re.compile(r'\b\d{5}(?:-\d{4})?\b'),
               'email': re.compile(r'[\w.+-]+(?:@|%40)[\w-]+\.[\w.-]+', re.I),
               'street': re.compile(r'\d{1,5}\s+[A-Za-z][\w. ]{2,40}')}
except Exception as e:
    sys.exit(f'ERROR: PII pattern file {PII_FILE} not loadable ({type(e).__name__}); refusing to write the question bank')


def redact(v):
    for p, s in pat:
        v = p.sub(s, v)
    for alt, label, kind in scan_alts:
        if kind in GENERIC and any(alt.search(x) for x in pii_scan._variants(v)) and not alt.search(v):
            v = GENERIC[kind].sub(label, v)
    return v


def cells(line):
    s = line.strip()
    if not s.startswith('|'):
        return None
    return [c.strip() for c in s.strip('|').split('|')]


def norm(label):
    label = re.sub(r'\*|\(required\)|\(optional\)|\(exact label\)', '', label, flags=re.I)
    label = re.sub(r'[“”"`]', '', label)
    return re.sub(r'\s+', ' ', label).strip(' :?-—').lower()


# label fragment -> answer key. The vocabulary is what traces, PAGE files and QB rows carry instead of values (08 §1).
MAP = [('email', 'identity.email'), ('phone', 'identity.mobile_phone'), ('first name', 'identity.first_name'),
       ('last name', 'identity.last_name'), ('full name', 'identity.full_name'), ('legal name', 'identity.legal_name'),
       ('preferred', 'identity.preferred_name'), ('linkedin', 'identity.linkedin_url'),
       ('street', 'address.street'), ('address', 'address.full'), ('city', 'address.city'), ('zip', 'address.zip'),
       ('postal', 'address.zip'), ('country', 'address.country'), ('state', 'address.state'), ('location', 'address.location'),
       ('sponsor', 'work_auth.sponsorship'), ('authorized', 'work_auth.authorized'), ('eligible to work', 'work_auth.authorized'),
       ('legally', 'work_auth.authorized'),
       ('gender', 'eeo.gender'), ('hispanic', 'eeo.hispanic'), ('race', 'eeo.race'), ('ethnic', 'eeo.race'),
       ('veteran', 'eeo.veteran'), ('disabilit', 'eeo.disability'),
       ('how did you hear', 'screening.how_heard'), ('salary', 'comp.expectation'), ('compensation', 'comp.expectation'),
       ('start date', 'availability.start_date'), ('available to start', 'availability.start_date'),
       ('relocat', 'screening.relocation'), ('travel', 'screening.travel'), ('background', 'screening.background_check'),
       ('felony', 'screening.felony'), ('convicted', 'screening.felony'), ('18 years', 'screening.age_18'),
       ('driver', 'screening.drivers_license'),
       ('non-compete', 'screening.noncompete'), ('previously applied', 'screening.previously_applied'),
       ('employed by', 'screening.worked_here_before'), ('relative', 'attest.relatives'),
       ('resume', 'documents.resume'), ('résumé', 'documents.resume'), ('cover letter', 'documents.cover_letter'),
       ('school', 'education.school'), ('degree', 'education.degree'), ('field of study', 'education.field'),
       ('major', 'education.field'), ('graduat', 'education.grad_year'),
       ('years', 'experience.years_q'), ('consent', 'consent.data_processing'), ('privacy', 'consent.privacy'),
       ('terms', 'consent.terms'), ('sms', 'consent.sms'), ('text message', 'consent.sms'), ('website', 'identity.website'),
       ('source', 'screening.how_heard')]


def key_from(label, src):
    s = label.lower()
    for k, v in MAP:
        if k in s:
            return v
    s2 = src.lower()
    for k, v in MAP[:30]:
        if k in s2:
            return v
    return 'freeform.' + re.sub(r'[^a-z0-9]+', '_', norm(label))[:50].strip('_')


def srctype(src, ans):
    t = (src + ' ' + ans).lower()
    s = src.strip().lower()
    if 'needs user' in t or 'needs applicant' in t:
        return 'needs_user'
    if 'best-effort' in t:
        return 'best_effort'
    if s.startswith(('07', 'rule', 'docs/07')):
        return 'rule_playbook'
    if s.startswith(('02', 'answers')):
        return 'standing_answers'
    if 'résumé' in t or 'resume:' in t:
        return 'resume'
    return 'other'


OBS = 'AppApply-Capture/question-bank-observations.csv'
F = ['question_id', 'label_normalized', 'label_verbatim', 'answer_key', 'answer_planned', 'answer_source', 'control',
     'required', 'selector', 'ats', 'company', 'job_id', 'origin', 'file']
existing = list(csv.DictReader(open(OBS, encoding='utf-8'))) if os.path.exists(OBS) else []
rows = []
CARD_JOB = re.compile(r'-(' + common.JOB_ID_RE + r')-(R\d{8}-)')
for f in (sorted(glob.glob('Runs/*/PREP-*-prep.md')) if REBUILD else []):
    m = CARD_JOB.search(f)
    if not m:
        continue
    t = open(f, encoding='utf-8').read()
    ats = (re.search(r'ATS:\s*([^·\n]+)', t) or [None, ''])[1].strip()
    comp = (re.search(r'^# PREP — (.*?) — ', t, re.M) or [None, ''])[1]
    sec = t.split('## Planned answers', 1)
    if len(sec) < 2:
        continue
    for line in sec[1].split('\n## ', 1)[0].splitlines():
        c = cells(line)
        if not c or len(c) < 4 or set(c[0]) <= set('-: ') or c[0] == '#':
            continue
        label, ans, src = c[1], c[2], c[3]
        rows.append(dict(origin='prep-card', file=os.path.basename(f), job_id=m.group(1), company=comp, ats=ats,
                         label_verbatim=label, label_normalized=norm(label), answer_key=key_from(label, src),
                         answer_planned=ans, answer_source=srctype(src, ans), control='',
                         required='yes' if '*' in label or 'required' in label.lower() else 'unknown', selector=''))
for f in (sorted(glob.glob('Runs/*/*-a1-*.md')) if REBUILD else []):
    t = open(f, encoding='utf-8').read()
    if '## Fields' not in t:
        continue
    hdr = None
    for line in t.split('## Fields', 1)[1].split('\n## ', 1)[0].splitlines():
        c = cells(line)
        if not c:
            continue
        if hdr is None:
            hdr = [h.lower() for h in c]
            continue
        if set(c[0]) <= set('-: '):
            continue
        d = dict(zip(hdr, c))
        lab = d.get('label (verbatim)') or d.get('label') or ''
        if not lab:
            continue
        b = os.path.basename(f)
        ats = re.sub(r'^(paused|skipped|submitted)-', '', b).split('-')[0]
        rows.append(dict(origin='findings', file=b, job_id='', company='', ats=ats, label_verbatim=lab,
                         label_normalized=norm(lab), answer_key=key_from(lab, d.get('source', '')),
                         answer_planned=d.get('answer used', ''), answer_source=srctype(d.get('source', ''), ''),
                         control=d.get('control', ''), required=d.get('required', ''),
                         selector=d.get('selector / name', '') or d.get('selector', '')))
n = 0
for r in rows:
    for k in ('answer_planned', 'label_verbatim', 'selector'):
        new = redact(r[k])
        n += new != r[k]
        r[k] = new
    r['question_id'] = hashlib.sha1(r['label_normalized'].encode()).hexdigest()[:10]
seen = {(r.get('origin', ''), r.get('file', ''), r.get('label_verbatim', '')) for r in existing}
new = [r for r in rows if (r['origin'], r['file'], r['label_verbatim']) not in seen]
if REBUILD and new:
    with open(OBS, 'a', newline='', encoding='utf-8') as fh:
        if os.path.exists(OBS) and os.path.getsize(OBS) and open(OBS, 'rb').read()[-1:] != b'\n':
            fh.write('\n')
        w = csv.DictWriter(fh, fieldnames=F, extrasaction='ignore')
        if not existing:
            w.writeheader()
        w.writerows(new)
rows = existing + new
for r in rows:
    if not r.get('question_id'):
        r['question_id'] = hashlib.sha1((r.get('label_normalized') or norm(r.get('label_verbatim', ''))).encode()).hexdigest()[:10]
    r.setdefault('label_normalized', norm(r.get('label_verbatim', '')))
# Redact personal values found in the EXISTING rows too, rewriting the file in place with the same rows in the same
# order: only the matched substrings change (08 §1).
n_existing = 0
for r in existing:
    for k in ('answer_planned', 'label_verbatim', 'selector'):
        v = redact(r.get(k, ''))
        n_existing += v != r.get(k, '')
        r[k] = v
if n_existing:
    with open(OBS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=F, extrasaction='ignore')
        w.writeheader()
        w.writerows(existing)
    print('redacted', n_existing, 'personal value(s) inside existing observation rows; file rewritten in place, same rows')
agg = {}
for r in rows:
    a = agg.setdefault(r['question_id'], dict(n=0, ats=set(), keys=collections.Counter(), verb=collections.Counter(),
                                              src=collections.Counter(), norm=r['label_normalized'], findings=0))
    a['n'] += 1
    a['ats'].add(r.get('ats', ''))
    a['keys'][r.get('answer_key', '')] += 1
    a['verb'][r.get('label_verbatim', '')] += 1
    a['src'][r.get('answer_source', '')] += 1
    a['findings'] += r.get('origin', '') != 'prep-card'
os.makedirs('AppApply-Capture', exist_ok=True)
with open('AppApply-Capture/question-bank.csv', 'w', newline='', encoding='utf-8') as fh:
    w = csv.writer(fh)
    w.writerow(['question_id', 'label_normalized', 'times_seen', 'seen_on_live_form', 'answer_key', 'answer_sources',
                'ats_list', 'example_labels'])
    for q, a in sorted(agg.items(), key=lambda x: -x[1]['n']):
        w.writerow([q, a['norm'], a['n'], a['findings'], a['keys'].most_common(1)[0][0],
                    '; '.join(f'{k}:{v}' for k, v in a['src'].most_common(4)), '; '.join(sorted(a['ats']))[:200],
                    ' | '.join(v for v, _ in a['verb'].most_common(3))[:300]])
print('observations', len(existing), 'appended', len(new) if REBUILD else 0, 'redactions', n, 'bank unique', len(agg),
      collections.Counter(r['origin'] for r in rows))
kc = collections.Counter((r.get('answer_key') or 'none').split('.')[0] for r in rows)
print(kc.most_common())
print('freeform unique', sum(1 for a in agg.values() if a['keys'].most_common(1)[0][0].startswith('freeform')))
