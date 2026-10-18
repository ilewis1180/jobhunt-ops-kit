# resume/ — building, checking and shipping the PDFs

The résumé side of the system: markdown on disk is the source of truth, a self-hosted markdown-resume editor renders
it, a script builds the upload PDFs, and an ATS screener verifies what a parser sees. Nothing here is a real résumé;
the examples are fictional.

| Path | What |
|---|---|
| `scripts/build_ats_pdf.py` | render an ATS-shape `.md` to PDF with headless Chromium and check it (pages, soft hyphens, name line, non-ASCII) |
| `scripts/build_backup.py` | build the editor's Restore JSON from `.md` files and a records file (`examples/records.example.json`); validates the shape the editor checks silently |
| `scripts/check_resume.py` | lint a résumé: front matter, icons, definition-list indentation, and the `--shape ats|display` house rules |
| `css/` | the theme and ATS overrides (MIT), a stand-in base stylesheet, and `fetch_base_css.sh` for the editor's own (copyleft) base |
| `references/` | the editor's markdown dialect, CSS and pagination, storage and export JSON, and driving it from a browser |
| `examples/` | `ATS-Example.md` (flat upload shape), `Display-Example.md` (three-column shape), `records.example.json`, `example_backup.json` built from them |
| `templates/` | `applicant-profile.example.yml`, `Facts-Source-of-Truth.template.md`, `approved-bullets.schema.json` (+ example) |
| `docs/` | the ATS screener guide (generic sections) and the per-application checklist |

## Two shapes

- **ATS shape** (`ATS-Example.md`): entry lines `**Title | Company | Mon YYYY - Mon YYYY**<br>`, location on the next
  line, literal `•` bullet paragraphs, one skill per line ending in `<br>`, standard headings (`## Professional
  Summary`, `## Skills`, `## Professional Experience`, `## Education`, `## Certifications`), US Letter, 2 pages at most.
  Every rule exists because a parser mis-read the alternative (`docs/ats-screener-guide.md` §6).
- **Display shape** (`Display-Example.md`): three-column definition-list entries, icons, pipe-separated skills.
  Exported from the editor's print dialog; the build script refuses it on purpose.

## The loop

```bash
python3 resume/scripts/check_resume.py --shape ats My-ATS.md
python3 resume/scripts/build_ats_pdf.py My-ATS.md out/My-ATS.pdf              # --base-css minimal-base.css offline
python3 resume/scripts/build_backup.py --dir . --records records.json --out backup.json
```
Then: push the markdown into the editor (or restore the JSON), verify the page count and a SHA-256 hash against disk,
rescan the PDF, and copy the verified PDF to the ops data root's `Resume/` under the name the answers file §Résumé uses.

## Facts, bullets, profile

- `Facts-Source-of-Truth.template.md`: every figure on every résumé traces here, with `[CONFIRMED]` / `[ESTIMATE]` /
  `⟨OPEN⟩` tags and a retired-claims list.
- `approved-bullets.schema.json`: the bullets the applicant approved word for word; a résumé worker builds only from
  `status: approved`, and `text_ats` is used exactly as written.
- `applicant-profile.example.yml`: the machine-readable twin of the answers file, for a form-filling worker. Keep it
  in step with the answers file and the résumé's work history.

## Licences

`ohmycv-theme.css`, `ohmycv-ats.css`, `minimal-base.css` and the scripts are this kit's own (MIT). The editor's base
stylesheet (`ohmycv-base.css`) is upstream junian/markdown-resume (AGPL-3.0) / Renovamen/oh-my-cv (GPL-3.0) code and
is fetched on demand, never committed here.
