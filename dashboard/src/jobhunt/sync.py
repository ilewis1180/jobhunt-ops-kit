"""Sync worker: rebuilds the portal's read model from the mirrored ops files.

Reads /data/ops (the ops data root) and /data/content (the résumé workspace), both mounted read-only, and the
Job Queue (Queue, Raw) and JD Archive Google Sheets through a read-only service account (sheets.py).
Every JOBHUNT_SYNC_INTERVAL seconds it fingerprints both trees plus the sheet contents; when anything
changed it parses everything and replaces the read model in ONE transaction, so the portal never sees
half a sync. If Google fails, the previous sheet rows are kept and a warning is recorded.

Run mode: while a run is live on the applying machine (parsers.run_state: Runs/<date>/RUN-ACTIVE.json, or fresh dispatch
events), it also does a light sync every JOBHUNT_RUN_INTERVAL seconds between the full ones: the Queue tab
only, plus attempts, traces, run files and the dispatch board. Everything else waits for the next full sync.

Run once:   python -m jobhunt.sync --once
Run a loop: python -m jobhunt.sync
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from . import parsers as P
from . import sheets as S
from .db import dsn

log = logging.getLogger("jobhunt.sync")

OPS = Path(os.environ.get("JOBHUNT_OPS_DIR", "/data/ops"))
CONTENT = Path(os.environ.get("JOBHUNT_CONTENT_DIR", "/data/content"))
INTERVAL = int(os.environ.get("JOBHUNT_SYNC_INTERVAL", "600"))
RUN_INTERVAL = int(os.environ.get("JOBHUNT_RUN_INTERVAL", "30"))
CDP_HOST = os.environ.get("JOBHUNT_CDP_HOST", "host.docker.internal")
CDP_PORT = int(os.environ.get("JOBHUNT_CDP_PORT", "9222"))
SCHEMA_SQL = Path(__file__).with_name("schema.sql")

# Order matters only for readability; every table is truncated and refilled together.
TABLES = ("jobs", "jds", "board", "attempts", "trace_steps", "questions", "tenants",
          "resumes", "bullets", "docs", "run_files", "sheet_rows", "token_usage")
LIGHT_TABLES = ("board", "attempts", "trace_steps", "run_files", "token_usage")


def cdp_reachable() -> bool:
    """TCP connect only. The portal never speaks CDP; this is just the Health tile."""
    try:
        with socket.create_connection((CDP_HOST, CDP_PORT), timeout=2):
            return True
    except OSError:
        return False


def fetch_sheets(warnings: list[str], fetch=None) -> tuple[list[dict] | None, str, str]:
    """Returns (rows or None to keep the previous rows, state for the Health tile, fingerprint part)."""
    if not S.configured():
        return None, "not configured", "sheets:none"
    try:
        fetched = (fetch or S.fetch_all)()
    except Exception as e:
        warnings.append(f"Sheets: {type(e).__name__}: {e}"[:500])
        return None, "failed", "sheets:keep"
    rows: list[dict] = []
    for name, (source, values) in fetched.items():
        rows += P.rows_from_values(name, source, values, warnings)
    digest = hashlib.sha256(json.dumps(fetched, sort_keys=True).encode()).hexdigest()[:16]
    return rows, "ok", f"sheets:{digest}"


def collect_attempts(warnings: list[str]) -> tuple[list[dict], list[dict]]:
    capture = OPS / "AppApply-Capture"
    attempts = P.parse_outcomes(capture)
    steps, starts = P.parse_traces(capture, warnings)
    for a in attempts:
        a.update(starts.get((a["run_id"], a["attempt_id"]), {}))
    return attempts, steps


def collect(warnings: list[str], sheet_rows: list[dict] | None) -> dict[str, list[dict] | None]:
    runs = OPS / "Runs"
    capture = OPS / "AppApply-Capture"
    attempts, steps = collect_attempts(warnings)
    return {
        "jobs": P.parse_scrapes(runs),
        "jds": P.parse_jds(runs),
        "board": P.parse_boards(runs),
        "attempts": attempts,
        "trace_steps": steps,
        "questions": P.parse_questions(capture),
        "tenants": P.parse_ledger(OPS / "04-ACCOUNT-LEDGER.md", warnings),
        "resumes": P.parse_resumes(OPS),
        "bullets": P.parse_bullets(CONTENT / "3-Bullet-Bank" / "approved-bullets" / "Approved-Bullets.md"),
        "docs": P.parse_docs(OPS),
        "run_files": P.parse_run_files(OPS),
        "token_usage": P.parse_usage(runs, warnings),
        "sheet_rows": sheet_rows,  # None = keep what is there (Google unreachable)
    }


def load(conn: psycopg.Connection, data: dict[str, list[dict] | None], names: tuple[str, ...] = TABLES,
         truncate: bool = True) -> dict[str, int]:
    counts = {}
    tables = [t for t in names if data.get(t) is not None]
    if not tables:
        return counts
    with conn.cursor() as cur:
        if truncate:
            cur.execute("TRUNCATE " + ", ".join(f"portal.{t}" for t in tables) + " RESTART IDENTITY")
        for table in tables:
            rows = data[table]
            counts[table] = len(rows)
            if not rows:
                continue
            cols = list(rows[0].keys())
            sql = (f"INSERT INTO portal.{table} ({', '.join(cols)}) "
                   f"VALUES ({', '.join(['%s'] * len(cols))})")
            cur.executemany(sql, [[Jsonb(r[c]) if isinstance(r[c], dict) else r[c] for c in cols] for r in rows])
    return counts


def sync_once(conn: psycopg.Connection, last_fp: str | None, force: bool = False) -> str | None:
    started = datetime.now(timezone.utc)
    warnings: list[str] = []
    chrome = cdp_reachable()
    if not OPS.exists() or not any(OPS.iterdir()):
        raise RuntimeError(f"ops folder {OPS} is missing or empty; refusing to wipe the read model")
    sheet_rows, sheets_state, sheets_fp = fetch_sheets(warnings)
    fp = P.fingerprint(OPS, CONTENT) + "|" + sheets_fp
    with conn.transaction():
        with conn.cursor() as cur:
            if fp == last_fp and not force:
                cur.execute(
                    "INSERT INTO portal.sync_runs (started_at, finished_at, ok, skipped, fingerprint, counts, warnings) "
                    "VALUES (%s, now(), true, true, %s, %s, %s)",
                    (started, fp, Jsonb({"chrome_cdp": chrome, "sheets": sheets_state}), Jsonb(warnings)))
                return fp
            data = collect(warnings, sheet_rows)
            counts = load(conn, data)
            counts["chrome_cdp"] = chrome
            counts["sheets"] = sheets_state
            cur.execute(
                "INSERT INTO portal.sync_runs (started_at, finished_at, ok, skipped, fingerprint, counts, warnings) "
                "VALUES (%s, now(), true, false, %s, %s, %s)",
                (started, fp, Jsonb(counts), Jsonb(warnings)))
            cur.execute("DELETE FROM portal.sync_runs WHERE started_at < now() - interval '30 days'")
    log.info("synced: %s; %d warnings", json.dumps(counts), len(warnings))
    return fp


def light_fingerprint() -> str:
    capture = OPS / "AppApply-Capture"
    parts = []
    for name in ("outcomes.csv", "outcomes-jt.csv"):
        f = capture / name
        stat = f.stat() if f.is_file() else None
        parts.append(f"|{name}:{stat.st_size}:{stat.st_mtime:.0f}" if stat else f"|{name}:none")
    return P.fingerprint(capture / "staging", capture / "traces", OPS / "Runs") + "".join(parts)


def light_once(conn: psycopg.Connection, last_fp: str | None) -> str | None:
    """Run mode: refresh only what a live run changes. Queue rows are replaced alone (DELETE WHERE sheet =
    'Queue'), so Raw and JD Archive stay as the last full sync left them."""
    started = datetime.now(timezone.utc)
    warnings: list[str] = []
    chrome = cdp_reachable()
    if not OPS.exists() or not any(OPS.iterdir()):
        raise RuntimeError(f"ops folder {OPS} is missing or empty; refusing to wipe the read model")
    queue_rows, sheets_state, sheets_fp = fetch_sheets(warnings, S.fetch_queue)
    fp = "light|" + light_fingerprint() + "|" + sheets_fp
    base = {"mode": "light", "chrome_cdp": chrome, "sheets": sheets_state}
    with conn.transaction(), conn.cursor() as cur:
        if fp == last_fp:
            cur.execute(
                "INSERT INTO portal.sync_runs (started_at, finished_at, ok, skipped, fingerprint, counts, warnings) "
                "VALUES (%s, now(), true, true, %s, %s, %s)", (started, fp, Jsonb(base), Jsonb(warnings)))
            return fp
        attempts, steps = collect_attempts(warnings)
        data = {"board": P.parse_boards(OPS / "Runs"), "attempts": attempts, "trace_steps": steps,
                "run_files": P.parse_run_files(OPS), "token_usage": P.parse_usage(OPS / "Runs", warnings)}
        counts = load(conn, data, LIGHT_TABLES)
        if queue_rows is not None:
            cur.execute("DELETE FROM portal.sheet_rows WHERE sheet = 'Queue'")
            load(conn, {"sheet_rows": queue_rows}, ("sheet_rows",), truncate=False)
            counts["queue_rows"] = len(queue_rows)
        cur.execute(
            "INSERT INTO portal.sync_runs (started_at, finished_at, ok, skipped, fingerprint, counts, warnings) "
            "VALUES (%s, now(), true, false, %s, %s, %s)", (started, fp, Jsonb({**counts, **base}), Jsonb(warnings)))
    log.info("light sync: %s; %d warnings", json.dumps(counts), len(warnings))
    return fp


def live_run() -> dict | None:
    try:
        return P.run_state(OPS)
    except OSError:  # a half-synced flag file must not stop the loop
        log.exception("run-state check failed")
        return None


def record_failure(conn: psycopg.Connection, err: Exception) -> None:
    try:
        conn.rollback()
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                "INSERT INTO portal.sync_runs (started_at, finished_at, ok, error) VALUES (now(), now(), false, %s)",
                (f"{type(err).__name__}: {err}"[:2000],))
    except Exception:  # the database itself may be the failure
        log.exception("could not record the failed sync")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="sync once (forced) and exit")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    last_fp = light_fp = None
    was_live = False
    while True:
        try:
            # autocommit: each conn.transaction() below is then a real BEGIN/COMMIT, not a savepoint.
            with psycopg.connect(dsn(), autocommit=True) as conn:
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
                next_full = 0.0
                while True:
                    full = args.once or last_fp is None or time.monotonic() >= next_full
                    try:
                        if full:
                            next_full = time.monotonic() + INTERVAL
                            last_fp = sync_once(conn, last_fp, force=args.once or last_fp is None)
                        else:
                            light_fp = light_once(conn, light_fp)
                    except psycopg.OperationalError:
                        raise
                    except Exception as e:  # a bad file must not kill the loop
                        log.exception("sync failed")
                        record_failure(conn, e)
                        if args.once:
                            raise SystemExit(1)
                    if args.once:
                        return
                    live = live_run()
                    if live and not was_live:
                        log.info("run mode on: %s (%s); light sync every %d s", live["run_id"], live["source"], RUN_INTERVAL)
                    elif was_live and not live:
                        log.info("run mode off")
                    was_live = bool(live)
                    wait = max(0.0, next_full - time.monotonic())
                    time.sleep(min(RUN_INTERVAL, wait) if live else wait)
        except psycopg.OperationalError:
            log.exception("database unavailable; retrying in 30 s")
            if args.once:
                raise SystemExit(1)
            time.sleep(30)


if __name__ == "__main__":
    main()
