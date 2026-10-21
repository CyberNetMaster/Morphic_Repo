# Morphic

Morphic is a design tool for load-bearing printed parts. You describe a part in plain
English, check the problem on a drawing, and Morphic runs 2D topology optimization for
six real, cited materials across three print processes. It ranks the results by mass,
explains the winner with checked numbers, and exports STL, SVG, DXF, a PDF report, and
a run bundle that reruns to the same answer.

Status: under construction. The build spec is in `.plans/morphic-spec.md`.

## Install

```
uv sync
```

Copy `.env.example` to `.env` and fill in the key for the LLM provider named in
`morphic/config.py` (`LLM_PROVIDER`). The provider is a thin adapter in `morphic/llm.py`.

## Run tests

```
uv run pytest
```

## License

MIT. See `LICENSE`.

## Timing (measured 2026-10-20, step S9)

Measured with `uv run morphic bench` on the aerospace bracket, metal catalog, on the development laptop
(12 logical cores, PyPardiso in symmetric positive-definite mode). Logs are in `.plans/bench/`.

| Elements | Seconds per iteration | One cold fill level (beta 1 to 16) |
|---|---|---|
| 40,051 | 0.85 | 237 iterations, 3.4 min |
| 80,199 | 1.62 | 230 iterations, 6.3 min |
| 149,994 | 3.9 | 250 iterations, 16 min |

A 10-level warm sweep at the 40k live cap took 16.4 min per catalog, so live mode uses a 7-level sweep
(about 46 min per part with three processes, refinement and the cold re-run). The three demo parts are
precomputed at an 80k element cap with a cold run per fill level (about 7.5 h for all three; 150k would
take about 11.5 h). See spec section 6.10.

Step S9b (same benchmark) made each iteration 2.3x faster with identical results (within 4.6e-11):
0.37 s per iteration at 40k elements, and 6.6 min for the 10-level warm catalog instead of 16.4 min.

## Demo parts

`examples/rc_arm.json`, `examples/drone_arm.json`, `examples/aero_bracket.json` (spec section 14).
The bracket is a 2D slice of the GE / GrabCAD Jet Engine Bracket Challenge (2013) and is not comparable
to the 3D challenge results; sources are listed in the file's `references` field.

## Local reports, bundles and reproduction (S13)

These commands use saved, checked problems and computed results. They require no API key or network:

```powershell
uv run morphic report examples/cache/rc_arm --out output/rc_arm.pdf
uv run morphic report examples/cache/rc_arm --material pa6cf --out output/pa6cf.pdf
uv run morphic bundle examples/cache/rc_arm --out output/rc_arm.zip
uv run morphic rerun output/rc_arm.zip --out output/rerun-diff.json
```

The PDF has one A4 page per design, including the problem drawing, exported shape, recovered nodal
utilization on a shared 0–1 scale, smoothed re-check results, hand checks, linked citations, and limits.
The zip contains the solved problem, material and process YAML, settings, source commit, environment
description, results, densities, available snapshots, geometry files and report. SHA-256 checksums
detect damaged or changed files. Only solver artifacts are included; `.env` is never read or bundled.
For existing S14 caches, the historical solve environment was not recorded: `environment.txt` explicitly
describes the environment at bundle creation. The original solve commit is preserved separately from
the exporter commit.

`morphic rerun` runs both checks by default and prints an individual diff for every compared field:

- **Evaluation (strict, 0.5%)** rebuilds the smoothed geometry from the stored final densities, runs
  linear-area-fraction FE with nodal recovery, recomputes hand checks and baselines, and ranks again.
  It compares final reported physics, geometry, mass savings, material cost, and ranking. Numbers
  embedded in hand-check descriptions are included. Fill targets and selection history are replay
  inputs; historical iteration counts, timings and pre-smoothing grid checks are not final measurements.
- **Optimization (loose)** starts fresh catalogs and refinement using the saved settings and libraries.
  Every material must select exactly the same fill level and have mass within **2%**. Multithreaded
  PyPardiso can sum in different orders; the OC updates can amplify tiny differences over many iterations.
  Bitwise-identical shapes are not promised. A production optimization replay can take hours.

Use `--mode evaluation` or `--mode optimization` to run one check, and `--failures-only` to reduce console
output while retaining the complete JSON diff. Exit status is 0 for pass, 1 for comparison failure,
and 2 for invalid input or execution failure. Settings are restored before engine imports in isolated
local processes; bundled libraries take precedence over installed ones. Bundles contain no code, so
run the recorded source revision when reproducing on a different checkout. A code-version difference
is shown and never hidden.

```powershell
# Full ten-level pipeline at a small mesh for an integration check, not production claims:
uv run morphic precompute examples/rc_arm.json --cap 1200 --out output/smoke-cache
uv run morphic bundle output/smoke-cache/rc_arm --out output/smoke.zip
uv run morphic rerun output/smoke.zip --out output/smoke-diff.json

# Hash-indexed local cache; the first command prints its location/key:
uv run morphic cache --source examples/cache/rc_arm
uv run morphic cache --key <sha256>

# Recorded iterations only; no invented or interpolated shapes:
uv run morphic render examples/cache/rc_arm --process fdm --out output/growth.gif
```

The cache key hashes the solved problem, combined material/process hash, solver settings, and code
version. `RunCache` writes entries atomically and verifies artifact checksums on load. Existing named
S14 caches remain compatible. `render` provides a local 2D snapshot GIF; the cinematic 3D MP4 renderer
is the separate S15 stretch task.

## Design agent

`uv run morphic explore examples/drone_arm.json` runs the design agent (`morphic/agent.py`). It reads the
results of a quick-mode run, proposes one change per round (thickness, materials, printer group, or
design-space size; never the safety factor, a limit, a load or a support), runs the engine again in
quick mode (10k-element cap, 7 warm levels, no refinement, no cold re-run), and repeats for at most
5 rounds. It then recommends the lightest passing round. Every number in its reasons and in the
recommendation is checked against the engine results the same way as the explanation (spec section 10);
text that fails the check is replaced by a template. The structured log of every round goes to
`.plans/agent/<part>.json`. `--no-llm` uses the built-in fallback rule only; `--rounds` and `--cap`
change the round count and the element cap.

## Integrated app

Run `uv run streamlit run app/streamlit_app.py --server.address 127.0.0.1` for the local
Describe → Check → Compare → Export flow. The configured provider in `morphic/config.py`
is used for parsing, checked explanations and design exploration. Credentials are read only
from this checkout's `.env`; provider request details are excluded from error logs.
Offline templates and deterministic proposals remain fallbacks for failed API calls or validation.

Compare generates an explanation from the saved, smoothed results, checks its numbers, and
caches it for an hour. Its Design agent panel runs up to five changes in the background,
shows progress and trial results, and provides a downloadable log. `Review recommended design`
restores the chosen round, including translated pads/zones, on Check with full mode selected.
Quick exploration results do not replace the current checked result or its exports.

Export provides geometry, results JSON, a PDF (one page per material), and a reproducible ZIP.
The downloaded PDF is exactly the report inside the ZIP. Generated files and agent logs stay
under `.plans/live_runs/`; downloads and browser screenshots are local files. No publishing
or remote Git operations are part of this workflow.
