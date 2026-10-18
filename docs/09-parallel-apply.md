# 09 — Parallel Phase 3: one orchestrator and up to 5 apply lanes

Phase 3 (07 Blocks 3–4; Block 2 is the single-session fallback) split across several sessions. Everything in 00–08
still holds; this file only adds what changes when more than one session applies at once. **No personal data.**

**Why:** in a serial run most of the time went to waiting on the operator, not filling forms. So the parallel design
does three things: it **batches questions** (each lane asks about up to 3 cards in one round, §5); lanes **keep
preparing read-only while the operator is away** (§2, §5); and it **keeps every lane window "visible"** to the browser,
since input to a hidden window is silently lost (§2).

## §1 Who does what

| | **Orchestrator** (1 session) | **Lane N** (up to 5 sessions) |
|---|---|---|
| Started by | the operator's `phase 3` | the operator's `phase 3 lane N (orchestrator <RunID>)` (the orchestrator gives them the line, §4 step 9) |
| Run ID | `…-orch` | `…-apply<N>` |
| Browser | the dedicated profile (§2 rule 1), its own window for the LinkedIn and tenant checks; it opens no postings | the dedicated profile, its own window proven before any claim (§4 lane step 3), one front tab for everything |
| Owns | recovery · sheet integrity · LinkedIn check · **preflight** · the dispatch board · the **decision sweep** · the login list · the "needs you" board and **phone pushes** · **every Queue write** · merging capture fragments · JD Archive append · git · the roll-up summary | claim up to 3 cards → prepare read-only → **one question round** in its own chat → fill → INTENT → Submit → confirm → findings + 08 capture → report each event → next round |
| Never | fills a form, ticks a consent, clicks Submit, sends or relays a "yes" | writes the Queue, commits, appends to a shared CSV, works a card it did not claim |

**Approval is per card, and it is recorded on the board.** A lane fills only a card with an `approved` event (00 rule
2), from one of three places: the operator's answer to that card's question in the lane's own chat; their **"apply as
carded"** ruling in the orchestrator's sweep (`preapprove`, §4 step 5), usable only when the live form matches the card
and the current answers file; or their yes from an earlier lane of the **same run**, carried over when nothing changed
(`prior_approval` in the claim brief). The orchestrator never relays a yes. In an ask-ahead round each card is its own
question with its own answer.

The operator may answer a lane's question from a phone (remote control of the session): that is still that lane's chat.
**Only one parallel run at a time.**

## §2 Machine and browser rules

**What hides a window:** macOS tells Chrome a window is occluded when it is **minimised**, **fully covered**, or **the
display is asleep or locked**. The page then reports `document.visibilityState = "hidden"`. Silently lost: real clicks
and keystrokes. Still working: page script, screenshots, uploads. A partly covered, unfocused window is fine.

**A background tab is worse:** a tab that is not its window's front tab always reports `hidden`, and Chrome freezes it:
script calls time out after 45 s, screenshots fail, timers never fire. Only its own window fixes a background tab.

**Machine setup (before lanes start; §4 step 7). `lane-windows.sh` with no arguments checks 1, 2 and 5:**
1. **AC power.** Chrome throttles background pages harder on battery.
2. **Display awake** for the whole run (a caffeinate utility). The report must say "Display sleep: prevented".
3. **Don't lock the machine** while lanes run.
4. **Lane count fits the screen:** on a laptop screen alone, at most 3 lanes; five need an external display. **Nobody
   but the operator arranges windows:** sessions never move, resize or minimise a Chrome window. The lane-windows
   report names any covered window; the operator fixes it.
5. **Nothing in front of the lane windows:** chat and video apps on another display or small.
6. Optional, test first: relaunch Chrome with `--disable-backgrounding-occluded-windows`; rely on it only if a covered
   window still reads `visible`. **No flag makes a background tab visible.**
7. **Spaces and an external display:** a window on an inactive Space is occluded. Lane windows side by side on one
   display, the chat app on another; nobody swipes Spaces while lanes fill.

**Browser rules (every session):**
1. **Every Phase 3 session uses the dedicated Chrome profile** (config `browser.profile_name`). Sign-ins do not carry
   across profiles. **Names are not stable; the extension's deviceId is** (config `browser.profile_device_id`): at
   session start list the connected browsers, compare the deviceId yourself and select it if another is in use. Ask the
   operator only if that deviceId is absent or carries another name.
2. **Each session needs its own window, and "create a tab group if empty" does not guarantee one.** So the lane
   **proves** its window before it claims anything (§4 lane step 3, `dispatch.py window <N> ok|hidden`), and the
   orchestrator gates each lane start with `lane-windows.sh --wait-new` (§4 step 9). If the tab is not alone in a
   visible window, **the operator moves the window**; the lane posts `window <N> hidden`, keeps preparing read-only,
   and re-proves when it is right, re-navigating its front tab before its first script call.
3. **Work only in that window's front tab**, the tab it opened with. Navigate it in place for every posting. Never
   create a tab for a posting; if a link opens a new tab, read its URL and navigate your front tab there. Never close
   the front tab (closing the group's first tab loses the whole group).
4. **Visibility check** (`document.visibilityState`): before `claim`; before the first click or keystroke on each card;
   after any wait over 5 minutes; right before Submit. If `hidden`: post `window <N> hidden --note "…"` (plus `event …
   needs_user --note "window hidden"` if a card is mid-round); `claim`, `filling` and `submit_clicked` stay refused until
   `window <N> ok`; ask the operator to wake the display or restore the window without clicking inside it; keep
   preparing read-only.
5. **Warm up on every new host:** after each navigation to a new site, expect the first click to be swallowed; check
   and click once more. After the first keystroke into any field, read the value back before typing more.
6. **Leaving a form you did not submit:** use the form's own Cancel or Back (a `beforeunload` guard blocks `navigate`);
   `about:blank` is refused, so navigate to the employer's job list; else ask.
7. **After a validation message appears or clears,** take a fresh screenshot before the next coordinate click (the
   layout moves). Prefer ref clicks and `scroll_to(ref)` over remembered coordinates.
8. **Every tool times out.** Check in this order: a hidden or background tab (read `visibilityState` once with a plain
   expression; `hidden` or another timeout → `window <N> hidden`, stop calling script, ask the orchestrator for a
   `lane-windows.sh` report), then a renderer freeze after an upload (do not retry; ask the operator what dialog is on
   screen and to not switch tabs). **Never `fetch` from a page to localhost** (it raises a local-network prompt).
9. `form_input` events are untrusted (`isTrusted = false`): a fallback only, fine for native `<select>`s, never on LinkedIn.
10. **The operator never switches tabs inside a lane's window.** For a login or a code they type into that lane's front
    tab and reply `done`.
11. **Extension reconnect** (tools error, then recover): the lane stops, posts `needs_user --note "extension reconnect"`,
    asks the operator to close its old window, re-opens, and if Submit might have been clicked confirms read-only (01
    §11) and never clicks again.
12. **Page-script tool limits:** output is cut at about 1,000 characters; text with URLs, paths, query strings, cookies
    or base64 comes back blocked; **no `setTimeout`, `await` or sleeps inside the tool** (in a throttled tab they hang 45
    s). Return compact plain text. Always give network reads a URL pattern.
13. **Token economy** (cost is turns × context size). **Batch:** fill a page with one batched call (click, type, key, by
    ref), then one script sweep; the warm-up click first; **Submit is never inside a batch**. **Screenshots:** small
    scale, only after a validation message, for proof (08 §1.1), or when a ref or the sweep cannot tell. **Reads:**
    interactive filter or a ref id, with a character cap; don't re-read a JD that is on disk. **Context:** follow the
    wrap-up size in §5.

## §3 The dispatch board (`ops/tools/dispatch.py`)

State lives in `Runs/<date>/dispatch-<OrchRunID>/`. `board.csv` is write-once. Claims and tenant locks are `mkdir`s
(atomic). Each lane appends only to its own `events/lane<N>.jsonl`; the orchestrator only to `events/orch.jsonl`.
`python3 ops/tools/dispatch.py -h` lists every command.

- **`init <OrchRunID> --queue api|<export>`** puts each PREP card whose Queue row is Ready or Paused-SignIn (Apply? not
  No) on the board. It holds back In progress, Paused-Question and duplicate cards, and any card with an INTENT but no
  findings. It leaves out Submitted, Skipped and Closed rows, and anything with a submitted findings file. It
  registers every `PREP-DECISIONS-*` / `DECISION-*` file that names a board Job ID. It **refuses** while another board
  still has lanes holding unfinished claims (a replacement orchestrator resumes with `--run <OrchRunID>`).
- **Lanes:** every LinkedIn Easy Apply card goes to the Easy Apply lane (`--ea-lane`, default 5; cap `--ea-cap`,
  default 15 per run). Every other card is grouped by employer and tenant; each group lives in one lane and has one
  **lock**, so two lanes never work the same employer or account at once. A lane may hold several of its own cards on
  one lock (ask-ahead).
- **`claim <N> --peek`** shows what `claim` would hand out and claims nothing (no window proof needed).
- **`claim <N> --ahead 3`** keeps up to 3 open claims and prints each card's brief: attempt N, résumé, decisions files,
  `packet: compact|full`, `login`, `preapproved`, `prior_approval`. Own list first (priority, then no-login), then the
  end of other lanes' lists, never Easy Apply unless it is the Easy Apply lane. **`--hands-free`** skips login cards.
- **`window <N> ok|hidden [--note]`** is the lane's window proof. `claim` refuses until the latest window event is `ok`;
  `filling` and `submit_clicked` refuse unless that `ok` is newer than the last hidden report; `board` shows **WINDOW
  HIDDEN**; `watch` pushes it.
- **`event <N> <JobID> <kind> […]`** checks the order `claimed → awaiting_yes → approved → filling → intent →
  submit_clicked → submitted`. **`approved --approval "<the exact reply>"`** is posted per card the moment the answer
  arrives, so the card↔answer mapping is on disk before any field is touched. `submit_clicked` needs a `window ok`
  **less than 10 minutes old**. Before a terminal event it runs `pii_scan.py` over the attempt's findings, INTENT and
  trace, and refuses on a hit. `submitted|unconfirmed|external` write the OUTCOME-/QB- fragments to `staging/` from the
  findings and INTENT when the lane has not (never over an existing one), after a scan; a lane-written fragment is
  parsed with the csv module first and the event refused on a bad column count.
- **`event … awaiting_submit --note "<what the operator must do>"`:** a hand-off at or before Submit (captcha, blocked
  click, code, terms box, file dialog). INTENT must exist. Shows first as SUBMIT HANDOFF on `board` and `watch`. After
  the operator acts the lane posts `external` (their click) or `submitted` (its own). **`event … retract --note`** voids a
  `submit_clicked` posted before any click happened. **`event … external --note "<evidence>"`:** the operator clicked
  Submit in this lane's window and the lane read the confirmation; ends the card as externally submitted.
- **Orchestrator commands:** `board [--holds]` · `list [lane]` · `show <JobID>` · `needs [lane]` (every card's Needs-you
  items split into answered by the answers file, covered by a prior decisions line (`RULED?`), and still to ask (`ASK`))
  · `open|hold|drop|reviewed|login|preapprove|full <JobID>… [--note]` (`drop` and `hold` refuse cards a lane holds;
  `open`/`reopen` refuse a card with an INTENT and no findings unless the note says `not sent: <what you checked>`) ·
  `external <ids> --note` (the operator submitted outside a lane; the card can never be reopened) · `confirm <ids>
  --note "<evidence>" [--findings]` (a `done:unconfirmed` card that read-only evidence shows was submitted; `queue-plan`
  then writes Submitted) · `reopen <JobID> --note` · `decisions <file>` · `queue-plan --queue api [--apply]` (writes
  B/C/F/H/I plus D and E if blank for every finished card, dropped cards as Skipped/Closed, released cards' H, and
  B = Ready for a hold cleared with `open`; reads every cell back) · `watch [--once] [--replay]` (one line per lane
  event the operator should hear about).

## §4 Starting a run

**Pre-run checklist (every line is a stop if it fails):**
1. `lane-windows.sh` with no arguments: Chrome has a window, the Automation prompt is granted, power is AC, display
   sleep is prevented.
2. The dedicated profile (by deviceId) is the one in use.
3. `queue_api.py check` passes. If it fails, nobody types into the Sheets UI while lanes drive Chrome; Queue writes
   wait until every lane has retired.
4. No dispatch folder for today still has lanes holding claims.
5. The operator knows the two gate rules: nobody opens or moves a Chrome window while a gate is running, and lanes
   start strictly one after another.
6. The operator knows the stop protocol (§7).

**Orchestrator**, after `phase 3`:
1. Run ID on line 1. `import-inbox.py`. `backup.sh --status` (older than 36 h → say so). Confirm no other applying
   session is open. **Mail timeline (start):** `mail_track.py timeline --run-id <RunID>`, then read the operator its
   BRIEF (a STALE warning, follow-ups due, new rejections and interview mail from the last 3 days). Never a stop.
2. Read 00, this file, 07 (answer rules and Blocks 3–4) and 04's login rows. The orchestrator never fills, so it reads
   01 only for §1.4, §1.5 and §11, and never the answers file, 03 or 08 in full: grep the one section a ruling needs.
3. **Recovery pass (01 §11)** over every row and earlier runs' "what the next session must fix". **Sheet integrity**
   (01 §1.5). **LinkedIn check** (01 §8.1) in its own window of the dedicated profile; open one gated tenant the operator
   is signed into and confirm the account menu. **Close the orchestrator's own tab when these checks end**, so a lane's
   tab group does not land in it.
4. **Board and preflight:** `dispatch.py init <RunID> --queue api`; `preflight.py --run <RunID>`; then `drop <ids>
   --note "preflight: closed"` and `login <ids> --note "preflight: <wall>"`.
5. **Decision sweep:** `dispatch.py needs` first; ask only its ASK items, every held card's F question, and any standing
   answer proposed in the latest RUN-SUMMARY or LEARNINGS. **Show any prior ruling inside the question.** Multiple-choice
   rounds of up to 4, **single-select per card**: "Apply as carded · Skip · Ask me in the lane" (never "tick to apply").
   Each question shows the card's drafted text and any non-standard answer. Write `PREP-DECISIONS-<RunID>.md` (one
   line per card), `dispatch.py decisions <file>`, then `preapprove` / `open` / `drop --note "… (<file>)"`. "Ask me in
   the lane" cards get nothing. Packets are compact by default; `full <ids>` only on request.
6. **Logins:** post the login list (`init` plus preflight) grouped by tenant, each tenant's Real Apply URL as a link.
   The operator signs in once per tenant in their own window of the profile and says `done` or `skip <tenant>`. That
   sign-in does not follow into a lane's window on many tenants: each lane checks the account menu in its own window
   (§5 step 2) and posts `awaiting_login` if missing. List as "sign in" only confirmed walls (preflight `login-wall`) or
   code gates; `maybe` tenants get one line, "no action unless a wall shows". The Easy Apply lane starts only if the
   LinkedIn stored-résumé list is present.
7. **Machine setup (§2):** plug in, display awake, unlocked, other apps off the lane area; `lane-windows.sh` and read
   its power and display-sleep lines; agree the lane count.
8. Optionally file the sessions in a sidebar group "Phase 3 — <RunID>".
9. **Start lanes one at a time, through the window gate.** For each lane N:
   1. `ids=$(ops/tools/lane-windows.sh --ids)` (the baseline). Until the gate ends, **nobody opens, closes or moves a
      Chrome window**.
   2. Give the operator lane N's line: "new session in the repo, type `phase 3 lane N (orchestrator <RunID>)`".
   3. Run `ops/tools/lane-windows.sh --wait-new "$ids" --timeout 300` in the background and **wait for it to exit**. It
      waits for exactly one new Chrome window and PASSes only if that window has **one tab** and part of it **shows on
      screen** (exit 0 PASS · 1 FAIL · 2 cannot read Chrome · 3 timeout). A timeout when the lane reused a window that
      was already in the baseline: run `lane-windows.sh` and check the lane's tab is alone and VISIBLE (a PASS in effect).
   4. **PASS** → next lane. **FAIL or timeout** → show the operator the report before the next lane; they fix the window.
   5. **Title the lane's chat** "Phase 3 lane N — <RunID>" when it registers, so a message to that name reaches it.
      The lane proves its own window and never waits for this message. Starting a lane is not approval. Subagents
      cannot be lanes: they share the session's browser window and cannot ask the operator.
10. **Phone pushes (§7):** run `dispatch.py watch` under a monitor that turns each line into a notification.

**Login-only session** (`phase 3 logins`): steps 1–4 and 6 only, no lanes. For each tenant the session verifies the
account menu on one posting (01 §8.4), writes the tenant's row in 04, and runs `login`/`open` on the board so the next
`init` sees them. Ends with `queue-plan` (nothing to write is fine), a short RUN-SUMMARY and a commit.

**Lane N**, after `phase 3 lane N (orchestrator <OrchRunID>)`. Every step is mechanical; no step waits for another
session. The `--wait-new` gate is running while you do steps 1–5, so do them **before** the long read.
1. Run ID `…-apply<N>` (from `date`) on line 1. Title the session "Phase 3 lane <N> — <OrchRunID>" if you can. Every
   `dispatch.py` call takes `--run <OrchRunID>`.
2. List the connected browsers. If the configured deviceId is not the one in use, select it. Ask only if it is absent.
3. Open your tab group (create if empty). From here on, create or close no other tab.
4. `navigate` the front tab to the configured light page (`browser.lane_tab_url`, default `https://example.com/`),
   never a posting. Then read `document.visibilityState` as a plain expression, no `await`.
5. `ops/tools/lane-windows.sh --lane-tab`: your window shows `alone` and `VISIBLE`. **PROOF** = step 4 said `visible`
   **and** that line says alone and VISIBLE.
6. `dispatch.py --run <OrchRunID> register <N> <LaneRunID>` (it prints your list and the lane-tab line).
7. **PROOF true** → `dispatch.py --run <OrchRunID> window <N> ok`. Go to step 9.
8. **PROOF false, or step 4 timed out** → `… window <N> hidden --note "<tabs> tabs / <verdict>"`. Do not ask anyone to
   move anything (the operator manages windows). No script call and no page until the window is right (re-run
   `lane-windows.sh` every few minutes, or when told it is fixed). Then repeat steps 4–5 and 7.
9. Now read: 00 (hard rules), the answers file, 07 (answer rules and Block 4), 08 §1–3, this file's §2, §5 and §6, 01
   §4–§5, the 03 quick reference and only the `03-ATS/<ats>.md` notes for the ATSs of your cards, 04 only for their
   tenants. Skip the recovery pass, integrity check, LinkedIn check and pre-triage; the orchestrator did them.
10. A "gate PASS/FAIL" message from the orchestrator is information only. **Never wait for it.** `claim` refuses until
    your latest window event is `ok`.

## §5 The lane loop (rounds of up to 3 cards)

1. **Claim:** `dispatch.py claim <N> --ahead 3` (`--hands-free` while the operator is away). Read each card and the
   decisions files it lists; the newest PREP-DECISIONS wins over the card. Read the JD if you need it.
2. **Prepare each card, read-only,** in the front tab. Open the posting and reach the form without typing, ticking or
   uploading anything.
   - Login wall → `event … awaiting_login`, and ask in the round.
   - **Gated tenant (Workday, SuccessFactors, ADP): confirm the sign-in in this lane's window** before inventorying.
     The tenant's own page must show the account menu; otherwise `awaiting_login`.
   - **Don't re-render what is already on disk.** The JD is `jd-<JobID>-*.md`; a Greenhouse card's question list is in
     `Runs/<date>/preflight-<OrchRunID>.jsonl` (Ashby and Lever: their public API). Diff the card against those, and
     open the form only to check the tenant sign-in, settle a difference, or fill. A form with no API list is
     inventoried live with an interactive-elements read, never a full page-text dump.
   - **Diff three ways:** live form, card, **current answers file**. A card can be stale.
   - **Résumé-fidelity check:** every drafted sentence traces to a line of the résumé that job gets. Fix and show.
   - Time-based answers are computed **at fill time**.
3. **Ask one round, minus the cards that already carry a ruling:**
   - `preapproved` in the brief **and** the three-way diff found nothing: post `event … approved --approval "apply as
     carded (sweep, <PREP-DECISIONS file>)"`, post the compact packet as a report, go to step 4. Any difference → ask.
   - `prior_approval` in the brief **and** card, answers file and live form unchanged since: post `event … approved
     --approval "carried: <original reply> (<time>, <lane run>)"`, go to step 4. Anything changed → ask again.
   - For the rest: `event … awaiting_yes` per card, then **one multiple-choice call with one question per card**: Yes,
     as carded · Yes, with change · Skip. **Each question carries its whole packet in the question text** (the question
     box may be all the operator sees on a phone): **compact** (default), **flags first**: line 1 company · role · Job
     ID · card link; then `REVIEW:` with only the real flags: (1) knockouts and answers that differ from the card or the
     answers file, each with the planned answer; (2) any new required free text; (3) drafted text verbatim, **only when
     new or changed**; then one line `Routine, no change:` naming what matches. **Full** (only after `full`): the 07
     Block 2 step 4 packet.
   - **Hands-on steps go into that card's question** ("Yes, and I have uploaded the photo"). When the form ends at
     Submit, the question says the lane clicks Submit and asks the operator to click nothing after the hands-on step
     except replying `done`.
   - As each answer arrives, post it: `event … approved --approval "<exact reply>"` for a yes (with or without change),
     `skipped` / `released` for a skip. `filling` is refused without it. "Yes, with change" carries the change in the same
     answer; never a follow-up "what change?", never a separate "OK to submit?" when the packet said "and submit".
4. **Fill each approved card in order** (`event … filling`), per the card and 01 §4, verifying every field; a page per
   batch, then one sweep (§2 rule 13). A yes older than 30 minutes → reload the form, recompute time-based answers.
   Anything the card did not cover → `needs_user`. Codes → `awaiting_code`.
5. **Gate and submit:** pre-submit gate (01 §4 step 8); draft the INTENT and run `intent_check.py <draft>` until
   `coverage OK` (one row per field ID, yes/no Required column); write the INTENT (`event … intent`); read
   `visibilityState` **now** and post `window <N> ok`; capture proof (08 §1.1); then **Submit as its own tool call**
   (`event … submit_clicked`). **Any hand-off at or before Submit** (captcha, code, password, terms box, file dialog, a
   blocked Submit click): the INTENT exists first; post `event … awaiting_submit --note "<what the operator must do>"`
   **before** saying it in chat; after they act, read the confirmation yourself and post `external` or `submitted`. A
   step labelled "Continue" or "Next" that ends the flow is the Submit. `submit_clicked` is posted only after a click
   happened; one posted early is voided with `retract`. Confirm read-only (03). Write the findings file.
6. **Report:** `dispatch.py event <N> <JobID> submitted|unconfirmed|paused|skipped|closed|released --findings <file>`
   (`--approval "<exact reply>"` for submits; `--status Paused-<X> --f "Q1: …"` for pauses). The event runs the PII
   scan first. Then the 08 fragments (§6). **Never touch the Queue.**
7. Next round. Times come from `date` or tool output, never typed by hand.

**Away mode** (the operator steps away, the orchestrator sends word, or the window is `hidden`): finish or `released`
any card mid-fill; claim `--hands-free` and prepare read-only; queue the round's question; fill nothing until the
operator is back and the window is `visible` (re-read `visibilityState` and post `window <N> ok` after any wait over 5
minutes); if they are gone for the night, wrap up and retire.

**Between rounds:** compact the conversation with a hand-off note (claimed cards and states, the window-proof time,
the answers given). The rolling context, not the page, is what costs.

**Relief lanes:** when a lane retires with ready cards left (`board` shows "idle (retired) · n ready"), tell the
operator "start lane N again" (they close the old lane's window first), run a fresh gate; the new session registers as
a new lane run on the same lane number.

**Lane wrap-up:** after ~5 applications or ~150k tokens of context, when context is tight, when `claim` has nothing
left, or when the operator is done: finish or `released` every held card; write `RUN-SUMMARY-<RunID>.md` and
`LEARNINGS-<RunID>.md` (00 session end, minus the Queue, the JD Archive and git); `dispatch.py retire <N>`; send the
orchestrator a short report; tell the operator whether to open a fresh lane.

**Easy Apply (the Easy Apply lane):** pick the résumé the answers file names from LinkedIn's **stored résumé list**
(the upload control is in a shadow root the tools cannot reach; list missing → `needs_user`); always overwrite the
phone and first-name prefill from the answers file; remove the work-history and education entries prefilled from the
profile; check the modal exists in the DOM before re-clicking Easy Apply.

**Models.** A lane fills and submits under the applicant's name, so what keeps it safe is the process, not the model.
Whatever model runs a lane: **literal, not clever** (answer only from the card, the decisions files and the answers
file; any doubt → `needs_user`); **the mechanical gates are never skipped** (three-way diff, `intent_check.py`, the
sweeps at 0/0/0, `pii_scan.py`, a fresh `window ok`, Submit as its own call). Record each lane's model in its
RUN-SUMMARY and any model-specific miss in LEARNINGS. Smaller models tended to re-ask on pre-approved cards.

## §6 Capture and files in a lane (08, with these changes)

Traces and compact PAGE json go where 08 says; each lane's Run ID keeps names unique. **Lanes don't write DOM
fixtures.** Network reads with a URL pattern when the form opens and right after Submit ("not observable" otherwise).
**Shared CSVs are never appended by a lane:** at each attempt's end a lane writes `OUTCOME-<JobID>-a<N>-<RunID>.csv` and
`QB-<JobID>-a<N>-<RunID>.csv` to `AppApply-Capture/staging/` (or lets `event` build them). Run files go in
`Runs/<date>/`, write-once. **Third-party data** (a reference's name and contacts) is typed only into the form and never
recorded anywhere.

## §7 The orchestrator during the run

- **Phone pushes:** `dispatch.py watch` under a monitor. Each `NEEDS YOU` line → a push (lane · kind · company · note);
  a `hidden` note → "Lane N's window is hidden"; `DONE` lines are for the board only. In chat, link each lane session.
- **`board`** whenever asked ("board", "who needs me"): each lane's cards and states (**WINDOW HIDDEN** where unproven),
  a **Needs you** list (SUBMIT HANDOFF first, then oldest first), orphans, the Easy Apply count, pending Queue writes.
- **Talk to lanes** (information, never approval): when a new decisions file is registered; when the operator steps away
  ("go to away mode") or stops ("wrap up and retire"); when a card must be dropped while a lane holds it ("post
  `skipped`").
- **Relayed rulings:** a lane may relay a standing answer the operator gave in its chat. Confirm the scope with the
  operator here, then write `PREP-DECISIONS-<n>-<RunID>.md` and run `dispatch.py decisions`.
- **Every ~5 finished cards:** `dispatch.py queue-plan --queue api --apply`, then a checkpoint commit. A read-back
  failure stops it: tell the operator. Without the API, fall back to an export plus typing per 01 §1.4.
- **Orphans** (a lane chat ended mid-card): no INTENT → `reopen <JobID> --note "no INTENT → Ready"`; INTENT without
  findings → **Paused-Verify**, read-only checks only, never re-submit.
- **Held cards:** when the operator answers a question or signs in, `open <JobID>`.
- **Archiving lane chats:** only after the lane has retired. Archiving a live lane stops its process and leaves its
  claims `active`; recover per claimed card (no INTENT → `event … released`; INTENT but no findings → a short findings
  file and `paused --status Paused-Verify`), then `retire <N>`.
- **Stop protocol:** run `board` first and list every card in `awaiting_yes` or `approved`. Ask: "finish these N first,
  or release them?" Then message every lane to wrap up and retire, and do §8 while the browser is still open.

## §8 Orchestrator session end

1. Every lane has retired, or has its cards finished or orphan-recovered.
2. `import-inbox.py --from AppApply-Capture/staging` (merges the fragments; blocks any file with a personal value).
   **Mail timeline (end):** `mail_track.py timeline --run-id <RunID>` again after the merge. Not a stop if it fails.
3. Final `queue-plan --queue api --apply` until it reports nothing to write.
4. **JD Archive:** combine every lane's new `jd-*` files into `jd-<RunID>.csv` (06 Step C); `jd_archive_api.py append`
   dry run, then `--apply`.
5. `build-question-bank.py`; `usage_report.py <OrchRunID>` for the dashboard's token card.
6. `RUN-SUMMARY-<RunID>.md`: the lanes' summaries rolled up (Submitted, best-effort answers that went out, still
   waiting on the operator, proposed additions to the answers file), the board's final line. Then
   `LEARNINGS-<RunID>.md` for anything about running in parallel.
7. Commit, and tell the operator what waits on them.
