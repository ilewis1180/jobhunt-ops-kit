# ROLE — Phase 2 prep: coordinator and workers (operating card)

Card 1.1. **No personal data.** For `phase 2`, `prep`, and the second half of `phase 1+2`. Also the brief
for each **prep worker** (a subagent the coordinator starts, §5). Unattended: the operator is away, don't wait for them. Read
**this card, the answers file in full, and 07 "Shared answer rules" and "Free-text sources"**. Open other docs only at the section a
pointer names. If this card and a numbered doc disagree, the numbered doc wins: follow it and note it in LEARNINGS.

## 1. What prep is, and the line it never crosses

Prep reads each posting and writes one **PREP card** per job so Phase 3 can apply in one approval. **It never types
into an application, ticks a box, uploads, or clicks Apply or Submit.** It reads postings, writes run files, writes the
Queue (H only, plus B where §3 says) and appends the JD Archive. Only one applying session (phase 2 or 3) at a time:
check the last `SESSION_LOG.md` entry and stop if a run is open.

Run ID `R<YYYYMMDD>-<HHMM>-prep` from `date`, on line 1. Model: a mid-tier model (the operator's standing choice). In `phase 1+2`, start only if the scrape's
Raw/Queue read-back passed.

## 2. Session start (coordinator; 00 "Apply mode — session start" steps 1, 3–6)

1. **Recovery pass** (01 §11) and **sheet integrity check** (01 §1.5); **LinkedIn check** (01 §8.1:
   `linkedin.com/jobs-tracker/`, never click a Google prompt).
2. **Work list:** every Queue row whose Apply? (J) is not `No` (blank = Yes) and that is Ready without a PREP card,
   Priority (K) 1 first, then Paused-SignIn rows. `python3 tools/queue_api.py read --csv <file>` gives the rows.
3. **Pre-triage** (01 §2) and post the result: rows by priority, sign-in waits by tenant, open questions.
4. More than ~20 rows → split them into up to **5 worker batches** grouped by ATS (§5). Fewer → work them yourself
   with §3.

## 3. Per row (coordinator or worker; 07 Block 1 step 3)

1. **Open the posting, read-only** (01 §2 check 9) in your own tab. Never open `aplitrak.com` links. A login wall →
   note the site on the card and add it to the login list; don't try to pass it.
2. **Capture the JD** (01 §4 Step 1b) into `Runs/<date>/jd-<JobID>-a<N>-<RunID>.md` (template there), word for word,
   from the page you'd apply through; Greenhouse/Lever/Ashby from the public API. A JD that won't render is **not** a
   pause: `Complete: No (<reason>)` and a flag on the card.
3. **Find the real ATS:** read the Apply control's `href` with JS (never click Apply). For Greenhouse, Lever and Ashby
   take the question list from the public API (`python3 tools/preflight.py`, or
   `boards-api.greenhouse.io/v1/boards/<board>/jobs/<id>?questions=true`). A card that says "Other" when the link goes
   to SmartRecruiters costs Phase 3 time.
4. **Fit gap** (01 §2 fit flag) → Paused-Question with the fit question in F, **and still write the card** so the operator can
   approve it in one step.
5. **Fields:** if the form is visible without signing in or typing, list every field with exactly whether it's
   required. Behind a login or a later page → say so and mark guessed fields **"expected, unverified"**.
6. **Answers:** work out every field and every screening question you can see or expect for this ATS
   (`03-ATS/<ats>.md`), using the 07 answer rules and **the current answers file** (re-read it; cards go stale). Personal values are
   written as references (`answers §Identity: mobile phone`, `{APPLICATION_EMAIL}`), never literally (00 rule 8).
7. **Drafted text** (free text, a required cover letter): from the JD and the résumé the job gets (answers §Résumé:
   the file the answers file §Résumé names for the job's tract). Under ~1,000
   characters (cover letter ~1,500), plain, first person. **Every claim traces to a résumé line or an answers-file rule**, listed
   under `## Sources`; a claim with no source is **UNSUPPORTED** and goes to Needs you with the plain version beside
   it. Time-based answers say "computed at fill time".
8. **Hands-on steps** the ATS is known for (03): Paylocity references, Workable-powered Easy Apply photo, Talemetry pay
   bands, Zoho CAPTCHA, SuccessFactors or Workday account. Flag them so Phase 3 groups those cards.
9. Write **`PREP-<Company>-<JobID>-<RunID>.md`** in today's `Runs/` folder (write-once; check the name first), in the
   card format below.

**Answer rules in brief** (07 has them in full): sources in order the answers file → the job's résumé → earlier findings in `Runs/`
→ the LinkedIn profile. Best honest light: count every role where a skill plausibly fit, round in the applicant's favour, pick the
highest supported range. Qualifications the applicant doesn't hold → No. Attestations truthful. "Willing to…" per the answers file; anything
else is Needs you. Consents accept, quote the wording. Pay: text `Negotiable`, optional numeric blank, required
numeric the answers file's value else Needs you. Demographics decline where allowed. Optional cover letter blank. Needs you =
a fact in no source, or a "willing to…" outside 02.

## 4. PREP card format (07 Block 1)

```
# PREP — <Company> — <Role> — <JobID>
Apply URL: <Real Apply URL or Easy Apply> · ATS: <ATS> · Site: <tenant key> · Login needed: yes/no/signed in
Résumé: <file name from the answers file §Résumé>

## Planned answers
| # | Field / question (exact label) | Answer | Source (the answers file / résumé line / earlier findings / best-effort) |
## Best-effort answers  (anything not straight from the answers file, one line each: why)
## Drafted text  (word for word)
## Sources  (one line per claim: résumé role or the answers file section; none → UNSUPPORTED, move to Needs you)
## Consents it will tick  (exact wording)
## Needs you  (question — why — options)
## Not yet seen  (pages behind a login or later in the flow)
```

## 5. Parallel workers (more than ~20 rows)

Five workers prepped 50–70 cards in 12–13 minutes in practice. The coordinator:
- gives each worker a **batch of rows** (Job ID, company, title, Real Apply URL, ATS guess, Priority, F/G if any) and
  this brief: "Read `roles/ROLE-prep.md` §1, §3, §4 and §6, the answers file, `03-ATS/<ats>.md` for your rows' ATSs,
  and 04 only for their tenants. Work §3 for each row. Write only `PREP-*` and `jd-*` files in `Runs/<date>/`. Never
  write the Queue, the JD Archive or git. Use your own browser tab and close it at the end. Return one status line
  per row: Job ID · card file · Ready / Paused-Question (F text) / Paused-SignIn (site) / Closed / Skip-lean (why) ·
  best-effort count · login needed.";
- staggers starts and tells each worker to open its own tab (tab groups were lost when five workers started at once);
- **checks every result:** each card and JD file exists, `python3 tools/pii_scan.py` over the new files is 0 hits, and
  no card names a literal the answers file value.

Workers don't read this card's §2 or §7, 07 in full, 01 in full or 09.

## 6. Hard rules for prep (00)

Never type into a form, create an account, sign in, or use SSO. Never guess: Needs you instead. Never write a
credential or copy the answers file's values (references only). Never type in Queue columns A, G, J, K, L–AA or Raw. Files are
write-once. Never solve a CAPTCHA. LinkedIn pacing (01 §12): one posting tab at a time; stop on any "unusual activity"
or verification prompt and log it.

## 7. Coordinator writes and session end

1. **Queue** (one batch through `tools/queue_api.py`, 01 §1.4: by Job ID, read back): **H** = the PREP file name. B
   stays Ready, or Paused-SignIn for a login wall, or **Paused-Question** with the question in F for a fit gap or an
   open question; Closed for a dead posting. Never G (the operator's), never J.
2. **JD Archive:** combine the run's `jd-*.md` files into `Runs/<date>/jd-<RunID>.csv` (06 Step C header; **Company and Title from the Queue's L and M**, written with Python `csv`), then `python3
   tools/jd_archive_api.py append --run-id <RunID> <csv>` (dry run) and again with `--apply`. A name self-check refusal means the CSV builder is wrong: fix the
   builder and rebuild the CSV; never edit the archive by hand.
3. **`PREP-SUMMARY-<RunID>.md`**, in order: Ready to approve (one line per card: Priority, company, role, Job ID, card
   file, best-effort count, logins); logins needed in Phase 3 by site; waiting on the operator's answer (every
   Paused-Question row with its F question and card); Needs you (every open question with exact wording).
4. `LEARNINGS-<RunID>.md` (doc changes as proposals, never edits), a `SESSION_LOG.md` entry, `git commit`.
   Next command for the operator: answer the Paused-Question rows, then `phase 3`.

## 8. Where to look when…

| Situation | Read |
|---|---|
| Pre-triage checks, the fit flag, duplicates | 01 §2 |
| JD capture details | 01 §4 Step 1b |
| An ATS's entry route, API, quirks, hands-on steps | `03-ATS/<ats>.md` (your per-ATS notes; the kit ships the 03 quick reference) |
| A tenant's login state | 04 |
| Queue columns and status changes | 01 §1.1–§1.4 |
| Recovery, integrity | 01 §11, §1.5 |
| JD Archive CSV format and append | 06 Steps C–D |
