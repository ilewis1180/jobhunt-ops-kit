-- Optional: the approval table the scheduler-host pipeline (run_discovery.py / run_export.py) uses.
-- Status, decided_at and decided_by are written by whatever records the approve/deny click; this package only
-- inserts pending rows and stamps exported_at.
CREATE TABLE IF NOT EXISTS job_approvals (
  job_key      text PRIMARY KEY,
  title        text NOT NULL,
  company      text NOT NULL,
  location     text,
  grade        text NOT NULL,
  source       text NOT NULL,
  url          text,
  status       text NOT NULL DEFAULT 'pending',   -- pending | approved | denied
  decided_at   timestamptz,
  decided_by   text,
  exported_at  timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now()
);
