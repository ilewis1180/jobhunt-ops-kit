# mdresume CSS, styling and pagination

Source: `site/src/assets/default-resume.css.txt`, `site/src/utils/css.ts`, `site/src/utils/constants/data.ts`, `packages/vue-smart-pages/src/utils/breakPage.ts` — all on **`master`**.

## How CSS gets in

Everything is scoped by one ID selector:

```ts
export const PREVIEW_SELECTOR = "#vue-smart-pages-preview";
```

The shipped sheet has that prefix baked into every rule. Your CSS from the editor's CSS tab is injected **raw and unscoped** via `injectCSS` — no sanitization, no automatic scoping. It only behaves because you keep writing the prefix. An unprefixed rule leaks to the whole app.

Two separate sheets exist: `oh-my-cv-backbone-preview` (the CSS tab) and `oh-my-cv-dynamic-preview` (generated from the style knobs). Both are single-ID specificity, so **which wins depends on injection order** — verify empirically rather than assuming your rule beats a knob.

**CSS is stored per résumé.** Each record carries its own full copy. Editing one résumé's CSS changes nothing elsewhere. Duplicating a résumé copies `css` and `styles` along with the markdown, which is the cheap way to propagate a theme by hand.

## The style knobs

`ResumeStyles` has exactly nine fields. What each actually does:

| Key | Unit | Effect |
|---|---|---|
| `marginV` | px | preview padding-top. **Bottom is `max(marginV - 10, 10)`** — deliberately smaller than the top. |
| `marginH` | px | left/right padding |
| `lineHeight` | unitless | `p, li`; `h2, h3` get `×1.154`; `dl` gets `×1.038` |
| `paragraphSpace` | px | **`h2 { margin-top }` only.** Nothing else. |
| `themeColor` | hex | see below |
| `fontEN`, `fontCJK` | `{name, fontFamily?}` | `font-family: <EN>, <CJK>` on the root |
| `fontSize` | px | root only; everything else is `em`-relative |
| `paper` | `"A4"` \| `"letter"` | page geometry + `@page size` |

`themeColor` applies to exactly three things — nothing else is themed:

```css
#id :not(.resume-header-item) > a { color: … }   /* body links, not header contacts */
#id h1, #id h2, #id h3 { color: … }
#id h2 { border-bottom-color: … }
```

## Paper — the key that breaks things

```ts
export const PAPER = {
  A4:     { h: 297 + 2,   w: 210 },
  letter: { h: 279.4 + 3, w: 215.9 }
};
export const MM_TO_PX = 3.78;
```

**The keys are `A4` and `letter` — lowercase `l`.** The UI shows "Letter" only because the dropdown applies `capitalize` to the raw key. Writing `paper: "Letter"` into storage makes `PAPER["Letter"]` undefined and the renderer throws, blanking the preview.

Resolved page heights: **A4 ≈ 1130 px, letter ≈ 1067 px**. Width goes to CSS in millimetres; height is used as a pixel number.

Usable content height = `pageHeight − marginV − max(marginV − 10, 10)`. At the corpus defaults (marginV 55): **A4 ≈ 1030 px, letter ≈ 967 px.** Letter is shorter but wider, so real content often still fits — measure, don't extrapolate.

## Pagination

```ts
for (const child of Array.from(page.children)) {
  const childH = child.clientHeight + marginTop + marginBottom;
  if (pageH + childH > contentH || child.className === NEW_PAGE) {
    newPage.appendChild(getPageBreakElement(height - pageH - top));
    pageH = 0;
  }
  newPage.appendChild(child.cloneNode(true));
  pageH += childH;
}
```

What this means in practice:

- It walks **only direct children of the preview root** — one level deep. An `<li>` is never a break candidate.
- **Nothing is ever split.** A `<ul>`, `<p>`, `<dl>` or `<h2>` is measured whole and moved whole. This is the single most common cause of "why is half my page empty" — one list that didn't fit got pushed entirely.
- A block taller than a full page overflows past the break rather than splitting.
- No orphan/widow control.
- Breaks are `<div class="vue-smart-page-break">` spacers. Count them: `document.querySelectorAll('.vue-smart-page-break').length + 1` is the page count.
- `\newpage` forces a break via `className === "md-it-newpage"` — note the strict equality, so any extra class defeats it.
- Re-runs debounced 200 ms, after `document.fonts.load` resolves, so measurements are post-webfont.

Cutting content from page 1 does **not** reliably shrink page 2 — it pulls more content down. To lose a page, reduce *total* height.

## Printing and PDF

PDF export is `window.print()`. There is no PDF library. `@page { size: A4 }` / `{ size: letter }` comes from the `paper` key, which is why it must be a valid CSS page-size keyword.

At print time the JS spacer margins are zeroed and replaced with real `page-break-before: always`, so the browser repaginates. On-screen pagination is WYSIWYG approximation, not the authority — check the print preview for anything critical.

One trap: printing while dark mode is on forces every link to black, discarding `themeColor`.

## The corpus override

The base sheet lays entries out as:

```css
#vue-smart-pages-preview dl { display: flex; }
#vue-smart-pages-preview dl dt,
#vue-smart-pages-preview dl dd:not(:last-child) { flex: 1; }
```

`flex: 1` means basis 0, but content still influences the final width — so the middle column starts at a different x on every row and the block reads ragged. The fix, in `css/ohmycv-theme.css`, pins column 1 to a percentage, lets column 2 fill, and pins column 3 flush right and unwrapped. It also sets `text-align: left; hyphens: none` on `dt`/`dd`, because a wrapped title under `text-align: justify` (upstream's default) stretches into visibly uneven word spacing.

Paste **base + overrides, base first**. The overrides alone strip the layout.
