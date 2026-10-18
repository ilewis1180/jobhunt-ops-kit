#!/usr/bin/env python3
"""Lint a markdown-resume file before pushing it to the editor or building a PDF.

Catches the failure modes that are silent in the app: broken YAML front matter, legacy icon markup that renders as
nothing, definition-list indentation that turns into a code block, and the house rules you choose.

    python3 check_resume.py ATS-Example.md
    python3 check_resume.py --shape ats --max-pages-hint 2 *.md
    python3 check_resume.py --shape display --max-skills 15 --skills-sep '|' Display-Example.md

Shapes:
  ats      the flat shape for upload portals: no definition lists, no markdown bullets, no icons; entries are
           `**Title | Company | Mon YYYY - Mon YYYY**<br>` lines with literal `•` bullet paragraphs; one skill per
           line ending in <br> (a wrapped pipe-separated skills line fragments in extraction)
  display  the three-column definition-list shape (`**Title**` / `~ Company · Location` / `~ Dates`), icons allowed
  any      (default) only the dialect checks, no shape rules
"""
import argparse
import re
import sys

try:
    import yaml
except ImportError:
    yaml = None

ENTRY_LINE = re.compile(r"^\*\*[^*|]+\|[^*|]+\|\s*[A-Z][a-z]{2} \d{4} - (?:[A-Z][a-z]{2} \d{4}|Present)\*\*<br>\s*$")
DATE_RANGE = re.compile(r"\b[A-Z][a-z]{2} \d{4}\s*[–—]\s*(?:[A-Z][a-z]{2} \d{4}|Present)")


def check(path, shape, max_skills, skills_sep, forbid):
    errs, warns = [], []
    text = open(path, encoding="utf-8").read()

    # --- front matter -------------------------------------------------
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        errs.append("no YAML front matter starting on line 1 (the app treats the whole file as body and renders no header)")
        body = text
    else:
        fm_raw, body = m.group(1), m.group(2)
        if yaml is None:
            warns.append("PyYAML not installed; front matter not parsed")
        else:
            try:
                fm = yaml.safe_load(fm_raw) or {}
            except yaml.YAMLError as e:
                errs.append(f"front matter is not valid YAML ({e.__class__.__name__}); the app fails silently and shows a stale header")
                fm = {}
            if not fm.get("name"):
                warns.append("front matter has no 'name'; no centred <h1> will render")
            for i, item in enumerate(fm.get("header") or []):
                if not isinstance(item, dict) or "text" not in item:
                    errs.append(f"header[{i}] has no 'text'")

    # --- icons --------------------------------------------------------
    legacy = len(re.findall(r'<span class="iconify"', text))
    if legacy:
        errs.append(f'{legacy} legacy <span class="iconify"> tag(s): the current runtime does not hydrate them; they render '
                    'as nothing. Use <iconify-icon icon="..."></iconify-icon>')
    if shape == "ats" and "iconify" in body:
        errs.append("ats shape: icons are not allowed (they never reach the PDF text layer)")

    # --- body H1 ------------------------------------------------------
    if re.search(r"^# ", body, re.M):
        warns.append("body contains an H1; the name should come from front matter or it will not get the centred header styling")

    # --- definition lists ---------------------------------------------
    deflist_lines = 0
    for n, line in enumerate(body.split("\n"), 1):
        mm = re.match(r"^(\s*)([~:])(\s?)", line)
        if not mm:
            continue
        deflist_lines += 1
        indent, marker, space = mm.groups()
        if len(indent) >= 4:
            errs.append(f"line {n}: '{marker}' indented {len(indent)} spaces; 4+ becomes a code block. Use 2.")
        elif len(indent) != 2:
            warns.append(f"line {n}: '{marker}' indented {len(indent)} spaces; 2 is the convention")
        if not space:
            errs.append(f"line {n}: no space after '{marker}'; the marker is not recognised")
    if shape == "ats" and deflist_lines:
        errs.append(f"ats shape: {deflist_lines} definition-list line(s); flex columns set off multi-column and table flags in parsers")
    if shape == "ats" and re.search(r"^[-*] ", body, re.M):
        errs.append("ats shape: markdown bullets found; use literal '•' paragraphs (CSS-drawn markers never reach the text layer)")
    if shape == "ats" and DATE_RANGE.search(body):
        errs.append("ats shape: a date range uses an en/em dash; use an ASCII hyphen (`Mon YYYY - Mon YYYY`), some parsers flag special characters")
    if shape == "ats":
        entries = [ln for ln in body.splitlines() if ln.startswith("**") and "|" in ln]
        bad = [ln for ln in entries if not ENTRY_LINE.match(ln)]
        if bad:
            warns.append(f"ats shape: {len(bad)} entry line(s) do not match `**Title | Company | Mon YYYY - Mon YYYY**<br>` "
                         f"(first: {bad[0][:60]!r}); parsers split roles on a line with a date range")
        if re.search(r"^## Education\s*&\s*Certification", body, re.M | re.I):
            errs.append("ats shape: '## Education & Certification' is recognised by no engine; split into '## Education' and '## Certifications'")

    # --- line breaks ---------------------------------------------------
    if re.search(r"\S  \n", body):
        warns.append("trailing double-space line break found; breaks:false makes this unreliable, prefer an explicit <br>")

    # --- skills ---------------------------------------------------------
    sk = re.search(r"^## (?:Technical |Core )?Skills\s*\n\s*\n(.+?)(?=\n\s*\n|\Z)", body, re.S | re.M)
    if sk:
        block = sk.group(1).strip()
        if shape == "ats":
            lines = [ln for ln in block.splitlines() if ln.strip()]
            if len(lines) == 1 and "|" in block:
                errs.append("ats shape: skills are one pipe-separated line; a wrapped line fragments in extraction. One skill per line, each ending in <br>")
            missing_br = [ln for ln in lines[:-1] if not ln.rstrip().endswith("<br>")]
            if missing_br:
                warns.append(f"ats shape: {len(missing_br)} skills line(s) without a trailing <br> (breaks:false joins them into one line)")
            if max_skills and len(lines) > max_skills:
                errs.append(f"skills block has {len(lines)} items; the cap is {max_skills}")
        else:
            line = block.replace("\n", " ")
            n = len([p for p in line.split(skills_sep) if p.strip()]) if skills_sep else 0
            if max_skills and n > max_skills:
                errs.append(f"skills line has {n} items; the cap is {max_skills}")
            if skills_sep and "·" in line and skills_sep not in line:
                warns.append(f"skills line uses '·'; this corpus separates skills with ' {skills_sep} '")

    # --- house rules: forbidden strings ----------------------------------
    for kw in forbid:
        if kw and kw in body:
            errs.append(f"contains {kw!r} (forbidden by --forbid: a résumé must not reference notes or another résumé)")

    return errs, warns


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--shape", choices=("ats", "display", "any"), default="any")
    ap.add_argument("--max-skills", type=int, default=0, help="cap on skills items (0 = no cap)")
    ap.add_argument("--skills-sep", default="|", help="display shape: the separator between skills on one line")
    ap.add_argument("--forbid", action="append", default=["notes.md"], help="a string a résumé must never contain (repeatable)")
    a = ap.parse_args()
    bad = 0
    for p in a.paths:
        errs, warns = check(p, a.shape, a.max_skills, a.skills_sep, a.forbid)
        status = "FAIL" if errs else ("warn" if warns else "ok")
        print(f"\n{status.upper():5} {p}")
        for e in errs:
            print(f"  error: {e}")
        for w in warns:
            print(f"  warn : {w}")
        bad += bool(errs)
    print(f"\n{len(a.paths)} file(s), {bad} with errors")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
