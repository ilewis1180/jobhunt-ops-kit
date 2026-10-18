# Per-application checklist: matching the résumé to one posting

For the prep step of an apply run (07 Block 1), or anyone checking a résumé against a specific job. **It does not
change which résumé gets sent:** the pipeline sends one of a few fixed PDFs (the answers file §Résumé picks) and does
not rewrite a résumé per job. This checklist finds gaps and writes them down.

## 1. Start from one real job description
Use the captured `jd-<JobID>-…md`, not the title or a summary. If the JD is `Complete: No`, do only §4.

## 2. Requirements matrix
One row per requirement the JD states, required first, then preferred:

| Requirement (JD wording) | Evidence in the résumé being sent | Match | Truthful fix, if any |
|---|---|---|---|
| … | quote the line, or "none" | strong / partial / missing | a term already in the Facts file, or "none: real gap" |

- **"Missing" is an answer too.** Never fill a gap with a claim that is not in the Facts file; retired claims stay
  retired, and KPIs the applicant never held are never invented.
- **A partial match is often a wording problem**: the Facts file backs the experience, but the résumé uses other
  words. Note it; it becomes a résumé edit only under §7.
- Put the matrix on the PREP card. Two or more **missing required** items is a fit question for the operator, not a
  decision for the applier.

## 3. Keywords
Pull the 15–20 most important terms from the JD, grouped: required qualifications · tools and platforms · domain
language · responsibilities. Use the JD's **exact spelling** when the claim is true (hyphenation changes the match).
**No stuffing**: each term appears where the evidence is (a bullet, the summary, Skills), never in a keyword block or
hidden text. Add a term only if the Facts file supports it.

## 4. Format audit (the file you will upload)
Rescan only if the PDF was rebuilt since its last screener pass; otherwise confirm the PDF you upload is
byte-identical to the verified one. Pass criteria: `ats-screener-guide.md` §3c.

## 5. Targeted scan (optional)
Paste the JD into the screener's targeted-scoring field and scan the PDF you will upload. The score is a heuristic for
ranking fixes, not the employer's ATS score, and no pass/fail gate. Check every suggested rewrite against the Facts file.

## 6. Hiring-manager skim
Read the top third of page 1 as a hiring manager would in a few seconds. Do the summary and the first role answer the
JD's top two requirements? If not, write that on the card; fixing it means editing the résumé (§7), not the application.

## 7. When a gap is worth changing the résumé
A résumé edit changes every future application that uses that PDF, so it is the applicant's decision. Suggest one when
the **same** truthful wording gap shows up on three or more PREP cards. Then run the loop in the screener guide §4.

## Record on the PREP card
`Résumé: <file>` · `Matrix: N strong / N partial / N missing (required: N missing)` · `Top keyword gaps: …` ·
`Skim: pass / note` · `Targeted scan: score or not run`
