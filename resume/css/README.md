# Résumé CSS

| File | What | Licence |
|---|---|---|
| `ohmycv-base.css` | the editor's own default stylesheet; **fetched, not shipped** (`fetch_base_css.sh`) | upstream: junian/markdown-resume AGPL-3.0, from Renovamen/oh-my-cv GPL-3.0 |
| `minimal-base.css` | a small original stand-in with the same selectors, so builds work offline and the example backup contains no copyleft code | MIT (this kit) |
| `ohmycv-theme.css` | column-alignment overrides for the three-column (display) shape | MIT (this kit) |
| `ohmycv-ats.css` | extraction overrides for the ATS shape: `h1` letter-spacing reset, hyphenation off | MIT (this kit) |

Order matters: base first, then theme, then ATS overrides. The overrides alone strip the layout.
