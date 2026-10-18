#!/usr/bin/env python3
"""Build a markdown-resume editor restore file (the "Restore DB" JSON) from résumé markdown on disk.

The editor's Restore validates the JSON and, if anything is off, shows one toast with no field name and no console
log. Some malformed shapes throw uncaught and show nothing at all. This script asserts the full shape before writing,
so a restore either works or you find out here.

Restore MERGES by record id, so reusing ids overwrites the existing records rather than creating duplicates. Which
ids map to which files is YOUR data: give it in a records file (JSON list of {"id", "file", "name"}; see
resume/examples/records.example.json), never hard-code it here.

    python3 build_backup.py --dir ../examples --records ../examples/records.example.json --out /tmp/backup.json
    python3 build_backup.py --dir . --records records.json --base-css ../css/ohmycv-base.css --paper letter

CSS: base first (the editor's own stylesheet, fetched by resume/css/fetch_base_css.sh, or minimal-base.css), then the
theme overrides, then the ATS extraction overrides. The overrides alone strip the layout.
"""
import argparse
import json
import os
import sys

SYSTEM_CJK = (
    'system-ui, -apple-system, "Segoe UI", "PingFang SC", "Hiragino Sans GB", '
    '"Microsoft YaHei", "Microsoft JhengHei", "Yu Gothic", "Meiryo", "Malgun Gothic", '
    '"Apple SD Gothic Neo", "Noto Sans CJK SC", "Noto Sans CJK TC", "Noto Sans CJK JP", '
    '"Noto Sans CJK KR", "Noto Sans SC", "Noto Sans TC", "Noto Sans JP", "Noto Sans KR", '
    '"WenQuanYi Micro Hei", "Droid Sans Fallback", sans-serif'
)

VALID_PAPER = ("A4", "letter")  # lowercase 'letter': "Letter" blanks the preview


def build_styles(paper, font_size, theme, font_en, margin_v, margin_h, line_height, para_space):
    return {
        "marginV": margin_v, "marginH": margin_h, "lineHeight": line_height, "paragraphSpace": para_space,
        "themeColor": theme,
        "fontCJK": {"name": "System CJK", "fontFamily": SYSTEM_CJK},
        "fontEN": {"name": font_en},
        "fontSize": font_size,
        "paper": paper,
    }


def validate(storage):
    """Mirror of the app's check(), plus the paper-key check it omits."""
    problems = []
    for rid, r in storage.items():
        if not rid.isdigit():
            problems.append(f"{rid}: record ids are epoch-millisecond digit strings")
        for k in ("name", "markdown", "css"):
            if not isinstance(r.get(k), str):
                problems.append(f"{rid}: '{k}' must be a string")
        if not isinstance(r.get("update"), (str, type(None))):
            problems.append(f"{rid}: 'update' must be a string or absent")
        s = r.get("styles")
        if not isinstance(s, dict):
            problems.append(f"{rid}: 'styles' must be an object")
            continue
        for k in ("fontSize", "lineHeight", "marginH", "marginV", "paragraphSpace"):
            if not isinstance(s.get(k), (int, float)) or isinstance(s.get(k), bool):
                problems.append(f"{rid}: styles.{k} must be a number")
        for k in ("paper", "themeColor"):
            if not isinstance(s.get(k), str):
                problems.append(f"{rid}: styles.{k} must be a string")
        for k in ("fontCJK", "fontEN"):
            if not isinstance(s.get(k), dict) or not isinstance(s[k].get("name"), str):
                problems.append(f"{rid}: styles.{k} must be an object with a string 'name'")
        if s.get("paper") not in VALID_PAPER:
            problems.append(f"{rid}: styles.paper is {s.get('paper')!r}; must be one of {VALID_PAPER}. "
                            "An invalid key passes the app's own validation and then blanks the preview.")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=".", help="folder holding the résumé .md files (css paths are relative to it too)")
    ap.add_argument("--records", required=True, help='JSON list of {"id": "<epoch ms>", "file": "<name>.md", "name": "<display name>"}')
    ap.add_argument("--out", default="backup.json")
    ap.add_argument("--base-css", default="ohmycv-base.css", help="the editor's base stylesheet, or minimal-base.css")
    ap.add_argument("--theme-css", default="ohmycv-theme.css")
    ap.add_argument("--ats-css", default="ohmycv-ats.css", help="ATS extraction overrides appended last; '' to skip")
    ap.add_argument("--paper", default="letter", choices=VALID_PAPER)
    ap.add_argument("--font-size", type=int, default=12)
    ap.add_argument("--font-en", default="Verdana")
    ap.add_argument("--theme-color", default="#377bb5")
    ap.add_argument("--margin-v", type=int, default=55)
    ap.add_argument("--margin-h", type=int, default=45)
    ap.add_argument("--line-height", type=float, default=1.3)
    ap.add_argument("--paragraph-space", type=int, default=5)
    a = ap.parse_args()

    def rd(name):
        p = name if os.path.isabs(name) else os.path.join(a.dir, name)
        if not os.path.exists(p):
            sys.exit(f"missing: {p}")
        return open(p, encoding="utf-8").read()

    records = json.load(open(a.records, encoding="utf-8"))
    if not isinstance(records, list) or not records:
        sys.exit("--records must be a non-empty JSON list")
    css = rd(a.base_css).rstrip() + "\n\n" + rd(a.theme_css)
    if a.ats_css:
        css += "\n" + rd(a.ats_css)
    styles = build_styles(a.paper, a.font_size, a.theme_color, a.font_en, a.margin_v, a.margin_h, a.line_height,
                          a.paragraph_space)
    storage = {}
    for rec in records:
        for k in ("id", "file", "name"):
            if k not in rec:
                sys.exit(f"record {rec} has no {k!r}")
        storage[str(rec["id"])] = {"name": rec["name"], "markdown": rd(rec["file"]), "css": css, "styles": styles,
                                   "update": str(rec["id"])}
    problems = validate(storage)
    if problems:
        print("Refusing to write; the restore would fail silently:", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        sys.exit(1)
    out = a.out if os.path.isabs(a.out) or os.path.dirname(a.out) else os.path.join(a.dir, a.out)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(storage, f)
    print(f"wrote {out}: {len(storage)} records, css {len(css)} chars, paper {a.paper}")
    print("Restore via My Resumes -> 'Restore DB ...'. It merges by id, so these records overwrite in place.")


if __name__ == "__main__":
    main()
