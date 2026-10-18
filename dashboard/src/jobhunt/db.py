"""Connection settings. Each container gets only its own role's password (secrets/<service>.env)."""
from __future__ import annotations

import os

from psycopg.conninfo import make_conninfo


def dsn() -> str:
    return make_conninfo(
        host=os.environ.get("JOBHUNT_DB_HOST", "db"),
        port=os.environ.get("JOBHUNT_DB_PORT", "5432"),
        dbname=os.environ.get("JOBHUNT_DB_NAME", "jobhunt"),
        user=os.environ["JOBHUNT_DB_USER"],
        password=os.environ["JOBHUNT_DB_PASSWORD"],
        application_name=os.environ.get("JOBHUNT_APP_NAME", "web-jobhunt"),
        connect_timeout=5,
    )
