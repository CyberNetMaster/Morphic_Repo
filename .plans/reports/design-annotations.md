# Design annotations: Geist type system and the Describe step

Applied on 2026-10-22 against `design-refs/brief.md`. Everything stayed on this computer: no push, no remote change, no pull request, no upload. No LLM call was made (screens come from `.plans/reports/polish_capture_app.py`, which switches the adapter off). No key was printed. No engine module under `morphic/` changed and no computed value changed.

One network action was needed once: the Geist font package (`geist` 1.8.2) was downloaded from the npm registry so its files could be bundled. At run time nothing is fetched; the two font files are read from `app/static/fonts/` and inlined.

## Global: typeface and type scale

| Item | What was done | Where |
|---|---|---|
| Geist and Geist Mono | `Geist-Variable.woff2` and `GeistMono-Variable.woff2` (weights 100 to 900) plus `LICENSE.txt` (SIL Open Font License 1.1) sit in `app/static/fonts/`. `theme.font_face_css()` emits two `@font-face` rules with the files inlined as data URIs; the app injects them once per session (Streamlit caches the unchanging message by hash). Inlining was chosen over Streamlit's static server because that server only serves the main script's own `static/` folder, which the screenshot fixtures do not share. | `app/theme.py`, `app/ui.py` |
| Font stacks | `FONT_SANS = Geist, …`, `FONT_MONO = 'Geist Mono', …`; `.streamlit/config.toml` mirrors both (`font`, `headingFont`, `codeFont`) so Streamlit's own widgets use them too. A test asserts the mirror and that no `http` appears in the font CSS. | `app/theme.py`, `.streamlit/config.toml` |
| Type scale tokens | `TEXT_DISPLAY = 36` with `TRACK_DISPLAY = -0.02em` (page titles, the wordmark); `TEXT_XL`/`TEXT_LG` headings at `WEIGHT_SEMIBOLD = 600` with `TRACK_HEADING = -0.01em`; body `TEXT_MD = 15` at `WEIGHT_REGULAR = 400`, `LINE_BODY = 1.5`; eyebrow `TEXT_XS = 11`, uppercase, `WEIGHT_MEDIUM = 500`, `EYEBROW_TRACKING = +0.08em`, secondary color. | `app/theme.py` |
| Tabular figures | `font-variant-numeric: tabular-nums` and `"tnum"` on the root, so every number lines up in both faces. | `app/theme.py` |
| Mono for numerals and technical values | Hero numbers, readouts, the funnel counts, scale marks, `.mx-num` values, step numbers, chart tick labels, the drawing's force and dimension labels, and the character count are set in Geist Mono. `ui.pill` and `ui.table` detect a value that starts with a number (or a sign, `$`, `~`, `#` or a comparison before one) and set it in mono; names and status words stay in Geist. | `app/theme.py`, `app/ui.py`, `app/maps.py` |

The scale is applied through the tokens, so every step and the Validation tab pick it up, not only the Describe elements below.

## Page feedback on Describe

| # | Annotation | What was done |
|---|---|---|
| 1 | Brand wordmark | `ui.logomark()` draws an original mark: one node branching to two along a strut, with a thin inner web, in the accent gradient (`ACCENT_LIGHT` to `ACCENT`) with a soft white sheen along its top edge and a faint glow. "Morphic" sits beside it in Geist semibold with `-0.02em` tracking. The whole top row (wordmark, step pills, Design/Validation switch) is one container, `st-key-topbar`: frosted glass (`glass` token, 18 px blur), a hairline bottom edge, rounded bottom corners, sticky at the top of the scroll. The two style-only markdown elements that used to push the bar down are hidden, so the bar is flush with the top. |
| 2 | Tagline | `.mx-sub`: Geist regular at 17 px (one step above body), secondary grey, `max-width: 60ch`, line height 1.5. It is tucked under the title (8 px) with the larger gap below it (24 px), so it reads as part of the title block. |
| 3 | Description box | A frosted surface (`glass_input` token, a touch lighter than its card, 14 px backdrop blur) with a soft inner shadow and a hairline inset ring, 22 px radius, 24/32 px padding, text at 18 px. On focus the ring becomes a soft accent glow instead of an outline; the resize grip is gone. The placeholder is a realistic bracket description. A row of example pills (RC car arm, Drone arm, Aerospace bracket: the three demo parts, which are the real texts available) fills the box with that demo's text; a character count in Geist Mono sits inside the bottom-right of the box. |
| 4 | "Run" eyebrow | Every `.mx-eyebrow` now starts with a short accent line (10 × 2 px) before the label. Process-colored eyebrows and colored stage eyebrows use their own color for the line. |
| 5 | "Or a sketch" | A hairline divider with "or" centered on it separates the text box from the sketch option; the eyebrow reads "Sketch photo" and takes the same treatment. The drop zone is a dashed-edge glass card with an original pencil-and-strut icon and the one-line helper text; its Upload button keeps the input tone. |
| 6 | Notes | `ui.footnote()`: a small info glyph, Geist at 13 px in the secondary color, a faint left bar and a barely tinted field. Applied to the standalone notes: the Quick mode note on Describe, the drawing legend on Check, the Pareto and fill-level notes on Compare, the four Validation notes and the Export bundle note. Inline sub-lines inside the design cards stay plain notes. |
| 7 | "What happens next" | `ui.flow()`: three numbered pills (Check, Generate, Export) joined by thin lines, the next step lit in the accent, the rest muted. |

## Files

| File | Change |
|---|---|
| `app/static/fonts/` | New: the two Geist variable files and the OFL license. |
| `app/theme.py` | Font stacks and `font_face_css()`; the type scale tokens; `ACCENT_LIGHT`, `glass_input`; top bar, wordmark, title, tagline, eyebrow indicator, Describe box, count, example pills, or-divider, footnote, flow; mono on numerals; the style-only element rule. |
| `app/ui.py` | `logomark`, `is_numeric`, numeric-aware `pill` and `table`, `footnote_html`, `footnote`, `flow`, `or_divider`; `inject_css` emits the fonts. |
| `app/streamlit_app.py` | The top bar container; count, example pills, divider and flow on Describe; footnotes on the other steps. |
| `app/sketch_upload.py` | Glass dashed drop zone with its icon; eyebrow "Sketch photo". |
| `app/maps.py` | Drawing force and dimension labels in Geist Mono. |
| `.streamlit/config.toml` | Geist font stacks. |
| `tests/test_app.py` | Four new tests: fonts bundled and inlined with no external URL, numerals in mono, the Describe pieces, and an example pill filling the description through AppTest. |

## Checks run

- Full suite: `python -m pytest -p no:cacheprovider --junitxml=.plans/reports/polish-tests.xml`: 201 passed, 0 failed, 0 errors, 0 skipped (122 s).
- In the browser (headless Chrome, 1440 px): `document.fonts.check` reports both Geist faces loaded from the inlined rules; the top bar's box starts at y = 0; the footnote keeps a 12 px gap to the button below it.
- All 13 screens in `.plans/reports/screens/` retaken (`shoot.py 8797` and `phase3_extra_screens.py` against the offline capture app).

## Notes

- Two Streamlit layout facts were measured and worked around: a raw-HTML markdown block ends 16 px short (the container's `margin-bottom: -1rem` is meant for a trailing paragraph), so an HTML block's visible gap below equals its own `margin-bottom`; and every style-only markdown element costs one 16 px flex gap unless hidden.
- The sticky glass bar was checked in full-page captures only; with a scrolled viewport the content passes under it, which the captures cannot show.
