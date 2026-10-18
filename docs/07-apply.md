# 07 — Phase 2 (prep) and Phase 3 (approve and submit)

**Why prep and submit are split:** an AI applier working in a browser needs the operator's "yes" in the chat itself
before it fills their details into a form, ticks a consent box, or clicks Submit. It asks about each application
separately: a lane may ask about up to 3 in one round, but each is its own question with its own answer (09 §5). A
file, or one up-front yes for many, does not count. So the work splits:

| Phase | Operator present? | What happens |
|---|---|---|
| 1 Scrape | no | `05-scrape.md`: Saved jobs → Raw → new Queue rows. |
| 2 Prep | no | Triage, read each posting, capture the JD, work out every answer and draft, write one PREP card per job. Nothing typed into any application. |
| 3 Approve and submit | **yes** | Always in parallel (09): an orchestrator (Block 3) plus up to 5 lanes (Block 4). For each card the operator says yes **in that lane's chat** → the lane fills, ticks the listed consents, submits. Logins and one-time codes happen live. Block 2 alone (`phase 3 single`) is the fallback. |

Paste one block (between its rules) as the first message of a new session, or type the routing word (00). A new
session per phase; one applying run at a time (a parallel Phase 3 is one run). A blank Apply? (J) counts as Yes.

## Shared answer rules (both blocks refer to these as "07 answer rules")

- **Sources, in order:** the answers file → the résumé that job gets (answers §Résumé names the file per role family)
  → earlier findings files in `Runs/` (answers already given to the same question) → the applicant's public profile.
- **Best honest light.** Every answer must be one the applicant can defend from those sources. Inside that limit, pick
  the most favourable one: years of experience count every résumé role where the skill was plausibly part of the job,
  rounded in the applicant's favour; "have you done X" is Yes when any résumé role reasonably covers X; ranges and
  dropdowns take the highest option the résumé supports.
- **Qualifications the applicant does not have** (a licence, certification, degree, clearance, a named product or
  industry the résumé does not show) → **No**. Never claim one.
- **Legal statements and attestations** → truthfully, from the answers file's attestation table.
- **"Willing to…"** → only what the answers file covers (background check, relocation, travel, on-call or weekend work,
  physical requirements, commission-only or contract roles). Anything else → Needs you.
- **Consent** (data processing, transfer, privacy, terms) → the answers file's standing answer; quote the wording on
  the card. SMS consent is its own answer.
- **Current or previous pay** → text field: `Negotiable`; optional numeric: blank; required numeric: the answers file's
  figure, else Needs you.
- **Demographics** → decline wherever the form allows; no decline option → the answers file's value, else Needs you.
- **Short free text** ("why this role", "additional info"): draft from the JD and the résumé, every claim sourced
  (below), under ~1,000 characters, plain, first person, no filler. **Required cover letter:** same, under ~1,500
  characters; optional → blank.
- **Needs you** (never invented): a fact in no source, a demographic with no decline option, a reference's details, a
  "willing to" outside the answers file.

## Free-text sources

- **Every claim in drafted text traces to a résumé line or an answers-file rule.** Numbers, tools, "led", "owned",
  industries come from the résumé the job gets, or they are not written.
- Below each draft on the card, `Sources:` (claim → résumé role or answers section). A claim with no source is
  **UNSUPPORTED**: it moves to Needs you with the plain version beside it, and is never shipped as drafted.
- A lane that finds an unsourced claim in a card says so in its `REVIEW:` list and does not type it.

## Live form and parser checks (Blocks 2 and 4, before INTENT and again before Submit)

1. **Read the live form before writing INTENT.** One page read per page, then compare to the card. Anything the card
   did not predict is a `REVIEW:` flag before any typing: an account or wizard, an extra page, a required free text, a
   numeric-only field (salary: never `Negotiable` there), a how-heard option that does not exist, a consent not in the
   answers file.
2. **After a résumé upload, autofill or saved-profile restore, check the work history first.** Compare every row to
   the résumé the job gets: employer, title, dates (current role has no end date), location and state, description.
   Correct ordinary rows in place and re-read them. **Work history = every role on the résumé** (the answers file §Work
   history lists any exception): delete all rows and retype when more than 3 are wrong. **When the form caps the rows**,
   merge by employer into contiguous-year rows: the highest title held in the span, the full dates, the latest location,
   one progression sentence and the strongest résumé bullets; never drop an employer. Always delete a row with no
   employer, a role not on the résumé, a skill tag that is not a skill.
3. **Re-read the other prefills** against the answers file at the same time: personal fields wiped by the parser,
   country or phone, school and years, veteran list, every pre-ticked consent. A consent that arrives ticked is set to
   the answers file's answer. Record the original and the fix in the INTENT ledger.
4. **On the Review page, read the work history again** and record `work history on Review/last page: verified` in the
   INTENT. A field left wrong on purpose is a `REVIEW:` flag before Submit, not a note after it.
5. Tenants whose parser damages history (Workday, Dayforce, Brassring, Avature, iCIMS, UltiPro, Lever): **upload the
   résumé first**, then do items 2 and 3.

## Where you are

State the environment after your Run ID. In a local coding agent: files live in the data root, outputs go to
`Runs/<date>/` and `AppApply-Capture/`, traces are appended as you go, the Queue is written through `queue_api.py`,
and the session ends with a commit. In a browser-only (cloud) session with a drive connector: read a published
read-only copy, write every output as a **new** file into an inbox folder with the Run ID in its name
(`TRACE-…-<RunID>.jsonl`, `OUTCOME-…-<RunID>.csv`, `QB-<RunID>.csv`), and tell the operator to run
`import-inbox.py` afterwards. The same in both: the sheets, the answer rules, 01's Queue rules, **submit authority =
the operator's yes in this chat, per application**, and never a personal value in a capture file.

---

## Block 1 — Prep (new session; runs unattended)

---

Prep mode (Phase 2). Work the Queue rows whose Apply? (J) is not `No`. I am away; do not wait for me.

**Type nothing into any application, tick no box, click no Submit.** This session reads postings and writes cards.

0. Where you are (table above).
1. No other applying session is running.
2. Session start: 00 steps 1, 3, 4, 5, 6 (Run ID `…-prep`; read 01, the answers file, 03, 04 and this file's answer
   rules; recovery pass; integrity check; LinkedIn check). Skip step 7: there are no submits. Pre-triage (01 §2), post
   the results.
3. For each Ready row, Priority 1 first, then each Paused-SignIn row (a card lets the operator apply as soon as they
   sign in):
   - Open the posting read-only. Capture the JD (06). An unrendered JD is `Complete: No (<reason>)`, never a pause.
     Never open aggregator redirect links.
   - Fit gap → `Paused-Question` with the question in F, **and still write the card**.
   - **Find the real ATS:** read the Apply control's `href` (never click Apply). For Greenhouse, Lever and Ashby take
     the question list and the JD from the public API (`ops/tools/preflight.py`).
   - If the form is visible without signing in, list every field with exactly whether it is required. Behind a login
     or a later page: say so, mark guessed fields **"expected, unverified"**.
   - Work out every answer from the 07 answer rules **and the current answers file**. Draft any free text and required
     cover letter now; every sentence traces to a résumé line. Time-based answers say "computed at fill time".
   - Flag hands-on steps the ATS is known for (03): references, photo, pay bands, CAPTCHA, account creation.
   - Write **`PREP-<Company>-<JobID>-<RunID>.md`** (write-once) in the card format below.
   - Queue: leave B as it is; write the card file name in H (01 §1.4).
   - A login wall at the posting → note the site on the card, add it to the login list; never try to get past it.
4. Keep going until every Ready row has a card or the session nears its limits.
5. Session end: `PREP-SUMMARY-<RunID>.md` with, in order: **Ready to approve** (one line per card: priority, company,
   role, Job ID, card file, best-effort count, logins needed) · **Logins needed in Phase 3**, by site · **Waiting on
   your answer** (every Paused-Question row with its question) · **Needs you** (every open question, by job). Then the
   JD Archive import (06) and `LEARNINGS-<RunID>.md`.

**PREP card format:**

```
# PREP — <Company> — <Role> — <JobID>
Apply URL: <Real Apply URL or Easy Apply> · ATS: <ATS> · Site: <tenant key> · Login needed: yes/no/signed in
Résumé: <file from answers §Résumé>
JD: jd-<JobID>-<RunID>.md
Pre-triage result: <ok | Duplicate | fit question>

## Planned answers
| # | Field / question (exact label) | Answer | Source (answers / résumé line / earlier findings / best-effort) |
(Personal values are written as references, e.g. `answers §Identity: mobile phone`, `{APPLICATION_EMAIL}`, never literally.)

## Best-effort answers  (anything not straight from the answers file, one line each: why)
## Drafted text  (word for word)
## Sources  (one line per claim in the drafted text: résumé role or answers section; none → UNSUPPORTED, move to Needs you)
## Consents it will tick  (exact wording)
## Needs you  (question — why — options)
## Not yet seen  (pages behind a login or later in the flow)
```

---

## Block 2 — Approve and submit, single session (fallback; operator present)

---

Apply mode (Phase 3, single). I am here. Work the PREP cards from the latest `PREP-SUMMARY-*.md`, in its order, plus
every Queue row now Ready or Paused-SignIn with a card in H. If a `PREP-DECISIONS-*.md` exists for that run, read it
first: where it and a card disagree, it wins.

0. Where you are. Read `08-capture-spec.md` and record the capture for every attempt.
1. No other applying session is running.
2. Session start: 00 in full (Run ID `…-apply`). Submit approval is given **per job** below, not in advance.
3. **Logins first:** post the login list grouped by site. I sign in and say `done` (or `skip <site>`). One-time codes:
   tell me when one is on screen.
4. **For each card, a short approval request:** company · role · Job ID · card link; the best-effort answers, the
   drafted text and the consents in full; the Needs-you questions with options; ending with **"Reply yes to fill, tick
   the consents listed, and submit — or give changes."** I reply `yes`, `yes, with <changes>`, or `skip`. Post the next
   card while one is being filled, but act only on a card I said yes to.
5. **After yes:** the live-form and parser checks, then fill per the card and 01 §4. Anything the live form asks that
   is not on the card → stop and show me before submitting. Otherwise: pre-submit gate → INTENT → one Submit, **its own
   tool call, never inside a batch** → confirm (03) → findings → Queue write with my reply, word for word, in column I.
6. Session end: 00 session end. At the top of the RUN-SUMMARY: Submitted (company, role, Job ID, how confirmed) ·
   best-effort answers that went out, by job · still waiting on me · proposed additions to the answers file
   (best-effort answers that came up twice or more).

---

## Block 3 — Parallel Phase 3: orchestrator (new session; operator present)

---

Phase 3 orchestrator (`09-parallel-apply.md`). I am here. Follow 09 §2 (machine setup), §4 (pre-run checklist and
orchestrator), §7 and §8 exactly. Run ID `…-orch`.

You never fill a form, tick a consent, click Submit, or pass a "yes" to a lane. My approvals happen in each lane's own
chat. You own: the recovery pass; the dispatch board (`dispatch.py`) and preflight (`preflight.py`); the decision
sweep (`dispatch.py needs` first, prior rulings shown, single-select rounds of up to 4: "Apply as carded · Skip · Ask
me in the lane" per card → `PREP-DECISIONS-<RunID>.md`, then `preapprove` / `open` / `drop`; packets compact by
default, `full <ids>` only if I ask); the mail timeline at start and end (`mail_track.py timeline`, read-only, never a
stop); the login list; the machine setup check (09 §2); the "needs you" board with phone pushes from `dispatch.py
watch`; every Job Queue write plus a checkpoint commit every ~5 finished cards; the capture merge; the JD Archive
append; git.

When the board is ready, the logins are done and `lane-windows.sh` shows AC power and display sleep prevented, start
the lanes **one at a time through the window gate** (09 §4 step 9). You never tile, move or resize windows: I move
them. At most 3 lanes on a laptop screen. When I step away or stop, tell the lanes.

---

## Block 4 — Parallel Phase 3: apply lane N (new session; operator present)

---

Phase 3 lane <N> (`09-parallel-apply.md`). I am here. Answer literally from the card, the decisions file and the
answers file; on any doubt ask me (`needs_user`) instead of guessing. Run ID `…-apply<N>`. Follow 09 §4 lane steps
1–10 exactly, then §5–6: title this session "Phase 3 lane <N> — <OrchRunID>", pass `--run <OrchRunID>` to every
`dispatch.py` call, use the dedicated browser profile by deviceId, prove your own window (tab alone, visible,
`lane-windows.sh` agrees → `dispatch.py window <N> ok`; never wait for a message about it), work only in its front tab.
Then, in rounds:
1. `claim <N> --ahead 3`.
2. Prepare each card read-only, diffing it against the live form, the card and the current answers file, and
   checking drafted text against the résumé. Easy Apply cards: run the 03 preflight first. Read the live form once;
   anything the card did not predict goes in `REVIEW:`.
3. Cards the brief marks `preapproved` or `prior_approval`: if your three-way diff finds nothing changed, post
   `approved` from that ruling, report the packet here, and fill. Otherwise ask me in **this** chat: one
   multiple-choice call with **one question per card** (Yes, as carded / Yes, with change / Skip), flags-first packet
   (09 §5.3). Post each answer as it arrives: `event … approved --approval "<my exact reply>"`, or `skipped` / `released`.
4. For each approved card: fill → parser checks after any upload or autofill → gate → `intent_check.py` → INTENT (**no
   INTENT, no Submit click, and no handing me a captcha, password or Submit step before it exists**) → fresh `window
   <N> ok` → proof captured (Review page and every free-text answer) → Submit as its own call, **seen by you** → confirm
   → findings → capture fragments to `staging/` → `event`.

While I am away, prepare only (`--hands-free`). Never write the Queue or commit. Only my answer to a card's own
question in this chat approves that card. Wrap up per 09 §5 after ~5 applications or when context is tight.

---
