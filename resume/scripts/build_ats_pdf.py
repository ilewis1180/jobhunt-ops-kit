#!/usr/bin/env python3
"""Render a flat ATS-shaped résumé (markdown) to PDF locally, without the editor.

The editor's HTML export is the normal path, but a browser blocks repeated automatic downloads, which silently leaves a
STALE file in the downloads folder and produces a PDF of the previous revision. This renders from the .md on disk so
what you get is always what you last edited, and checks the result the way an ATS parser sees it.

Only the ATS shape of the dialect is handled: front-matter header, ## / ### headings, **bold**, <br>, blank-line
separated paragraphs. No definition lists, no markdown bullet lists, no icons: the ATS shape deliberately uses none of
those (CSS-drawn bullets and flex columns never reach the PDF text layer). The script refuses such a file rather than
render it wrong; use the editor's print dialog for a display-shaped résumé.

    python3 build_ats_pdf.py ATS-Example.md out/ATS-Example.pdf
    python3 build_ats_pdf.py ATS-Example.md out/x.pdf --css-dir ../css --base-css minimal-base.css --max-pages 2
    python3 build_ats_pdf.py ATS-Example.md out/x.pdf --chrome "/path/to/chrome" --expect-name "Alex Example"

Needs a Chromium-based browser (auto-detected on macOS, Linux and Windows, or --chrome / $CHROME) and `pdftotext`
(poppler) for the checks; without pdftotext the PDF is still written and the checks are skipped.
"""
import argparse
import html
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSS_DIR = os.path.join(os.path.dirname(HERE), 'css')

# mirrors the editor record's `styles` object (resume/references/css-and-layout.md)
FONT_EN, FONT_SIZE, LINE_HEIGHT = "Verdana", 12, 1.3
MARGIN_V, MARGIN_H, PARA_SPACE = 55, 45, 5

CHROME_CANDIDATES = {
    'Darwin': ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
               '/Applications/Chromium.app/Contents/MacOS/Chromium',
               '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
               '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'],
    'Linux': ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge'],
    'Windows': [r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
                r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'],
}


def find_chrome(explicit=None):
    for c in [explicit, os.environ.get('CHROME')] + CHROME_CANDIDATES.get(platform.system(), []):
        if not c:
            continue
        if os.path.exists(c):
            return c
        w = shutil.which(c)
        if w:
            return w
    sys.exit('no Chromium-based browser found: pass --chrome <path> or set $CHROME')


def split_front_matter(text):
    if not text.startswith("---"):
        sys.exit("no front matter")
    end = text.index("\n---", 3)
    return text[4:end], text[end + 4:].lstrip("\n")


def parse_header(fm):
    m = re.search(r"^name:\s*(.+)$", fm, re.M)
    if not m:
        sys.exit("front matter has no name:")
    name = m.group(1).strip()
    items = []
    for block in re.findall(r"^\s*-\s+text:\s*(.+?)(?=^\s*-\s+text:|\Z)", fm, re.M | re.S):
        lines = block.strip().splitlines()
        text = lines[0].strip()
        link = None
        for line in lines[1:]:
            lm = re.match(r"\s*link:\s*(.+)$", line)
            if lm:
                link = lm.group(1).strip()
        items.append((text, link))
    return name, items


def inline(s):
    s = html.escape(s, quote=False)
    s = s.replace("&lt;br&gt;", "<br>")
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return s


def render_body(body):
    for bad, why in ((r"^\s{0,3}[~:] ", "definition list"), (r"^[-*] ", "markdown bullet list")):
        if re.search(bad, body, re.M):
            sys.exit(f"refusing: file contains a {why}; this renderer does not handle it (use the editor's print dialog)")
    if "iconify" in body:
        sys.exit("refusing: file contains iconify markup")
    out = []
    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        if not block:
            continue
        m = re.match(r"^(#{2,3})\s+(.*)$", block)
        if m:
            tag = "h%d" % len(m.group(1))
            out.append(f"<{tag}>{inline(m.group(2))}</{tag}>")
        else:
            out.append(f"<p>{inline(block)}</p>")
    return "\n".join(out)


def read_css(css_dir, names):
    parts = []
    for n in names:
        p = n if os.path.isabs(n) else os.path.join(css_dir, n)
        if not os.path.exists(p):
            sys.exit(f"css file missing: {p} (see resume/css/README.md: the upstream base stylesheet is fetched, not shipped)")
        parts.append(open(p, encoding="utf-8").read())
    return "\n".join(parts)


def build_html(md_path, css):
    src = open(md_path, encoding="utf-8").read()
    fm, body = split_front_matter(src)
    name, items = parse_header(fm)
    spans = []
    for i, (text, link) in enumerate(items):
        cls = "resume-header-item" + (" no-separator" if i == len(items) - 1 else "")
        inner = f'<a href="{html.escape(link)}">{html.escape(text)}</a>' if link else html.escape(text)
        spans.append(f'<span class="{cls}">{inner}</span>')
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
@page {{ size: letter; margin: {MARGIN_V}px {MARGIN_H}px; }}
html, body {{ margin: 0; padding: 0; }}
#vue-smart-pages-preview {{
  font-family: {FONT_EN}, sans-serif;
  font-size: {FONT_SIZE}px;
  line-height: {LINE_HEIGHT};
}}
#vue-smart-pages-preview p {{ margin-bottom: {PARA_SPACE}px; }}
{css}
</style></head><body>
<div class="vue-smart-pages" id="vue-smart-pages-preview">
<div class="resume-header"><h1>{html.escape(name)}</h1>
{chr(10).join(spans)}
</div>
{render_body(body)}
</div></body></html>""", name


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('markdown')
    ap.add_argument('pdf')
    ap.add_argument('--css-dir', default=DEFAULT_CSS_DIR, help=f'folder with the css files (default {DEFAULT_CSS_DIR})')
    ap.add_argument('--base-css', default='ohmycv-base.css', help='the editor\'s base stylesheet (fetched; or minimal-base.css)')
    ap.add_argument('--theme-css', default='ohmycv-theme.css')
    ap.add_argument('--ats-css', default='ohmycv-ats.css', help='the extraction overrides (h1 letter-spacing, hyphens)')
    ap.add_argument('--chrome', help='browser binary (default: auto-detect, or $CHROME)')
    ap.add_argument('--max-pages', type=int, default=2, help='warn when the PDF runs past this many pages')
    ap.add_argument('--expect-name', help='the first extracted line must equal this (catches letter-spacing damage)')
    ap.add_argument('--html-only', action='store_true', help='write the HTML next to the PDF path and stop (no browser needed)')
    a = ap.parse_args()

    css = read_css(a.css_dir, [a.base_css, a.theme_css, a.ats_css])
    page, name = build_html(a.markdown, css)
    out = os.path.abspath(a.pdf)
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    if a.html_only:
        hp = os.path.splitext(out)[0] + '.html'
        open(hp, 'w', encoding='utf-8').write(page)
        print(f'{hp}: html written ({len(page)} chars); no PDF (--html-only)')
        return 0
    chrome = find_chrome(a.chrome)
    with tempfile.TemporaryDirectory(prefix='ats-render-') as td:
        tmp = os.path.join(td, 'render.html')
        open(tmp, "w", encoding="utf-8").write(page)
        r = subprocess.run([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={out}", "file://" + tmp], capture_output=True, text=True)
    if not os.path.exists(out):
        sys.exit(f'browser wrote no PDF ({chrome}): {r.stderr.strip()[:300]}')
    if not shutil.which('pdftotext'):
        print(f'{out}: written; pdftotext not found, checks skipped')
        return 0
    txt = subprocess.run(["pdftotext", "-layout", out, "-"], capture_output=True, text=True).stdout
    pages = txt.count(chr(12))
    bullets = sum(1 for line in txt.splitlines() if line.strip().startswith(chr(0x2022)))
    non_ascii = sorted({c for c in txt if ord(c) > 127 and c != '\u2022'})
    first = txt.strip().splitlines()[0].strip() if txt.strip() else ''
    print(f"{out}: {pages} page(s), soft-hyphens {txt.count(chr(0x2010))}, bullet lines {bullets}, "
          f"non-ascii chars {''.join(non_ascii) or 'none'}")
    print("  first line:", repr(first))
    rc = 0
    if pages > a.max_pages:
        print(f"  WARNING: over {a.max_pages} pages", file=sys.stderr)
        rc = 1
    if txt.count(chr(0x2010)):
        print("  WARNING: U+2010 soft hyphens in the text layer (hyphens: auto leaked)", file=sys.stderr)
        rc = 1
    expect = a.expect_name or name
    if first != expect:
        print(f"  WARNING: first line is not the name {expect!r} (letter-spacing or header damage)", file=sys.stderr)
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
