# ATS screening and the markdown-resume editor: how the two fit together

For any session that renders, exports or scans a résumé. Generic sections only; keep your own scan history and
record ids in your private workspace.

## 1. What each app is for

| App | Job |
|---|---|
| **markdown-resume editor** (self-hosted `junian/markdown-resume`, `master`; Oh My CV lineage) | holds the résumé records and renders the paginated preview. The ATS-shape PDFs are built by script (§4), not exported from the editor. |
| **ATS screener** (self-hosted open-source `ats-screener`) | parses a PDF or DOCX and scores it against several simulated ATS engines (Workday, Taleo, SuccessFactors, iCIMS, Greenhouse, Lever). Use it to check the **PDF you will upload**. |

The rule learned the hard way: **check the file you send, not the markdown or HTML it came from.** A PDF has no DOM;
extractors work from glyph coordinates.

## 2. Scanning a résumé PDF

1. Build the PDF fresh from disk first (§4). Never scan a stale download.
2. Open the scanner in a **fresh load**; after a scan the page shows Start Over / Re-Scan.
3. Upload the PDF (the Upload button wraps a hidden `<input type="file">`). The file name and size appear.
4. Click **Scan Resume** (find it by label each time; its ref changes between loads).
5. The **Resume Overview** (parse) panel appears within about 10 s; full scoring takes 20–40 s and ends with
   "Scan complete. Average score N out of 100. X of 6 ATS systems passed."
6. Read the **parse panel first** (§3a): it is deterministic, and it is where the pass criteria live.
7. Check the three formatting flags **visually** (Multi-Column Layout, Tables Detected, Images/Graphics): the page
   text returns only the labels, not pass/fail; a screenshot shows a green check or a warning icon.
8. Then read the scores (§3b), treating them as secondary.
9. **With a job description** (the "Add Job Description for Targeted Scoring" path): paste the posting, scan, and
   treat the keyword block as a ranking of fixes, never as the employer's score. Without a JD the tool invents its
   own target keywords; treat that block as low-signal.

## 3. What the results mean

### 3a. Parse panel: deterministic, trust this

| Field | Meaning | Good value for an ATS-shape PDF |
|---|---|---|
| Words / Pages | extracted text size | Pages = the count you built for (2 is the usual cap) |
| Sections | headings matched to canonical sections | Contact, Summary, Skills, Experience, Education, Certifications all detected |
| Skills Found | items that survive the screener's own taxonomy | every skill intact, none split in two (fewer than you listed is fine) |
| **Positions** | how many experience entries the parser split | **must equal the number of roles** |
| Education | entries found | ≥ 1 |
| Contact Info | name / e-mail / phone / LinkedIn | all four parsed correctly |
| **Formatting flags** | Multi-Column, Tables, Images | **all three green** |

### 3b. Scores: useful for comparing, noisy on their own

- Average score with a band, "X/6 Systems Passed", a delta against the previous scan **of any file** (history
  persists across page loads, so switching résumés shows a spurious regression).
- Per engine: score, delta, verdict (`LIKELY TO PASS` / `MAY BE FILTERED`), sub-scores (Formatting, Keywords,
  Sections, Experience, Education), matched and missing keyword counts.
- **Two scoring paths.** A banner "AI scoring temporarily unavailable" means the **rule-based** path (precise
  sub-scores). The AI path returns round numbers and has **invented content** (a "CRITICAL" item quoting a bullet that
  does not exist). Scores from different paths cannot be compared.
- Experience sub-score (rule-based): `min(1, quantified/0.4)*40 + min(1, actionVerbRatio/0.7)*30 + bulletCountScore
  (≥8 bullets → 30)`; the verb check looks only at the first word of each bullet against a fixed list. Do not game it.

### 3c. Pass criteria

A PDF is **screener-verified** when all hold:
1. Built from disk with `build_ats_pdf.py`: zero `<dl>`, zero `<table>`, zero U+2010 soft hyphens, the name extracts as
   one line, bullet lines extract as literal `•`, the page count you built for.
2. **ASCII-only extracted text except `•`** (Taleo and SuccessFactors flag "special characters in dates").
3. All three formatting flags green.
4. Positions = role count; Education ≥ 1; the expected sections detected; contact parsed; skills unfragmented.
5. Scores reported but **not required to hit a number**; record them for comparison between builds.

## 4. Building the PDFs locally

```bash
python3 resume/scripts/build_ats_pdf.py My-ATS.md out/My-ATS.pdf          # base css fetched, or --base-css minimal-base.css
pdftotext -layout out/My-ATS.pdf - | python3 -c "import sys;t=sys.stdin.read();print([c for c in set(t) if ord(c)>127 and c!='•'] or 'all clean')"
```

- Renders the front-matter header, `##`/`###` headings, `**bold**`, `<br>` and paragraphs with base + theme + ATS
  overrides (h1 letter-spacing reset, `hyphens: none`), prints to PDF with a headless Chromium (US Letter, margins
  55/45 px, Verdana 12 px, line-height 1.3, paragraph gap 5 px: the editor record's `styles`).
- Prints `N page(s), soft-hyphens 0, bullet lines N, non-ascii chars none` and the first extracted line, which must be
  the name. Exit 1 on too many pages, soft hyphens, or a damaged first line.
- It **refuses** definition lists, markdown bullets and iconify markup: by design it only works for the ATS shape.
  Display-shape résumés are exported from the editor's print dialog.
- **Why it exists:** the editor's export relies on browser downloads; a browser blocks repeated automatic downloads,
  so the old file stays in the downloads folder and you ship a PDF of the *previous* revision.

### The loop

Disk is the source of truth. Edit the `.md` → `check_resume.py --shape ats` → push it into the editor record (or
restore `build_backup.py`'s JSON) and reload → verify page count and a **SHA-256** hash against disk → rebuild the PDF
with the script → rescan → regenerate the restore JSON. The editor record and the PDF must both match the same disk
hash. **Compare hashes, never byte lengths.**

## 5. Editor navigation

My Resumes `/markdown-resume/resumes` (Backup DB… / Restore DB… top right) · Edit `/markdown-resume/edit/<recordId>`
(Markdown and CSS tabs, paper combobox `letter` / `A4`, Save) · page count
`document.querySelectorAll('.vue-smart-page-break').length + 1` · storage: IndexedDB `localforage` /
`keyvaluepairs` / `MARKDOWN_RESUME_data`, per origin and per browser profile (read it from an editor tab, reload after
writing). Details: `references/*.md`.

## 6. Known pitfalls

1. **Markdown `-` bullets don't reach the PDF text layer** (CSS-drawn): the screener sees one block and reports
   Positions = 1. Use literal `•` paragraphs.
2. **Put the date range on line 1 of each entry** (`**Title | Company | Mon YYYY - Mon YYYY**<br>`, then the
   location, then bullets): parsers split entries on a non-bullet line that contains a date range.
3. **Dates:** three-letter month and an ASCII hyphen. An en dash reads as a special character on some engines.
4. **`## Education & Certification` is recognised by no engine**: split it.
5. **Flex three-column rows (`<dl>`) set off Multi-Column and Tables** in the PDF even though the DOM order is fine.
   That is why the ATS shape exists.
6. **Extraction corruptors:** `h1 { letter-spacing: 0.1em }` splits the name into letters; `hyphens: auto` injects
   U+2010; a wrapped pipe-separated skills line fragments (one skill per line with `<br>`); a hyphenated compound
   (`AI-automation`) misses the keyword `AI automation`.
7. **Don't trust the recommendations as written:** the same report can contradict itself, list a present skill as
   missing, and invent figures in suggested rewrites. Check every suggestion against your Facts file.
8. **A pasted report may not be about the current file.** Rescan the actual PDF before acting on it.
9. **Scoring can stall** at `Scoring...` with no console error: click Scan again or reload; the parse panel is enough
   to verify against.
10. **Browser-automation caveats:** pick the right connected browser profile (the editor records live in one profile's
    IndexedDB); the Restore button opens a native file picker an agent cannot drive (write IndexedDB directly instead);
    hand-typed base64 chunks caused transcription errors (hash-verify every chunk, or send the whole file).
