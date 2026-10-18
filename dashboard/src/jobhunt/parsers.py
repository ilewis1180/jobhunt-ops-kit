"""Parsers for the mirrored ops files (docs/11-data-model.md). Pure functions: paths in, row dicts out.

Every parser tolerates missing columns and records a warning instead of failing the sync.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))  # jd-*.csv holds full job descriptions

RUN_ID_RE = re.compile(r"R\d{8}-\d{4}-[a-z]+\d*")
JOB_ID_RE = re.compile(r"(?<!\d)(\d{9,11})(?!\d)")
CREDENTIAL_RE = re.compile(r"pass(word)?|token|secret|credential|otp|2fa|mfa|pin\b|recovery", re.I)
# Allowlist for the file routes (safe_path): top-level docs and the log, and these data folders only.
SERVED_ROOT_FILES = r"(0\d-[A-Za-z0-9-]+|SESSION_LOG)\.md"
SERVED_DIRS = {"Runs", "AppApply-Capture", "Resume", "1-Resumes", "3-Bullet-Bank", "4-ATS"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def run_id_of(path: Path) -> str | None:
    m = RUN_ID_RE.search(path.as_posix())
    return m.group(0) if m else None


def _int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ts(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


# --- Runs/*/scrape-*.csv, prebuild-*.csv -------------------------------------------------------

def parse_scrapes(runs_dir: Path) -> list[dict]:
    files = sorted(list(runs_dir.glob("*/scrape-*.csv")) + list(runs_dir.glob("*/prebuild-*.csv")),
                   key=lambda p: (run_id_of(p) or "", p.name))
    jobs: dict[str, dict] = {}
    for p in files:
        run = run_id_of(p)
        for r in read_csv(p):
            jid = r.get("LinkedIn Job ID", "")
            if not jid:
                continue
            prev = jobs.get(jid)
            jobs[jid] = {
                "job_id": jid,
                "company": r.get("Company"),
                "title": r.get("Job Title"),
                "location": r.get("Location"),
                "work_mode": r.get("Work Mode"),
                "employment_type": r.get("Employment Type"),
                "posted_date": r.get("Posted Date"),
                "easy_apply": r.get("Easy Apply"),
                "status_raw": r.get("Status Raw"),
                "tracker_stage": r.get("Tracker Stage"),
                "linkedin_url": r.get("LinkedIn Job URL"),
                "apply_url": r.get("Real Apply URL"),
                "apply_domain": r.get("Apply Domain"),
                "ats_guess": r.get("ATS Guess"),
                "salary_raw": r.get("Salary Raw"),
                "first_seen_run": prev["first_seen_run"] if prev else run,
                "last_seen_run": run,
                "source_file": p.relative_to(runs_dir.parent).as_posix(),
            }
    return list(jobs.values())


# --- Runs/*/jd-*.csv ----------------------------------------------------------------------------

def parse_jds(runs_dir: Path) -> list[dict]:
    best: dict[str, dict] = {}
    for p in sorted(runs_dir.glob("*/jd-*.csv")):
        for r in read_csv(p):
            jid = r.get("LinkedIn Job ID", "")
            text = r.get("Full Job Description", "")
            if not jid or not text:
                continue
            if jid in best and len(best[jid]["full_text"]) >= len(text):
                continue
            best[jid] = {
                "job_id": jid,
                "company": r.get("Company"),
                "title": r.get("Job Title"),
                "captured_date": r.get("Captured Date"),
                "source_url": r.get("Source URL"),
                "chars": len(text),
                "full_text": text,
                "source_file": p.relative_to(runs_dir.parent).as_posix(),
            }
    return list(best.values())


# --- Runs/*/dispatch-*/board.csv ----------------------------------------------------------------

def parse_boards(runs_dir: Path) -> list[dict]:
    rows: dict[str, dict] = {}
    for p in sorted(runs_dir.glob("*/dispatch-*/board.csv"), key=lambda p: run_id_of(p) or ""):
        run = run_id_of(p)
        for r in read_csv(p):
            jid = r.get("job_id", "")
            if not jid:
                continue
            rows[jid] = {
                "job_id": jid,
                "run_id": run,
                "lane": r.get("lane"),
                "company": r.get("company"),
                "role": r.get("role"),
                "ats": r.get("ats"),
                "ats_label": r.get("ats_label"),
                "tenant_key": r.get("tenant_key"),
                "login": r.get("login"),
                "state": r.get("state"),
                "card": r.get("card"),
                "resume": r.get("resume"),
                "apply_url": r.get("apply_url"),
                "source_file": p.relative_to(runs_dir.parent).as_posix(),
            }
    return list(rows.values())


# --- AppApply-Capture/outcomes.csv + traces -----------------------------------------------------

def _outcome_row(r: dict[str, str]) -> dict:
    return {
        "run_id": r["run_id"],
        "attempt_id": r["attempt_id"],
        "job_id": r.get("job_id"),
        "company": r.get("company"),
        "ats": r.get("ats"),
        "tenant": r.get("tenant"),
        "outcome": r.get("outcome"),
        "confirmation_method": r.get("confirmation_method"),
        "started_at": _ts(r.get("started_at")),
        "ended_at": _ts(r.get("ended_at")),
        "duration_s": _num(r.get("duration_s")),
        "pages": _int(r.get("pages")),
        "fields": _int(r.get("fields")),
        "required_fields": _int(r.get("required_fields")),
        "human_interventions": r.get("human_interventions"),
        "halt_reason": r.get("halt_reason"),
        "trace_file": r.get("trace_file"),
        "card": None,
        "resume": None,
        "browser": None,
    }


def parse_outcomes(capture_dir: Path) -> list[dict]:
    """outcomes.csv plus the live per-attempt fragments in staging/OUTCOME-*.csv (same header).

    Lanes write a fragment per attempt during a run; the orchestrator merges them into outcomes.csv only at
    session end (tools/import-inbox.py), moving merged ones to staging/_imported/, which is not read here.
    While the merge syncs over, one attempt can sit in both places: (run_id, attempt_id) is the table's
    primary key, so keep the first seen and let outcomes.csv win."""
    # outcomes-jt.csv: same header, JT-<10 hex> job-tools keys; read after outcomes.csv.
    files = [capture_dir / "outcomes.csv", capture_dir / "outcomes-jt.csv"] + sorted((capture_dir / "staging").glob("OUTCOME-*.csv"))
    out, seen = [], set()
    for p in files:
        if not p.is_file():
            continue
        for r in read_csv(p):
            key = (r.get("run_id"), r.get("attempt_id"))
            if not all(key) or key in seen:
                continue
            seen.add(key)
            out.append(_outcome_row(r))
    return out


def _target_name(t) -> str | None:
    if isinstance(t, dict):
        return t.get("label") or t.get("name") or t.get("id")
    return str(t) if t else None


def _short(v, n=500) -> str | None:
    if v is None:
        return None
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s[:n]


def parse_traces(capture_dir: Path, warnings: list[str]) -> tuple[list[dict], dict[tuple[str, str], dict]]:
    """Returns (steps, start-step info keyed by (run_id, attempt_id))."""
    steps: list[dict] = []
    starts: dict[tuple[str, str], dict] = {}
    for p in sorted((capture_dir / "traces").glob("**/*.jsonl")):
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                warnings.append(f"bad JSON: {p.name} line {n}")
                continue
            run, att, step = o.get("run_id"), o.get("attempt_id"), _int(o.get("step"))
            if not run or not att or step is None:
                warnings.append(f"trace line without run/attempt/step: {p.name} line {n}")
                continue
            if o.get("action") == "start":
                starts[(run, att)] = {"card": o.get("card"), "resume": o.get("resume"), "browser": o.get("browser")}
            verify = o.get("verify")
            steps.append({
                "run_id": run,
                "attempt_id": att,
                "step": step,
                "ts": _short(o.get("ts"), 40),
                "action": o.get("action"),
                "page": _short(o.get("page"), 40),
                "target_name": _short(_target_name(o.get("target")), 300),
                "answer_key": o.get("answer_key"),
                "answer_source": _short(o.get("answer_source"), 80),
                "value_safe": _short(o.get("value_safe")),
                "value_ref": _short(o.get("value_ref"), 300),
                "result": _short(o.get("result"), 80),
                "human": _short(o.get("human"), 40),
                "verify_ok": verify.get("ok") if isinstance(verify, dict) else None,
                "note": _short(o.get("note") or o.get("halt_reason") or o.get("outcome")),
            })
    # A trace can repeat a step number; keep the last one so the primary key holds.
    dedup = {(s["run_id"], s["attempt_id"], s["step"]): s for s in steps}
    return list(dedup.values()), starts


def parse_questions(capture_dir: Path) -> list[dict]:
    p = capture_dir / "question-bank.csv"
    if not p.exists():
        return []
    out = {}
    for r in read_csv(p):
        if r.get("question_id"):
            out[r["question_id"]] = {
                "question_id": r["question_id"],
                "label_normalized": r.get("label_normalized"),
                "times_seen": _int(r.get("times_seen")),
                "seen_on_live_form": r.get("seen_on_live_form"),
                "answer_key": r.get("answer_key"),
                "answer_sources": r.get("answer_sources"),
                "ats_list": r.get("ats_list"),
                "example_labels": r.get("example_labels"),
            }
    return list(out.values())


# --- 04-ACCOUNT-LEDGER.md -----------------------------------------------------------------------

def _cell(s: str) -> str:
    return re.sub(r"[`*]", "", s).strip()


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_ledger(path: Path, warnings: list[str]) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip().lower() == "## tenants")
    except StopIteration:
        warnings.append("ledger: no '## Tenants' section")
        return []
    header = None
    out: dict[str, dict] = {}
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if not line.strip().startswith("|"):
            continue
        cells = _split_row(line)
        if header is None:
            header = [_cell(c).lower() for c in cells]
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        row = dict(zip(header, cells))
        key = _cell(row.get("tenant key", ""))
        if not key:
            continue
        out[key] = {
            "tenant_key": key,
            "match_on": _cell(row.get("match on (url host / path prefix)", row.get("match on", ""))),
            "ats": _cell(row.get("ats", "")),
            "state": _cell(row.get("state", "")),
            "since": _cell(row.get("since", "")),
            "waiting": _cell(row.get("queue rows waiting (job id)", "")),
        }
    if header and not {"tenant key", "ats", "state"} <= set(header):
        warnings.append(f"ledger: unexpected header {header}")
    return list(out.values())


# --- Résumés, bullets, docs, run files ----------------------------------------------------------

def tract_of(name: str) -> str:
    stem = Path(name).stem
    prefix = os.environ.get("JOBHUNT_RESUME_PREFIX", "")
    return stem.split(prefix, 1)[-1] if prefix and prefix in stem else stem


def parse_resumes(ops: Path) -> list[dict]:
    d = ops / "Resume"
    if not d.exists():
        return []
    return [{
        "file": p.name,
        "tract": tract_of(p.name),
        "size_bytes": p.stat().st_size,
        "modified_at": mtime(p),
        "rel_path": p.relative_to(ops).as_posix(),
    } for p in sorted(d.glob("*.pdf"))]


NOT_APPROVED_SECTIONS = re.compile(r"^(counts|held|excluded|retired|résumé layout)", re.I)


def parse_bullets(path: Path) -> list[dict]:
    """Approved-Bullets.md: '## section' / '### company' / '#### role' headings, '- ' bullet lines.

    Only approved bullets are kept: the Counts, Held, Excluded, Retired and layout sections are skipped.
    """
    if not path.exists():
        return []
    out, section, sub, role = [], None, None, None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#### "):
            role = line[5:].strip()
        elif line.startswith("### "):
            sub, role = line[4:].strip(), None
        elif line.startswith("## "):
            section, sub, role = line[3:].strip(), None, None
        elif line.startswith("- ") and section and not NOT_APPROVED_SECTIONS.match(section):
            out.append({"ordinal": len(out) + 1, "section": section, "subsection": sub, "role": role,
                        "text": line[2:].strip(), "source_file": path.name})
    return out


def is_private(rel: str) -> bool:
    """Files the portal must never list or serve: anything with "private" in a path part (the answers file), and
    anything outside the allowlist of served folders (SERVED_ROOT_FILES at the top level, SERVED_DIRS below it)."""
    parts = Path(rel).parts
    if any("private" in part.lower() for part in parts) or not parts:
        return True
    if len(parts) == 1:
        return not re.fullmatch(SERVED_ROOT_FILES, parts[0])
    return parts[0] not in SERVED_DIRS


def parse_docs(ops: Path) -> list[dict]:
    out = []
    # Docs list: the numbered docs plus SESSION_LOG.md; never the private answers file.
    for p in sorted(ops.glob("0*.md")) + [q for q in (ops / "SESSION_LOG.md",) if q.is_file()]:
        if is_private(p.name):
            continue
        first = next((l for l in p.read_text(encoding="utf-8", errors="replace").splitlines() if l.startswith("# ")), "")
        out.append({"name": p.stem, "title": first[2:].strip() or p.stem, "rel_path": p.name,
                    "modified_at": mtime(p), "size_bytes": p.stat().st_size})
    return out


RUN_FILE_KINDS = ("PREP-DECISIONS", "PREP-SUMMARY", "RUN-SUMMARY", "LEARNINGS", "INTENT", "PREP",
                  "paused", "skipped", "DECISION", "LOGIN-CHECKLIST", "IMPROVEMENT-PLAN", "RUNBOOK-PROPOSAL", "jd")


def parse_run_files(ops: Path) -> list[dict]:
    out = []
    for p in sorted((ops / "Runs").glob("*/*.md")):
        kind = next((k for k in RUN_FILE_KINDS if p.name.startswith(k + "-")), "other")
        m = JOB_ID_RE.search(p.name)
        out.append({"rel_path": p.relative_to(ops).as_posix(), "kind": kind, "run_id": run_id_of(p),
                    "job_id": m.group(1) if m else None, "run_date": p.parent.name, "modified_at": mtime(p)})
    return out


# --- Runs/<date>/USAGE-<RunID>.csv (token use per session) ------------------------------------

USAGE_INT = ("input_tokens", "output_tokens", "cache_creation_tokens", "cache_read_tokens",
             "jobs_attempted", "jobs_submitted")


def parse_usage(runs_dir: Path, warnings: list[str]) -> list[dict]:
    """Token use written by the orchestrator (phase 1, 2 or 3): one CSV per orchestrator run, rewritten at each
    checkpoint, one row per session (the orchestrator itself and each lane); the 16-column contract is in
    docs/11-data-model.md. Lenient: unknown columns are ignored, missing ones are None.
    weekly_pct_* are the account's weekly-limit percentages (0-100) as the orchestrator read them."""
    out: dict[tuple[str, str], dict] = {}
    for p in sorted(runs_dir.glob("*/USAGE-*.csv")):
        file_run = run_id_of(p) or ""
        for n, r in enumerate(read_csv(p), 2):
            session = r.get("session") or ""
            if not session:
                warnings.append(f"usage: {p.name} row {n} has no session")
                continue
            run = r.get("run_id") or file_run
            row = {
                "run_id": run,
                "run_date": p.parent.name,
                "phase": r.get("phase") or None,
                "session": session,
                "session_run_id": r.get("session_run_id") or None,
                "model": r.get("model") or None,
                "started_at": _ts(r.get("started_at")),
                "updated_at": _ts(r.get("updated_at")),
                "weekly_pct_start": _num(r.get("weekly_pct_start")),
                "weekly_pct_now": _num(r.get("weekly_pct_now")),
                "weekly_resets_at": _ts(r.get("weekly_resets_at")),
                "source_file": p.relative_to(runs_dir.parent).as_posix(),
            }
            row.update({k: _int(r.get(k)) for k in USAGE_INT})
            out[(run, session)] = row
    return list(out.values())


# --- Live run on the Mac (run mode) ------------------------------------------------------------

RUN_FLAG = "RUN-ACTIVE.json"
RUN_FLAG_DEFAULT = timedelta(minutes=15)
RUN_EVENTS_FRESH = timedelta(minutes=5)
DATE_DIR_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def run_state(ops: Path, now: datetime | None = None) -> dict | None:
    """Is an apply run live on the Mac? Returns {"run_id", "source", "until"} or None.

    Explicit: the orchestrator writes Runs/<date>/RUN-ACTIVE.json ({"run_id", "started_at", "expires_at"})
    at session start, rewrites it at each checkpoint and deletes it at session end; expires_at covers a crash.
    A flag without a readable expires_at counts for 15 min from its mtime. Once a flag file exists it alone
    decides. Until the Mac writes one: a dispatch-*/events file changed in the last 5 min means live."""
    now = now or datetime.now(timezone.utc)
    runs = ops / "Runs"
    if not runs.is_dir():
        return None
    days = sorted((d for d in runs.iterdir() if d.is_dir() and DATE_DIR_RE.fullmatch(d.name)), reverse=True)[:2]
    flags = [d / RUN_FLAG for d in days if (d / RUN_FLAG).is_file()]
    if flags:
        for f in flags:
            try:
                o = json.loads(f.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                o = {}
            o = o if isinstance(o, dict) else {}
            until = _ts(str(o.get("expires_at") or ""))
            if until and until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            until = until or mtime(f) + RUN_FLAG_DEFAULT
            if until > now:
                return {"run_id": o.get("run_id") or "", "source": "flag", "until": until}
        return None
    for d in days:
        for ev in d.glob("dispatch-*/events/*"):
            if ev.is_file() and now - mtime(ev) < RUN_EVENTS_FRESH:
                return {"run_id": run_id_of(ev) or "", "source": "events", "until": mtime(ev) + RUN_EVENTS_FRESH}
    return None


# --- Google Sheets (Job Queue: Queue, Raw; JD Archive) ------------------------------------------

KEY_COLUMNS = ("LinkedIn Job ID", "Job ID", "job_id")


def rows_from_values(sheet: str, source: str, values: list[list[str]], warnings: list[str]) -> list[dict]:
    """Sheet values (first row = header) -> portal.sheet_rows dicts. Stored generically (jsonb) until the
    field mapping is in docs/11-data-model.md. Columns that look like credentials are dropped, never stored."""
    if not values:
        return []
    header = [str(h).strip() for h in values[0]]
    dropped = {h for h in header if h and CREDENTIAL_RE.search(h)}
    if dropped:
        warnings.append(f"{sheet}: dropped credential-looking columns {sorted(dropped)}")
    key_col = next((c for c in KEY_COLUMNS if c in header), None)
    out, seen = [], set()
    for i, raw in enumerate(values[1:], 2):  # i = the sheet's own row number
        row = {h: (str(raw[j]).strip() if j < len(raw) else "") for j, h in enumerate(header) if h and h not in dropped}
        if not any(row.values()):
            continue
        # Queue col A is a spilling UNIQUE() of Job IDs. A row without one belongs to no job, whatever sits
        # beside it (the spill's blank tail, or stray typed cells). Never key a Queue row by position.
        if sheet == "Queue" and key_col and not row.get(key_col):
            warnings.append(f"Queue: skipped row {i} (no Job ID)")
            continue
        key = (row.get(key_col) if key_col else "") or f"row-{i}"
        if key in seen:
            key = f"{key}#row-{i}"
        seen.add(key)
        out.append({"sheet": sheet, "row_key": key, "data": row, "source_file": f"{source}#row-{i}"})
    return out


def fingerprint(*roots: Path) -> str:
    """Cheap change detector: file count plus newest mtime and total size under each root."""
    parts = []
    for root in roots:
        n = size = 0
        newest = 0.0
        if root.exists():
            for p in root.rglob("*"):
                if p.is_file() and ".stfolder" not in p.parts:
                    st = p.stat()
                    n += 1
                    size += st.st_size
                    newest = max(newest, st.st_mtime)
        parts.append(f"{root.name}:{n}:{size}:{newest:.0f}")
    return "|".join(parts)
