"""Export decided jobs to state/staging/approved-jobs-<date>.csv, then stamp exported_at.

Order matters: select, write the file atomically, only then stamp. A failed write leaves the rows
unexported, so the next run retries. Approved and denied rows are both exported (the Mac needs the
denials too); the Mac decides what to ingest.
"""
import csv
import os
from datetime import datetime
from pathlib import Path

from . import db


def write_csv(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=db.EXPORT_COLS)
        w.writeheader()
        w.writerows(rows)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def run_export(staging_dir, now=None, fetch=db.fetch_decided, stamp=db.stamp_exported):
    rows = fetch()
    if not rows:
        return None, 0
    now = now or datetime.now()
    path = Path(staging_dir) / f"approved-jobs-{now:%Y-%m-%d-%H%M%S}.csv"
    write_csv(rows, path)
    stamped = stamp([r["job_key"] for r in rows])
    return path, stamped
