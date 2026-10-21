# Workspace B

Design agent (`morphic/agent.py`, `morphic explore`). Written 2026-10-21 on branch `emdash/b-agent-j5t44`.
Everything stayed local: no push, no remote change, no pull request, no upload. `.env` is untracked and no key appears in the tree.

## What was built

- **`morphic/agent.py`** (new; no existing engine module was changed). The loop:
  1. Round 0 runs the problem as given in quick mode and reads the results.
  2. The LLM is shown the results JSON and the history and proposes one change: `thickness`, `material` (list), `process` (printer group), `design_space` (width, height), or `stop`.
  3. The proposal is checked: allowed action only; any answer that touches `safety_factor`, a deflection limit, a load, a pad hole or a support is rejected with the reason; thickness must stay within 0.25x-4x and the design space within 0.5x-3x of the start; the change must differ from the current value and from every combination already tried; the changed problem must pass the red sanity checks. One retry with the rejection message, then a deterministic fallback rule (spec section 8 scaling: nothing passes -> thicker by the measured shortfall; loose limits -> thinner; else a taller design space; else stop).
  4. The reason the LLM gives goes through the spec 10 number check against the results it was shown. One retry with the list of bad numbers; if it still fails, the change is kept and the reason is replaced by a plain description with the original text stored as `reason_rejected`.
  5. The engine runs in quick mode on a copied problem (`catalog.run_all(..., quick=True, rerun="none")`, 10k-element cap, 7 warm live levels, no refinement, no cold re-run) for the processes the printer allows.
  6. Steps 2-5 repeat for at most 5 rounds, or until the LLM answers `stop`.
  7. The best round is the lightest design that passes every limit and is allowed by the printer; if no round passes, the round whose closest allowed design has the smallest shortfall `max(SF_target/SF, deflection/limit)`.
  8. The recommendation text comes from the LLM and goes through the same number check (every number must match a value in the log within the rounding the text uses; units must match the key); one retry, then a template built from the log.
- **Structured log** (`ExploreLog`, JSON): settings, LLM provider and model, and per round: index, change, knobs (thickness, design space, printer, materials), proposal (action, value, reason, source `llm | fallback`, `reason_grounded`, every attempt with raw answer or error or bad numbers), results (every design: status, fill %, mass, SF, stress, deflection per case vs limit, hand-check fails, cost), seconds, notes. Then the recommendation (round, change, best design, text, source, attempts). The app can display it as is.
- **CLI** `morphic explore <problem.json> [--rounds 5] [--cap 10000] [--out LOG] [--no-llm] [--rerecommend LOG]`. The default log path is `.plans/agent/<part>.json`. `--rerecommend` redoes only the recommendation from a saved log (no engine run), added after the first real run because the API was down at the end of it.
- **Design-space change**: pads and zones are shifted by half the size change so they stay centred; a note is added to the problem.
- **Process change** sets the printer group and adds that group's library materials if none is in the list.
- **README**: a "Design agent" section.

## Tests (`tests/test_agent.py`, 15 tests, 26 s)

Fake LLM (scripted answers) and fake engine (deterministic masses from thickness and height):
rounds are logged and at most 5 run; the lightest passing round wins; a better round is quoted with engine numbers; `stop` ends early; `--no-llm` uses the fallback only; forbidden changes (`safety_factor`, `max_deflection_mm`) are rejected twice and the fallback is used; out-of-range, repeat, unknown-material and sanity-failing proposals are rejected; design-space change keeps pads centred and does not touch the original; process change adds a material; the number check accepts display rounding and matching units and rejects unknown numbers and wrong units; an ungrounded reason is dropped but the change kept; a bad recommendation text falls back to a template that itself passes the check; an API exception falls back without crashing; log round-trip and `rerecommend`. One test runs the real engine (test bracket, cap 1200, 3 levels, 1 round).

Full suite without slow tests: all pass (`pytest -m "not slow"`).

## Real runs on the drone arm (`examples/drone_arm.json`, printer desktop_fdm, Gemini `gemini-3.8-flash`)

Quick mode measured first: one FDM catalog takes 57 s (`.plans/agent/quick_timing_fdm.txt`).

**Run 1** (`.plans/agent/drone_arm.json`, console in `drone_arm_run.txt`, 9.4 min). Gemini returned 504/503 on 4 of 5 proposal calls and the network dropped on the recommendation call, so 4 rounds used the fallback rule and the text came from the template. The one LLM proposal (round 3, thickness 10 -> 7 mm, reason grounded) gave the winner.

| round | change | best allowed design |
|---|---|---|
| 0 | as given | pa6cf 14.23 g at 50% fill (pla, petg fail deflection: 1.524 / 2.349 mm vs 0.5 mm) |
| 1 | height 18 -> 22.5 mm (fallback) | pa6cf 11.77 g at 30% |
| 2 | height -> 28.12 mm (fallback) | pa6cf 12.33 g at 25% |
| 3 | thickness 10 -> 7 mm (LLM) | **pa6cf 8.63 g at 25%, SF 9.0, worst deflection 0.428 mm vs 0.5 mm** |
| 4 | height -> 35.15 mm (fallback) | pa6cf 8.64 g at 20% |
| 5 | height -> 43.94 mm (fallback) | pa6cf 10.31 g at 20% |

`--rerecommend` when the API came back: the LLM text passed the number check on the first attempt (8.63 g, 0.46 USD, 7.0 mm, 0.428 mm, 0.5 mm, 9.0, 2.0, 0.731 mm, 1.13 mm all in the log). The first-run log before that is kept as `drone_arm_first_run.json`.

**Run 2** (`.plans/agent/drone_arm_run2.json`, 8.2 min). 3 of 5 proposals from the LLM, each with a grounded reason; rounds 4 and 5 hit a 503 and used the fallback. Recommendation written by the LLM, grounded on the first attempt.

| round | change | best allowed design |
|---|---|---|
| 0 | as given | pa6cf 14.23 g at 50% |
| 1 | height 18 -> 24 mm (LLM: "worst deflection 0.458 mm near the limit of 0.5 mm; a taller space is stiffer per gram") | pa6cf 12.53 g at 30% |
| 2 | thickness 10 -> 8 mm (LLM: "0.355 mm against 0.5 mm and sf 13.15 leave margin") | pa6cf 10.02 g at 30% |
| 3 | height -> 30 mm (LLM) | pa6cf 9.0 g at 20% |
| 4 | height -> 37.5 mm (fallback) | **pa6cf 8.84 g at 15%, SF 7.3, worst deflection 0.383 mm vs 0.5 mm, 0.47 USD** |
| 5 | height -> 46.88 mm (fallback) | pa6cf 10.09 g at 15% |

Both runs say the same thing: the arm as given is over-built for pa6cf; a thinner part or a taller section cuts about 40% of the mass; pla and petg only pass once the section is much taller (run 2 round 4: pla 23.57 g).

## Things to know

- Quick-mode numbers are catalog levels (no refinement) at the 10k cap with 100 warm iterations, so some designs carry "not fully converged". The agent compares rounds at the same settings, so the comparison is fair, but the final numbers for a chosen option should come from a full run.
- The LLM adapter is not retried on 503/504 (same policy as `parse.py`); the fallback rule keeps the loop going, and `--rerecommend` recovers the text later. A short retry on 503 would make runs with a flaky API cleaner; not added, to keep the adapter unchanged.
- Mass bottoms out at the lowest live level (15%) when the section is tall, which is why round 5 is heavier than round 4 in both runs; the agent does not know that and keeps going taller. A rule "stop when the best is at the lowest fill level" would save one round.
- The agent never changes the problem on its own outside the loop; the recommended problem is only in the log (`knobs` of the best round).

## Commits

- `f2dc31e` Design agent: module, CLI, tests, README, run 1 logs.
- (this commit) run 2 logs and this report.
