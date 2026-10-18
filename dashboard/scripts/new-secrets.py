"""Create secrets/db.env, secrets/sync.env and secrets/app.env with fresh random role passwords.

Never overwrites an existing file and never prints a value. The passwords only guard the portal's own
loopback Postgres (a rebuildable read model), and no human ever needs them.
Rotation: stop the stack, delete the three files AND the volume jobhunt-dashboard-pgdata, rerun this,
then `docker compose up -d` (the roles are created on first start of an empty volume).
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

d = Path(__file__).resolve().parent.parent / "secrets"
d.mkdir(exist_ok=True)
files = {n: d / f"{n}.env" for n in ("db", "sync", "app")}
existing = [p.name for p in files.values() if p.exists()]
if existing:
    sys.exit(f"refusing: {', '.join(existing)} already exist in {d} (see the docstring to rotate)")

admin, sync, app = (secrets.token_urlsafe(32) for _ in range(3))
files["db"].write_text(
    f"POSTGRES_PASSWORD={admin}\nJOBHUNT_SYNC_PASSWORD={sync}\nJOBHUNT_APP_PASSWORD={app}\n", encoding="utf-8")
files["sync"].write_text(f"JOBHUNT_DB_PASSWORD={sync}\n", encoding="utf-8")
files["app"].write_text(f"JOBHUNT_DB_PASSWORD={app}\n", encoding="utf-8")
print("created:", ", ".join(str(p) for p in files.values()))
