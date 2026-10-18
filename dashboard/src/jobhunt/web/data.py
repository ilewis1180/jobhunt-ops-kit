"""Read-only queries and view models for the portal. Connects as jobhunt_app (SELECT only)."""
from __future__ import annotations

import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

from ..db import dsn

CT = ZoneInfo(os.environ.get("JOBHUNT_TZ", "UTC"))  # the applying machine's zone (Queue col C is written in it)

# ATS code -> (chip class, monogram, label). Classes and colours come from the design canvas.
ATS = {
    "workday": ("wd", "W", "Workday"),
    "linkedin_easy_apply": ("li", "in", "LinkedIn Easy Apply"),
    "greenhouse": ("gh", "G", "Greenhouse"),
    "ashby": ("ash", "A", "Ashby"),
    "oracle": ("or", "O", "Oracle CE"),
    "oraclecloudce": ("or", "O", "Oracle CE"),
    "successfactors": ("sf", "S", "SuccessFactors"),
}

STATUS = {
    "submitted": ("Submitted", "s-sub"),
    "paused": ("Paused", "s-pause"),
    "closed": ("Closed", "s-skip"),
    "released": ("Released", "s-ready"),
    "ready": ("Ready", "s-ready"),
    "in progress": ("In progress", "s-ready"),
    "hold": ("Paused", "s-pause"),
    "saved": ("Saved", "s-skip"),
    "skipped": ("Skipped", "s-skip"),
}
RESUME_PREFIX = os.environ.get("JOBHUNT_RESUME_PREFIX", "") or "\0"  # a prefix to strip from résumé file names
STATUS_FILTERS = ["Submitted", "In progress", "Ready", "Paused", "Skipped", "Closed", "Released", "Saved"]

SOURCE_STYLE = [  # (regex on trace answer_source, label, class)
    (r"^standing_(02|answers)$|^02$|^answers$", "Standing answer", "s-ready"),
    (r"user_answer|decision", "Your ruling", "s-sub"),
    (r"card", "PREP card", "s-sub"),
    (r"best_effort|drafted", "Judgment call", "s-pause"),
    (r"parser|prefill|résumé|resume", "Parser / prefill", "s-ready"),
    (r"rule_", "Standing rule", "s-ready"),
]


def conn() -> psycopg.Connection:
    return psycopg.connect(dsn(), row_factory=dict_row, autocommit=True)


def q(sql: str, params=None) -> list[dict]:
    with conn() as c, c.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def ats_chip(code: str | None, label: str | None = None) -> dict:
    code = (code or "").strip().lower()
    if code in ATS:
        cls, mono, lab = ATS[code]
    else:
        lab = label or (code.replace("_", " ").title() if code else "Unknown")
        cls, mono = "ot", "+"
    return {"cls": cls, "mono": mono, "label": lab}


def ct(dt: datetime | None, fmt: str = "%b %d %H:%M") -> str:
    return dt.astimezone(CT).strftime(fmt) if dt else ""


def source_style(src: str | None) -> tuple[str, str]:
    s = (src or "").lower()
    for rx, label, cls in SOURCE_STYLE:
        if re.search(rx, s):
            return label, cls
    return (src or "—"), "s-ready"


# --- Applications ------------------------------------------------------------------------------

def latest_attempts() -> dict[str, dict]:
    rows = q("SELECT * FROM portal.attempts ORDER BY coalesce(started_at, ended_at) NULLS FIRST")
    return {r["job_id"]: r for r in rows if r["job_id"]}


# The Job Queue sheet (docs/11-data-model.md): key "Job ID", "Status" (Ready / Submitted / Skipped / Closed /
# Paused-<why>), "Apply?", "Flags" (skip reasons, ';'-separated), "Tenant key", "ATS", "Job Title".
def queue() -> dict[str, dict]:
    return {r["data"].get("Job ID") or r["row_key"]: r["data"]
            for r in q("SELECT row_key, data FROM portal.sheet_rows WHERE sheet = 'Queue'")}


def queue_status(qrow: dict) -> tuple[str, str, str] | None:
    raw = (qrow.get("Status") or "").strip()
    if not raw:
        return None
    if raw.lower().startswith("paused"):
        why = raw.split("-", 1)[1] if "-" in raw else ""
        return "Paused", "s-pause", why
    if raw.lower() == "submitted-unconfirmed":  # submitted, but no confirmation page or email seen yet
        return "Submitted", "s-sub", "unconfirmed"
    status, cls = STATUS.get(raw.lower(), (raw, "s-ready"))
    return status, cls, ""


def queue_touched(qrow: dict) -> datetime | None:
    """Queue col C "Last touched", written by the applier in its local zone: "2026-09-29 13:45", "2026-09-23 3:30"
    or a bare date."""
    raw = (qrow.get("Last touched") or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=CT)
        except ValueError:
            continue
    return None


def answer_counts() -> dict[tuple[str, str], int]:
    rows = q("SELECT run_id, attempt_id, count(*) AS n FROM portal.trace_steps "
             "WHERE answer_key IS NOT NULL GROUP BY 1, 2")
    return {(r["run_id"], r["attempt_id"]): r["n"] for r in rows}


def applications() -> list[dict]:
    jobs = {r["job_id"]: r for r in q("SELECT * FROM portal.jobs")}
    board = {r["job_id"]: r for r in q("SELECT * FROM portal.board")}
    atts = latest_attempts()
    answers = answer_counts()
    jd_ids = {r["job_id"] for r in q("SELECT job_id FROM portal.jds")}
    prep = {r["job_id"] for r in q("SELECT job_id FROM portal.run_files WHERE kind = 'PREP' AND job_id IS NOT NULL")}

    qs = queue()
    out = []
    for jid in set(jobs) | set(board) | set(atts) | set(qs):
        j, b, a, qr = jobs.get(jid, {}), board.get(jid, {}), atts.get(jid), qs.get(jid, {})
        # The Queue is the orchestrator's record, so its Status wins; files fill in when a job isn't on it.
        qst = queue_status(qr) if qr else None
        if qst:
            status, cls, why = qst
            reason = "; ".join(x for x in (why, qr.get("Flags"), (a or {}).get("halt_reason") if status == "Paused" else None) if x)
            # The lane has submitted but the orchestrator writes the Queue only at its next checkpoint.
            if status in ("Ready", "In progress") and a and (a["outcome"] or "").lower() == "submitted":
                status, cls, reason = "Submitted", "s-sub", "Queue not updated yet"
        elif a:
            key = (a["outcome"] or "").lower()
            status, cls = STATUS.get(key, ((a["outcome"] or "Unknown").title(), "s-ready"))
            reason = a["halt_reason"] or ""
        elif b:
            key = "hold" if (b.get("state") or "").startswith("hold") else (b.get("state") or "ready")
            status, cls = STATUS.get(key, (b.get("state") or "Unknown", "s-ready"))
            reason = (b.get("state") or "").split(":", 1)[1].strip() if ":" in (b.get("state") or "") else ""
        else:
            status, cls = STATUS["saved"]
            reason = ""
        ats_code = (a or {}).get("ats") or b.get("ats") or qr.get("ATS") or j.get("ats_guess") or qr.get("ATS Guess")
        n_ans = answers.get((a["run_id"], a["attempt_id"])) if a else None
        when = a["ended_at"] or a["started_at"] if a else None
        touched = queue_touched(qr) if qr else None
        # No outcome row yet (fragments not synced, or an older run): a Submitted row takes its Queue time,
        # shown with "~" because it is when the sheet was written, not a confirmed submit time.
        approx = not when and status == "Submitted" and touched is not None
        shown = touched if approx else when
        out.append({
            "job_id": jid,
            "company": (a or {}).get("company") or b.get("company") or qr.get("Company") or j.get("company") or "—",
            "role": b.get("role") or qr.get("Job Title") or j.get("title") or "",
            "location": j.get("location") or qr.get("Location") or "",
            "ats": ats_chip(ats_code, b.get("ats_label")),
            "status": status,
            "stcls": cls,
            "reason": reason,
            "resume": ((a or {}).get("resume") or b.get("resume") or "").replace(RESUME_PREFIX, "").replace(".pdf", "") or "—",
            "when_dt": when or touched,  # sort key: newest activity first
            "when": ("~" + ct(shown, "%b %d" if shown.hour == shown.minute == 0 else "%b %d %H:%M")) if approx
                    else (ct(when) if when else "Not yet"),
            "answers": f"{n_ans} answers" if n_ans else ("PREP card" if jid in prep else "—"),
            "has_attempt": a is not None,
            "has_jd": jid in jd_ids,
            "lane": b.get("lane") or "",
        })
    far = datetime(1970, 1, 1, tzinfo=timezone.utc)
    order = {"Paused": 0, "In progress": 1, "Ready": 2, "Submitted": 3, "Skipped": 4}
    out.sort(key=lambda r: (r["when_dt"] or far, -order.get(r["status"], 9)), reverse=True)
    return out


def filter_apps(rows: list[dict], status: str = "", ats: str = "", text: str = "") -> list[dict]:
    t = text.strip().lower()
    return [r for r in rows
            if (not status or r["status"] == status)
            and (not ats or r["ats"]["label"] == ats or (ats == "Other" and r["ats"]["cls"] == "ot"))
            and (not t or t in f"{r['company']} {r['role']} {r['job_id']}".lower())]


# --- Token use ---------------------------------------------------------------------------------

def fmt_tokens(n: int | float | None) -> str:
    if not n:
        return "0"
    for div, unit in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if n >= div:
            v = n / div
            return f"{v:.1f}{unit}" if v < 100 else f"{v:.0f}{unit}"
    return str(int(n))


def fmt_pct(v: float | None) -> str:
    return "—" if v is None else (f"{v:.1f}%" if v < 10 else f"{v:.0f}%")


def token_usage() -> dict:
    """Per-session token use from the orchestrator's USAGE files, grouped by day and run.

    Weekly quota: the orchestrator records the account's weekly-limit % at the run's start and at each checkpoint.
    A run's share is max(now) - min(start) over its rows. The limit is account-wide and lanes run in parallel, so a
    session's share is estimated from its share of the run's tokens (shown as "est.")."""
    rows = q("SELECT * FROM portal.token_usage ORDER BY run_date DESC, run_id DESC, session")
    if not rows:
        return {"days": [], "weekly_now": None}
    subs = {r["run_id"]: r["n"] for r in q(
        "SELECT run_id, count(DISTINCT job_id) AS n FROM portal.attempts WHERE lower(outcome) = 'submitted' GROUP BY 1")}
    runs: dict[str, dict] = {}
    for r in rows:
        total = sum(int(r[k] or 0) for k in ("input_tokens", "output_tokens", "cache_creation_tokens", "cache_read_tokens"))
        submitted = r["jobs_submitted"] if r["jobs_submitted"] is not None else subs.get(r["session_run_id"] or "")
        run = runs.setdefault(r["run_id"], {"run_id": r["run_id"], "date": r["run_date"], "phase": r["phase"],
                                            "sessions": [], "total": 0, "submitted": 0, "starts": [], "nows": []})
        run["phase"] = run["phase"] or r["phase"]
        run["total"] += total
        run["submitted"] += submitted or 0
        if r["weekly_pct_start"] is not None:
            run["starts"].append(float(r["weekly_pct_start"]))
        if r["weekly_pct_now"] is not None:
            run["nows"].append(float(r["weekly_pct_now"]))
        run["sessions"].append({
            "session": r["session"], "phase": r["phase"] or "—", "model": r["model"] or "—",
            "run": r["session_run_id"] or "", "total": total,
            "tokens": fmt_tokens(total), "io": f"{fmt_tokens(r['input_tokens'])} / {fmt_tokens(r['output_tokens'])}",
            "cache": f"{fmt_tokens(r['cache_read_tokens'])} / {fmt_tokens(r['cache_creation_tokens'])}",
            "submitted": submitted, "per_job": fmt_tokens(total / submitted) if submitted else "—",
            "updated": ct(r["updated_at"], "%H:%M") if r["updated_at"] else ""})
    days: dict[str, dict] = {}
    for run in runs.values():
        delta = (max(run["nows"]) - min(run["starts"])) if run["starts"] and run["nows"] else None
        # A negative delta means the weekly window reset during the run: the share can't be computed.
        run["pct"] = delta if delta is not None and delta >= 0 else None
        for s in run["sessions"]:
            s["pct"] = (f"~{fmt_pct(run['pct'] * s['total'] / run['total'])}"
                        if run["pct"] is not None and run["total"] else "—")
        run.update(tokens=fmt_tokens(run["total"]), pct_s=fmt_pct(run["pct"]),
                   per_job=fmt_tokens(run["total"] / run["submitted"]) if run["submitted"] else "—")
        d = days.setdefault(run["date"], {"date": run["date"], "runs": [], "total": 0, "submitted": 0, "pct": None})
        d["runs"].append(run)
        d["total"] += run["total"]
        d["submitted"] += run["submitted"]
        if run["pct"] is not None:
            d["pct"] = (d["pct"] or 0) + run["pct"]
    out = []
    for d in sorted(days.values(), key=lambda d: d["date"], reverse=True):
        label = datetime.strptime(d["date"], "%Y-%m-%d").strftime("%a %b %d") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["date"] or "") else d["date"]
        out.append({**d, "label": label, "tokens": fmt_tokens(d["total"]), "pct_s": fmt_pct(d["pct"]),
                    "n_sessions": sum(len(r["sessions"]) for r in d["runs"]),
                    "per_job": fmt_tokens(d["total"] / d["submitted"]) if d["submitted"] else "—"})
    latest = max(rows, key=lambda r: (r["updated_at"] or datetime.min.replace(tzinfo=timezone.utc)) if r["weekly_pct_now"] is not None
                 else datetime.min.replace(tzinfo=timezone.utc))
    return {"days": out, "weekly_now": fmt_pct(float(latest["weekly_pct_now"])) if latest["weekly_pct_now"] is not None else None,
            "resets": ct(latest["weekly_resets_at"], "%a %b %d %H:%M") if latest["weekly_resets_at"] else None}


# --- One application ---------------------------------------------------------------------------

def application(job_id: str) -> dict | None:
    job = next(iter(q("SELECT * FROM portal.jobs WHERE job_id = %s", (job_id,))), None)
    board = next(iter(q("SELECT * FROM portal.board WHERE job_id = %s", (job_id,))), None)
    attempts = q("SELECT * FROM portal.attempts WHERE job_id = %s "
                 "ORDER BY coalesce(started_at, ended_at) DESC NULLS LAST", (job_id,))
    jd = next(iter(q("SELECT * FROM portal.jds WHERE job_id = %s", (job_id,))), None)
    if not (job or board or attempts or jd):
        return None
    files = q("SELECT rel_path, kind, run_id FROM portal.run_files WHERE job_id = %s ORDER BY rel_path", (job_id,))
    a = attempts[0] if attempts else None
    steps = q("SELECT * FROM portal.trace_steps WHERE run_id = %s AND attempt_id = %s ORDER BY step",
              (a["run_id"], a["attempt_id"])) if a else []
    row = next((r for r in applications() if r["job_id"] == job_id), None)

    trail, answers = [], []
    filled = [s for s in steps if s["answer_key"]]
    for s in steps:
        act, human = s["action"], s["human"] or ""
        if act == "start":
            trail.append(("Claimed by lane", " · ".join(x for x in (a.get("browser"), a.get("card")) if x)))
            if human == "approval":
                trail.append(("Approved", "Your yes in the lane chat"))
        elif act in ("approval", "intent"):
            trail.append(("Approved" if act == "approval" else "Intent written", s["note"] or ""))
        elif human in ("needs_user", "login", "captcha") and act not in ("end",):
            trail.append((f"Needed you ({human.replace('_', ' ')})", s["target_name"] or s["note"] or ""))
        elif act == "halt":
            trail.append(("Halted", s["note"] or ""))
        elif act == "submit":
            if filled:
                trail.append(("Filling", f"{len(filled)} answers on {a.get('pages') or '?'} page(s)"))
            trail.append(("Submit clicked", s["target_name"] or ""))
        elif act == "confirm":
            trail.append(("Confirmed", a.get("confirmation_method") or ""))
        elif act == "end":
            trail.append((f"Ended: {s['note'] or a.get('outcome') or ''}", a.get("halt_reason") or ""))
    for s in filled:
        label, cls = source_style(s["answer_source"])
        answers.append({"q": s["target_name"] or s["answer_key"], "key": s["answer_key"],
                        "a": s["value_safe"] or s["value_ref"] or "—", "src": label, "cls": cls})

    summary = []
    if a:
        summary = [f"Job ID {job_id}", f"Run {a['run_id']}"]
        if a.get("duration_s"):
            summary.append(f"{a['duration_s']:.0f} s")
        if a.get("fields") is not None:
            summary.append(f"{a['fields']} fields, {a.get('required_fields') or 0} required")
        if a.get("confirmation_method"):
            summary.append(f"confirmed by {a['confirmation_method']}")
    return {"job": job or {}, "board": board or {}, "attempt": a, "attempts": attempts, "jd": jd,
            "row": row, "trail": trail, "answers": answers, "files": files, "summary": " · ".join(summary)}


# --- Today, Stats ------------------------------------------------------------------------------

def last_sync() -> dict | None:
    rows = q("SELECT * FROM portal.sync_runs ORDER BY id DESC LIMIT 1")
    ok = q("SELECT * FROM portal.sync_runs WHERE ok AND NOT skipped ORDER BY id DESC LIMIT 1")
    if not rows:
        return None
    r = rows[0]
    return {"last": r, "last_data": ok[0] if ok else None,
            "age_min": int((datetime.now(timezone.utc) - r["started_at"]).total_seconds() // 60)}


def health() -> list[dict]:
    s = last_sync()
    items = []
    if not s:
        return [{"name": "Portal sync", "state": "Never ran", "cls": "s-pause"}]
    ok = s["last"]["ok"] and s["age_min"] <= 30
    items.append({"name": f"Portal sync ({s['age_min']} min ago)", "state": "OK" if ok else "Failing", "cls": "s-sub" if ok else "s-pause"})
    chrome = (s["last"].get("counts") or {}).get("chrome_cdp")
    items.append({"name": "Browser on the apply host", "state": "Up" if chrome else "Down", "cls": "s-sub" if chrome else "s-pause"})
    if s["last_data"]:
        items.append({"name": f"Mac data synced {ct(s['last_data']['finished_at'])}", "state": "OK", "cls": "s-sub"})
    sheets = (s["last"].get("counts") or {}).get("sheets") or "unknown"
    n = q("SELECT count(*) AS n FROM portal.sheet_rows")[0]["n"]
    items.append({"name": f"Google Sheets ({n} rows)", "state": {"ok": "OK", "failed": "Failing"}.get(sheets, sheets.capitalize()),
                  "cls": {"ok": "s-sub", "failed": "s-pause"}.get(sheets, "s-ready")})
    return items


def window_start(window: str) -> datetime | None:
    now = datetime.now(CT)
    if window == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if window == "week":
        return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return None


def stats(window: str = "all") -> dict:
    since = window_start(window)
    atts = [a for a in latest_attempts().values()
            if since is None or ((a["ended_at"] or a["started_at"]) and (a["ended_at"] or a["started_at"]) >= since)]
    submitted = [a for a in atts if a["outcome"] == "submitted"]
    raw_saved = q("SELECT count(DISTINCT data->>'LinkedIn Job ID') AS n FROM portal.sheet_rows WHERE sheet = 'Raw'")[0]["n"]
    saved = raw_saved or q("SELECT count(*) AS n FROM portal.jobs")[0]["n"]
    qs = list(queue().values())
    approved = sum(1 for r in qs if (r.get("Apply?") or "").strip().lower() == "yes")
    q_status = Counter((queue_status(r) or ("Unknown",))[0] for r in qs)
    prepped = q("SELECT count(DISTINCT job_id) AS n FROM portal.run_files WHERE kind = 'PREP'")[0]["n"]
    dispatched = q("SELECT count(*) AS n FROM portal.board")[0]["n"]
    filled = [a for a in atts if (a["fields"] or 0) > 0]

    def bars(pairs):
        top = max([n for _, n in pairs] + [1])
        return [{"label": l, "n": n, "w": f"{max(n / top * 100, 1 if n else 0):.0f}%"} for l, n in pairs]

    funnel = bars([("Saved on LinkedIn", saved), ("Apply = Yes", approved), ("Prepped (PREP card)", prepped),
                   ("Dispatched to a lane", dispatched), ("Submitted (Queue)", q_status.get("Submitted", 0))])
    skips = Counter()
    for r in qs:
        if (queue_status(r) or ("",))[0] in ("Skipped", "Closed"):
            flags = [re.sub(r"\s*of \d+$", "", f.strip()) for f in (r.get("Flags") or "").split(";") if f.strip()]
            for f in flags or ["No reason recorded" if (queue_status(r) or ("",))[0] == "Skipped" else "Posting closed"]:
                skips[f[:1].upper() + f[1:]] += 1
    halts = Counter()
    for a in atts:
        if a["outcome"] != "submitted":
            halts[a["outcome"] or "unknown"] += 1
    by_ats = Counter(ats_chip(a["ats"])["label"] for a in submitted)
    ats_rows = []
    top = max(by_ats.values() or [1])
    colours = {"wd": "#9A4A08", "li": "#0A5CA8", "gh": "#1B6B4F", "ash": "#5B3FA0", "or": "#A3261F", "sf": "#2C5E8E", "ot": "#55554B"}
    for label, n in by_ats.most_common(6):
        cls = next((v[0] for v in ATS.values() if v[2] == label), "ot")
        ats_rows.append({"label": label, "n": n, "w": f"{n / top * 100:.0f}%", "c": colours[cls]})

    today = datetime.now(CT).date()
    days = []
    per_day = Counter((a["ended_at"] or a["started_at"]).astimezone(CT).date() for a in submitted if (a["ended_at"] or a["started_at"]))
    top_day = max(per_day.values() or [1])
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        n = per_day.get(d, 0)
        days.append({"d": d.strftime("%a"), "n": n, "h": f"{max(n / top_day * 110, 2):.0f}px"})

    durations = [float(a["duration_s"]) for a in submitted if a["duration_s"]]
    questions = q("SELECT count(*) AS n FROM portal.questions")[0]["n"]
    human = sum(1 for a in atts if (a["human_interventions"] or "0") not in ("", "0"))
    return {
        "window": window,
        "tiles": [
            {"label": "Saved from LinkedIn", "n": saved, "sub": "distinct jobs on the Raw tab" if raw_saved else "scrape files"},
            {"label": "Approved to apply", "n": approved, "sub": "Queue rows with Apply? = Yes"},
            {"label": "Submitted", "n": q_status.get("Submitted", 0), "sub": "Queue status (all time)"},
            {"label": "Skipped or closed", "n": q_status.get("Skipped", 0) + q_status.get("Closed", 0), "sub": "Queue status"},
        ],
        "funnel": funnel,
        "halts": bars(halts.most_common(6)),
        "skips": bars(skips.most_common(8)),
        "paused_queue": sum(v for k, v in q_status.items() if k == "Paused"),
        "days": days,
        "ats": ats_rows,
        "effort": [
            ("Avg time per submitted card", f"{sum(durations) / len(durations):.0f} s" if durations else "—"),
            ("Attempts with a human step", str(human)),
            ("Paused on the Queue, waiting on you", str(q_status.get("Paused", 0))),
            ("Questions in the bank", str(questions)),
        ],
    }


def today() -> dict:
    apps = applications()
    count = Counter(r["status"] for r in apps)
    funnel = [
        {"label": "Scraped", "n": q("SELECT count(DISTINCT data->>'LinkedIn Job ID') AS n FROM portal.sheet_rows "
                                    "WHERE sheet = 'Raw'")[0]["n"] or len(q("SELECT job_id FROM portal.jobs"))},
        {"label": "Prepped", "n": q("SELECT count(DISTINCT job_id) AS n FROM portal.run_files WHERE kind='PREP'")[0]["n"]},
        {"label": "Ready", "n": count.get("Ready", 0)},
        {"label": "Submitted", "n": count.get("Submitted", 0)},
        {"label": "Paused", "n": count.get("Paused", 0)},
        {"label": "Closed / released", "n": count.get("Closed", 0) + count.get("Released", 0)},
    ]
    # Paused jobs on the Queue each wait on the operator (a sign-in, an answer, a CAPTCHA). Ones with an apply
    # attempt come first because they have an audit trail to open.
    paused = sorted((r for r in apps if r["status"] == "Paused"), key=lambda r: not r["has_attempt"])
    needs, needs_total = paused[:8], len(paused)
    recent = [r for r in apps if r["status"] == "Submitted"][:5]
    upnext = [r for r in apps if r["status"] == "Ready" and not r["has_attempt"]][:3]
    latest_run = q("SELECT run_id FROM portal.attempts ORDER BY started_at DESC NULLS LAST LIMIT 1")
    return {"funnel": funnel, "needs": needs, "needs_total": needs_total, "recent": recent, "upnext": upnext, "health": health(),
            "latest_run": latest_run[0]["run_id"] if latest_run else None}
