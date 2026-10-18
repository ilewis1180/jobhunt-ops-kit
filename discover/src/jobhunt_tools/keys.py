"""Job keys: the same rule as ops/tools/common.py (and the ops repo's jobkey.py).

A job with a LinkedIn number keeps that number. Every other job gets JT-<10 hex>: the first 10 hex of SHA-1 over
normalized company|title|location, the key docs/10-discover.md and the Job Queue use. The board is stored separately.
"""
import hashlib
import re

_LINKEDIN = (
    re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(?:[^/?#\s]*?-)?(\d{6,})", re.I),
    re.compile(r"[?&](?:currentJobId|jobId)=(\d{6,})", re.I),
)


def normalize(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def linkedin_id(text):
    s = (text or "").strip()
    if re.fullmatch(r"\d{6,}", s):
        return s
    for rx in _LINKEDIN:
        m = rx.search(s)
        if m:
            return m.group(1)
    return ""


def jt_key(company, title, location):
    """JT- + first 10 hex of SHA-1(normalized company|title|location)."""
    raw = "|".join(normalize(x) for x in (company, title, location))
    return "JT-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def job_key(company, title, location, job_url=""):
    return linkedin_id(job_url) or jt_key(company, title, location)
