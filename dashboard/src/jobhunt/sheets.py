"""Read-only Google Sheets access for the sync worker.

Credential: a dedicated read-only service account (key file mounted read-only into the sync container ONLY, at
JOBHUNT_GOOGLE_SA_FILE), scope spreadsheets.readonly. The portal never touches the ops tools' OAuth token. Viewer
access to the two sheets is granted on the Google side.
"""
from __future__ import annotations

import os
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
API = "https://sheets.googleapis.com/v4/spreadsheets"
SKIP_TABS = {"readme"}

# (logical sheet name stored in portal.sheet_rows, spreadsheet id env var, tabs to read or None = every tab
# except README). The JD Archive's data tab is read by position (first non-README tab), not by name.
SOURCES = [
    ("Queue", "JOBHUNT_QUEUE_SHEET_ID", ["Queue"]),
    ("Raw", "JOBHUNT_QUEUE_SHEET_ID", ["Raw"]),
    ("JD Archive", "JOBHUNT_JD_SHEET_ID", None),
]


def configured() -> bool:
    path = os.environ.get("JOBHUNT_GOOGLE_SA_FILE", "")
    return bool(path) and os.path.isfile(path)


_SESSION: AuthorizedSession | None = None


def _session() -> AuthorizedSession:
    """One session per process: it refreshes its own token, so run mode's 30 s Queue reads don't mint one each time."""
    global _SESSION
    if _SESSION is None:
        creds = service_account.Credentials.from_service_account_file(os.environ["JOBHUNT_GOOGLE_SA_FILE"], scopes=SCOPES)
        _SESSION = AuthorizedSession(creds)
    return _SESSION


def _get(s: AuthorizedSession, url: str) -> dict:
    r = s.get(url, timeout=30)
    if r.status_code != 200:
        # Google's error body names the problem (permission, not found); it never echoes the credential.
        raise RuntimeError(f"Sheets API {r.status_code}: {r.text[:300]}")
    return r.json()


def tab_titles(s: AuthorizedSession, sheet_id: str) -> list[str]:
    meta = _get(s, f"{API}/{sheet_id}?fields=sheets.properties(title,index)")
    props = sorted((x["properties"] for x in meta.get("sheets", [])), key=lambda p: p.get("index", 0))
    return [p["title"] for p in props]


def tab_values(s: AuthorizedSession, sheet_id: str, tab: str) -> list[list[str]]:
    rng = quote("'" + tab.replace("'", "''") + "'", safe="")
    data = _get(s, f"{API}/{sheet_id}/values/{rng}?majorDimension=ROWS&valueRenderOption=FORMATTED_VALUE")
    return data.get("values", [])


def fetch_all() -> dict[str, tuple[str, list[list[str]]]]:
    """Returns {logical name: (source label, rows)}. Raises on any API error so the caller keeps old rows."""
    s = _session()
    out: dict[str, tuple[str, list[list[str]]]] = {}
    titles_cache: dict[str, list[str]] = {}
    for name, env, tabs in SOURCES:
        sid = os.environ[env]
        if sid not in titles_cache:
            titles_cache[sid] = tab_titles(s, sid)
        titles = titles_cache[sid]
        if tabs is None:
            data_tabs = [t for t in titles if t.strip().lower() not in SKIP_TABS]
            if not data_tabs:
                raise RuntimeError(f"{name}: no data tab found (tabs: {titles})")
            tab = data_tabs[0]
        else:
            tab = tabs[0]
            if tab not in titles:
                raise RuntimeError(f"{name}: tab {tab!r} not found (tabs: {titles})")
        out[name] = (f"sheet:{name}/{tab}", tab_values(s, sid, tab))
    return out


def fetch_queue() -> dict[str, tuple[str, list[list[str]]]]:
    """Run mode's light read: the Queue tab only, one request. Same shape as fetch_all(); raises on any error."""
    return {"Queue": ("sheet:Queue/Queue", tab_values(_session(), os.environ["JOBHUNT_QUEUE_SHEET_ID"], "Queue"))}
