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
