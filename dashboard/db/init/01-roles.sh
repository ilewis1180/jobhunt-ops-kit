#!/bin/sh
# Runs once, on the first start of an empty data volume (postgres entrypoint).
# jobhunt_sync owns schema "portal" and rebuilds it. jobhunt_app can only read it.
# Passwords come from secrets/db.env; nothing is echoed.
set -eu

: "${JOBHUNT_SYNC_PASSWORD:?missing in secrets/db.env}"
: "${JOBHUNT_APP_PASSWORD:?missing in secrets/db.env}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v sync_pw="$JOBHUNT_SYNC_PASSWORD" -v app_pw="$JOBHUNT_APP_PASSWORD" <<'SQL'
CREATE ROLE jobhunt_sync LOGIN PASSWORD :'sync_pw';
CREATE ROLE jobhunt_app  LOGIN PASSWORD :'app_pw';

REVOKE ALL ON DATABASE jobhunt FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE jobhunt TO jobhunt_sync, jobhunt_app;

CREATE SCHEMA portal AUTHORIZATION jobhunt_sync;
GRANT USAGE ON SCHEMA portal TO jobhunt_app;
ALTER DEFAULT PRIVILEGES FOR ROLE jobhunt_sync IN SCHEMA portal GRANT SELECT ON TABLES TO jobhunt_app;

-- Belt and braces: the app role is read-only even if a grant is added by mistake later.
ALTER ROLE jobhunt_app SET default_transaction_read_only = on;
ALTER ROLE jobhunt_app SET search_path = portal;
ALTER ROLE jobhunt_sync SET search_path = portal;
SQL
