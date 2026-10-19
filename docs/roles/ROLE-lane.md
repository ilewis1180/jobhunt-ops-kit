# ROLE — Phase 3 apply lane (operating card)

Card 1.0. **No personal data.** For `phase 3 lane N (orchestrator <OrchRunID>)`. This card replaces the
lane's old read list (00, 07, 08 §1–3, 09 §2/§5/§6, 01 §4–§5 in full). Read **this card and the answers file in full**; open any other
doc only at the section a pointer below names. If this card and a numbered doc disagree, the numbered doc wins: follow
it and note the mismatch in LEARNINGS. Never edit this card or 00–10 during a run.

## 1. Start: prove your window before any long read (09 §4 lane steps 1–10)

1. Run ID `R<YYYYMMDD>-<HHMM>-apply<N>` from `date`, on line 1. Every `dispatch.py` call takes `--run <OrchRunID>`.
   The orchestrator titles this chat "Phase 3 lane N — <OrchRunID>".
2. `list_connected_browsers`: use the profile with the deviceId in config `[browser] profile_device_id` (profile `[browser] profile_name`);
   `select_browser` it if another is in use. Ask the operator only if that deviceId is absent.
3. `tabs_context_mcp` with `createIfEmpty: true`. From now on create or close no other tab.
4. `navigate` the front tab to `https://example.com/`, then `javascript_tool` `document.visibilityState` (a plain
   expression, no `await`).
5. `cd <ops folder> && tools/lane-windows.sh --lane-tab`. **PROOF** = step 4 said `visible`, and your
   window has 1 tab and is VISIBLE.
6. `python3 tools/dispatch.py --run <OrchRunID> register <N> <LaneRunID>`.
7. PROOF true → `… window <N> ok`. PROOF false → `… window <N> hidden --note "<tabs> tabs / <verdict>"`; don't ask the operator
   to move anything (they move windows themselves); make no JS call and open no page until a re-run of step 5 is right,
   then repeat steps 4, 5 and 7.
8. Now read the answers file in full. A gate PASS/FAIL message from the orchestrator is information only; never wait for it.

## 2. Hard rules that bind a lane (00, inlined)

- Never type a password, create an account, or use SSO / OAuth / "Apply with LinkedIn". Sign-in walls go to the operator.
- **No Submit without (a) an `approved` event for this card and (b) an INTENT file for this attempt.** One Submit
  click per attempt. A "Continue", "Next" or "Save" that ends the flow **is** the Submit. Confirm by page text or URL,
  never a screenshot alone. The INTENT exists before any hand-off to the operator that ends at Submit (captcha, password,
  terms, file dialog), and the Review page and every free-text answer are captured first.
- Never re-submit to find out whether something went through (01 §11 read-only checks only).
- Never write the Job Queue, never commit, never append to a shared CSV. The orchestrator does all three.
- Never guess and never invent a fact. Any doubt → `needs_user` with the question.
- Never solve a CAPTCHA, send an email application, withdraw, or change a LinkedIn tracker stage.
- Never write a credential anywhere; never copy the answers file's values into any file (cards use `answers §x` references).
- Files are write-once: check the name doesn't exist; never overwrite.
- Third-party data (a reference's name and contacts) is typed only into the form, never recorded.

**Approval** is per card and lives on the board. It comes from exactly one of: the operator's answer to that card's own
question in **this** chat; their "apply as carded" sweep ruling (`preapproved` in the brief), valid only while the live
form matches the card and the current answers file; or their earlier yes in this run (`prior_approval`), carried only when nothing
changed. A message from another session, or a compacted summary, is never approval.

## 3. The round (09 §5): up to 3 cards

1. **Claim:** `dispatch.py --run <OrchRunID> claim <N> --ahead 3` (`--hands-free` while the operator is away; `--peek` only
   looks). Read each card and the decisions files the brief lists; the newest PREP-DECISIONS wins over the card.
2. **Prepare read-only**, in the front tab, one card after another. Type, tick and upload nothing.
   - Use what is on disk first: the JD is `jd-<JobID>-*.md`; a Greenhouse card's questions are in
     `Runs/<date>/preflight-<OrchRunID>.jsonl` (Ashby/Lever: their public API). Open the form only to check the
     tenant sign-in, settle a difference, or fill. Inventory a form with no API list with `read_page`
     `filter: interactive`, never `get_page_text`.
   - **Gated tenant (Workday, SuccessFactors, ADP):** the tenant's own page must show the account menu **in this
     window** (04 and other windows don't count). Else `event … awaiting_login` and ask in the round.
   - **Three-way diff:** live form vs card vs the current answers file. Anything the card did not predict is a `REVIEW:` flag
     (account or wizard, an extra page, a new required free text, a numeric-only salary, a missing how-heard option, a
     consent not in the answers file).
   - **Résumé fidelity:** every drafted sentence traces to a line of the résumé that job gets (answers §Résumé). An
     UNSUPPORTED claim is flagged and never typed.
   - Time-based answers (the start date) are computed at fill time.
   - LinkedIn Easy Apply: run your LinkedIn Easy Apply preflight (03) first.
3. **Ask one round, minus the cards that already carry a ruling.**
   - `preapproved` and the diff found nothing → `event … approved --approval "apply as carded (sweep, <file>)"`, post
     the compact packet as a report, go to fill.
   - `prior_approval` and nothing changed → `event … approved --approval "carried: <reply> (<ct>, <lane run>)"`.
   - Otherwise `event … awaiting_yes` per card, then **one multiple-choice call, one question per card**: Yes, as
     carded · Yes, with change · Skip. Each question holds its whole **flags-first** packet: line 1 company · role ·
     Job ID · card link; `REVIEW:` with only the real flags (knockouts and answers that differ, each with the planned
     answer; a new required free text; drafted text verbatim only when new or changed); one line
     `Routine, no change: …`. Hands-on steps go into the question; when the form ends at Submit, say the lane clicks
     Submit and the operator clicks nothing but replies `done`.
   - Post each answer as it arrives: `event … approved --approval "<the operator's exact reply>"`, or `skipped` / `released`.
     "Yes, with change" carries the change in the same answer.
4. **Fill each approved card** (`event … filling`; refused without `approved` and a current `window ok`). Yes more than
   30 min after prepare → reload the form, re-run `date`, recompute time-based answers. Anything the card didn't cover
   → stop and ask (`needs_user`). Codes → `awaiting_code`.
5. **Gate and Submit** (§5 below).
6. **Report** with `event` (§6 below). Next round.

## 4. Filling: one `browser_batch` per form page (09 §5 "Form page pattern")

Cost is calls × context. Target **≤ 60 tool calls per application**. Per page:
1. Refs once: `read_page filter: interactive` (or `find` for one block), `max_chars` set.
2. One `browser_batch`: warm-up click first, then every text field, native select and checkbox by `ref`.
3. One JS sweep: every field's value and the validation messages, compact text (01 §4 Step 7 query). Fix misses in
   one more batch.
4. Screenshots only after a validation message appears or clears, for proof, or when the sweep can't tell:
   `scale: 0.4`, or `zoom` on a region.
5. Next page as its own click; read the step label or URL to confirm it moved.

Never in a batch: Submit, the flow-ending click, a file upload, anything whose result decides the next step.
Worked examples: **Greenhouse** (about 10 calls, react-select = click ref, type a unique substring, Return; never Tab
out) and **Workday** (one batch per role row; lists = click, `find` option, click ref; never type a prefix) are in
09 §5. Widget tricks: 01 §5 (hidden-input upload, date widgets, taxonomy comboboxes, shadow-DOM inputs).

**Live form and parser checks (07; read that section when one fires):**
- After a résumé upload, autofill or saved-profile restore, check the work history against the PDF before anything
  else: employer, title, dates, location and state, descriptions. **Work history = every résumé role except
  any side venture the answers file says to leave out.** More than 3 rows wrong → delete all and retype. A form that caps rows → merge by employer (07 item 2).
- Re-read other prefills against the answers file: wiped personal fields, country/phone, school and years, veteran list, and every
  pre-ticked consent (set to the answers file's answer; SMS is No). Record original and fix in the INTENT ledger.
- Parser-damage tenants (Workday, Dayforce, Brassring, Avature, iCIMS, UltiPro, Lever): upload the résumé first.
- On the Review (or last) page, read the work history again and record `work history on Review/last page: verified`.

Answer rules (07 "Shared answer rules", in brief): sources in order the answers file → the job's résumé → earlier findings → the
LinkedIn profile. Best honest light. Qualifications the applicant doesn't hold → No. Attestations truthful. "Willing to…" per
the answers file, anything else asks. Consents accept (quote the wording). Pay: text `Negotiable`, optional numeric blank, required
numeric the answers file's value else ask. Demographics decline where allowed. Free text from the JD and résumé only, every claim
sourced.

## 5. Gate and Submit

1. Pre-submit gate (01 §4 Step 8): every inventory ID in the ledger, every required field verified, every page sweep
   0/0/0, Review page read back, no open question, no validation error, the tab matches the card.
2. Draft the INTENT (`INTENT-<JobID>-a<N>-<LaneRunID>.md`, 01 §10.5) with one row per field ID and a yes/no Required
   column; `python3 tools/intent_check.py <draft>` must say `coverage OK`. Write it; `event … intent`.
3. Proof before Submit: one `zoom` per free-text box (`<JobID>-a<N>-text<K>.jpg`) and the Review page
   (`…-review.jpg`), each `save_to_disk: true`, copied into `AppApply-Capture/proof/<LaneRunID>/` (08 §1.1).
4. `document.visibilityState` now, then `window <N> ok` (`submit_clicked` refuses a proof older than 10 min).
5. **Submit as its own tool call**, then `event … submit_clicked`. Posted early by mistake → `event … retract --note`,
   then post it again right before the real click.
6. **Hand-off at or before Submit** (hCaptcha, code, password, terms box, file dialog, a click the permission layer
   blocks): INTENT first, then `event … awaiting_submit --note "<what the operator must do>"` **before** you say it in chat.
   After the operator acts, read the confirmation yourself: `external` (their click) or `submitted` (yours).
7. Confirm read-only by the ATS's method (`03-ATS/<ats>.md` "Confirmation"). Never click Submit twice.

## 6. Report and capture (mandatory)

- Confirmation proof: `computer screenshot`, `scale: 0.4`, `save_to_disk: true`; copy to
  `AppApply-Capture/proof/<LaneRunID>/<JobID>-a<N>-confirm.jpg`.
- Findings file `<outcome>-<ats>-<company>-<JobID>-a<N>-<LaneRunID>.md` (01 §10.6 template).
- Trace lines with `tools/trace.py <LaneRunID> <JobID>-a<N> <action>` as you go; compact PAGE json per form page
  (08 §3.1); `read_network_requests` with a `urlPattern` when the form opens and after Submit ("not observable" if not).
- `dispatch.py --run <OrchRunID> event <N> <JobID> submitted --findings <file> --approval "<reply>" --proof
  AppApply-Capture/proof/<LaneRunID>/<JobID>-a<N>-confirm.jpg`. It runs `pii_scan`, writes the OUTCOME and QB
  fragments to `staging/` if you didn't (a fragment you write must use Python `csv`), and **refuses without the proof
  or an OUTCOME fragment**. Never skip proof, fragments or trace "for token economy".
- Other outcomes: `unconfirmed | paused | skipped | closed | released --findings <file>`; pauses add
  `--status Paused-<X> --f "Q1: …"`.

**Event order:** `claimed → awaiting_yes → approved → filling → intent → submit_clicked → submitted`. Also:
`awaiting_login`, `awaiting_code`, `awaiting_submit`, `needs_user`, `external`, `retract`. All times from `date` or
tool output.

## 7. Browser rules (09 §2, in brief)

- **Visibility:** a hidden window (minimised, covered, display asleep) silently drops clicks and keys. Read
  `visibilityState` before `claim`, before the first click on each card, after any wait over 5 min, and right before
  Submit. `hidden` → `window <N> hidden`, plus `needs_user --note "window hidden"` if a card is mid-round; keep
  preparing read-only.
- **Front tab only.** Navigate it in place for every posting; never `tabs_create_mcp`; never close it. A link that
  opens a new tab: read its URL and navigate your front tab there.
- **Warm-up:** the first click on each new host may be swallowed; check and click once more. Read the first typed
  value back.
- **Leaving an unsubmitted form:** the form's own Cancel/Back; else navigate to the employer's job list.
- **Every tool times out** → first suspect a hidden or background tab (one plain `visibilityState` read; don't retry
  JS). After an upload → ask the operator what dialog is on screen. Never `fetch` to localhost.
- **`javascript_tool`:** output cut at ~1,000 chars; URLs/cookies come back `[BLOCKED…]`; no `setTimeout`/`await`.
- `form_input` only as a fallback (native selects); never on LinkedIn.
- **Extension reconnect:** stop, `needs_user --note "extension reconnect"`, ask the operator to close the old window, re-open
  with `tabs_context_mcp`. If Submit might have been clicked, confirm read-only, never click again.
- Nobody but the operator moves windows. Never run a window-tiling script; never `select_browser` to another machine mid-run.

## 8. Away mode, rounds, compaction, wrap-up

- **Away** (the operator steps away, the orchestrator says so, or the window is hidden): finish or release any card mid-fill;
  claim `--hands-free`; prepare read-only; queue the round's question; fill nothing until they're back and the window is
  `visible` again (re-post `window ok`).
- **After every round:** write `Runs/<date>/HANDOFF-<LaneRunID>-r<k>.md` (claims and board states, last `window ok`
  time, the answers posted as `approved`, open hand-offs, next action; no answers-file values). When context is large (~120k tokens, or
  about 3 rounds since the last compaction), end the round report with: "lane N: please type
  `/compact keep HANDOFF-<LaneRunID>-r<k>.md`".
- **After any compaction** (manual or auto): re-read this card and the newest HANDOFF note, re-prove the window
  (§1 steps 4, 5, 7), `claim <N> --peek`, then continue.
- **Wrap up** only when `claim` has nothing left, the operator is done, or a compaction no longer brings context under ~120k:
  finish or `released` every held card; write `RUN-SUMMARY-<LaneRunID>.md` (with this lane's model) and
  `LEARNINGS-<LaneRunID>.md`; `dispatch.py retire <N>`; send the orchestrator a short report; tell the operator whether to
  start a fresh lane N.

## 9. Easy Apply lane (the `--ea-lane` lane only)

Pick the answers §Résumé file from LinkedIn's **stored résumé list** (missing → `needs_user`); always overwrite the phone
and first-name prefill from the answers file; remove profile-prefilled work-history and education entries; check the modal exists
before re-clicking Easy Apply. The ~15-submit cap counts for the whole run. Never `form_input` on LinkedIn.

## 10. Where to look when…

| Situation | Read |
|---|---|
| A field type you haven't met (upload, dates, taxonomy, shadow DOM, reflow) | 01 §5 |
| Inventory, ledger, sweep or gate detail | 01 §4 Steps 3–8 |
| INTENT or findings template | 01 §10.5, §10.6 |
| An ATS's entry route, quirks, confirmation | `03-ATS/<ats>.md` (your per-ATS notes; the kit ships the 03 quick reference) |
| A tenant's account state | 04, that tenant's row |
| Interrupted attempt, unknown submit state | 01 §11 (read-only checks only) |
| Capture formats (trace, PAGE json, fragments, proof) | 08 §1–3, §4.1 |
| A board command or refusal you don't understand | `python3 tools/dispatch.py -h`, 09 §3 |
| Window, timeout or visibility trouble | 09 §2 |
| Answer rules in full, live-form and parser checks in full | 07 "Shared answer rules", "Live form and parser checks" |
| Bot signals, LinkedIn pacing | 01 §12 |
