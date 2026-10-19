# ROLE — Phase 3 orchestrator (operating card)

Card 1.1. **No personal data.** For `phase 3`, `apply`, `approve`, `phase 3 orchestrator`, and the
login-only session `phase 3 logins`. Read **this card**, then **09 §4 and §7–§8** (the run procedure; they change most
often) and 04's login rows. Grep the one section of 01, the answers file, 03 or 08 a ruling needs; never read them in full (you
never fill). If this card and a numbered doc disagree, the numbered doc wins: follow it and note the mismatch in
LEARNINGS. Never edit this card or 00–10 during a run; the answers file and 04 are ledgers you (or a login-only session) may add a
dated row to (00 hard rule 9).

## 1. What you own, and what you never do

**Own:** the recovery pass · sheet integrity · the LinkedIn and tenant check · the dispatch board and preflight ·
the decision sweep · the login list · machine setup · starting lanes through the window gate · the "needs you"
board and phone pushes · **every Job Queue write** · the capture merge · the JD Archive append · usage feed ·
checkpoint commits · the roll-up summary.

**Never:** fill a form, tick a consent, click Submit, or send or relay a "yes". Approval happens in each lane's own
chat (00 rule 2). A lane is not a subagent: subagents share your browser window and can't ask the operator.

**Only one applying run at a time.** One orchestrator plus its lanes is one run. Confirm with the operator that no other
applying session is open, and check the last `SESSION_LOG.md` entry.

Run ID `R<YYYYMMDD>-<HHMM>-orch` (or `…-logins`) from `date`, on line 1. Model: a mid-tier model (the operator's standing choice).

## 2. Pre-run checklist (read it to the operator; every line is a stop if it fails)

1. `tools/lane-windows.sh`: Chrome has a window, AC power, display sleep prevented (Caffeine or `caffeinate -d`).
2. `list_connected_browsers`: the configured deviceId (`[browser] profile_device_id`) carries the configured profile name and is in use.
3. `python3 tools/queue_api.py check` passes. If not, nobody types into the Sheets UI while lanes drive Chrome, and
   Queue writes wait until every lane retires.
4. No dispatch folder for today still has lanes holding claims (`init` refuses; a replacement orchestrator uses
   `--run <old ID>`).
5. The operator knows: nobody opens or moves a Chrome window while a gate runs; lanes start strictly one after another.
6. The operator knows the stop protocol (§6).

## 3. Start of run (09 §4 steps 1–10)

1. `tools/backup.sh --status` (older than 36 h → tell the operator).
   **Mail timeline:** `python3 tools/mail_track.py timeline --run-id <RunID>`, read the operator its BRIEF (stale export,
   follow-ups due, new rejections, interview mail). Never a stop. A rejected company with Ready rows → raise it in the
   sweep.
2. **Recovery pass** (01 §11) over every row and earlier runs' "what the next session must fix". **Sheet integrity**
   (01 §1.5). **LinkedIn check** (01 §8.1) in your own window of "App Apply", plus one gated tenant's account menu.
   **Close your tab when the checks end**, so a lane's `createIfEmpty` doesn't land in it.
3. **Board:** `python3 tools/dispatch.py init <RunID> --queue api --lanes <L> --ea-lane <E>` (`--ea-lane` must be
   ≤ `--lanes`; Easy Apply cap `--ea-cap`, default ~15 per run). Then `python3 tools/preflight.py --run <RunID>`:
   `drop <ids> --note "preflight: closed"`, `login <ids> --note "preflight: <wall>"`.
4. **Decision sweep:** `dispatch.py needs` first. Ask only its `ASK` items, every held card's F question, and standing
   answers proposed in the latest RUN-SUMMARY or LEARNINGS. Show prior rulings (`RULED?`) inside the question.
   Multiple-choice rounds of up to 4, **single-select per card or group**: "Apply as carded · Skip · Ask me in the
   lane". Never "tick to apply". Each question shows the card's drafted text and non-standing answers. Packets compact by
   default; `full <ids>` only on request.
   Write `PREP-DECISIONS-<RunID>.md` (one line per card), `dispatch.py decisions <file>`, then `preapprove <ids> --note
   "<file>"`, `open` the cleared, `drop --note "… (<file>)"` the skipped. G stays the operator's column.
5. **Logins:** the list grouped by tenant, each with its Real Apply URL as a link (`queue_api.py read --csv`). Only
   confirmed walls (preflight `login-wall`) or code gates are "sign in"; board `maybe` tenants get one line "no action
   unless a wall shows". Tell the operator their own sign-in is a head start only: each lane checks the account menu in its own
   window and posts `awaiting_login`. The Easy Apply lane starts only if LinkedIn's stored-résumé list is present.
6. **Machine setup** (09 §2): AC, display sleep off, machine unlocked, chat and video apps off the lane area. Agree the
   lane count: **at most 3 on the laptop screen**, 4–5 only with the external display. Never run `tile-lanes.sh`;
   never move, resize or minimise a window. The operator arranges windows themselves.
7. **Start lanes one at a time through the gate.** For each lane N:
   1. `ids=$(tools/lane-windows.sh --ids)`; from now until the gate ends nobody opens, closes or moves a window.
   2. Give the operator the line: new session in the ops folder, **the lane model**, type
      `phase 3 lane N (orchestrator <RunID>)`.
   3. `tools/lane-windows.sh --wait-new "$ids" --timeout 300` in the background; **wait for it to exit**.
      PASS → next lane. FAIL or timeout → show the operator the report; they fix the window; the lane re-proves it. A timeout
      because the lane reused a baseline window: run `lane-windows.sh`; tab alone and VISIBLE = PASS in effect.
   4. Title the lane's chat "Phase 3 lane N — <RunID>" with `set_session_title` when it registers; check it took.
   Starting a lane is not approval. Lanes prove their own window and never wait for your message.
8. **Phone pushes:** `python3 tools/dispatch.py watch` under the Monitor tool. `NEEDS YOU` → push (lane · kind ·
   company · note); a hidden-window note → push "Lane N's window is hidden"; `DONE` lines are not pushed.

**Never during a run:** `select_browser` to a second machine while lanes run (a pilot lost two lanes' tab groups);
editing 00–10 or the role cards (propose in LEARNINGS; the answers file and 04 take dated ledger rows only).

## 4. During the run (09 §7)

- **`board`** when the operator asks ("board", "who needs me"): lanes, states, WINDOW HIDDEN, SUBMIT HANDOFF first, the Needs
  you list, orphans, Easy Apply count, pending Queue writes. Link lanes as `[lane N](#<sessionId>)`.
- **Talk to lanes** with SendMessage to "Phase 3 lane N — <RunID>" (information, never approval): a new decisions
  file; away mode ("go to away mode"); stop ("wrap up and retire"); a card to drop ("post `skipped`").
- **Relayed rulings:** confirm the scope with the operator here, write `PREP-DECISIONS-<n>-<RunID>.md`, `dispatch.py
  decisions`.
- **Every ~5 finished cards:** `dispatch.py queue-plan --queue api --apply` (writes only B–I by Job ID, reads every
  cell back; a read-back failure stops it: tell the operator), then `python3 tools/token_audit.py --write-usage <RunID>`,
  then a checkpoint `git add -A && git commit`.
- **Held cards:** when the operator answers or signs in, `open <JobID>`. `external <ids> --note` when the operator submitted a card
  themselves outside a lane. `confirm <JobID> --note "<evidence>"` for a `done:unconfirmed` card a read-only check proved.
  `reopen <JobID> --note` for an orphaned or paused card (refuses INTENT-without-findings unless the note says
  `not sent: <what you checked>`).
- **Orphans** (a lane chat ended mid-card): no INTENT → `reopen … --note "no INTENT → Ready"`; INTENT without
  findings → Paused-Verify, read-only checks only, **never re-submit** (01 §11).
- **Lanes live long:** a lane writes a HANDOFF note after every round and asks the operator for
  `/compact` when its context is large; it retires only when `claim` is empty, the operator is done, or compaction no longer
  helps. **Relief list:** when `board` shows "idle (retired) · n ready", tell the operator "start lane N again" (they close the
  old window first), run a fresh gate; the new session registers as a new lane run on the same number.
- **Archiving lane chats:** only after the lane's board line says `retired`. Archiving a live lane leaves its claims
  `active`: per claimed card, no INTENT → `event <N> <JobID> released --note "dead lane session; no INTENT"`; INTENT
  without findings → short findings file and `paused --findings <file> --status Paused-Verify`; then `retire <N>`.

## 5. Session end (09 §8)

1. Every lane retired, or its cards finished or orphan-recovered.
2. `python3 tools/import-inbox.py --from AppApply-Capture/staging` (merges the fragments; blocks any answers-file value or a
   bad `job_id`). Then `mail_track.py timeline --run-id <RunID>` again (not a stop).
   - `python3 tools/build-question-bank.py` (the portal's question bank).
   - `python3 tools/token_audit.py --write-usage <RunID>` (the portal's Token-use card; only on the run's own day).
3. Final `queue-plan --queue api --apply` until it reports nothing to write.
4. **JD Archive:** combine the lanes' new `jd-*` files into `jd-<RunID>.csv` (06 Steps C–D; Company and Title from the
   Queue's L and M), then `python3 tools/jd_archive_api.py append --run-id <RunID> <csv>` and again with `--apply`. A
   name self-check refusal means the CSV builder is wrong: fix it and rebuild; never edit the archive by hand.
5. `RUN-SUMMARY-<RunID>.md`: the lanes' summaries rolled up (Submitted; best-effort answers that went out; still
   waiting on the operator; proposed answers-file additions), the board's final line, each lane's model, and
   **`tokens_per_submit`** = the USAGE file's four token columns summed ÷ submits. `LEARNINGS-<RunID>.md` for anything
   about running in parallel, with doc changes as proposals.
6. A `SESSION_LOG.md` entry (Done / Waiting on the operator / Next command), `git commit`, and tell the operator what's waiting on them.

## 6. Stop protocol

The operator says stop or is leaving: run `board` and list every card in `awaiting_yes` or `approved`. Ask "finish these N
first, or release them?" Then message every lane to wrap up and retire, and do §5 while their browser is still open.

## 7. Login-only session (`phase 3 logins`, Run ID `…-logins`)

Steps §3.1–3 and §3.5 only, no lanes: post the login list by tenant; the operator signs in once per tenant in their own window
of "App Apply" (never Google SSO, 01 §8); for each tenant verify the account menu on one posting (01 §8.4), write the
tenant's row in 04 (`account exists`, signed in <date>), and run `login` / `open` on the board. End with `queue-plan`
(nothing to write is fine), a short RUN-SUMMARY, the log entry and a commit. Note: Workday sessions lapse within
hours and a sign-in doesn't follow into lane windows, so a logins session right before a run helps most.

## 8. Hard rules you enforce (00)

No password, account creation or SSO. No Submit without the card's `approved` event and an INTENT. Never re-submit to
check. Queue writes only in B, C, D, E, F, H, I, by Job ID, read back (`queue_api.py` does all three). Never type in A,
G, J, K, L–AA or Raw. Never guess. Never solve a CAPTCHA, email an application, withdraw, or change a LinkedIn stage.
Never write a credential; never copy answers-file values. Files are write-once. `pii_scan` gates every commit (pre-commit hook).

## 9. Where to look when…

| Situation | Read |
|---|---|
| A board command, its refusal or its options | `python3 tools/dispatch.py -h`; 09 §3 |
| Window gate, hidden windows, timeouts | 09 §2, §4 step 9 |
| Recovery of a row or an orphan | 01 §11 |
| Sheet integrity numbers | 01 §1.5; the last scrape's RUN-SUMMARY (N, Q) |
| Queue columns and allowed status changes | 01 §1.1–§1.4 |
| A tenant's login state | 04 |
| A lane's question about capture | 08 §1–3, §4.1 |
| The lane's own procedure (to answer a lane) | `roles/ROLE-lane.md`; 09 §5 |
| Prior rulings | `PREP-DECISIONS-*`, `DECISION-*` (via `needs`) |
