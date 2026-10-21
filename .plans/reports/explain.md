# Workspace C

Implemented S12 from section 10 of `.plans/morphic-spec.md`.

- Added `morphic/explain.py`: display-rounded results JSON, unit-aware numeric grounding, one correction attempt with the bad numbers, and a deterministic template fallback.
- Uses the existing `morphic.llm.complete_json` adapter. The default is offline; `use_llm=True` explicitly enables it. All adapter tests use mocks, and no live API calls were made.
- The template explains mass ranking, the required printer, and material cost excluding print cost. It handles missing costs and no eligible winner.
- Added `tests/test_explain_grounding.py`, including a planted mass of 92.30 g against a computed display value of 12.30 g. The check rejects it, retries once, and falls back if the correction is also wrong.
- Engine modules and the LLM adapter are unchanged. No keys were accessed, no uploads were performed, and no remote Git operations were used.

Integration contract: call `results_json(rank_result)` after final smoothed rechecks, then `explain(payload)`. The payload stores quantities as decimal strings plus explicit units. The UI should display the same strings. The builder currently projects material name, printer, eligibility/rank, mass (two decimal places), and material cost (two decimal places). Additional quantities can use the same value/unit format. Number matching allows display rounding but does not silently convert units. Exact material and printer names are recognized as labels, including embedded digits. Numeric grounding does not prove arbitrary natural-language claims; the prompt restricts prose to the supplied results, and the offline template provides deterministic wording.

Validation: 26 explanation tests passed. The final full suite passed: **98 passed in 51.91 seconds**, including slow tests, with this command:

```powershell
& C:/Users/night/projects/morphic/.venv/Scripts/python.exe -m pytest -p no:cacheprovider
```

The first full-suite run had 89 passes and five setup errors caused by sandbox access to pytest's temporary directory. A workspace-local temporary directory encountered the same restriction. The final run was permitted outside the sandbox and passed. Test-created temporary directories inside the workspace were removed. The staged diff passed `git diff --cached --check`.

The existing project virtual environment was used because `uv run --offline` could not acquire the uv cache lock. No dependencies were downloaded.
