"""Catalog per process (spec 6.3), level choice (6.5), refinement (6.6), cold re-run (6.7).

One catalog = one process = one mesh. Fill levels are swept downward. Every level is
evaluated once at the reference material (E = 1, nu = 0.33) and scaled to each
material (6.4). The final re-check of each pick uses the material's real E and nu.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from . import config, evaluate, topopt
from .domain import Domain, build_domain
from .materials import Material, Process, printer_allows
from .problem import Problem


# ----------------------------------------------------------------------------- data
@dataclass
class LevelRun:
    fill: float
    xPhys: np.ndarray
    x: np.ndarray
    mech: evaluate.Mechanics  # at the reference material
    iterations: int
    converged: bool
    stalled: bool
    seconds: float
    seconds_per_iter: float
    mode: str
    snapshots: list = field(default_factory=list)
    kind: str = "catalog"  # catalog | refine | rerun

    def scaled(self, E: float) -> tuple[np.ndarray, np.ndarray]:
        return evaluate.scaled_mechanics(self.mech, E)


@dataclass
class LevelStatus:
    fill: float
    stress_pass: bool
    deflection_pass: bool
    connected: bool
    sf: float
    deflection_ratio: float  # max over cases of deflection / limit
    label: str = ""  # "", "isolated stress failure", "non-monotonic deflection"

    @property
    def passed(self) -> bool:
        return self.stress_pass and self.deflection_pass and self.connected and self.label != "non-monotonic deflection"


@dataclass
class MaterialPick:
    material_id: str
    status: str  # "pass" | "fail" | "loose"
    levels: list[LevelStatus]
    v_pick: float | None
    v_final: float | None
    window: tuple[float, float] | None
    refinement: list[LevelStatus] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class Catalog:
    process: Process
    domain: Domain
    weights: np.ndarray
    sweep_mode: str
    levels: dict[float, LevelRun] = field(default_factory=dict)
    refined: dict[float, LevelRun] = field(default_factory=dict)  # memoized by fill
    notes: list[str] = field(default_factory=list)
    seconds: float = 0.0
    early_stopped: bool = False

    def run_at(self, fill: float) -> LevelRun | None:
        return self.levels.get(fill) or self.refined.get(fill)


@dataclass
class Design:
    material: Material
    process: Process
    domain: Domain
    fill: float | None
    density: np.ndarray | None  # final density field (binary SIMP output), None if failed outright
    mech: evaluate.Mechanics | None
    checks: evaluate.Checks | None
    pick: MaterialPick
    status: str  # pass | fail
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    converged: bool = True
    rerun: dict = field(default_factory=dict)  # cold re-run info + snapshots
    printer_allowed: bool = True

    @property
    def mass_g(self) -> float | None:
        return self.checks.mass_g if self.checks else None


# ----------------------------------------------------------------------------- level choice
def level_statuses(levels: dict[float, LevelRun], domain: Domain, material: Material, sf_target: float) -> list[LevelStatus]:
    problem = domain.problem
    limits = np.array([lc.max_deflection_mm for lc in problem.load_cases])
    in_plane = np.array([lc.has_in_plane for lc in problem.load_cases])
    out = []
    for fill in sorted(levels):
        run = levels[fill]
        d, s = run.scaled(material.E)
        smax = float(s[in_plane].max()) if in_plane.any() else 0.0
        sf = material.strength / smax if smax > 0 else np.inf
        ratio = float(np.max(d[in_plane] / limits[in_plane])) if in_plane.any() else 0.0
        out.append(LevelStatus(fill=fill, stress_pass=sf >= sf_target, deflection_pass=ratio <= 1.0,
                               connected=run.mech.connected, sf=sf, deflection_ratio=ratio))
    # deflection must improve as fill rises; an odd level is treated as failed
    for k in range(1, len(out)):
        if out[k].deflection_ratio > out[k - 1].deflection_ratio + 1e-9 and out[k - 1].connected and out[k].connected:
            out[k].label = "non-monotonic deflection"
    return out


def choose_level(statuses: list[LevelStatus]) -> tuple[float | None, tuple[float, float] | None, list[str]]:
    """Spec 6.5: v_pick = the lowest level that passes with the next level up also passing.
    A single stress-only failure above the pick with passes on both sides is isolated and ignored.
    Two or more adjacent failures above the pick move the pick above them."""
    notes: list[str] = []
    n = len(statuses)
    if n == 0:
        return None, None, ["no levels"]
    passed = [s.passed for s in statuses]
    # candidate: passes and the next level up passes (the top level counts if it passes)
    cands = [i for i in range(n) if passed[i] and (i == n - 1 or passed[i + 1])]
    if not cands:
        return None, None, ["no fill level passes with the level above it also passing"]
    i = cands[0]
    while True:
        # scan the levels above i+1 for failures
        moved = False
        j = i + 1
        while j < n:
            if passed[j]:
                j += 1
                continue
            k = j
            while k < n and not passed[k]:
                k += 1
            run_len = k - j
            s = statuses[j]
            stress_only = (not s.stress_pass) and s.deflection_pass and s.connected and s.label == ""
            if run_len == 1 and stress_only and j - 1 >= 0 and passed[j - 1] and k < n and passed[k]:
                s.label = "isolated stress failure"
                notes.append(f"isolated stress failure at {s.fill:.0%} ignored")
                j = k
                continue
            # a real failure run above the pick: move the pick above it
            above = [c for c in cands if c >= k]
            if not above:
                return None, None, [f"levels above {statuses[j].fill:.0%} fail and no higher passing pair exists"]
            i = above[0]
            moved = True
            notes.append(f"pick moved above failing levels at {statuses[j].fill:.0%}-{statuses[k-1].fill:.0%}")
            break
        if not moved:
            break
    v = statuses[i].fill
    window = (statuses[i - 1].fill, v) if i > 0 else None
    return v, window, notes


# ----------------------------------------------------------------------------- catalog sweep
def _run_level(cat: Catalog, fill: float, mode: str, x0, snapshot_every: int, kind: str, callback,
               max_iters: int | None = None) -> LevelRun:
    prob = cat.domain.topopt_problem(config.CATALOG_REFERENCE_NU, cat.weights)
    settings = topopt.TopOptSettings(volfrac=fill, rmin=cat.domain.rmin_elements, mode=mode, x0=x0,
                                     snapshot_every=snapshot_every)
    if max_iters is not None:
        settings.max_iters = max_iters

    def cb(info, xPhys):
        if callback:
            callback({"process": cat.process.id, "fill": fill, "kind": kind, **info}, xPhys)

    res = topopt.run(prob, settings, cb)
    mech = evaluate.analyze_design(cat.domain, res.xPhys, config.CATALOG_REFERENCE_E, config.CATALOG_REFERENCE_NU)
    return LevelRun(fill=fill, xPhys=res.xPhys, x=res.x, mech=mech, iterations=res.iterations,
                    converged=res.converged, stalled=res.stalled, seconds=res.seconds,
                    seconds_per_iter=res.seconds_per_iter, mode=mode, snapshots=res.snapshots, kind=kind)


def _all_fail_everything(cat: Catalog, fill: float, materials: list[Material], sf_target: float) -> bool:
    for m in materials:
        st = level_statuses({fill: cat.levels[fill]}, cat.domain, m, sf_target)[0]
        if st.stress_pass or st.deflection_pass:
            return False
    return True


def _all_pass(cat: Catalog, fill: float, materials: list[Material], sf_target: float) -> bool:
    for m in materials:
        st = level_statuses({fill: cat.levels[fill]}, cat.domain, m, sf_target)[0]
        if not st.passed:
            return False
    return True


def run_catalog(problem: Problem, process: Process, materials: list[Material], cap: int,
                sweep_mode: str = "warm", levels=config.FILL_LEVELS, early_stop: bool = True,
                extend_low: bool = True, snapshot_every: int = config.SNAPSHOT_EVERY_CATALOG,
                callback=None) -> Catalog:
    """Downward sweep of fill levels for one process. sweep_mode: "warm" (live) or "cold" (demo)."""
    t0 = time.perf_counter()
    domain = build_domain(problem, process.id, process.min_wall_mm, cap)
    prob0 = domain.topopt_problem(config.CATALOG_REFERENCE_NU)
    weights = topopt.normalization_weights(prob0, config.NORMALIZATION_FILL)
    cat = Catalog(process=process, domain=domain, weights=weights, sweep_mode=sweep_mode)
    cat.notes += domain.warnings
    sf = problem.safety_factor
    prev: LevelRun | None = None
    seq = list(levels)
    if extend_low:
        seq = seq + [f for f in config.FILL_LEVELS_EXTRA_LOW if f < min(seq)]
    for idx, fill in enumerate(seq):
        if fill in config.FILL_LEVELS_EXTRA_LOW and fill not in levels:
            if not _all_pass(cat, min(cat.levels), materials, sf):
                break
            cat.notes.append(f"every material passes at {min(cat.levels):.0%}: extending down to {fill:.0%}")
        mode = "cold" if (sweep_mode == "cold" or prev is None) else "warm"
        run = _run_level(cat, fill, mode, None if mode == "cold" else prev.x, snapshot_every, "catalog", callback)
        cat.levels[fill] = run
        prev = run
        if early_stop and idx == 0 and _all_fail_everything(cat, fill, materials, sf):
            cat.early_stopped = True
            cat.notes.append(f"{fill:.0%} fails every limit for every material: sweep stopped")
            break
    if extend_low and min(cat.levels) <= min(config.FILL_LEVELS_EXTRA_LOW) and _all_pass(cat, min(cat.levels), materials, sf):
        cat.notes.append("limits are loose; part size is set by the minimum wall")
    cat.seconds = time.perf_counter() - t0
    return cat


# ----------------------------------------------------------------------------- refinement
def refine_pick(cat: Catalog, material: Material, pick: MaterialPick, quick: bool = False,
                callback=None) -> MaterialPick:
    """Bisect inside the window, 3 steps, warm-started from the v_pick design; memoized by fill."""
    sf = cat.domain.problem.safety_factor
    if pick.v_pick is None or quick or pick.window is None:
        pick.v_final = pick.v_pick
        if quick and pick.v_pick is not None:
            pick.notes.append("quick mode: catalog level reported without refinement")
        return pick
    lo, hi = pick.window  # lo fails, hi passes
    base = cat.levels[hi]
    passing = [hi]
    for _ in range(config.REFINE_BISECTION_STEPS):
        mid = round(0.5 * (lo + hi), 4)
        run = cat.refined.get(mid)
        if run is None:
            run = _run_level(cat, mid, "refine", base.x, config.SNAPSHOT_EVERY_CATALOG, "refine", callback)
            cat.refined[mid] = run
        st = level_statuses({mid: run}, cat.domain, material, sf)[0]
        pick.refinement.append(st)
        if st.passed:
            hi = mid
            passing.append(mid)
        else:
            lo = mid
    # non-monotonic noise: keep the smallest fill that passed
    v_final = min(passing)
    if v_final != hi:
        pick.notes.append("refinement results were not monotonic; kept the smallest passing fill")
    pick.v_final = v_final
    return pick


def final_recheck(cat: Catalog, material: Material, pick: MaterialPick, callback=None):
    """Re-run the chosen shape with the real E and nu; step up if it fails (spec 6.6 step 5)."""
    sf = cat.domain.problem.safety_factor
    candidates = []
    if pick.v_final is not None:
        candidates.append(pick.v_final)
    candidates += sorted({s.fill for s in pick.refinement if s.passed and s.fill > (pick.v_final or 0)})
    if pick.v_pick is not None and pick.v_pick not in candidates:
        candidates.append(pick.v_pick)
    # catalog levels above the pick as a last resort
    if pick.v_pick is not None:
        candidates += [f for f in sorted(cat.levels) if f > pick.v_pick]
    tried = []
    for fill in candidates:
        run = cat.run_at(fill)
        if run is None:
            continue
        mech, checks = evaluate.evaluate(cat.domain, run.xPhys, material, sf)
        tried.append(fill)
        if checks.passed_in_plane:
            if fill != pick.v_final:
                pick.notes.append(f"re-check with real E and nu failed at {pick.v_final:.1%}; stepped up to {fill:.1%}")
                pick.v_final = fill
            return run, mech, checks
    return None, None, None


def pick_material(cat: Catalog, material: Material, quick: bool = False, callback=None) -> Design:
    problem = cat.domain.problem
    sf = problem.safety_factor
    statuses = level_statuses(cat.levels, cat.domain, material, sf)
    v, window, notes = choose_level(statuses)
    pick = MaterialPick(material_id=material.id, status="fail", levels=statuses, v_pick=v, v_final=None,
                        window=window, notes=notes)
    allowed = printer_allows(problem.printer, cat.process)
    if v is None:
        # fail: report the best numbers (at 60% or the best passing stress)
        top = max(cat.levels)
        run = cat.levels[top]
        mech, checks = evaluate.evaluate(cat.domain, run.xPhys, material, sf)
        pick.reason = "; ".join(notes) if notes else "no fill level passes"
        return Design(material=material, process=cat.process, domain=cat.domain, fill=top, density=run.xPhys,
                      mech=mech, checks=checks, pick=pick, status="fail",
                      reasons=checks.fail_reasons or [pick.reason], notes=notes, printer_allowed=allowed,
                      converged=run.converged or run.stalled)
    if window is None:
        pick.notes.append("passes at the lowest level computed; limits are loose")
        pick.status = "loose"
    pick = refine_pick(cat, material, pick, quick, callback)
    run, mech, checks = final_recheck(cat, material, pick, callback)
    if run is None:
        pick.status = "fail"
        top = max(cat.levels)
        run = cat.levels[top]
        mech, checks = evaluate.evaluate(cat.domain, run.xPhys, material, sf)
        return Design(material=material, process=cat.process, domain=cat.domain, fill=top, density=run.xPhys,
                      mech=mech, checks=checks, pick=pick, status="fail",
                      reasons=checks.fail_reasons + ["re-check with real material failed at every level"],
                      notes=pick.notes, printer_allowed=allowed, converged=run.converged or run.stalled)
    if pick.status != "loose":
        pick.status = "pass" if checks.passed else "fail"
    status = "pass" if checks.passed else "fail"
    d = Design(material=material, process=cat.process, domain=cat.domain, fill=pick.v_final, density=run.xPhys,
               mech=mech, checks=checks, pick=pick, status=status, reasons=checks.fail_reasons,
               notes=pick.notes + checks.notes, printer_allowed=allowed, converged=run.converged or run.stalled)
    if not d.converged:
        d.notes.append("not fully converged")
    return d


# ----------------------------------------------------------------------------- cold re-run
def cold_rerun(design: Design, cat: Catalog, callback=None) -> Design:
    """Re-run the chosen fill cold from uniform density with a snapshot every iteration (spec 6.7)."""
    if design.fill is None:
        return design
    sf = cat.domain.problem.safety_factor
    run = _run_level(cat, design.fill, "cold", None, config.SNAPSHOT_EVERY_COLD_RERUN, "rerun", callback)
    mech, checks = evaluate.evaluate(cat.domain, run.xPhys, design.material, sf)
    info = {"fill": design.fill, "iterations": run.iterations, "converged": run.converged or run.stalled,
            "seconds": run.seconds, "snapshots": run.snapshots, "replaced": False, "note": ""}
    if checks.passed:
        design.density, design.mech, design.checks = run.xPhys, mech, checks
        design.reasons = checks.fail_reasons
        info["replaced"] = True
    else:
        info["note"] = "animation shows an independent run at the same fill level"
        design.notes.append(info["note"])
    design.rerun = info
    return design


# ----------------------------------------------------------------------------- everything
@dataclass
class RunResult:
    problem: Problem
    cap: int
    sweep_mode: str
    catalogs: dict[str, Catalog]
    designs: list[Design]
    seconds: float
    notes: list[str] = field(default_factory=list)


def run_all(problem: Problem, materials: dict[str, Material], processes: dict[str, Process], cap: int,
            sweep_mode: str = "warm", quick: bool = False, rerun: str = "winner", levels=config.FILL_LEVELS,
            callback=None) -> RunResult:
    """Run every process catalog, pick every material, and do the cold re-runs.

    rerun: "winner" (live: the overall winner only), "per_process" (demo: top design per process), "none".
    """
    t0 = time.perf_counter()
    chosen = [materials[m] for m in problem.materials if m in materials]
    by_proc: dict[str, list[Material]] = {}
    for m in chosen:
        by_proc.setdefault(m.process, []).append(m)
    catalogs: dict[str, Catalog] = {}
    designs: list[Design] = []
    for pid, mats in by_proc.items():
        proc = processes[pid]
        cat = run_catalog(problem, proc, mats, cap, sweep_mode=sweep_mode, levels=levels,
                          snapshot_every=0 if quick else config.SNAPSHOT_EVERY_CATALOG, callback=callback)
        catalogs[pid] = cat
        for m in mats:
            designs.append(pick_material(cat, m, quick=quick, callback=callback))
    if rerun != "none" and not quick:
        passing = [d for d in designs if d.status == "pass" and d.printer_allowed]
        targets: list[Design] = []
        if rerun == "winner" and passing:
            targets = [min(passing, key=lambda d: d.mass_g)]
        elif rerun == "per_process":
            for pid in catalogs:
                ps = [d for d in passing if d.process.id == pid]
                if ps:
                    targets.append(min(ps, key=lambda d: d.mass_g))
        for d in targets:
            cold_rerun(d, catalogs[d.process.id], callback)
    return RunResult(problem=problem, cap=cap, sweep_mode=sweep_mode, catalogs=catalogs, designs=designs,
                     seconds=time.perf_counter() - t0)
