-- Dashboard read model. Applied by the sync worker (role jobhunt_sync, schema owner) at start.
-- Everything here is rebuilt from the mirrored ops files on each sync; nothing is authored here.
-- The portal connects as jobhunt_app, which can only SELECT (see db/init/01-roles.sh).

-- Schema "portal" itself is created by db/init/01-roles.sh (owner jobhunt_sync). Postgres checks the
-- database-level CREATE privilege even for CREATE SCHEMA IF NOT EXISTS, and jobhunt_sync lacks it on purpose.
SET search_path = portal;

CREATE TABLE IF NOT EXISTS sync_runs (
    id           bigserial PRIMARY KEY,
    started_at   timestamptz NOT NULL,
    finished_at  timestamptz,
    ok           boolean,
    skipped      boolean NOT NULL DEFAULT false,  -- true when no source file changed
    fingerprint  text,
    counts       jsonb,
    warnings     jsonb,
    error        text
);

-- LinkedIn scrape rows (Runs/*/scrape-*.csv, prebuild-*.csv). Latest run wins per job.
CREATE TABLE IF NOT EXISTS jobs (
    job_id           text PRIMARY KEY,
    company          text,
    title            text,
    location         text,
    work_mode        text,
    employment_type  text,
    posted_date      text,
    easy_apply       text,
    status_raw       text,
    tracker_stage    text,
    linkedin_url     text,
    apply_url        text,
    apply_domain     text,
    ats_guess        text,
    salary_raw       text,
    first_seen_run   text,
    last_seen_run    text,
    source_file      text
);

-- Full job descriptions (Runs/*/jd-*.csv). The longest text per job wins.
CREATE TABLE IF NOT EXISTS jds (
    job_id         text PRIMARY KEY,
    company        text,
    title          text,
    captured_date  text,
    source_url     text,
    chars          integer,
    full_text      text,
    source_file    text
);

-- Orchestrator dispatch boards (Runs/*/dispatch-*/board.csv). Latest board wins per job.
CREATE TABLE IF NOT EXISTS board (
    job_id      text PRIMARY KEY,
    run_id      text,
    lane        text,
    company     text,
    role        text,
    ats         text,
    ats_label   text,
    tenant_key  text,
    login       text,
    state       text,
    card        text,
    resume      text,
    apply_url   text,
    source_file text
);

-- One row per apply attempt (AppApply-Capture/outcomes.csv), plus start-step fields from its trace.
CREATE TABLE IF NOT EXISTS attempts (
    run_id               text NOT NULL,
    attempt_id           text NOT NULL,
    job_id               text,
    company              text,
    ats                  text,
    tenant               text,
    outcome              text,
    confirmation_method  text,
    started_at           timestamptz,
    ended_at             timestamptz,
    duration_s           numeric,
    pages                integer,
    fields               integer,
    required_fields      integer,
    human_interventions  text,
    halt_reason          text,
    trace_file           text,
    card                 text,
    resume               text,
    browser              text,
    PRIMARY KEY (run_id, attempt_id)
);

-- Trace steps (AppApply-Capture/traces/**/*.jsonl). Values are the trace's own value_safe /
-- value_ref only; the portal never reads the private answers file.
CREATE TABLE IF NOT EXISTS trace_steps (
    run_id         text NOT NULL,
    attempt_id     text NOT NULL,
    step           integer NOT NULL,
    ts             text,
    action         text,
    page           text,
    target_name    text,
    answer_key     text,
    answer_source  text,
    value_safe     text,
    value_ref      text,
    result         text,
    human          text,
    verify_ok      boolean,
    note           text,
    PRIMARY KEY (run_id, attempt_id, step)
);

CREATE TABLE IF NOT EXISTS questions (
    question_id        text PRIMARY KEY,
    label_normalized   text,
    times_seen         integer,
    seen_on_live_form  text,
    answer_key         text,
    answer_sources     text,
    ats_list           text,
    example_labels     text
);

-- 04-ACCOUNT-LEDGER.md "Tenants" table. Sign-in state only; the Notes column is not stored.
CREATE TABLE IF NOT EXISTS tenants (
    tenant_key  text PRIMARY KEY,
    match_on    text,
    ats         text,
    state       text,
    since       text,
    waiting     text
);

CREATE TABLE IF NOT EXISTS resumes (
    file         text PRIMARY KEY,
    tract        text,
    size_bytes   bigint,
    modified_at  timestamptz,
    rel_path     text
);

CREATE TABLE IF NOT EXISTS bullets (
    id           serial PRIMARY KEY,
    ordinal      integer,
    section      text,
    subsection   text,
    role         text,
    text         text,
    source_file  text
);

-- Run docs (0*.md at the ops root) for the Library viewer.
CREATE TABLE IF NOT EXISTS docs (
    name         text PRIMARY KEY,
    title        text,
    rel_path     text,
    modified_at  timestamptz,
    size_bytes   bigint
);

-- Per-run files (PREP cards, INTENT, RUN-SUMMARY, LEARNINGS, paused-/skipped- notes).
CREATE TABLE IF NOT EXISTS run_files (
    rel_path     text PRIMARY KEY,
    kind         text,
    run_id       text,
    job_id       text,
    run_date     text,
    modified_at  timestamptz
);

-- Rows of the Google Sheets (Queue, Raw, JD Archive), stored generically as JSON by row key;
-- columns that look like credentials are dropped.
CREATE TABLE IF NOT EXISTS sheet_rows (
    sheet        text NOT NULL,
    row_key      text NOT NULL,
    data         jsonb NOT NULL,
    source_file  text,
    PRIMARY KEY (sheet, row_key)
);

-- Token use per session (Runs/<date>/USAGE-<RunID>.csv, written by the orchestrator at each checkpoint).
CREATE TABLE IF NOT EXISTS token_usage (
    run_id                 text NOT NULL,
    run_date               text,
    phase                  text,
    session                text NOT NULL,
    session_run_id         text,
    model                  text,
    started_at             timestamptz,
    updated_at             timestamptz,
    input_tokens           bigint,
    output_tokens          bigint,
    cache_creation_tokens  bigint,
    cache_read_tokens      bigint,
    jobs_attempted         integer,
    jobs_submitted         integer,
    weekly_pct_start       numeric,
    weekly_pct_now         numeric,
    weekly_resets_at       timestamptz,
    source_file            text,
    PRIMARY KEY (run_id, session)
);
