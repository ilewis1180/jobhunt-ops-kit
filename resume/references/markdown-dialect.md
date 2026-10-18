# mdresume markdown dialect

Source of truth: `site/src/utils/markdown.ts` on the **`master`** branch of `junian/markdown-resume`. That file is byte-identical on `main` and `master`, so the pipeline itself is stable — but the default template and icon runtime are not, and only `master` matches this deployment.

The whole pipeline is four lines:

```ts
const { body, attributes } = frontmatter(md);
let html = markdown.render(body);
html = resolveDeflist(html);
html = resolveHeader(html, attributes);
```

There is **no sanitization anywhere** — no DOMPurify, no allowlist. Output goes straight to `innerHTML`. Any HTML you write renders. That is by design for a local single-user editor, and it is why `<br>`, `<u>`, `<small>` and `<iconify-icon>` all work.

## Parser options

```ts
new MarkdownIt({ html: true })
```

That is the entire options object, so everything else is at markdown-it defaults:

| Option | Value | Consequence |
|---|---|---|
| `html` | **true** | raw HTML passes through |
| `breaks` | **false** | a single newline is a *space*. Use `<br>` for a line break. |
| `linkify` | false | bare URLs are not auto-linked; write `[text](url)` |
| `typographer` | false | no smart quotes or dash substitution |

Uses the **default** preset (not `commonmark`), so pipe tables are enabled. Not verified by execution — test before relying on a table.

## Plugins

| Plugin | Adds |
|---|---|
| `markdown-it-deflist` | definition lists (see below) |
| `@ohmycv/markdown-it-katex` | `$inline$` and `$$block$$` TeX |
| `@ohmycv/markdown-it-cross-ref` | `[~Label]:` definitions and `[~Label]` references |
| `@ohmycv/markdown-it-latex-cmds` | `\newpage` and `\\[10px]` |
| `markdown-it-link-attributes` | adds `target="_blank" rel="noopener"` to `http(s)` links |

## Front matter

Delimited by `---` (or `= yaml =`), and it **must start on line 1** — otherwise the whole file is treated as body with no header.

Only two keys are read:

```yaml
---
name: Alex Example
header:
  - text: <iconify-icon icon="tabler:mail"></iconify-icon> alex@example.com
    link: mailto:alex@example.com
  - text: Denver, Colorado
    newLine: true
---
```

- `name` → `<h1>` inside `<div class="resume-header">`, centred by CSS.
- `header[]` → `<span class="resume-header-item">` each. `text` is injected **raw and unescaped** (that is how icons work). `link` wraps it in an anchor. `newLine: true` emits a `<br>` *before* its own item and marks the *previous* item `no-separator`.
- The ` | ` between items is CSS (`.resume-header-item:not(.no-separator)::after`), not markup.

**A YAML parse error is silent.** The parser returns the last successfully parsed attributes from a module-level cache, so a broken header shows the *previous* header rather than erroring. If header edits appear to do nothing, suspect a YAML error.

An empty `---\n---` still emits an empty `.resume-header` div. That is why the stock template uses a body `# Name` heading instead — but note a body `<h1>` sits *outside* `.resume-header` and does not get the centred styling.

## Definition lists — the three-column entry row

```markdown
**Job Title**
  ~ Company · Location
  ~ 2022 – 2024
```

- **Both `~` and `:` work**, identically. A space after the marker is mandatory.
- The marker line must be indented **0–3 spaces**; 4+ becomes a code block. Two spaces is the safe convention this corpus uses.
- Renders `<dt>` + one `<dd>` per marker line, laid out as a flex row.
- **Consecutive entries do not merge.** `markdown-it-deflist` would merge them, but the app post-processes:

  ```ts
  dl.replace(/<\/dd>\n<dt>/g, "</dd>\n</dl>\n<dl>\n<dt>")
  ```

  Every term block becomes its own `<dl>`, so no separator between entries is needed. (Testing with bare `markdown-it` + `markdown-it-deflist` and no post-processing will tell you they merge — that result does not apply to this app.)
- A `~`/`:` line interrupts a preceding paragraph, so no blank line is required before the definitions.

## Custom syntax

| Syntax | Renders | Notes |
|---|---|---|
| `\newpage` | `<div class="md-it-newpage">` | forces a page break. Must be alone on its own line, exact 8-char match. |
| `\\[10px]` | `<div class="md-it-line-break" style="margin-top:10px">` | vertical space. Any CSS unit. No unescaped whitespace inside the brackets. |
| `[~P1]:` … | `<li class="crossref-item" data-caption="P1">` | definition; continuation lines indented 4 spaces |
| `[~P1]` | `<sup class="crossref-ref">` | reference — **only renders if the matching definition exists**, otherwise stays literal text |
| `$x$` / `$$x$$` | KaTeX | `throwOnError: false`; errors render as `<p class='katex-error'>`. `$100 and $200` is safe — a digit after the closing `$` invalidates it. |
| `<iconify-icon icon="tabler:mail"></iconify-icon>` | icon | the current form |
| `![alt](./images/<id>)` | image | served from IndexedDB via a service worker |

## Not supported

- `<span class="iconify" data-icon="…">` — the loaded runtime (iconify-icon 3.0.2) does not hydrate it. It renders as nothing. The editor has a **Migrate Iconify** toolbar tool that rewrites the old form.
- Auto-linked bare URLs.
- Anything relying on `breaks: true`.
