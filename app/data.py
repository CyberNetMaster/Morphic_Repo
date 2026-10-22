"""Results for the app: the precomputed demo parts (examples/cache) and live runs.

Both paths produce the same on-disk format as `morphic.precompute` (results.json, densities.npz,
utilization.npz, rerun_<process>.npz, <material>.stl/.svg/.dxf), so the Compare and Export steps
read one format. A live run mirrors `precompute_part` with live settings (40k cap, 7-level warm
sweep, cold re-run of the winner only) and reports progress through a `Progress` object.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from dataclasses import asdict
from pathlib import Path

import numpy as np

from morphic import catalog, config, geometry, precompute, rank
from morphic.baseline import strut_baseline
from morphic.domain import choose_mesh
from morphic.materials import library_hash, load_materials, load_processes
from morphic.parse import compare_problems
from morphic.problem import Problem, problem_from_dict, problem_to_dict

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
CACHE_DIR = precompute.CACHE_DIR
LIVE_DIR = ROOT / ".plans" / "live_runs"
DEMOS = {"RC car arm": "rc_arm", "Drone arm": "drone_arm", "Aerospace bracket": "aero_bracket"}

# Timing model from the S9b benchmark (README, spec 6.10): 0.37 s per iteration at 40,051 elements,
# close to linear in the element count. Small meshes have a per-iteration floor (solver set-up).
SECONDS_PER_ELEMENT_ITER = 0.37 / 40_051
SECONDS_PER_ITER_FLOOR = 0.03
ITERS_COLD_LEVEL = 237  # measured cold 60% level
ITERS_WARM_LEVEL = 100  # warm level cap (plateau rule stops at 91-96)
ITERS_REFINE_PER_PROCESS = 6 * config.MAX_ITERS_REFINE  # memoized bisections, typical
ITERS_RERUN = 240


# ----------------------------------------------------------------------------- loading
def load_results(folder: Path) -> dict:
    with open(Path(folder) / "results.json", encoding="utf-8") as f:
        r = json.load(f)
    r["_dir"] = str(folder)
    return r


def load_npz(folder: Path, name: str) -> dict[str, np.ndarray]:
    p = Path(folder) / name
    if not p.exists():
        return {}
    with np.load(p) as z:
        return {k: np.array(z[k]) for k in z.files}


def demo_problem(stem: str) -> Problem:
    with open(EXAMPLES / f"{stem}.json", encoding="utf-8") as f:
        return problem_from_dict(json.load(f))


def demo_text(stem: str) -> str:
    return (EXAMPLES / f"{stem}.txt").read_text(encoding="utf-8")


PARSED_DIR = EXAMPLES / "parsed"


def _squash(text: str) -> str:
    return " ".join((text or "").split())


def match_demo_text(text: str) -> str | None:
    """The demo part whose description text equals ``text`` (whitespace aside), or None."""
    t = _squash(text)
    if not t:
        return None
    for stem in DEMOS.values():
        f = EXAMPLES / f"{stem}.txt"
        if f.exists() and _squash(f.read_text(encoding="utf-8")) == t:
            return stem
    return None


def saved_parse(stem: str) -> Problem | None:
    """The saved, checked parse of a demo text (examples/parsed/<stem>.parsed.json), or None without one.
    Spec 4.4 step 5: the demo parts load from saved JSON, so the demo never depends on the network."""
    f = PARSED_DIR / f"{stem}.parsed.json"
    if not f.exists():
        return None
    with open(f, encoding="utf-8") as fh:
        return problem_from_dict(json.load(fh)["problem"])


def demo_preview(stem: str) -> dict | None:
    """Headline numbers of a cached demo part for the Describe step (the winning design, its mass,
    the weight saved, and where its shape lives), read straight from results.json. None without a cache."""
    folder = CACHE_DIR / stem
    if not (folder / "results.json").exists():
        return None
    r = load_results(folder)
    win = r["ranking"].get("winner")
    if not win:
        return None
    d = next(x for x in r["designs"] if x["material"] == win)
    c = next(x for x in r["ranking"]["cards"] if x["material"] == win)
    nelx, nely = r["catalogs"][d["process"]]["mesh"]
    p = r["problem"]
    return {"stem": stem, "folder": str(folder), "name": p["name"], "material": win, "process": d["process"],
            "mass_g": d["checks"]["mass_g"], "fill": d.get("fill"), "density_key": f"design/{win}",
            "saved_vs_strut": c.get("weight_saved_vs_strut"), "saved_vs_block": c.get("weight_saved_vs_block"),
            "nelx": nelx, "nely": nely, "width_mm": p["design_space"]["width_mm"],
            "height_mm": p["design_space"]["height_mm"], "thickness_mm": p["thickness_mm"],
            "cases": len(p["load_cases"]), "safety_factor": p["safety_factor"]}


def match_demo(problem: Problem) -> str | None:
    """The cached demo part whose solved problem equals this one (numbers within display rounding),
    or None. Lets a parsed or hand-entered demo load instantly (spec 4.4 step 5)."""
    for stem in DEMOS.values():
        res = CACHE_DIR / stem / "results.json"
        if not res.exists():
            continue
        try:
            want = problem_from_dict(load_results(CACHE_DIR / stem)["problem"])
        except Exception:
            continue
        if not compare_problems(problem, want) and problem.printer == want.printer:
            return stem
    return None


# ----------------------------------------------------------------------------- estimate
def processes_used(problem: Problem, materials: dict | None = None) -> list[str]:
    materials = materials or load_materials()
    out: list[str] = []
    for m in problem.materials:
        if m in materials and materials[m].process not in out:
            out.append(materials[m].process)
    return out


def quick_process(problem: Problem) -> str:
    """Quick mode runs one process: the one the printer selector names, else FDM."""
    return {"desktop_fdm": "fdm", "sls_service": "sls", "metal_service": "metal"}.get(problem.printer, "fdm")


def estimate_runtime(problem: Problem, quick: bool, processes: dict | None = None) -> dict:
    processes = processes or load_processes()
    W, H = problem.design_space.width_mm, problem.design_space.height_mm
    cap = config.ELEMENT_CAP_QUICK if quick else config.ELEMENT_CAP_LIVE
    used = [quick_process(problem)] if quick else processes_used(problem)
    rows, total = [], 0.0
    for pid in used:
        proc = processes[pid]
        mesh, eff = choose_mesh(W, H, proc.min_wall_mm, cap)
        per_it = max(SECONDS_PER_ELEMENT_ITER * mesh.nel, SECONDS_PER_ITER_FLOOR)
        levels = config.FILL_LEVELS_LIVE
        its = ITERS_COLD_LEVEL + (len(levels) - 1) * ITERS_WARM_LEVEL
        if not quick:
            its += ITERS_REFINE_PER_PROCESS
        secs = per_it * its
        rows.append({"process": pid, "elements": mesh.nel, "h_mm": mesh.h, "effective_min_wall_mm": eff,
                     "min_wall_mm": proc.min_wall_mm, "seconds": secs})
        total += secs
    if not quick and rows:  # cold re-run of the winner: assume the largest mesh
        total += max(max(SECONDS_PER_ELEMENT_ITER * r["elements"], SECONDS_PER_ITER_FLOOR) for r in rows) * ITERS_RERUN
    return {"cap": cap, "rows": rows, "seconds": total, "quick": quick}


# ----------------------------------------------------------------------------- live run
class Progress:
    """Shared between the run thread and the UI. Plain attributes, read without a lock
    (the UI only needs a recent snapshot)."""

    def __init__(self):
        self.t0 = time.perf_counter()
        self.stage = "starting"
        self.process = ""
        self.kind = ""
        self.fill = None
        self.iteration = 0
        self.beta = None
        self.objective = None
        self.preview = None  # (xPhys uint8, nelx, nely)
        self.preview_at = 0.0
        self.log: list[str] = []
        self.done = False
        self.error = ""
        self.result_dir: Path | None = None

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.t0

    def say(self, msg: str) -> None:
        self.log.append(f"[{self.elapsed / 60:4.1f} min] {msg}")
        self.stage = msg


def run_live(problem: Problem, quick: bool, out_root: Path, progress: Progress) -> Path:
    """Live pipeline (spec 6, live settings). Same outputs as `precompute_part`."""
    t0 = time.perf_counter()
    materials, processes = load_materials(), load_processes()
    cap = config.ELEMENT_CAP_QUICK if quick else config.ELEMENT_CAP_LIVE
    levels = config.FILL_LEVELS_LIVE
    if quick:
        pid = quick_process(problem)
        problem = problem.model_copy(deep=True)
        problem.materials = [m for m in problem.materials if materials[m].process == pid] or [
            m for m in materials if materials[m].process == pid]
    settings = config.solver_settings() | {"cap_used": cap, "sweep_mode_used": "warm", "levels_used": list(levels),
                                           "quick": quick, "format_version": precompute.FORMAT_VERSION}
    version = precompute.code_version()
    key = precompute.cache_key(problem, settings, version)
    out = Path(out_root) / key[:12]
    out.mkdir(parents=True, exist_ok=True)
    progress.say(f"meshing ({'quick, ' if quick else ''}cap {cap:,} elements)")

    def cb(info, xPhys):
        progress.process, progress.kind, progress.fill = info["process"], info["kind"], info["fill"]
        progress.iteration, progress.beta, progress.objective = info["iter"], info["beta"], info["objective"]
        progress.stage = f"{info['process']} {info['kind']} at {info['fill']:.0%} fill"
        now = time.perf_counter()
        if now - progress.preview_at > 0.7:
            progress.preview_at = now
            progress.preview = (np.clip(xPhys * 255, 0, 255).astype(np.uint8), info["process"])

    res = catalog.run_all(problem, materials, processes, cap, sweep_mode="warm", quick=quick, rerun="winner",
                          levels=levels, callback=cb)
    progress.say("sizing the strut baselines and checking the smoothed shapes")
    baselines, extra = {}, {}
    for d in res.designs:
        cat = res.catalogs[d.process.id]
        b = strut_baseline(cat.domain, d.material, problem.safety_factor)
        baselines[d.material.id] = b
        grid_checks = d.checks
        rec = precompute._recheck_with_step_up(d, cat, out, progress.say) if d.density is not None else {}
        if rec:
            d.fill, d.density = rec["fill"], rec["density"]
            d.mech, d.checks = rec["mech"], rec["checks"]
            d.status = "pass" if (d.status == "pass" and rec["checks"].passed) else "fail"
            d.reasons = rec["checks"].fail_reasons
            files = geometry.export_all(rec["geom"], out / d.material.id, cat.domain)
            extra[d.material.id] = {"grid_checks": grid_checks, "geometry": rec["geom"], "files": files}
    ranking = rank.rank_designs(res, baselines)
    progress.say("writing results")

    dens, util = {}, {}
    for pid, cat in res.catalogs.items():
        for fill, run in list(cat.levels.items()) + list(cat.refined.items()):
            dens[f"{pid}/{run.kind}/{fill:.4f}"] = run.xPhys
    for d in res.designs:
        if d.density is not None:
            dens[f"design/{d.material.id}"] = d.density
        if d.mech is not None:
            util[d.material.id] = (d.mech.nodal_vm * problem.safety_factor / d.material.strength).astype(np.float32)
        if d.rerun.get("snapshots"):
            np.savez_compressed(out / f"rerun_{d.process.id}.npz",
                                iterations=np.array([i for i, _ in d.rerun["snapshots"]], dtype=np.int32),
                                **{f"it{i}": a for i, a in d.rerun["snapshots"]},
                                material=np.array(d.material.id), fill=np.array(d.fill))
    np.savez_compressed(out / "densities.npz", **dens)
    np.savez_compressed(out / "utilization.npz", **util)
    _f, _checks, _status = precompute._f, precompute._checks, precompute._status
    designs_json = []
    for d in res.designs:
        b = baselines[d.material.id]
        ex = extra.get(d.material.id, {})
        g = ex.get("geometry")
        designs_json.append(_f({
            "material": d.material.id, "process": d.process.id, "status": d.status, "fill": d.fill,
            "printer_allowed": d.printer_allowed, "converged": d.converged, "reasons": d.reasons, "notes": d.notes,
            "checks": _checks(d.checks), "grid_checks": _checks(ex.get("grid_checks")),
            "pick": {"status": d.pick.status, "v_pick": d.pick.v_pick, "v_final": d.pick.v_final,
                     "window": d.pick.window, "levels": [_status(s) for s in d.pick.levels],
                     "refinement": [_status(s) for s in d.pick.refinement], "notes": d.pick.notes,
                     "reason": d.pick.reason},
            "rerun": {k: v for k, v in d.rerun.items() if k != "snapshots"},
            "baseline": {"mass_block_g": b.mass_block_g, "strut_width_mm": b.strut_width_mm,
                         "mass_strut_g": b.mass_strut_g, "strut_passed": b.strut_passed, "note": b.note,
                         "struts": b.struts},
            "geometry": None if g is None else {"area_mm2": g.area_mm2, "volume_mm3": g.volume_mm3,
                                                "watertight": g.watertight, "volume_error": g.volume_error,
                                                "files": {k: v.name for k, v in ex["files"].items()}},
            "mesh_h_mm": d.domain.h, "effective_min_wall": d.domain.describe_min_wall(),
        }))
    catalogs_json = {pid: _f({
        "process": pid, "mesh": [cat.domain.mesh.nelx, cat.domain.mesh.nely], "elements": cat.domain.mesh.nel,
        "h_mm": cat.domain.h, "effective_min_wall_mm": cat.domain.effective_min_wall_mm,
        "min_wall_text": cat.domain.describe_min_wall(), "weights": cat.weights, "sweep_mode": cat.sweep_mode,
        "early_stopped": cat.early_stopped, "notes": cat.notes, "seconds": cat.seconds,
        "reused_from": cat.reused_from, "main_levels": list(cat.main_levels),
        "levels": [{"fill": f, "kind": r.kind, "mode": r.mode, "iterations": r.iterations, "converged": r.converged,
                    "converged_by": r.converged_by, "seconds": r.seconds,
                    "ref_deflection_dE": r.mech.deflection_mm * r.mech.E, "ref_stress_MPa": r.mech.stress_reported_MPa,
                    "connected": r.mech.connected}
                   for f, r in sorted(list(cat.levels.items()) + list(cat.refined.items()))],
    }) for pid, cat in res.catalogs.items()}
    results = _f({
        "format_version": precompute.FORMAT_VERSION, "key": key, "code_version": version,
        "materials_hash": library_hash(), "solver_settings": settings, "problem": problem_to_dict(problem),
        "seconds": time.perf_counter() - t0, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "catalogs": catalogs_json, "designs": designs_json,
        "ranking": {"order": [c.design.material.id for c in ranking.cards],
                    "cards": [{"material": c.design.material.id, "state": c.state, "rank": c.rank,
                               "reason": c.reason, "badges": c.badges, "material_cost_usd": c.material_cost_usd,
                               "weight_saved_vs_strut": c.weight_saved_vs_strut,
                               "weight_saved_vs_block": c.weight_saved_vs_block} for c in ranking.cards],
                    "pareto": [asdict(p) for p in ranking.pareto], "funnel": ranking.funnel,
                    "winner": ranking.winner.material.id if ranking.winner else None,
                    "messages": ranking.messages, "caption_cost": ranking.caption_cost},
    })
    (out / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    progress.say(f"done in {(time.perf_counter() - t0) / 60:.1f} min")
    return out


def start_live(problem: Problem, quick: bool, out_root: Path = LIVE_DIR) -> Progress:
    progress = Progress()

    def work():
        try:
            progress.result_dir = run_live(problem, quick, out_root, progress)
        except Exception:
            progress.error = traceback.format_exc()
            progress.say("failed")
        finally:
            progress.done = True

    threading.Thread(target=work, name="morphic-live", daemon=True).start()
    return progress


# ----------------------------------------------------------------------------- explanation (template)
def template_explanation(r: dict) -> str:
    """Spec 10 fallback: 3-4 short sentences filled from the results only. The LLM explanation
    with its number check is step S12; until then this template is what the app shows, and every
    number in it is read straight from the results."""
    rk = r["ranking"]
    cards = {c["material"]: c for c in rk["cards"]}
    designs = {d["material"]: d for d in r["designs"]}
    win = rk.get("winner")
    if not win:
        return " ".join(rk.get("messages") or ["No material passes the limits."])
    d, c = designs[win], cards[win]
    ch = d["checks"]
    proc = {"fdm": "FDM", "sls": "SLS", "metal": "metal printing"}.get(d["process"], d["process"])
    ranked = [m for m in rk["order"] if cards[m]["state"] == "ranked"]
    s1 = (f"{win} wins at {ch['mass_g']:.1f} g, printed by {proc} at {d['fill']:.0%} fill, "
          f"with a safety factor of {ch['sf']:.1f} against the {ch['sf_target']:g} target.")
    s2 = ""
    if c.get("weight_saved_vs_strut") is not None:
        s2 = (f"That is {c['weight_saved_vs_strut'] * 100:.0f}% lighter than a simple strut design sized to the "
              f"same limits and {c['weight_saved_vs_block'] * 100:.0f}% lighter than the solid block.")
    s3 = ""
    if len(ranked) > 1:
        nxt = ranked[1]
        s3 = (f"The next lightest is {nxt} at {designs[nxt]['checks']['mass_g']:.1f} g"
              + (f", which costs ${cards[nxt]['material_cost_usd']:.2f} in material against ${c['material_cost_usd']:.2f}"
                 if cards[nxt].get("material_cost_usd") is not None and c.get("material_cost_usd") is not None else "")
              + ".")
    filtered = [m for m in rk["order"] if cards[m]["state"] == "filtered"]
    s4 = ""
    if filtered:
        lighter = [m for m in filtered if designs[m]["status"] == "pass" and designs[m]["checks"]["mass_g"] < ch["mass_g"]]
        if lighter:
            m = min(lighter, key=lambda k: designs[k]["checks"]["mass_g"])
            s4 = (f"{m} would be lighter at {designs[m]['checks']['mass_g']:.1f} g, but it needs "
                  f"{cards[m]['reason'].replace('needs ', '')}.")
    return " ".join(x for x in (s1, s2, s3, s4) if x)
