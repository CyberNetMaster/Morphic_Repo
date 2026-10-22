# Workspace E

Design update: dark everywhere, and richer Describe and Check screens.

Date: 2026-10-21. Branch: `emdash/e-design-fr4sx`. Everything stayed on this computer. Nothing was pushed or
uploaded. No remote was added or changed. No engine module in `morphic/` was changed.

The session was interrupted by a power loss partway through. All edits on disk survived. The work was checked,
finished and committed after the restart.

## What changed

### 1. Dark everywhere

- Every step (Describe, Check, Compare, Export) and the Validation tab now use the dark stage and one dark palette.
  The app no longer switches to light for some steps.
- `design-refs/brief.md` now says "Dark everywhere". The rule that kept Describe, Check and Validation near-white
  is removed. The readability line now speaks of the stage, raised cards and inset readouts.
- `.streamlit/config.toml` uses the dark base. Its colors mirror `app/theme.py`, so Streamlit's own widgets
  (data editors, dropdowns, dialogs) match. A test checks that the two files agree.
- The Validation plots and the MBB benchmark image now use the dark palette.
- Amber text on pills and messages now uses a theme value that reads on dark. It was a dark brown before.

### 2. Describe

- **Three preview cards**, one per demo part. Each card shows:
  - the actual cached optimized shape, glowing on its own small dark stage;
  - the winning process and material as the eyebrow;
  - the mass of the lightest passing design and its fill level;
  - the weight saved against the strut design and against the solid block, as pills;
  - the part size, number of load cases and safety factor;
  - an "Open" button that loads the part and goes to Check, as before.
- Every number comes from the part's `results.json` in `examples/cache`. Nothing is typed in by hand. A part
  without a cache shows a plain note instead of a card.
- **A larger, refined input area.** The text box is wider and taller, with larger type and more padding. The
  printer selector, Quick mode and "Read my description" sit beside it.
- **One line for "what happens next"**, under the input area.

| Part | Winner | Mass | Lighter than strut | Lighter than block |
|---|---|---|---|---|
| RC car arm | FDM PA6-CF | 3.9 g | 39% | 84% |
| Drone arm | FDM PA6-CF | 13.3 g | 39% | 47% |
| Aerospace bracket | Metal AlSi10Mg | 111.1 g | 55% | 85% |

### 3. Check

- **The drawing sits on the dark stage.** Each pad has a soft glow made of six faint rings. Pads with a default
  size glow amber. Each load arrow keeps its load-case color and gets a faint wide stroke underneath.
- **Load cases are shown as pills** under the drawing, in the same color as their arrows. Each pill gives the
  name, the force and the deflection limit. Out-of-plane cases say "hand check".
- **Four instrument-style readouts** in a full-width row under the title:
  - safety factor, with its source ("from the text" or "default");
  - deflection limit, the tightest one over the in-plane load cases, with its source;
  - effective minimum wall for your printer's process, with every process listed underneath;
  - run time: "instant" for a precomputed demo part, with the live-run estimate stated. Any other part shows the
    estimate from the S9b timing model.
- Each readout has a tick strip on a stated scale, with a lit pointer at the value.
- The editors, sanity messages, run plan table, Quick mode and "Generate designs" are unchanged.

### 4. Everything else

- Compare and Export are unchanged in layout. They already used the dark palette.
- All new theme values are in `app/theme.py`. This covers the stage gradient, raised button color, pad glow
  rings, arrow glow, readout tick count, preview shape height and the dark amber text.

## Files

| File | Change |
|---|---|
| `app/theme.py` | New dark values. CSS for preview cards, readouts, load-case pills and the Describe input. |
| `app/ui.py` | New `readout` and `lc_pill` pieces. |
| `app/maps.py` | The Check drawing gets pad glows and arrow glows on dark. The drawing now defaults to dark. |
| `app/data.py` | New `demo_preview`, which reads the headline numbers of a cached demo part. |
| `app/streamlit_app.py` | New Describe layout, the Check readouts and pills, dark Validation plots, one dark CSS for all pages. |
| `.streamlit/config.toml` | Dark base theme. |
| `design-refs/brief.md` | "Dark everywhere". |
| `tests/test_app.py` | Four new tests. |

## Checks run

- `uv run pytest`: **156 passed**, 0 failed, 0 skipped, in 1 min 46 s. The report is in
  `.plans/reports/design-tests.xml`.
- The four new tests cover:
  - the readout and load-case pill HTML;
  - that the config, theme and brief agree on dark everywhere;
  - that the preview numbers equal the cached results;
  - that every pad and load arrow gets a glow on dark, and none on light.
- New screenshots are in `.plans/reports/screens/`: `1-describe.png` to `5-validation.png`. They were taken
  with the installed Chrome through `.plans/reports/shoot.py` against a local server on `127.0.0.1:8791`.
- No `.env` exists in this worktree. The Compare explanation therefore used the template fallback, and no
  request went to the LLM provider.

## Notes for the user

- `6-drone-agent.png`, `6-drone-agent-panel.png` and `7-agent-review.png` were **not** retaken. They come from a
  live design-agent run, which needs the LLM key and the network. They still show the earlier look.
- The Check step now reads Quick mode from the toggle's current value. Before, the estimate lagged one rerun
  behind the toggle. The run plan pill uses the same value.
- Existing issue, not changed: on the Check drawing, the pad name under a pin support overlaps the pin triangle.
  The overlap is the same as before. It is now white text on a white triangle, so it is a little harder to read.
- Existing issue, not changed: the Validation tables still show thin cell borders. The brief asks for no visible
  gridlines.
- Streamlit still warns that `use_container_width` is deprecated. The new Describe buttons use it to match the rest
  of the app.

## Spec conflicts

None found. Spec section 11 lists what each step must show. All of it is still shown. The changes are in layout
and styling only.

## Status on master, 2026-10-22

Checked again on `master` after the A to G merges. Everything stayed on this computer; nothing was pushed or uploaded.

- Task E is on master in full. Commit `308e9e1` (merged by `3f9190b`) carries the dark theme on every step, the three
  Describe preview cards from the cached results, the larger input area, the one-line "what happens next", the
  Check drawing on the dark stage with glowing pads and colored load arrows, the load-case pills and the four
  instrument readouts. `design-refs/brief.md` says "Dark everywhere" and the light-step rule is gone. All theme
  values sit in `app/theme.py`; the E commit touched no file under `morphic/`.
- The four open points listed under "Notes for the user" above are closed by commit `46c0ed2` ("Polish the app
  design against the brief", report in `.plans/reports/polish.md`): pad names no longer sit on support symbols,
  the Validation tables have no cell grid, no `use_container_width` call remains, and the three agent screens
  were retaken from the saved exploration replay with the LLM switched off.
- Current evidence: the full suite on this tree is 197 passed, 0 failed, 0 skipped
  (`.plans/reports/polish-tests.xml`), and all 13 screens in `.plans/reports/screens/` were retaken on 2026-10-22
  against `.plans/reports/polish_capture_app.py`, which makes no LLM request.

