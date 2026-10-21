# Workspace A — S11: the Streamlit app

Date: 2026-10-21. Branch: `emdash/a-app-z7rfi`. Everything stayed local.

## What was built

`app/` (new; no engine module was changed):

| File | Role |
|---|---|
| `app/theme.py` | The one place for every color, font, radius, shadow, spacing and motion value. Builds the CSS for the light pages and the dark stage, the Plotly layouts, and the stress / density color scales. |
| `app/ui.py` | Small HTML pieces: top bar with the step indicator, cards, pills, gauges (SVG arc), meters, funnel, messages, footnotes. |
| `app/maps.py` | Shape PNGs (void transparent), utilization PNGs (shared 0–1 scale, above 1 in red, void masked), the Check drawing (pins, rollers, arrows per load case, zones, dimensions, amber defaults), Pareto chart, Plotly 3D view from the STL colored by utilization, validation plots. |
| `app/data.py` | Loads the cached demo parts, matches a parsed problem to a cached part, the run-time estimate from the S9b timing model, the live run (same outputs as `morphic.precompute`, with a progress object for the UI), and the template explanation (spec 10 fallback) filled only from computed numbers. |
| `app/streamlit_app.py` | The four steps and the Validation tab. |
| `.streamlit/config.toml` | Base theme values; headless server. |
| `tests/test_app.py` | 9 tests: theme, demo matching and estimate, images, template explanation, UI pieces, and a headless run of every step and the Validation tab (Streamlit `AppTest`). |

Run: `uv run streamlit run app/streamlit_app.py`. Query parameters jump to a state for the video and screenshots:
`?demo=rc_arm&step=2`, `?tab=validation`.

## The four steps and the tab (spec 11)

1. **Describe**: text box, three demo buttons (load the text and the checked JSON, no network), printer selector
   (wins over the text when changed), Quick mode toggle, "Read my description" with the spec's spinner text.
   A parse failure opens the Check step with the manual form and the demo buttons.
2. **Check**: drawing (pins as filled triangles, slides as rollers with the free direction, loads as arrows scaled by
   force with one color per case, keep-in solid, keep-out hatched, dimensions; defaults in amber), editable values
   (scalars with "from the text" / default notes; data editors for pads, supports, load cases, loads, zones; the
   editors are the manual form, always available), sanity messages above the drawing (red blocks the run, yellow
   does not), effective min wall per process, the run-time estimate, and "Generate designs" (disabled while a red
   check is open). A problem that equals a demo part loads the cache; anything else starts a live run.
3. **Compare** (dark stage): live progress (process, fill, iteration, elapsed, preview of the growing shape);
   the winner large with a Shape / Stress switch; growth animation from the cold re-run snapshots with a scrubber,
   iteration count, Play, and the Wolff's-law caption; explanation; **a reserved "Design agent" panel** (glass card,
   `st.container(key="agent_panel")`, with an `st.empty()` mount point); funnel; Pareto (one point per material,
   filled by process, hollow grey when failed or filtered, dotted line on the front); a fill-level strip per material;
   then the card grid grouped by process with the process tint, winner spotlight, quiet failed/filtered cards,
   shape and utilization maps, mass hero, weight-saved pills, SF gauge with raw peak and note, deflection meters
   per case, out-of-plane and bearing hand checks with suggestions, min wall and mesh, material cost (labelled),
   Sources and Limits expanders, "View in 3D" (Plotly mesh, rendered only when opened). The fixed one-line note
   closes the page.
4. **Export**: STL / SVG / DXF per design, `results.json`; PDF report and run bundle buttons are present but
   disabled (step S13).

**Validation tab**: cantilever table (FE vs theory, error, pass at 3%, mesh stated), mesh-refinement plot (log),
MBB benchmark (our density image, compliance vs 233.71), hole check table and plot with and without nodal recovery
at 8 / 16 / 32 elements per radius, scaling-law ratios, "Run all checks" (clears the cache and re-runs; ~10 s).

## Checks run

- `uv run pytest`: **81 passed** in 1 m 31 s (the 72 engine tests plus the 9 new app tests).
- The app ran on `localhost:8765`; screenshots of every step are in `.plans/reports/screens/`
  (`1-describe.png` … `5-validation.png`, taken with the installed Chrome through Playwright,
  script `.plans/reports/shoot.py`).
- With the RC arm cache: PA6-CF wins at 3.9 g (10% fill), 39% lighter than the strut baseline, 84% lighter than
  the block; 84 candidates → 6 met the limits → 3 printable (FDM) → ranked by mass. Matches `results.json`.

## Decisions and notes for the user

- **Explanation**: `explain.py` is step S12, so the Compare step shows a template explanation built only from the
  results (every number is read from `results.json`). The card says so. S12 replaces it.
- **Live runs** write to `.plans/live_runs/<key>/` (ignored by git) in the same format as the demo cache, so the
  Compare and Export steps have one code path. Quick mode = one process (the printer's, else FDM), 10k elements,
  no refinement, no re-run. A full live run uses the 40k cap and the 7-level warm sweep; the estimate on the Check
  step comes from the S9b rate (0.37 s per iteration at 40k). I did not run a full live part in this session
  (about 25 min); the pipeline is the same code as the precompute with live settings, and the headless tests cover
  the UI around it.
- **Demo matching**: a parsed or hand-entered problem that equals a demo (within display rounding, same printer)
  loads the cache instantly (spec 4.4 step 5). Any edit makes it a live run.
- **Growth animation**: the RC arm's FDM cold re-run did not pass the limits, so (spec 6.7) the sweep's shape is
  the result and the animation carries the "independent run at the same fill level" note. The animation is a
  scrubber with Play; nothing loops.
- **MBB published figure**: not redistributed; the card shows our density field, the published compliance and
  the error, and names Fig. 3 bottom-left of Andreassen et al. (2011).
- **PDF report and run bundle**: S13, shown disabled on Export.
- **Streamlit `use_container_width`** is deprecated in 1.66 (warning in the log); a few data editors and buttons
  still use it. Harmless until the removal date; worth a sweep in S17.
- The Pareto labels overlap when several light materials sit together (RC arm: pa12 / pa6cf / pla). Hover shows
  each point; a label-repel pass is a small follow-up.
- `pyproject.toml`: added `pythonpath = ["."]` to the pytest options so `tests/test_app.py` can import `app`.

## Spec conflicts

None found. One soft point: the spec's "editable table" with yellow defaults is done as data editors plus
amber "default" pills and a "source" column, since Streamlit's editor cannot color single cells.
