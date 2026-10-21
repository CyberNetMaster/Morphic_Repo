# Workspace D

S13 implemented locally on 2026-10-21. No engine modules were modified. No network calls, uploads,
pushes, remote changes, pull requests, or API-key access were performed. Generated evidence stays
under the ignored `.plans/s13/` directory; `.env` remains ignored and uncommitted.

## Changes

- `morphic/report.py`: fpdf2 A4 report, one page per design or one selected material. Includes the
  checked problem drawing, actual exported SVG shape, recovered nodal utilization (shared 0–1 scale,
  red above 1), smoothed FE numbers, load-case deflections, raw and filtered stress/SF, hand checks,
  mass savings, material-only cost, mesh and wall size, material conditions, linked citations,
  interlayer-shear stand-in, convergence note, and limits. The aerospace slice caveat is included.
- `morphic/bundle.py`: allowlisted zip contents, full SHA-256 artifact manifest, input/library
  consistency checks, safe extraction, and isolated replay workers. Both modes use the saved settings
  before engine imports and load the bundled material/process YAML. Source and exporter versions are
  recorded separately. Historical S14 environment information was not stored; `environment.txt`
  explicitly reports the environment at bundle creation, including MKL thread count.
- Strict replay rebuilds smoothed geometry from stored final densities, runs linear-fraction FE,
  recalculates hand checks and strut/block baselines, and ranks again. It compares final physics,
  geometry, savings, cost, rankings and numbers embedded in hand-check prose at 0.5%. Selection
  history and fill targets are replay inputs; timings, iteration counts, catalog history and
  pre-smoothing checks are not final reported measurements.
- Loose replay starts catalogs and refinement from scratch. Every material must select the exact
  same final fill and reproduce mass within 2%. No cached catalog is reused for this mode.
- `morphic/cache.py`: SHA-256 keys compatible with existing S14 caches, local atomic imports,
  artifact checksums, cache lookup/miss behavior and dirty-source fingerprints for callers requesting
  a current code version. Copies only named solver artifacts, never directories or `.env`.
- CLI: implemented `report`, `bundle`, `rerun`, `cache`, and recorded-snapshot `render`; kept existing
  validation, benchmark, parse, mesh and precompute commands. Rerun prints each comparison, can write
  a full JSON diff, and returns 0/1/2 for pass/comparison failure/input or execution error.
- README documents both rerun modes, tolerances, runtime expectations, provenance limits and usage.

## Verification

The full repository suite passes: **79 tests**. The seven new S13 tests exercise real FE and fresh
optimization, non-default saved solver settings, a deliberately incorrect reported mass, archive
tampering/traversal, complete bundle contents, PDF page count, cache invalidation/corruption, numerical
tolerance boundaries and CLI error paths. Tests use a small approved RC-arm geometry with one material
and explicitly shortened iteration limits, solely for fast integration coverage.

A separate end-to-end CLI acceptance run uses the unchanged approved `examples/rc_arm.json`, all six
materials, all three processes, all ten fill levels, normal convergence limits, refinement, cold
reruns, baselines, and smoothed geometry export. Its element cap is explicitly **1,200** (actual mesh
74 x 16 = 1,184 elements per process), and its artifacts are labelled smoke/integration results.

| Check | Result |
|---|---|
| Cached RC smoke part: strict evaluation | PASS, 450 comparisons, maximum relative difference 0 |
| Cached RC smoke part: fresh optimization | PASS, 12 comparisons, identical fills and masses for all six materials |
| Existing production RC cache: strict evaluation | PASS, 450 comparisons, maximum relative difference 0 |
| Full test suite | 79 passed |
| RC report | Six A4 pages, one per material; rendered with Poppler and visually inspected |
| Drone and aerospace report generation | Six pages each; failed designs, filtered designs and bracket caveat supported |
| Recorded RC FDM GIF | 180 real saved frames; no shape interpolation |

Production strict replay uses the committed RC cache with the saved 80,000 cap (actual FDM/SLS mesh
282 x 63; metal mesh 563 x 125). **The existing production cache was not rerun through fresh full-size
optimization.** Both-mode acceptance was performed on the separately generated cached smoke demo;
this is not a production-mesh optimization reproducibility claim.

Local evidence:

- `.plans/s13/verified-tests.xml`: full-suite JUnit results.
- `.plans/s13/demo-cache/rc_arm/`: complete smoke cache, including exports and densities.
- `.plans/s13/rc_arm-smoke.zip`: smoke bundle.
- `.plans/s13/rc_arm-smoke-diff.json`: both-mode acceptance, including all 12 optimization comparisons.
- `.plans/s13/rc_arm-smoke-strict-diff.json`: expanded 450-field strict comparison.
- `.plans/s13/rc_arm-production.zip` and `rc_arm-production-diff.json`: production strict evaluation.
- `.plans/s13/rc_arm-report.pdf`, `drone_arm-report.pdf`, `aero_bracket-report.pdf`: report previews.
- `.plans/s13/growth.gif`: rendered recorded iterations.

The sandbox initially prevented pytest from accessing its private temporary directories. The tests
and replay workers were rerun with local filesystem access; no dependency downloads were needed.
The existing Python 3.12 environment at `C:/Users/night/projects/morphic/.venv/Scripts/python.exe`
was used with `python -m morphic.cli` so imports resolve to this worktree. Poppler came from the
locally installed Codex runtime. The final full-suite command was:

```powershell
C:/Users/night/projects/morphic/.venv/Scripts/python.exe -m pytest --basetemp=.plans/s13/verified-tests --junitxml=.plans/s13/verified-tests.xml
```

## Handoff

```powershell
uv run morphic report examples/cache/rc_arm --out output/rc_arm.pdf
uv run morphic bundle examples/cache/rc_arm --out output/rc_arm.zip
uv run morphic rerun output/rc_arm.zip --out output/diff.json
uv run morphic rerun output/rc_arm.zip --mode evaluation --failures-only
uv run morphic cache --source examples/cache/rc_arm
uv run morphic render examples/cache/rc_arm --process fdm --out output/growth.gif
```

`render` implements an offline 2D GIF of saved iterations. The cinematic 3D MP4 renderer remains the
separate S15 stretch task. Bundles carry data rather than executable source: a different checkout is
reported and may change the outcome. Multithreaded optimization is intentionally judged by the
spec's exact-fill/2%-mass rule, rather than bitwise density equality.

The local commit containing this report is the Workspace D S13 implementation commit; identify it
with `git log -1 -- .plans/reports/bundle.md`.
