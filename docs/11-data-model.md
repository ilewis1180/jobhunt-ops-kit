# 11 — Data model: every sheet tab, CSV and vocabulary

The contract between the tools, the playbooks and the dashboard. Synthetic examples of each file are in `examples/`.

## Sheets

**Job Queue → Raw** (append-only, 27 columns, 05 Step C header). Several rows per job over time; the newest wins.

**Job Queue → Queue** (one row per job): A `Job ID` (formula) · B `Status` · C `Last touched` · D `ATS` · E `Tenant
key` · F `Open questions (agent)` · G `Applicant's answers` · H `Findings file` · I `Chat approval record` · J `Apply?`
· K `Priority` · L `Company` · M `Job Title` · N `Location` · O `Work Mode` · P `Easy Apply` · Q `LinkedIn Job URL` ·
R `Real Apply URL` · S `Apply Domain` · T `ATS Guess` · U `Company Careers URL` · V `Salary Raw` · W `Posting Type` ·
X `Posted Date` · Y `Flags` · Z `Tracker Stage` · AA `Snapshot Date`. Tools write only B–F, H, I (01 §1.4).

**JD Archive** (append-only, 10 columns, 06): `LinkedIn Job ID, Company, Job Title, Source, Complete?, Captured Date,
Source URL, Characters, Notes, Full Job Description`.

## Job ids and keys

`\d{8,}` (LinkedIn posting number) or `JT-[0-9a-f]{10}` (jobs found by the search tools with no LinkedIn number; SHA-1
of normalised `company|title|location`, first 10 hex; `common.job_tools_key`). `jt-keys.csv`:
`jt_key,board,board_id,company,title,first_seen_run` maps a JT- key to the board's own id so the same job found twice
is caught. Attempt id: `<job_id>-a<N>`. Run id: `R<YYYYMMDD>-<HHMM>-<kind>`.

## Capture CSVs (`AppApply-Capture/`)

**outcomes.csv** and **outcomes-jt.csv** (17 columns; one row per attempt):
`run_id, attempt_id, job_id, company, ats, tenant, outcome, confirmation_method, started_at, ended_at, duration_s,
pages, fields, required_fields, human_interventions, halt_reason, trace_file`
- `outcome`: `submitted` · `unconfirmed` · `paused` · `skipped` · `closed` · `released`.
- `confirmation_method`: `redirect_confirmation`, `modal`, `job_page_status`, `in_flow_text`, joined with `+`.
- `human_interventions`: `approval`, `login`, `code`, `needs_user`, `submit_handoff`, `user_submit`, joined with `+`.
- `ats`: the family name from `dispatch.py` (`greenhouse`, `workday`, `linkedin_easy_apply`, …).
- `trace_file`: `traces/<RunID>/TRACE-<job_id>-a<N>.jsonl`, or blank.
- Times are UTC ISO (`Z`); `run_id` is the lane's own run id.

**question-bank-observations.csv** and **-jt.csv** (14 columns; one row per question seen):
`question_id, label_normalized, label_verbatim, answer_key, answer_planned, answer_source, control, required, selector,
ats, company, job_id, origin, file`
- `question_id`: first 10 hex of SHA-1 of `label_normalized`.
- `answer_key`: `identity.email`, `address.zip`, `work_auth.sponsorship`, `eeo.gender`, `screening.how_heard`,
  `comp.expectation`, `availability.start_date`, `documents.resume`, `education.degree`, `consent.terms`, … or
  `freeform.<slug>` (the MAP in `build-question-bank.py`).
- `answer_planned`: only a non-personal choice answer (`Yes`, `No`, `Decline…`, `Company Website`, `Negotiable`), else blank.
- `answer_source`: `standing_answers` · `resume` · `rule_playbook` · `user_answer` · `best_effort` · `needs_user` · `other`.
- `origin`: `prep-card` · `findings` · `lane` · `live-form`.

**question-bank.csv** (8 columns; rebuilt): `question_id, label_normalized, times_seen, seen_on_live_form, answer_key,
answer_sources, ats_list, example_labels`.

**timeline.csv** (16 columns; rebuilt by `mail_track.py timeline`, one row per submitted job):
`job_id, company, title, apply_at, apply_src, confirmation_at, rejection_at, interview_at, last_mail_at, thread_count,
match_methods, match_confidence, state, followup_due, mail_export_at, action_type`
- `apply_src`: `outcomes.csv` or `Queue last-touched`. `state`: `applied` · `confirmed` · `interview` · `rejected`
  (first match wins in the order rejected → interview → confirmed → applied, so the states are exclusive).
- `match_methods`: `a:company-field`, `b:subject-or-sender`, `c:body-text`, with `+title` when the title broke a tie;
  `match_confidence`: `high` · `medium` · `low` · blank.
- `followup_due` is set only when a mail needs the applicant (`action_type`: `assessment`, `more_info`, `reply`,
  `interview`, `offer`) and nothing newer cleared it; silence is never a follow-up.

**timeline-review.csv** (7): `thread_id, mail_status, sender_domain, first_received, guessed_job_id, why, subject`.
**followups.csv** (5, the operator's; never rewritten by a tool): `job_id, followed_up_at, followup_days, snooze_until, note`.

## Mail export (input to `mail_track.py`, written by your own mail exporter)

`<mail_export_dir>/job-threads.csv`: `thread_id, company, status, first_received_at, last_received_at, last_subject,
last_from, last_body, sender_domain` with `status` ∈ `received` (confirmation receipt) · `rejected` · `interview` ·
`assessment` · `more_info` · `recruiter` · `offer` · `alert` (job alerts, skipped). Bodies stay in that file; the tools
write only company, status, dates and thread ids. `<mail_export_dir>/export-status.json`: `{"exported_at":
"YYYY-MM-DDTHH:MM:SSZ"}`; an export older than 2 hours is reported STALE.

## Token usage feed (`Runs/<date>/USAGE-<OrchRunID>.csv`, 16 columns; `usage_report.py`)

`run_id, phase, session, session_run_id, model, started_at, updated_at, input_tokens, output_tokens,
cache_creation_tokens, cache_read_tokens, jobs_attempted, jobs_submitted, weekly_pct_start, weekly_pct_now,
weekly_resets_at`. One row per session of the run (`orch`, `lane<N>-<HHMM>`); rewritten atomically at checkpoints.

**Token audit** (`token_audit.py`): `TOKEN-AUDIT-sessions-*.csv` (one row per transcript: phase, run id guess, turns,
tool calls, screenshots, the four token counts, a scrubbed first line), `-by-phase`, `-by-run`, `-by-tool`.

## Dispatch board (`Runs/<date>/dispatch-<OrchRunID>/`, write-once; 09 §3)

`board.csv` (20 columns): `order, lane, job_id, company, role, ats, ats_label, tenant, tenant_key, lock, ea, login,
priority, queue_row, state, card, card_run, resume, apply_url, jd`. `meta.json`: run, created, lanes, ea_lane,
ea_cap, queue_export. `claims/<job_id>/claim.json`, `locks/<lock>/holder.json`, `events/lane<N>.jsonl`,
`events/orch.jsonl` (append-only JSON lines: `ts`, `ct`, `lane`, `run`, `job`, `claim_id`, `kind`, `attempt`, plus
`findings`, `approval`, `status`, `f`, `note`). Event kinds: `register`, `retire`, `window_ok`, `window_hidden`,
`claimed`, `awaiting_yes`, `awaiting_login`, `awaiting_code`, `needs_user`, `awaiting_submit`, `approved`, `filling`,
`intent`, `submit_clicked`, `retract`, `submitted`, `unconfirmed`, `paused`, `skipped`, `closed`, `released`,
`external`; orchestrator kinds `open`, `hold`, `drop`, `reviewed`, `login`, `preapprove`, `full`, `external`,
`confirm`, `decisions`, `queue_check`.

**preflight-<RunID>.csv** (9): `job_id, company, ats, status, final_host, http_status, questions_count,
required_count, note`, `status` ∈ `ok` · `closed` · `login-wall` · `unknown` · `error` · `skipped`; plus a `.jsonl`
with each Greenhouse card's question list.

## Vocabulary notes for anyone who kept the private repo's data

The public kit renames three tokens that carried the applicant's name: `needs_manny` → `needs_user`,
`manny_submit` → `user_submit`, `manny_answer` → `user_answer`; and two that named private file numbers:
`standing_02` → `standing_answers`, `rule_07` → `rule_playbook`. A dashboard reading older CSVs should accept both.
