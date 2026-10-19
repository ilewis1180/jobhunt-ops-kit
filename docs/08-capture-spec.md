# 08 — Capture spec: turning each application into automation training data

Applies to every Phase 3 attempt. **No personal data.** Read alongside 01 §4.

**Why:** every application done by hand should leave behind what a browser-automation engine needs to do the next one
alone: *where* each control is (locators), *what* goes in it (an answer key, never the value), *how* each page and
ATS behaves (recipes), and *how it ended* (outcome labels).

Everything lives in `AppApply-Capture/` under the data root. **In a parallel run (09 §6)** a lane never appends to
`outcomes.csv` or `question-bank-observations.csv`: it writes `OUTCOME-<JobID>-a<N>-<RunID>.csv` and
`QB-<JobID>-a<N>-<RunID>.csv` (header + rows) to `staging/`, and the orchestrator merges them with
`import-inbox.py --from AppApply-Capture/staging`.

| Path | What | Written |
|---|---|---|
| `traces/<RunID>/TRACE-<JobID>-a<N>.jsonl` | One JSON line per browser action, appended as it happens with `trace.py` (§2) | during each attempt |
| `pages/<RunID>/PAGE-<JobID>-a<N>-p<page>.json` | Compact PAGE json (§3.1): the fields of one form page with locators and answer keys | once per form page |
| `dom/<ats>/<page-slug>-<JobID>.html` | Value-stripped HTML snapshot (automation test fixture). Not written by lanes (tool output limits); the first 2 per ATS × page type, made outside Phase 3 | outside Phase 3 |
| `proof/<RunID>/<JobID>-a<N>-review.png`, `-text<K>.png`, `-confirm.png` | Screenshots for the operator's own check (§1.1) | before and after Submit |
| `question-bank-observations.csv` (+ `-jt.csv`) | One row per question seen (label, answer key, source, control, locator, ATS) | merged at session end |
| `question-bank.csv` | Aggregated unique questions, rebuilt from observations by `build-question-bank.py` | rebuilt at session end |
| `recipes/<ats>.yaml` + `recipes/00-INDEX.md` | Per-ATS automation recipe (entry, pages, locators, widgets, confirmation) | proposals in LEARNINGS; curated |
| `outcomes.csv` (+ `-jt.csv`) | One row per attempt (17 columns, 11 §Outcomes) | at each attempt's end |
| `timeline.csv`, `timeline-review.csv`, `followups.csv` | Mail-matched application timeline (`mail_track.py`, 11) | rebuilt by the tool; `followups.csv` is the operator's |

## §1 Redaction (non-negotiable)

- **Never write a personal value** (name, e-mail, phone, street, ZIP, dates of birth) or any credential into a capture
  file. Write **answer keys** instead: `identity.email`, `address.street`, `work_auth.sponsorship`, `eeo.gender`
  (vocabulary: `build-question-bank.py` MAP and `question-bank.csv`).
- Plain choice answers that are not personal (`Yes`, `No`, `Decline to self-identify`, `Company Website`,
  `Negotiable`) may be written as `value_safe`.
- Free text (cover letters, "why this role") → `value_ref: "card:<PREP file>#drafted-text"`, never the text.
- URLs: origin + path only; drop query strings. `trace.py` drops them from a trace line's `url`.
- The page-capture script never returns field values (only `value_present`) and strips values from any HTML snapshot;
  it masks URLs, paths, query strings, cookies, e-mails, phone numbers and base64-looking text in everything it returns.
- **The check is `ops/tools/pii_scan.py`.** It uses the same private patterns `import-inbox.py` blocks on, prints
  `file:line: <pattern name>` and never the matched value, and exits 1 on any hit. `--attempt <RunID> <JobID>-a<N>`
  scans everything one attempt wrote; `--canary` prints a harmless token that proves the scan fires.

### §1.1 Proof screenshots are exempt from §1

Proof is for the operator to check what was submitted, so personal values and free text may appear in it.
- Path: `AppApply-Capture/proof/<RunID>/<JobID>-a<N>-review.png`, `…-text<K>.png` (one per free-text field, after
  entry and before Submit, whole field visible) and `…-confirm.png`.
- Never run `pii_scan.py` on `proof/` (`--attempt` skips it; never pass the folder or a parent to it).
- **Never** use proof images as training data or fixtures, never copy them into `dom/`, `pages/`, `recipes/` or a
  trace. Never put a credential on screen for a proof image.
- A dashboard may show proof in the audit trail (mirrored read-only).
- **Proof is mandatory:** `dispatch.py event … submitted` refuses without `--proof <one of these files>` for this
  attempt, and refuses when no OUTCOME fragment is staged afterwards. Capture is never optional.

## §2 The trace line (JSONL, one object per action)

Append each line with `trace.py`. It sets `ts` (UTC), `run_id`, `attempt_id`, `job_id` and `step` (0 for `start`,
then +1), drops a `url`'s query string, and **refuses any line `pii_scan` would flag** (exit 2, nothing written).

```sh
python3 ops/tools/trace.py R20260924-0900-apply1 4466598786-a1 type --page 1 --json '{"target":{"label":"Email*","css":"#email","frame":"top"},"answer_key":"identity.email","answer_source":"standing_answers","value_ref":"answers.identity.email","result":"ok"}'
```

```json
{"ts":"2026-09-24T14:03:11.412Z","run_id":"R20260924-0900-apply1","attempt_id":"4466598786-a1",
 "job_id":"4466598786","ats":"greenhouse","tenant":"job-boards.greenhouse.io/example-co",
 "step":7,"page":1,"page_marker":"Apply for this job","url":"https://job-boards.greenhouse.io/example-co/jobs/6193828004",
 "action":"type","target":{"role":"textbox","name":"Email","label":"Email*","id":"email","name_attr":null,
 "data":{},"css":"#email","frame":"top"},
 "question_id":"a1b2c3d4e5","answer_key":"identity.email","answer_source":"standing_answers",
 "value_safe":null,"value_ref":"answers.identity.email",
 "verify":{"how":"re-read after blur","ok":true},"result":"ok","retries":0,"duration_ms":820,
 "human":null,"note":null}
```

- `action`: `start` · `navigate` · `read` · `click` · `type` · `select` · `check` · `upload` · `wait` · `next` ·
  `approval` · `intent` · `submit` · `confirm` · `halt` · `end` (the only values `trace.py` accepts).
- `target`: the locator candidates from the matching page-capture field record (role/name, label, id, name attribute,
  data attributes, css, frame). `frame` is `top`, `shadow:<host-tag>` or `iframe:<n>`. Record what actually worked in
  `note` when a fallback was needed.
- `answer_source`: `standing_answers` · `resume` · `rule_playbook` · `user_answer` · `best_effort` · `other`.
- `human`: `null` · `login` · `code` · `captcha` · `approval` · `needs_user`.
- `result`: `ok` · `retry` · `error` · `skipped`; error text in `note`.
- First line: `{"action":"start",…,"card":"PREP-….md","resume":"<the file that job used>"}`. Last line:
  `{"action":"end","outcome":"submitted|unconfirmed|paused|skipped|closed","confirmation":{…},"halt_reason":…}`.

## §3 When to capture (per page)

1. On arriving at each form page (after any login): run the page-capture script; read its summary and chunks and write
   the **compact PAGE json** (§3.1). Start request tracking on the tab with a URL pattern for the form's host.
2. As each field is filled: append its trace line.
3. Before Next or Submit: run the capture again as the 01 §4 step 7 sweep. Its summary has `missing` (required with
   no value) and `inv` (invalid). Append a `read` line with the counts.
4. After Submit: append `submit` and `confirm` lines. Submit stays its own tool call. The very next call reads the
   network requests for the same pattern and records, in the `confirm` line: method, host + path, status, and (if
   visible) **payload field names only**. Not visible → `"network": "not observable"`; never retry.
5. **PII gate before any terminal event:** `pii_scan.py --attempt <RunID> <JobID>-a<N>`. On a hit, replace the value
   with an answer key or `value_ref`, scan again. `dispatch.py event` runs the same scan as a backstop.
6. At the attempt's end: the `end` line, the OUTCOME fragment, the QB fragment (`origin = lane`, with `control`,
   `required` and `selector` filled), the proof files.

### §3.1 Compact PAGE json

One object per field of the page, plus the lane's `answer_key`. Never a value. `options` only for choice questions;
for long lists write `"options_count"`. Take `url` from the card or the navigate result (origin + path).

```json
{"capture":"capture v1","captured_at":"2026-09-24T14:03:05.000Z","run_id":"R20260924-0900-apply1",
 "attempt_id":"4466598786-a1","page":1,"heading":"Apply for this job","page_marker":"Step 1 of 3","sig":"5ce85a",
 "scope":"page","url":"https://job-boards.greenhouse.io/example-co/jobs/6193828004","captcha":"none",
 "counts":{"fields":15,"required":8,"missing":8,"shadow":0,"iframes":0},
 "fields":[{"k":1,"label":"Email*","control":"email","req":"star","id":"email","name":"email","css":"#email",
   "frame":"top","answer_key":"identity.email"},
  {"k":4,"label":"Will you require sponsorship?","control":"radio","req":"aria","name":"question_123",
   "css":"input[type=\"radio\"][name=\"question_123\"]","frame":"top","options":["Yes","No"],
   "answer_key":"work_auth.sponsorship"}],
 "buttons":[{"text":"Submit application","css":"#submit_app","frame":"top"}]}
```

- `req` says how the page marks the field required: `attr` · `aria` · `star` · `class` · `after` (CSS `::after "*"`).
  Omit it when optional.
- `control`: `text`, `email`, `select`, `radio`, `checkbox-group`, `yesno` (button pair), `button+listbox` (Workday
  dropdown), `text+combobox`, `file`, and so on.
- `sig` (a hash of labels and controls) with `heading` + `page_marker` identifies the page without a URL.

## §4 Mapping to the automation engine's model

| Engine field | From capture |
|---|---|
| `application.ats_platform` | trace `ats` |
| `application.outcome`, `submitted_at`, `confirmed_at`, `halt_reason` | trace `end` line / outcomes row |
| `application.resume_version_id` | trace `start.resume` |
| `steps[]` (`step_name`, `status`, `started_at`, `ended_at`, `duration_s`, `detail{}`) | trace lines grouped by `page` |
| `answer_audit[]` | one per filled field: `question_id`, `label`, `answer_key`, `answer_source`, `value_safe`/`value_ref`, `verify` |
| `artifacts[]` | PAGE json, DOM fixture, confirmation evidence |
| `needs_you[]` | trace lines with `human` set |
| `job.ats_platform`, `job.resolved_url` | Queue D and the form URL |

### §4.1 File names and `job_id` must survive the trip to Windows (non-negotiable)

The ops tree is mirrored to a dashboard host that may run Windows. Windows silently refuses any name containing `:` `"`
`*` `?` `<` `>` `|`, a control character, a trailing dot or space, or a reserved stem (`CON`, `PRN`, `AUX`, `NUL`,
`COM1`–`COM9`, `LPT1`–`LPT9`). **A file it refuses never arrives, and nothing reports an error.** Once, five OUTCOME
files whose `job_id` had two ISO timestamps glued into it (colons and all) were rejected for three days before anyone
noticed; the corruption was also inside the CSV (`job_id` held the timestamps, the time columns were empty).

Rules for any lane writing to `AppApply-Capture/staging/`:
1. `job_id` is **the Job ID and nothing else** (01 §1.2). `attempt_id` is `<job_id>-a<N>`; the run id belongs in
   `run_id`; the times belong in `started_at` / `ended_at`.
2. Staging names follow `OUTCOME-<job_id>-a<N>-<RunID>.csv` and `QB-<job_id>-a<N>-<RunID>.csv` exactly.
3. A timestamp in a name is compact (`20261007T172030Z`), never `isoformat()`.
4. **Write the file with a CSV writer**, never by joining strings: a field with a comma must be quoted (RFC 4180).
   `dispatch.py event … submitted|unconfirmed|external` parses a lane-written fragment and refuses the event when a row
   has the wrong number of columns.
5. `JT-` jobs go to the `-jt` files (`import-inbox.py` routes them) until the dashboard keys on them.

`import-inbox.py` enforces 1 and 2 at the boundary (`portability_problem()`, `bad_job_id()`): it blocks the file and
prints why.

## §5 Session end

Merge the fragments (`import-inbox.py --from AppApply-Capture/staging`), rebuild `question-bank.csv`
(`build-question-bank.py`), and list recipe corrections in `LEARNINGS-<RunID>.md` under "Recipe updates" (ATS · field
or page · what was observed · evidence trace line).
