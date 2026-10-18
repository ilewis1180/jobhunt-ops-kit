"""Outcomes page data: one row per application from the Mac's timeline.csv, plus follow-ups.

Pure stdlib and read-only. Files are read on every request, so the page is as fresh as the last Syncthing delivery.
timeline.csv (machine-rebuilt on the Mac): job_id, company, title, apply_at, confirmation_at, rejection_at,
interview_at, last_mail_at, state (applied | confirmed | rejected), followup_due, mail_export_at.
followups.csv (human-owned): job_id, followed_up_at, followup_days, snooze_until, note.
"""
from __future__ import annotations

import os

import csv
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CT = ZoneInfo(os.environ.get("JOBHUNT_TZ", "UTC"))
CAPTURE = "AppApply-Capture"
OPEN_STATES = ("applied", "confirmed")
AMBER_H, RED_H = 12, 36


def _read(path: Path) -> list[dict]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError):
        return []


def _dt(s: str | None) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=CT)


def _date(s: str | None) -> date | None:
    d = _dt(s)
    return d.astimezone(CT).date() if d else None


def _days(a: datetime | None, b: datetime | None) -> float | None:
    if not a or not b:
        return None
    d = (b - a).total_seconds() / 86400
    return d if d >= 0 else None


def _fmt(d: datetime | None) -> str:
    return d.astimezone(CT).strftime("%b %d") if d else "—"


def _span(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "median": "—", "avg": "—", "fast": "—", "slow": "—"}
    one = lambda v: "<1 d" if v < 1 else f"{v:.1f} d" if v < 10 else f"{v:.0f} d"
    return {"n": len(values), "median": one(statistics.median(values)), "avg": one(sum(values) / len(values)),
            "fast": one(min(values)), "slow": one(max(values))}


def _stamp(now: datetime, export_at: datetime | None, file_mtime: datetime | None) -> dict:
    """Freshness: amber over 12 h, red over 36 h, on the older of the mail export and the file delivery."""
    marks = [m for m in (export_at, file_mtime) if m]
    if not marks:
        return {"text": "no data yet", "cls": "s-skip", "hours": None}
    oldest = min(marks)
    hours = (now - oldest).total_seconds() / 3600
    cls = "s-bad" if hours > RED_H else "s-pause" if hours > AMBER_H else "s-sub"
    age = f"{hours:.0f} h" if hours < 48 else f"{hours / 24:.0f} d"
    return {"text": f"mail export {_fmt(export_at)} · file delivered {_fmt(file_mtime)} · {age} old",
            "cls": cls, "hours": hours}


def outcomes(ops: Path, state: str = "", today: date | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = today or now.astimezone(CT).date()
    cap = ops / CAPTURE
    tl_path = cap / "timeline.csv"
    raw = _read(tl_path)
    fups = {r["job_id"]: r for r in _read(cap / "followups.csv") if r.get("job_id")}

    rows, due = [], []
    gaps = {"apply_to_confirm": [], "apply_to_reject": [], "confirm_to_reject": [], "apply_to_interview": []}
    exports = []
    for r in raw:
        st = (r.get("state") or "applied").strip().lower()
        ap, cf, rj, iv = (_dt(r.get(k)) for k in ("apply_at", "confirmation_at", "rejection_at", "interview_at"))
        if e := _dt(r.get("mail_export_at")):
            exports.append(e)
        for key, a, b in (("apply_to_confirm", ap, cf), ("apply_to_reject", ap, rj),
                          ("confirm_to_reject", cf, rj), ("apply_to_interview", ap, iv)):
            if (v := _days(a, b)) is not None:
                gaps[key].append(v)
        row = {"job_id": r.get("job_id", ""), "company": (r.get("company") or "").strip() or "Unparsed company",
               "title": (r.get("title") or "").strip() or "—", "state": st,
               "applied": _fmt(ap), "confirmed": _fmt(cf), "interview": _fmt(iv), "rejected": _fmt(rj),
               "to_confirm": f"{_days(ap, cf):.0f} d" if _days(ap, cf) is not None else "",
               "to_reject": f"{_days(ap, rj):.0f} d" if _days(ap, rj) is not None else "",
               "sort": ap or datetime.min.replace(tzinfo=timezone.utc)}
        rows.append(row)
        # Follow-up: still open, due date reached, not snoozed, not already followed up past the due date.
        if st in OPEN_STATES:
            f = fups.get(row["job_id"], {})
            fd = _date(r.get("followup_due"))
            snooze = _date(f.get("snooze_until"))
            did = _date(f.get("followed_up_at"))
            if fd and fd <= today and not (snooze and snooze > today) and not (did and did >= fd):
                row_due = dict(row, due=fd.strftime("%b %d"), overdue=(today - fd).days,
                               since=(today - ap.astimezone(CT).date()).days if ap else None,
                               note=(f.get("note") or "").strip())
                due.append(row_due)
    due.sort(key=lambda d: -d["overdue"])
    rows.sort(key=lambda d: d["sort"], reverse=True)

    count = lambda s: sum(1 for r in rows if r["state"] == s)
    n_open = sum(1 for r in rows if r["state"] in OPEN_STATES)
    n_conf = sum(1 for r in rows if r["confirmed"] != "—")
    n_rej, n_int = count("rejected"), sum(1 for r in rows if r["interview"] != "—")
    total = len(rows)
    pct = lambda n: f"{n / total * 100:.0f}%" if total else "—"
    mtime = datetime.fromtimestamp(tl_path.stat().st_mtime, timezone.utc) if tl_path.exists() else None

    shown = [r for r in rows if not state or r["state"] == state]
    return {
        "state": state, "total": total, "rows": shown, "due": due,
        "tiles": [
            {"label": "Applied", "n": total, "sub": "rows in timeline.csv"},
            {"label": "Open", "n": n_open, "sub": "no rejection yet"},
            {"label": "Confirmed", "n": n_conf, "sub": f"{pct(n_conf)} of applied"},
            {"label": "Rejected", "n": n_rej, "sub": f"{pct(n_rej)} of applied"},
            {"label": "Interview", "n": n_int, "sub": f"{pct(n_int)} of applied"},
            {"label": "Follow-ups due", "n": len(due), "sub": "open, due date reached, not snoozed"},
        ],
        "spans": [
            {"label": "Applied to confirmation", **_span(gaps["apply_to_confirm"])},
            {"label": "Applied to rejection", **_span(gaps["apply_to_reject"])},
            {"label": "Confirmation to rejection", **_span(gaps["confirm_to_reject"])},
            {"label": "Applied to interview", **_span(gaps["apply_to_interview"])},
        ],
        "stamp": _stamp(now, max(exports) if exports else None, mtime),
        "missing": not tl_path.exists(),
    }
