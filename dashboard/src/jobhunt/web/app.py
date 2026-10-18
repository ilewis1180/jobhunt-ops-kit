"""The read-only job-hunt dashboard (FastAPI + Jinja + HTMX).

Read-only three ways: the mirrored folders are receive-only, the mounts are :ro, and the database role can only
SELECT. There is no POST route. Bind it to a private address (compose: JOBHUNT_BIND); it has no login.
"""
from __future__ import annotations

import csv
import io
import mimetypes
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt

from . import data as D
from . import outcomes as O
from ..parsers import is_private, run_state

HERE = Path(__file__).parent
ROOTS = {
    "ops": Path(os.environ.get("JOBHUNT_OPS_DIR", "/data/ops")),
    "content": Path(os.environ.get("JOBHUNT_CONTENT_DIR", "/data/content")),
}
IMAGES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
VIEWABLE = {".md", ".csv", ".jsonl", ".txt", ".pdf", *IMAGES}
# 08-CAPTURE-SPEC §1.1: AppApply-Capture/proof/<RunID>/<JobID>-a<N>-{review|text<K>|confirm}.png
PROOF_KIND = re.compile(r"-(review|confirm|text(\d+))\.(png|jpe?g|webp)$", re.IGNORECASE)
ATS_SCANNER_URL = os.environ.get("JOBHUNT_ATS_SCANNER_URL", "")  # your self-hosted ATS screener, if any

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
# URLs come from scraped CSVs; only ever link out to http(s).
templates.env.filters["http_only"] = lambda u: u if isinstance(u, str) and u.lower().startswith(("http://", "https://")) else ""
md =MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; frame-src 'self'; object-src 'self'; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'self'")


@app.middleware("http")
async def headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def live_run() -> dict | None:
    """Run mode (parsers.run_state): while the Mac is applying, Today and Applications refresh every 30 s."""
    try:
        return run_state(ROOTS["ops"])
    except OSError:
        return None


def page(request: Request, template: str, nav: str, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, template, {"nav": nav, "live": live_run(), **ctx})


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


@app.get("/healthz")
def healthz():
    try:
        s = D.last_sync()
    except Exception as e:  # database down
        return JSONResponse({"ok": False, "db": f"{type(e).__name__}"}, status_code=503)
    return {"ok": True, "db": "ok", "last_sync_min_ago": s["age_min"] if s else None,
            "last_sync_ok": s["last"]["ok"] if s else None}


@app.get("/", response_class=HTMLResponse)
def today(request: Request):
    return page(request, "today.html", "today", t=D.today())


@app.get("/applications", response_class=HTMLResponse)
def applications(request: Request, status: str = "", ats: str = "", q: str = ""):
    rows = D.filter_apps(D.applications(), status, ats, q)
    ctx = {"rows": rows, "status": status, "ats": ats, "q": q, "statuses": D.STATUS_FILTERS,
           "ats_filters": ["Workday", "LinkedIn Easy Apply", "Greenhouse", "Ashby", "Other"]}
    if is_htmx(request):
        return templates.TemplateResponse(request, "_app_rows.html", ctx)
    return page(request, "applications.html", "applications", usage=D.token_usage(), **ctx)


@app.get("/applications/usage", response_class=HTMLResponse)
def applications_usage(request: Request):
    """The token-use panel alone, for its 30 s refresh in run mode."""
    return templates.TemplateResponse(request, "_usage.html", {"usage": D.token_usage(), "live": live_run()})


@app.get("/applications.csv")
def applications_csv(status: str = "", ats: str = "", q: str = ""):
    rows = D.filter_apps(D.applications(), status, ats, q)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["job_id", "applied", "company", "role", "ats", "status", "reason", "resume", "answers"])
    for r in rows:
        w.writerow([r["job_id"], r["when"], r["company"], r["role"], r["ats"]["label"], r["status"],
                    r["reason"], r["resume"], r["answers"]])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="applications.csv"'})


@app.get("/applications/{job_id}", response_class=HTMLResponse)
def application(request: Request, job_id: str):
    a = D.application(job_id)
    if not a:
        raise HTTPException(404, "No such job in the read model")
    jd_html = md.render(a["jd"]["full_text"]) if a["jd"] else None
    return page(request, "detail.html", "applications", a=a, jd_html=jd_html, proof=proof_images(a["attempt"]))


def proof_images(attempt: dict | None) -> list[dict]:
    """Proof screenshots for one attempt, ordered review, text1..N, confirm. Empty is normal."""
    if not attempt or not attempt.get("run_id") or not attempt.get("attempt_id"):
        return []
    base = (ROOTS["ops"] / "AppApply-Capture" / "proof").resolve()
    run_dir = (base / attempt["run_id"]).resolve()
    if not run_dir.is_relative_to(base) or not run_dir.is_dir():
        return []
    prefix = f"{attempt['attempt_id']}-"
    shots = []
    for f in run_dir.iterdir():
        m = PROOF_KIND.search(f.name)
        if not (f.is_file() and f.name.startswith(prefix) and m and f.name[len(prefix):m.start()] == ""):
            continue
        kind = m.group(1).lower()
        if kind == "review":
            order, label = (0, 0), "Review page (before Submit)"
        elif kind == "confirm":
            order, label = (2, 0), "Confirmation (after Submit)"
        else:
            order, label = (1, int(m.group(2))), f"Text field {int(m.group(2))}"
        shots.append({"order": order, "label": label,
                      "rel": f.relative_to(ROOTS["ops"].resolve()).as_posix()})
    return sorted(shots, key=lambda s: s["order"])


@app.get("/questions", response_class=HTMLResponse)
def questions(request: Request, q: str = ""):
    t = f"%{q.strip()}%"  # an empty search matches everything
    rows = D.q("SELECT * FROM portal.questions WHERE concat_ws(' ', label_normalized, answer_key, example_labels) "
               "ILIKE %s ORDER BY times_seen DESC NULLS LAST, label_normalized LIMIT 300", (t,))
    total = D.q("SELECT count(*) AS n FROM portal.questions")[0]["n"]
    ctx = {"rows": rows, "q": q, "total": total}
    if is_htmx(request):
        return templates.TemplateResponse(request, "_question_rows.html", ctx)
    return page(request, "questions.html", "questions", **ctx)


@app.get("/outcomes", response_class=HTMLResponse)
def outcomes_page(request: Request, state: str = Query("", pattern="^(|applied|confirmed|rejected)$")):
    return page(request, "outcomes.html", "outcomes", o=O.outcomes(ROOTS["ops"], state))


@app.get("/stats", response_class=HTMLResponse)
def stats(request: Request, window: str = Query("all", pattern="^(all|week|today)$")):
    return page(request, "stats.html", "stats", s=D.stats(window))


@app.get("/library", response_class=HTMLResponse)
def library(request: Request, doc: str = ""):
    docs = D.q("SELECT * FROM portal.docs ORDER BY name")
    current = next((d for d in docs if d["name"] == doc), None) or next(
        (d for d in docs if d["name"].startswith("09")), docs[0] if docs else None)
    doc_html = None
    if current:
        p = safe_path("ops", current["rel_path"])
        doc_html = md.render(p.read_text(encoding="utf-8", errors="replace"))
    ctx = {"resumes": D.q("SELECT * FROM portal.resumes ORDER BY file"),
           "bullets": D.q("SELECT * FROM portal.bullets ORDER BY ordinal"),
           "docs": docs, "current": current, "doc_html": doc_html, "ats_url": ATS_SCANNER_URL,
           "tenant_states": D.q("SELECT state, count(*) AS n FROM portal.tenants GROUP BY 1 ORDER BY 2 DESC")}
    if is_htmx(request):
        return templates.TemplateResponse(request, "_doc.html", ctx)
    return page(request, "library.html", "library", **ctx)


@app.get("/accounts", response_class=HTMLResponse)
def accounts(request: Request):
    return page(request, "accounts.html", "accounts",
                tenants=D.q("SELECT * FROM portal.tenants ORDER BY since DESC, tenant_key"),
                health=D.health(), sync=D.last_sync())


# --- Files from the read-only mounts ----------------------------------------------------------

def safe_path(root: str, rel: str) -> Path:
    base = ROOTS.get(root)
    if base is None or is_private(rel):
        raise HTTPException(404)
    p = (base / rel).resolve()
    if not p.is_relative_to(base.resolve()) or not p.is_file() or p.suffix.lower() not in VIEWABLE:
        raise HTTPException(404)
    return p


@app.get("/files/{root}/{rel:path}")
def file(request: Request, root: str, rel: str, raw: bool = False):
    p = safe_path(root, rel)
    if p.suffix.lower() in IMAGES:
        return FileResponse(p, media_type=IMAGES[p.suffix.lower()],
                            headers={"Content-Disposition": f'inline; filename="{p.name}"'})
    if p.suffix.lower() == ".pdf":
        return FileResponse(p, media_type="application/pdf",
                            headers={"Content-Disposition": f'inline; filename="{p.name}"'})
    text = p.read_text(encoding="utf-8", errors="replace")
    if raw:
        return PlainTextResponse(text, media_type=mimetypes.guess_type(p.name)[0] or "text/plain")
    body = md.render(text) if p.suffix.lower() == ".md" else None
    return page(request, "file.html", "", name=p.name, rel=rel, root=root, body=body, text=None if body else text)
