# Workspace polish

Design polish pass over the Streamlit app against `design-refs/brief.md` (dark everywhere). Date: 2026-10-22.

Everything stayed on this computer. There was no push, no remote change, no pull request and no upload. No live LLM call was made: the screenshot server (`.plans/reports/polish_capture_app.py`) switches the adapter off, so the explanation card shows its template fallback. No key was read or printed. No engine module in `morphic/` was changed and no computed value changed; only how values are drawn.

## The four known issues

| Issue | Where | Fix |
|---|---|---|
| Pareto labels overlapped (pa6cf, pla, pa12 sat on each other) | `app/maps.py` `pareto_chart`, `place_labels` | Labels are placed by a small greedy pass in pixel space: each point tries eight slots (top, bottom, right, left, four corners) and takes the first with no overlap with other markers, placed labels or the plot edge, else the least overlap. Ranked points place first. Axis ranges are set explicitly so the placement knows where the points are. The winner gets a soft halo and a bold name. The cost caption moved from the rotated y title to a small line above the plot. |
| Pad names sat on the support symbols (hinge on its pin triangle, shock on its rollers) | `app/maps.py` `problem_drawing`, `pad_label_side` | A pad name takes the first free side of its pad: below by default, above when a pin or slide_x draws under it, right or left when a load arrow also comes from the free side. Names are 12 px. |
| The "Curb hit" force label was clipped at the right edge of the drawing | `app/maps.py` `problem_drawing` | Load arrows are computed before anything is drawn; the axes widen to hold every arrow tail and its label. The arrow label is now just the force ("40 N") in the case color; the name and limit are in the matching pill under the drawing. |
| Thin cell borders on the Validation tables (and the Run plan and Fill levels tables) | `app/theme.py` `.mx-table` | Streamlit's markdown table styles drew a full grid through the HTML tables. The theme now resets every cell border and keeps one hairline between rows and under the header. Pills inside cells lose their outer margin. |
| Deprecated `use_container_width=True` (12 calls) | `app/streamlit_app.py` | `width="stretch"` on every button, download button and data editor. A test asserts the old name is gone. |

## Audit findings and what was applied

Severity follows the UI polish skill: HIGH breaks an interaction, MEDIUM is a visible inconsistency, LOW is isolated polish. Every row below was applied.

| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| HIGH | `app/theme.py` buttons | `:active` scaled every button, including disabled ones; hover lift on touch latches as a stuck state | `:not(:disabled):active` scales to 0.96 over 150 ms ease-out; hover rules sit under `@media (hover: hover)`; `-webkit-tap-highlight-color: transparent` | Press scales to 0.96; hover only on hover-capable pointers |
| HIGH | `app/theme.py` reduced motion | `* { animation: none }` removed the check-mark draw entirely (the stroke stayed hidden at dash offset 24) | Cards cross-fade (150 ms opacity); the check mark is drawn static; meters show their final width | Reduced motion gets an opacity fade, not a missing element |
| MEDIUM | `app/theme.py` `[class*="st-key-agent"]` | The glass panel style matched the three agent buttons too (each button sat in its own large dark box) | `.st-key-agent_panel` only | Same detail done two ways |
| MEDIUM | `app/streamlit_app.py` stage view switch | The key `stage_seg` matched the `st-key-stage` card rule, so the Shape/Stress control had a stage of its own | Key renamed to `view_seg` | Same |
| MEDIUM | `app/theme.py` keyframes | `mxrise` ended on `opacity: 1; filter: none` with fill mode both, so quiet (filtered or failed) cards never reached their 0.6 opacity and desaturation | Keyframes name only the start; the end is the element's own style. Quiet cards are now visibly quieter, as the brief asks | Failed materials visibly quieter, never hidden |
| MEDIUM | `app/theme.py` entrances | 8 px rise over 420 ms on a custom curve | 12 px rise, 4 px blur, 300 ms ease-out (`RISE_PX`, `RISE_BLUR_PX`, `RISE_MS`, `EASE_OUT` tokens) | Stagger and entrance values from the skill |
| MEDIUM | `app/theme.py` Streamlit alerts, dialog, slider, chips, toggle, `st.text` | Default Streamlit look: blue info boxes, square chips in solid blue, a value bubble on the growth scrubber duplicating the iteration readout, a plain dialog | Alerts take the app's message style (soft tint per level); multiselect chips are accent-soft pills; the scrubber thumb has no bubble; the 3D dialog is a raised card with `overscroll-behavior: contain`; toggles get an inset track and a lit knob; `st.text` is small mono in the secondary tone | Brief: never default widgets |
| MEDIUM | `.streamlit/config.toml` | Streamlit's own widgets used its defaults for borders, radius and font | `borderColor`, `dataframeBorderColor` (raised tone), `dataframeHeaderBackgroundColor` (inset tone), `showWidgetBorder = false`, `baseRadius = 16px`, `buttonRadius = full`, the app's font stacks. A test checks the mirror against `theme.py` | One palette, one radius, one font |
| MEDIUM | `app/maps.py` Validation plots | Legends sat on the lines; the mesh chart showed Plotly's log ticks (2 3 4 … 10 2 3) and a dozen percent ticks; the "3% target" label was missing (Plotly places an hline label at the raw value on a log axis) | Legends above the plot; ticks at the actual mesh sizes; percent ticks per decade; the target label is placed by hand at log10(tol); the hole plot's label moved where no point sits | Elegant charts: thin lines, minimal gridlines |
| LOW | `app/theme.py` radii | Readouts and the Describe box used the card's own 22 px radius while sitting inside a 22 px card at 24 px inset | Inner surfaces use `RADIUS_MD` (16 px); the MBB image uses `RADIUS_SM` through `.mx-img` instead of an inline 8 px | Nested radius hierarchy |
| LOW | `app/streamlit_app.py` spacing | Inline pixel margins (6, 8, 10, 14 px) on pill rows and notes | `.mx-pills`, `.mx-block`, `.mx-block-sm` classes and `theme.SPACE_*` values; `ui.eyebrow(top=True)` gives the second section in a card (13.3 MBB) its gap | Spacing from the theme, one way |
| LOW | `app/theme.py` disabled buttons | A disabled button lost its surface and read as floating text ("Read my sketch") | 50 % opacity with a hairline inset ring, so the pill stays visible | State needs a static cue |
| LOW | `app/theme.py` `.mx-scale` | 10 px scale text under the readouts | 11 px (`TEXT_XS`) | Smallest size in the scale |
| LOW | `app/theme.py` cards | Shadow ring on the winner card with no border | `border: 1px solid transparent` under the shadow | Forced-colors mode still draws an edge |

Checked and left as they are: the pass/fail/accent colors hold at least 4.5:1 on the card tones; the eyebrow, hero, label and note sizes form one scale across every step; the process tints, pills and funnel already follow the brief; the data editor grid is Streamlit's canvas and takes only the theme colors.

Not verified: hover, press and reduced-motion states were read from the CSS, not replayed in a browser's animation panel. The screenshot run is headless Chrome at 1440 px; narrower windows were not captured.

## Files

| File | Change |
|---|---|
| `app/maps.py` | Pareto label placement (`place_labels`), winner halo, explicit ranges, caption annotation. Drawing: `pad_label_side`, `_pad_label`, arrows computed first, axes widened, short force labels. Validation plots: legends above, explicit ticks, hand-placed target labels. |
| `app/theme.py` | Motion tokens (`EASE_OUT`, `RISE_PX`, `RISE_BLUR_PX`, `PRESS_SCALE`, `PRESS_MS`, `HOVER_MS`), `POINT_HALO_RINGS`; button press and hover rules; table reset; alerts, dialog, slider, chips, toggle; spacing classes; radii; keyframes and reduced motion. |
| `app/streamlit_app.py` | `width="stretch"`; spacing classes; `img(..., cls=)`; the Pareto chart gets the winner; `view_seg` key; 13.3 eyebrow gap. |
| `app/ui.py` | `eyebrow(text, top=False)`. |
| `.streamlit/config.toml` | Border, data editor, radius and font options mirroring `theme.py`. |
| `tests/test_app.py` | Three new tests (label placement, pad label sides and in-range force labels, CSS rules and no deprecated calls) and a wider config mirror check. |
| `.plans/reports/polish_capture_app.py` | New. Screenshot server with every LLM call switched off; delegates to `phase3_capture_app.py` for the sketch and agent fixtures. |
| `.plans/reports/screens/*.png` | All 13 screens retaken. `phase3-extra-screens.json` carries the new hashes. |

## Checks run

- Full suite: `python -m pytest -p no:cacheprovider --junitxml=.plans/reports/polish-tests.xml`: 197 passed, 0 failed, 0 errors, 0 skipped (163 s). Report: `.plans/reports/polish-tests.xml`.
- Screens: `shoot.py 8797` for Describe, Check, Compare, Export and Validation; `phase3_extra_screens.py` for the five sketch screens and the three agent screens. All against `polish_capture_app.py` on port 8797, headless Chrome from the uv cache, nothing downloaded.
- The app on port 8765 that was already running was left alone; it still serves the code it was started with.

## Open points

- Label placement assumes a plot about 640 px wide. In a much narrower window two labels could touch again; the chart would need the real width from the browser to do better.
- The data editor headers still show Streamlit's column-type icons; they are drawn on a canvas and cannot be hidden from CSS.
