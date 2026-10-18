"""Direct-link resolver. Returns an employer/ATS URL or None ("no direct link").

Order: job_url_direct from the scrape, else follow redirects of the board URL and keep the
final URL only if it left the job boards. Outbound HTTP only, no browser, no sign-in, one
request per job with a short timeout. Never raises.
"""
from urllib.parse import urlparse

BOARD_HOSTS = ("linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com", "google.com")


def _is_board(url):
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in BOARD_HOSTS)


def resolve(job_url, job_url_direct=None, fetch=None):
    if job_url_direct and str(job_url_direct).startswith("http") and not _is_board(job_url_direct):
        return job_url_direct
    if not job_url or not str(job_url).startswith("http"):
        return None
    try:
        if fetch is None:
            from curl_cffi import requests as cr

            def fetch(u):
                return cr.get(u, impersonate="chrome", timeout=15, allow_redirects=True).url

        final = fetch(job_url)
    except Exception:
        return None
    if final and str(final).startswith("http") and not _is_board(final):
        return final
    return None
