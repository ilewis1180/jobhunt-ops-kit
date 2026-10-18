"""job_approvals table access through `docker exec ... psql` (a Postgres container on the scheduler host). No credential
is stored here: psql runs inside the container as its own user.

Allowed writes: INSERT new pending rows, and UPDATE exported_at. Status, decided_at and decided_by belong to whatever
UI records the approve/deny click (a chat bot, a web page). Values travel as psql variables (:'name'), never spliced
into SQL text.

Settings (environment): JOBHUNT_PG_CONTAINER (default jobhunt-postgres), JOBHUNT_PG_USER (default jobhunt),
JOBHUNT_PG_DB (default jobhunt). Schema: discover/schema.sql.
"""
import csv
import io
import os
import re
import subprocess

CONTAINER = os.environ.get("JOBHUNT_PG_CONTAINER", "jobhunt-postgres")
PSQL = ["docker", "exec", "-i", CONTAINER, "psql", "-U", os.environ.get("JOBHUNT_PG_USER", "jobhunt"),
        "-d", os.environ.get("JOBHUNT_PG_DB", "jobhunt"), "-v", "ON_ERROR_STOP=1", "-X", "-q"]
_SAFE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")

INSERT_SQL = (
    "INSERT INTO job_approvals (job_key, title, company, location, grade, source, url) "
    "VALUES (:'k', :'t', :'c', NULLIF(:'l',''), :'g', :'s', NULLIF(:'u','')) "
    "ON CONFLICT (job_key) DO NOTHING RETURNING job_key;\n"
)
EXPORT_COLS = ["job_key", "title", "company", "location", "grade", "source", "url", "status", "decided_at", "decided_by"]
SELECT_SQL = (
    "SELECT " + ", ".join(EXPORT_COLS) + " FROM job_approvals "
    "WHERE status <> 'pending' AND exported_at IS NULL ORDER BY decided_at, job_key"
)


def _run(args, sql, runner=subprocess.run):
    r = runner(PSQL + args, input=sql, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if r.returncode != 0:
        raise RuntimeError("psql failed: " + (r.stderr or "").strip()[:500])
    return r.stdout


def insert_pending(c, runner=subprocess.run):
    """Returns True if a new row was created, False if the key already existed."""
    v = dict(k=c["job_key"], t=c["title"], c=c["company"], l=c.get("location") or "",
             g=c["grade"], s=c["source"], u=c.get("url") or "")
    args = []
    for name, val in v.items():
        args += ["-v", f"{name}={val}"]
    out = _run(args + ["-A", "-t"], INSERT_SQL, runner)
    return bool(out.strip())


def fetch_decided(runner=subprocess.run):
    out = _run(["--csv", "-c", SELECT_SQL], "", runner)
    return list(csv.DictReader(io.StringIO(out)))


def stamp_exported(keys, runner=subprocess.run):
    for k in keys:
        if not _SAFE_KEY.match(k):
            raise ValueError("unsafe job_key refused: %r" % k)
    if not keys:
        return 0
    arr = "{" + ",".join(keys) + "}"
    sql = ("UPDATE job_approvals SET exported_at = now() "
           "WHERE job_key = ANY(:'keys'::text[]) AND exported_at IS NULL AND status <> 'pending' "
           "RETURNING job_key;\n")
    out = _run(["-v", f"keys={arr}", "-A", "-t"], sql, runner)
    return len([x for x in out.splitlines() if x.strip()])
