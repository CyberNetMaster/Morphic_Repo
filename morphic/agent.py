"""Design agent: explores alternatives when a design fails or could be better.

The loop (at most MAX_ROUNDS rounds after the starting run):

1. read the current results (round 0 is the problem as given, run in quick mode);
2. ask the LLM for one change: thickness, materials, process (printer group), or
   design-space size. It may never lower the safety factor or edit a limit or a load;
3. check the proposal (allowed action, sane range, not a repeat, sanity checks still pass);
4. run the engine in quick mode (spec 6.10: ELEMENT_CAP_QUICK, live levels, no refinement,
   no cold re-run) on the processes the printer allows;
5. record the round (proposal, reason, results) and repeat.

At the end it recommends the best round: the lightest design that passes every limit and is
allowed by the printer; if no round passes, the round whose best allowed design is closest to
the limits. The recommendation text comes from the LLM and goes through the same number
check as spec section 10 (every number must match a value in the results JSON within display
rounding, units must match; one retry with the bad numbers, then a template). Round reasons
written by the LLM go through the same check.

No engine module is modified: the agent only calls `catalog.run_all` on a copied problem.
The LLM is reached through `morphic.llm` (the existing adapter); tests pass a fake callable.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import catalog, config, sanity
from .evaluate import thickness_suggestion
from .materials import Material, Process, load_materials, load_processes, printer_allows
from .problem import MATERIAL_IDS, PRINTERS, Problem, problem_to_dict

MAX_ROUNDS = 5
ACTIONS = ("thickness", "material", "process", "design_space", "stop")
PROPOSAL_RETRIES = 1  # one retry after an invalid proposal, then the fallback rule
GROUNDING_RETRIES = 1  # spec 10: one retry with the list of bad numbers, then the template
# Range guards relative to the starting problem, so one bad answer cannot send the run off.
THICKNESS_RANGE = (0.25, 4.0)
SIZE_RANGE = (0.5, 3.0)
FORBIDDEN_KEYS = ("safety_factor", "max_deflection_mm", "max_deflection", "loads", "fx_N", "fy_N",
                  "fz_N_out_of_plane", "load_cases", "hole_r_mm", "supports")


# ----------------------------------------------------------------------------- log records
@dataclass
class Proposal:
    action: str
    value: dict
    reason: str
    source: str = "llm"  # llm | fallback | none
    reason_grounded: bool = True
    reason_rejected: str = ""  # the LLM's text when its numbers failed the check
    attempts: list = field(default_factory=list)  # [{attempt, raw | error, seconds}]


@dataclass
class Round:
    index: int
    change: str  # plain-English description of what differs from the round before
    knobs: dict  # thickness_mm, design_space, printer, materials
    proposal: Proposal | None
    results: dict  # summarize_run() output: every number the agent may quote
    seconds: float
    notes: list[str] = field(default_factory=list)


@dataclass
class ExploreLog:
    part: str
    source: str
    settings: dict
    llm: dict
    rounds: list[Round] = field(default_factory=list)
    recommendation: dict = field(default_factory=dict)
    seconds: float = 0.0

    def to_dict(self) -> dict:
        return _plain(asdict(self))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def _plain(v):
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, (np.floating, float)):
        v = float(v)
        return v if np.isfinite(v) else None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


# ----------------------------------------------------------------------------- results JSON
def knobs_of(problem: Problem) -> dict:
    return {"thickness_mm": float(problem.thickness_mm),
            "design_space": {"width_mm": float(problem.design_space.width_mm),
                             "height_mm": float(problem.design_space.height_mm)},
            "printer": problem.printer, "materials": list(problem.materials)}


def summarize_run(res: catalog.RunResult) -> dict:
    """The results JSON the agent reads and quotes from, rounded as the cards display them."""
    problem = res.problem
    cases = [lc.name for lc in problem.load_cases]
    designs = []
    for d in res.designs:
        c = d.checks
        ranked = d.status == "pass" and d.printer_allowed
        row = {"material": d.material.id, "process": d.process.id, "status": d.status,
               "printer_allowed": bool(d.printer_allowed), "ranked": ranked,
               "fill_pct": None if d.fill is None else round(100.0 * d.fill, 1),
               "reasons": list(d.reasons), "notes": [n for n in d.notes if n][:6]}
        if c is not None:
            defl = [round(float(x), 3) for x in c.deflection_mm]
            lims = [float(x) for x in c.deflection_limit_mm]
            ratios = np.asarray(c.deflection_mm, float) / np.asarray(c.deflection_limit_mm, float)
            w = int(np.argmax(ratios)) if ratios.size else 0
            row.update({
                "mass_g": round(float(c.mass_g), 2),
                "sf": None if not np.isfinite(c.sf) else round(float(c.sf), 2),
                "sf_target": float(c.sf_target),
                "stress_MPa": round(float(c.stress_reported_MPa), 1),
                "deflection_mm": defl, "deflection_limit_mm": lims, "load_cases": cases,
                "worst_deflection_mm": defl[w] if defl else None,
                "worst_deflection_limit_mm": lims[w] if lims else None,
                "worst_case": cases[w] if cases else "",
                "hand_checks_failed": [h.name for h in c.out_of_plane + c.bearing if not h.passed],
            })
            if d.material.cost_per_kg is not None:
                row["material_cost_usd"] = round(float(c.mass_g) / 1000.0 * d.material.cost_per_kg, 2)
        designs.append(row)
    ranked = [r for r in designs if r["ranked"] and r.get("mass_g") is not None]
    ranked.sort(key=lambda r: r["mass_g"])
    best = dict(ranked[0]) if ranked else None
    allowed = [r for r in designs if r["printer_allowed"]]
    return {"problem": knobs_of(problem), "safety_factor_target": float(problem.safety_factor),
            "n_designs": len(designs), "n_pass": sum(1 for r in designs if r["status"] == "pass"),
            "n_ranked": len(ranked), "n_allowed_by_printer": len(allowed),
            "best": best, "designs": designs,
            "shortfall": _shortfall(allowed if allowed else designs)}


def _shortfall(rows: list[dict]) -> float | None:
    """How far the closest allowed design is from passing: max(SF_target / SF, deflection / limit).
    1.0 means it passes. None when no design has numbers."""
    best = None
    for r in rows:
        if r.get("mass_g") is None:
            continue
        sf = r.get("sf")
        parts = [1.0]
        if sf is not None and sf > 0:
            parts.append(r["sf_target"] / sf)
        if r.get("worst_deflection_mm") is not None and r.get("worst_deflection_limit_mm"):
            parts.append(r["worst_deflection_mm"] / r["worst_deflection_limit_mm"])
        if r.get("hand_checks_failed"):
            parts.append(1.5)
        s = max(parts)
        best = s if best is None else min(best, s)
    return None if best is None else round(best, 3)


def score(results: dict) -> tuple:
    """Lower is better: passing rounds by mass, then failing rounds by shortfall."""
    if results.get("best"):
        return (0, results["best"]["mass_g"])
    return (1, results.get("shortfall") if results.get("shortfall") is not None else 1e9)


# ----------------------------------------------------------------------------- number check (spec 10)
_UNIT_OF_PATH = (("_mm", "mm"), ("mass_g", "g"), ("_MPa", "MPa"), ("_pct", "%"), ("_usd", "$"), ("_N", "N"))
_NUM_RE = re.compile(r"(?<![\w.\-])(-?\d+(?:\.\d+)?)(?:\s*(%|mm|MPa|g|N|\$))?(?![\w.])")


def collect_numbers(obj, path: str = "", out: list | None = None) -> list[tuple[str, float]]:
    """Every number in a JSON-like object with its key path."""
    if out is None:
        out = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        if np.isfinite(obj):
            out.append((path, float(obj)))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            collect_numbers(v, f"{path}.{k}" if path else str(k), out)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            collect_numbers(v, f"{path}[{i}]", out)
    return out


def _unit_of(path: str) -> str:
    leaf = path.rsplit(".", 1)[-1].split("[")[0]
    for suffix, unit in _UNIT_OF_PATH:
        if leaf.endswith(suffix) or leaf == suffix.strip("_"):
            return unit
    return ""


def ground_text(text: str, results: dict) -> list[str]:
    """Spec 10 number check. Returns the list of numbers that match nothing in `results`
    (within the rounding the text itself uses) or whose unit does not match the matched key."""
    values = collect_numbers(results)
    bad: list[str] = []
    for m in _NUM_RE.finditer(text):
        tok, unit = m.group(1), m.group(2) or ""
        if unit == "$":  # "$12" is written before the number; handled below
            unit = ""
        n = float(tok)
        decimals = len(tok.split(".")[1]) if "." in tok else 0
        tol = 0.5 * 10.0 ** (-decimals) + 1e-9
        before = text[max(0, m.start() - 1):m.start()]
        if before == "$":
            unit = "$"
        hits = [(p, v) for p, v in values if abs(v - n) <= tol]
        if not hits:
            bad.append(f"{tok}{(' ' + unit) if unit else ''}: not in the results")
            continue
        if unit and not any(_unit_of(p) == unit for p, _ in hits):
            bad.append(f"{tok} {unit}: the matching value is not in {unit}")
    return bad


# ----------------------------------------------------------------------------- LLM calls
def _strip_json(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.lower().startswith("json"):
            t = t[4:]
    i, j = t.find("{"), t.rfind("}")
    return t[i:j + 1] if i >= 0 and j > i else t


def _default_llm(system: str, user: str) -> dict:
    from . import llm

    res = llm.complete(system, user, config.LLM_TIMEOUT_S)
    return json.loads(_strip_json(res.text))


def llm_info() -> dict:
    return {"provider": config.LLM_PROVIDER, "model": config.LLM_MODELS.get(config.LLM_PROVIDER, "")}


PROPOSAL_SYSTEM = """You are the design agent of Morphic, a tool that finds the lightest printed part that meets a safety factor and a deflection limit.
You read the results of one engine run and propose ONE change for the next run. Answer with JSON only.

Allowed answers (exactly one):
{"action": "thickness", "thickness_mm": <number>, "reason": "<one or two short sentences>"}
{"action": "material", "materials": [<material ids>], "reason": "..."}
{"action": "process", "printer": "desktop_fdm" | "sls_service" | "metal_service" | "any", "reason": "..."}
{"action": "design_space", "width_mm": <number>, "height_mm": <number>, "reason": "..."}
{"action": "stop", "reason": "..."}

Rules:
- Goal: the lowest mass among designs that pass every limit and are allowed by the printer. If nothing passes, first make something pass.
- You may change only thickness, the material list, the printer group (which processes are allowed), or the design-space size.
- Never lower the safety factor. Never change a deflection limit, a load, a pad, a hole or a support. Those are the user's limits.
- Do not repeat a change that was already tried.
- Physics you can use: for the same shape, in-plane stress and deflection both scale with 1/thickness; mass scales with thickness. A taller design space (in the bending direction) gives a stiffer part per gram. A stiffer or stronger material passes at a lower fill level.
- The reason may quote numbers ONLY from the results JSON you were given, written exactly as they appear there (same rounding, same unit). Do not compute new numbers in the reason.
- Material ids: pla, petg, pa6cf (FDM); pa12 (SLS); alsi10mg, ti64 (metal). FDM needs a desktop FDM printer; SLS and metal need a service.
- Answer "stop" only when you believe no allowed change can give a lighter passing design.
"""

RECOMMEND_SYSTEM = """You are the design agent of Morphic. You are given the log of an exploration: several engine runs, each with one change and its results, and the index of the best round.
Write 3 to 4 short plain-English sentences that recommend the best round and say why, and what trade-off it makes (mass, material cost, which printer is needed, or that nothing passes).
Every number you write must appear in the JSON exactly as it is there (same rounding, same unit). Do not compute new numbers.
Answer with JSON only: {"text": "<the sentences>"}
"""


def _proposal_user(results: dict, history: list[dict], rounds_left: int, error: str | None, bad: list[str] | None,
                   previous: str | None) -> str:
    parts = [f"Rounds left after this one: {rounds_left}.",
             "Earlier rounds (change, results):", json.dumps(history, indent=1),
             "Current results JSON:", json.dumps(results, indent=1)]
    if error:
        parts += [f"Your previous answer was rejected: {error}", f"Previous answer: {previous}", "Answer again."]
    if bad:
        parts += ["Your previous reason used numbers that are not in the results JSON: " + "; ".join(bad),
                  f"Previous answer: {previous}", "Answer again with the same or another change, quoting only numbers from the JSON."]
    return "\n".join(parts)


# ----------------------------------------------------------------------------- proposals
def _history_entry(r: Round) -> dict:
    return {"round": r.index, "change": r.change, "knobs": r.knobs,
            "best": r.results.get("best"), "n_ranked": r.results.get("n_ranked"),
            "shortfall": r.results.get("shortfall")}


def validate_proposal(raw: dict, problem: Problem, start: Problem, tried: list[dict],
                      processes: dict[str, Process] | None = None) -> tuple[Proposal | None, str]:
    """Check an LLM answer. Returns (proposal, "") or (None, why it was rejected)."""
    if not isinstance(raw, dict):
        return None, "the answer is not a JSON object"
    for k in FORBIDDEN_KEYS:
        if k in raw:
            return None, f"'{k}' may not be changed (limits, loads and supports are fixed by the user)"
    action = str(raw.get("action", "")).strip()
    reason = str(raw.get("reason", "")).strip()
    if action not in ACTIONS:
        return None, f"unknown action {action!r}; allowed: {', '.join(ACTIONS)}"
    if action == "stop":
        return Proposal("stop", {}, reason), ""
    value: dict = {}
    if action == "thickness":
        t = _num(raw.get("thickness_mm"))
        if t is None or t <= 0:
            return None, "thickness_mm must be a positive number"
        lo, hi = THICKNESS_RANGE[0] * start.thickness_mm, THICKNESS_RANGE[1] * start.thickness_mm
        if not (lo <= t <= hi):
            return None, f"thickness_mm must stay between {lo:g} and {hi:g} mm in this exploration"
        if abs(t - problem.thickness_mm) < 0.01 * problem.thickness_mm:
            return None, "thickness_mm equals the current value"
        value = {"thickness_mm": round(t, 3)}
    elif action == "material":
        mats = raw.get("materials")
        if not isinstance(mats, list) or not mats:
            return None, "materials must be a non-empty list of ids"
        mats = [str(m) for m in mats]
        unknown = [m for m in mats if m not in MATERIAL_IDS]
        if unknown:
            return None, f"unknown material ids {unknown}; known: {list(MATERIAL_IDS)}"
        mats = list(dict.fromkeys(mats))
        if set(mats) == set(problem.materials):
            return None, "the material list equals the current one"
        value = {"materials": mats}
    elif action == "process":
        pr = str(raw.get("printer", ""))
        if pr not in PRINTERS:
            return None, f"printer must be one of {list(PRINTERS)}"
        if pr == problem.printer:
            return None, "the printer equals the current one"
        value = {"printer": pr}
    elif action == "design_space":
        w, h = _num(raw.get("width_mm")), _num(raw.get("height_mm"))
        if w is None or h is None or w <= 0 or h <= 0:
            return None, "width_mm and height_mm must be positive numbers"
        W0, H0 = start.design_space.width_mm, start.design_space.height_mm
        if not (SIZE_RANGE[0] * W0 <= w <= SIZE_RANGE[1] * W0 and SIZE_RANGE[0] * H0 <= h <= SIZE_RANGE[1] * H0):
            return None, (f"the design space must stay between {SIZE_RANGE[0]:g}x and {SIZE_RANGE[1]:g}x the "
                          f"starting size ({W0:g} x {H0:g} mm)")
        if abs(w - problem.design_space.width_mm) < 1e-6 and abs(h - problem.design_space.height_mm) < 1e-6:
            return None, "the design space equals the current one"
        value = {"width_mm": round(w, 3), "height_mm": round(h, 3)}
    prop = Proposal(action, value, reason)
    new = apply_proposal(problem, prop, processes)
    if knobs_of(new) in tried:
        return None, "this combination was already tried"
    red = sanity.blocking(sanity.check(new))
    if red:
        return None, "the changed problem fails a sanity check: " + "; ".join(m.message for m in red)
    return prop, ""


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def apply_proposal(problem: Problem, prop: Proposal, processes: dict[str, Process] | None = None,
                   materials: dict[str, Material] | None = None) -> Problem:
    """A new Problem with the change applied. The original is not touched."""
    d = problem_to_dict(problem)
    notes = list(d.get("notes", []))
    if prop.action == "thickness":
        d["thickness_mm"] = prop.value["thickness_mm"]
    elif prop.action == "material":
        d["materials"] = list(prop.value["materials"])
    elif prop.action == "process":
        d["printer"] = prop.value["printer"]
        # make sure the newly allowed group has at least one material to run
        mats = materials or load_materials()
        procs = processes or load_processes()
        allowed = [m.id for m in mats.values() if printer_allows(d["printer"], procs[m.process])]
        if allowed and not any(m in allowed for m in d["materials"]):
            d["materials"] = list(d["materials"]) + [m for m in allowed if m in MATERIAL_IDS]
    elif prop.action == "design_space":
        W0, H0 = d["design_space"]["width_mm"], d["design_space"]["height_mm"]
        W, H = prop.value["width_mm"], prop.value["height_mm"]
        dx, dy = 0.5 * (W - W0), 0.5 * (H - H0)  # pads and zones stay centred
        for p in d["pads"]:
            p["cx"] += dx
            p["cy"] += dy
        for z in d["zones"]:
            if z.get("circle"):
                z["circle"]["cx"] += dx
                z["circle"]["cy"] += dy
            if z.get("rect"):
                z["rect"]["x"] += dx
                z["rect"]["y"] += dy
        d["design_space"] = {"width_mm": W, "height_mm": H}
        notes.append(f"design agent: design space {W0:g} x {H0:g} mm -> {W:g} x {H:g} mm, pads and zones "
                     f"shifted by ({dx:g}, {dy:g}) mm to stay centred")
    d["notes"] = notes
    return Problem.model_validate(d)


def describe(prop: Proposal, before: Problem) -> str:
    v = prop.value
    if prop.action == "thickness":
        return f"thickness {before.thickness_mm:g} mm -> {v['thickness_mm']:g} mm"
    if prop.action == "material":
        return f"materials {', '.join(before.materials)} -> {', '.join(v['materials'])}"
    if prop.action == "process":
        return f"printer {before.printer} -> {v['printer']}"
    if prop.action == "design_space":
        ds = before.design_space
        return f"design space {ds.width_mm:g} x {ds.height_mm:g} mm -> {v['width_mm']:g} x {v['height_mm']:g} mm"
    return "stop"


def fallback_proposal(problem: Problem, start: Problem, results: dict, tried: list[dict],
                      processes: dict[str, Process] | None = None) -> Proposal:
    """Deterministic rule when the LLM gives no valid proposal (spec section 8 scaling):
    nothing passes -> thickness from the 1/t scaling of the closest allowed design;
    the best passes at the loose floor -> thinner; otherwise a taller design space; else stop."""
    cands: list[Proposal] = []
    best = results.get("best")
    if best is None:
        s = results.get("shortfall")
        if s and s > 1.0:
            t = round(problem.thickness_mm * s * 2) / 2 + 0.5  # next half millimetre above the scaled need
            cands.append(Proposal("thickness", {"thickness_mm": t},
                                  f"no allowed design passes; the closest is {s:g}x off the limits and in-plane "
                                  "stress and deflection scale 1/thickness", source="fallback"))
    else:
        if any("loose" in n for n in best.get("notes", [])):
            t = round(problem.thickness_mm * 0.8, 1)
            cands.append(Proposal("thickness", {"thickness_mm": t},
                                  "the best design passes at the lowest fill level: limits are loose, so a thinner "
                                  "part may still pass", source="fallback"))
        ds = problem.design_space
        cands.append(Proposal("design_space", {"width_mm": ds.width_mm, "height_mm": round(ds.height_mm * 1.25, 2)},
                              "a taller design space gives a stiffer part per gram", source="fallback"))
    for p in cands:
        ok, err = validate_proposal({"action": p.action, **p.value, "reason": p.reason}, problem, start, tried,
                                    processes)
        if ok:
            ok.source = "fallback"
            return ok
    return Proposal("stop", {}, "no further allowed change is left to try", source="fallback")


def propose(llm_call: Callable, problem: Problem, start: Problem, results: dict, history: list[dict],
            tried: list[dict], rounds_left: int, processes: dict[str, Process] | None = None) -> Proposal:
    """Ask the LLM; validate; re-ask once on an invalid answer or ungrounded numbers; else fall back."""
    attempts: list[dict] = []
    error = previous = None
    bad: list[str] | None = None
    best_prop: Proposal | None = None
    invalid = ungrounded = 0
    for attempt in range(1 + PROPOSAL_RETRIES + GROUNDING_RETRIES):
        ta = time.perf_counter()
        try:
            raw = llm_call(PROPOSAL_SYSTEM, _proposal_user(results, history, rounds_left, error, bad, previous))
        except Exception as exc:  # noqa: BLE001 - any API failure falls back to the rule
            attempts.append({"attempt": attempt + 1, "error": f"{type(exc).__name__}: {exc}",
                             "seconds": time.perf_counter() - ta})
            break
        rec = {"attempt": attempt + 1, "raw": raw, "seconds": time.perf_counter() - ta}
        prop, err = validate_proposal(raw, problem, start, tried, processes)
        if prop is None:
            rec["error"] = err
            attempts.append(rec)
            invalid += 1
            if invalid > PROPOSAL_RETRIES:
                break
            error, previous, bad = err, json.dumps(raw)[:2000], None
            continue
        attempts.append(rec)
        # spec 10 check on the reason: numbers must come from the results the LLM was shown
        bad_nums = ground_text(prop.reason, {"results": results, "history": history})
        if not bad_nums:
            prop.attempts = attempts
            return prop
        rec["bad_numbers"] = bad_nums
        best_prop = prop
        ungrounded += 1
        if ungrounded > GROUNDING_RETRIES:
            break
        error, previous, bad = None, json.dumps(raw)[:2000], bad_nums
    if best_prop is not None:  # valid change, but its reason kept quoting numbers that are not in the results
        best_prop.reason_rejected = best_prop.reason
        best_prop.reason = f"{describe(best_prop, problem)} (the LLM's stated numbers did not match the results and were dropped)"
        best_prop.reason_grounded = False
        best_prop.attempts = attempts
        return best_prop
    fb = fallback_proposal(problem, start, results, tried, processes)
    fb.attempts = attempts
    return fb


# ----------------------------------------------------------------------------- engine
def quick_processes(problem: Problem, materials: dict[str, Material], processes: dict[str, Process]) -> dict:
    """Processes to run in quick mode: those of the problem's materials that the printer allows.
    If the printer allows none of them, every process of the problem's materials runs."""
    pids = {materials[m].process for m in problem.materials if m in materials}
    allowed = {p for p in pids if printer_allows(problem.printer, processes[p])}
    return {p: processes[p] for p in sorted(allowed or pids)}


def run_quick(problem: Problem, materials: dict[str, Material], processes: dict[str, Process],
              cap: int = config.ELEMENT_CAP_QUICK, levels=config.FILL_LEVELS_LIVE, callback=None) -> catalog.RunResult:
    """Quick mode (spec 6.6 step 3, 6.10): small cap, warm live levels, no refinement, no cold re-run."""
    procs = quick_processes(problem, materials, processes)
    mats = {k: v for k, v in materials.items() if k in problem.materials and v.process in procs}
    sub = problem.model_copy(update={"materials": [m for m in problem.materials if m in mats]})
    return catalog.run_all(sub, mats, procs, cap=cap, sweep_mode="warm", quick=True, rerun="none",
                           levels=levels, callback=callback)


# ----------------------------------------------------------------------------- recommendation
def choose_best(rounds: list[Round]) -> Round:
    return min(rounds, key=lambda r: (score(r.results), r.index))


def template_recommendation(best: Round, rounds: list[Round]) -> str:
    r0 = rounds[0]
    b = best.results.get("best")
    if b is None:
        s = best.results.get("shortfall")
        txt = (f"No round gave a design that passes every limit with the chosen printer. Round {best.index} "
               f"({best.change}) came closest: its best allowed design is {s:g}x off the limits.")
        return txt + " Next steps the agent is not allowed to take: a lower safety factor or looser deflection limits."
    txt = (f"Recommended: round {best.index} ({best.change}). {b['material']} ({b['process']}) passes at "
           f"{b['fill_pct']:g}% fill with mass {b['mass_g']:g} g, safety factor {b['sf']:g} against a target of "
           f"{b['sf_target']:g}, and worst deflection {b['worst_deflection_mm']:g} mm against a limit of "
           f"{b['worst_deflection_limit_mm']:g} mm ({b['worst_case']}).")
    b0 = r0.results.get("best")
    if best.index == 0:
        txt += " None of the explored changes beat the starting design."
    elif b0 is None:
        txt += " The starting design had no passing option with the chosen printer."
    else:
        txt += f" The starting design's best option was {b0['material']} at {b0['mass_g']:g} g."
    if "material_cost_usd" in b:
        txt += f" Material cost {b['material_cost_usd']:g} $ (material only, not print cost)."
    return txt


def recommend(llm_call: Callable | None, rounds: list[Round]) -> dict:
    best = choose_best(rounds)
    log_json = {"best_round": best.index, "rounds": [_plain(asdict(r)) for r in rounds]}
    out = {"round": best.index, "change": best.change, "best_design": best.results.get("best"),
           "text": "", "grounded": True, "source": "template", "attempts": []}
    if llm_call is not None:
        user = json.dumps(log_json, indent=1)
        bad: list[str] = []
        for attempt in range(1 + GROUNDING_RETRIES):
            ta = time.perf_counter()
            prompt = user if not bad else (user + "\n\nYour previous text used numbers that are not in the JSON: "
                                           + "; ".join(bad) + "\nWrite it again with numbers from the JSON only.")
            try:
                raw = llm_call(RECOMMEND_SYSTEM, prompt)
                text = str(raw.get("text", "")).strip() if isinstance(raw, dict) else str(raw).strip()
            except Exception as exc:  # noqa: BLE001
                out["attempts"].append({"attempt": attempt + 1, "error": f"{type(exc).__name__}: {exc}",
                                        "seconds": time.perf_counter() - ta})
                break
            bad = ground_text(text, log_json)
            out["attempts"].append({"attempt": attempt + 1, "text": text, "bad_numbers": bad,
                                    "seconds": time.perf_counter() - ta})
            if not bad and text:
                out.update(text=text, source="llm")
                return out
    out["text"] = template_recommendation(best, rounds)
    return out


# ----------------------------------------------------------------------------- main loop
def explore(problem: Problem, llm_call: Callable | None = None, engine: Callable | None = None,
            materials: dict[str, Material] | None = None, processes: dict[str, Process] | None = None,
            max_rounds: int = MAX_ROUNDS, source: str = "", status: Callable[[str], None] | None = None,
            cap: int = config.ELEMENT_CAP_QUICK, levels=config.FILL_LEVELS_LIVE, use_llm: bool = True) -> ExploreLog:
    """Run the agent. `llm_call(system, user) -> dict`; None uses the configured provider, or the
    fallback rule alone when use_llm is False. `engine(problem) -> RunResult`; None runs quick mode.
    Returns the structured log."""
    t0 = time.perf_counter()
    materials = materials or load_materials()
    processes = processes or load_processes()
    say = status or (lambda s: None)
    if llm_call is None and use_llm:
        llm_call = _default_llm
    engine = engine or (lambda p: run_quick(p, materials, processes, cap=cap, levels=levels))
    log = ExploreLog(part=problem.name, source=source,
                     settings={"cap": cap, "levels": list(levels), "max_rounds": max_rounds, "quick": True,
                               "sweep_mode": "warm", "refinement": False, "cold_rerun": False},
                     llm=llm_info() if llm_call is _default_llm else {"provider": "fake" if llm_call else "none"})
    start = problem
    current = problem
    tried: list[dict] = []

    def run_round(idx: int, prob: Problem, prop: Proposal | None, change: str) -> Round:
        say(f"round {idx}: {change}; running the engine in quick mode")
        tr = time.perf_counter()
        res = engine(prob)
        summary = summarize_run(res)
        tried.append(knobs_of(prob))
        r = Round(index=idx, change=change, knobs=knobs_of(prob), proposal=prop, results=summary,
                  seconds=time.perf_counter() - tr, notes=list(getattr(res, "notes", []) or []))
        b = summary.get("best")
        say(f"round {idx}: " + (f"best {b['material']} {b['mass_g']} g" if b else
                                f"nothing passes (shortfall {summary.get('shortfall')})"))
        log.rounds.append(r)
        return r

    run_round(0, current, None, "starting problem as given")
    for k in range(1, max_rounds + 1):
        last = log.rounds[-1]
        history = [_history_entry(r) for r in log.rounds]
        if llm_call is None:
            prop = fallback_proposal(current, start, last.results, tried, processes)
        else:
            prop = propose(llm_call, current, start, last.results, history, tried, max_rounds - k, processes)
        if prop.action == "stop":
            log.rounds[-1].notes.append(f"agent stopped before round {k}: {prop.reason}")
            say(f"agent stops: {prop.reason}")
            break
        new = apply_proposal(current, prop, processes, materials)
        change = describe(prop, current)
        current = new
        run_round(k, current, prop, change)
    log.recommendation = recommend(llm_call, log.rounds)
    log.seconds = time.perf_counter() - t0
    return log


def log_from_dict(d: dict) -> ExploreLog:
    rounds = []
    for r in d.get("rounds", []):
        p = r.get("proposal")
        prop = Proposal(**p) if p else None
        rounds.append(Round(index=r["index"], change=r["change"], knobs=r["knobs"], proposal=prop,
                            results=r["results"], seconds=r.get("seconds", 0.0), notes=list(r.get("notes", []))))
    return ExploreLog(part=d.get("part", ""), source=d.get("source", ""), settings=d.get("settings", {}),
                      llm=d.get("llm", {}), rounds=rounds, recommendation=d.get("recommendation", {}),
                      seconds=d.get("seconds", 0.0))


def rerecommend(log: ExploreLog, llm_call: Callable | None = None) -> ExploreLog:
    """Redo only the recommendation from a saved log (no engine run), e.g. after an API outage."""
    log.recommendation = recommend(llm_call or _default_llm, log.rounds)
    log.llm = llm_info() if llm_call is None else log.llm
    return log


def write_log(log: ExploreLog, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(log.to_json(), encoding="utf-8")
    return path
