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

## Demo parts

`examples/rc_arm.json`, `examples/drone_arm.json`, `examples/aero_bracket.json` (spec section 14).
The bracket is a 2D slice of the GE / GrabCAD Jet Engine Bracket Challenge (2013) and is not comparable
to the 3D challenge results; sources are listed in the file's `references` field.
