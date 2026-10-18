# mdresume storage, backup and export

Source: `site/src/utils/database.ts`, `site/src/composables/resumeExport.ts`, `site/src/i18n/en.yaml` — **`master`** branch.

## Data model

One localForage entry holds every résumé:

```ts
const MARKDOWN_RESUME_KEY = "MARKDOWN_RESUME_data";
```

(Older builds used `ohmycv_data`. There is no migration code; data under the old key is stranded.)

```ts
type ResumeStorageItem = {
  name: string;
  markdown: string;
  css: string;        // full copy, per résumé
  styles: ResumeStyles;
  update: string;     // epoch ms
};
type ResumeStorage = { [id: string]: ResumeStorageItem };
```

IDs are epoch-milliseconds strings and double as the creation timestamp. The list sorts by `update` as a **string** compare, which only works while all IDs have the same digit length.

## Backup and restore

On the **My Resumes** page, top right: **Backup DB …** and **Restore DB …** (upstream calls these "Save as…" and "Import from…"; this build renames them). Backup is <kbd>⇧⌘S</kbd>; save inside the editor is <kbd>⌘S</kbd>.

Backup writes the storage object verbatim — no wrapper, no version field:

```json
{ "1788556441182": { "name": …, "markdown": …, "css": …, "styles": {…}, "update": … } }
```

It goes through a `data:` URI, so very large sets can hit a practical ceiling.

**Restore merges; incoming wins.** `{ ...existing, ...imported }`. Reusing an ID overwrites that record; a new ID adds one. Nothing is ever deleted by a restore, so repeated restores with fresh IDs accumulate duplicates.

### The validator — why a restore fails silently

`check()` type-checks, then shows one toast ("Data format is invalid.") with no field name and no console log.

Per record: `name`, `markdown`, `css` must be strings; `styles` must be an object; `update` string or undefined.
Per `styles`: `fontSize`, `lineHeight`, `marginH`, `marginV`, `paragraphSpace` numbers; `paper`, `themeColor` strings; `fontCJK` and `fontEN` objects each with a string `name`.

Traps:
- **`css` is required.** Omit it and the import dies silently.
- All nine `styles` fields are required.
- `paper` is checked only as a *string*, not against `A4`/`letter` — a bad value passes validation and breaks rendering later.
- `styles: null` passes `typeof … === "object"` then throws inside `check`, which is uncaught — **no toast at all**.
- `JSON.parse` failure is likewise uncaught and silent.

Use `scripts/build_backup.py`, which asserts the full shape before writing.

## Other operations

- **New** seeds the stock template plus `DEFAULT_CSS_CONTENT` and `DEFAULT_STYLES` (`themeColor #000000`, `fontEN Verdana`, `fontCJK System CJK`, `fontSize 12`, `marginV 55`, `marginH 45`, `lineHeight 1.3`, `paragraphSpace 5`).
- **Duplicate** deep-clones the whole record — **css and styles included**. This is the practical way to propagate a theme without pasting it five times. It renames via a regex built from the existing name, so names containing regex metacharacters (`C++`, parentheses) can misbehave.
- **Delete has no confirmation.** The trash icon deletes immediately. Back up first.
- **Import Markdown** replaces only the markdown of the open résumé — css, styles and name are untouched — and does **not** persist. You still have to save. There is no confirmation, so it silently discards unsaved edits. The URL variant fetches any origin.

## Exports

| Export | Mechanism | Fidelity |
|---|---|---|
| **PDF** | `window.print()` | **The only faithful export.** Layout preserved. |
| **HTML** | rendered markdown, images inlined as data URIs | layout preserved, but icons come from a **live CDN script** — offline, they vanish |
| **Markdown** | raw `mdContent` | front matter included, unrendered |
| **DOCX** | `html-docx-js-typescript` | **avoid** — see below |

### Why not DOCX

`html-docx-js-typescript` is not a real HTML→OOXML converter. It wraps the HTML in an MHT `altChunk` and lets **Word's legacy HTML importer** do the work at open time. Word predates CSS flexbox, so:

- the three-column `dl` rows **flatten into stacked paragraphs** — dates and locations drop onto their own lines
- `<iconify-icon>` custom elements need a script Word will not run, so **every icon silently disappears**
- page geometry is hardcoded **US Letter, 1-inch margins**, ignoring `paper`, `marginV` and `marginH`

If a posting demands `.docx`, produce it another way and read it back before sending. (The exact Word rendering is inferred from the altChunk mechanism, not opened in Word — but the flexbox and script limitations are certain.)
