"""Precompute the demo parts (spec step S14) and store the results for instant loading.

Per part, the full pipeline runs at the cached cap with a cold run per fill level:
catalogs for every process, level choice, refinement, the real-material re-check, the
cold re-run of the top design per process, strut and block baselines, geometry export
with the smoothed re-check (whose numbers replace the grid numbers, spec 9.6), and the
ranking. Each part is written to examples/cache/<part>/ as soon as it finishes:

  results.json         every number the UI shows, plus run settings and the cache key
  densities.npz        final density field of every design, every catalog / refinement level
  utilization.npz      recovered nodal utilization per design and load case (float32)
  rerun_<process>.npz  cold re-run snapshots, every iteration (uint8, for the animation)
  catalog_<process>.npz catalog snapshots every 2 iterations (uint8; large, not committed)
  <material>.stl/.svg/.dxf  exported geometry of every design that has one

The cache key is SHA-256 of (problem JSON + materials hash + solver settings + code version),
as in spec section 12. The run bundle (S13) wraps this format; it is not built yet.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

import numpy as np

from . import catalog, config, evaluate, geometry, rank, topopt
from .baseline import strut_baseline
from .domain import build_domain
from .evaluate import Checks, HandCheck
from .materials import library_hash, load_materials, load_processes
from .problem import Problem, problem_from_dict, problem_to_dict

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "examples" / "cache"
FORMAT_VERSION = 1


# ----------------------------------------------------------------------------- keys / versions
def code_version() -> str:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "morphic", "pyproject.toml", "uv.lock"],
                               cwd=ROOT, capture_output=True, text=True).stdout.strip()
        return head + ("-dirty" if dirty else "")
    except Exception:
        return "unknown"


def cache_key(problem: Problem, settings: dict, version: str) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(problem_to_dict(problem), sort_keys=True).encode())
    h.update(library_hash().encode())
    h.update(json.dumps(settings, sort_keys=True, default=str).encode())
    h.update(version.encode())
    return h.hexdigest()


# ----------------------------------------------------------------------------- serialization
def _f(v):
    if v is None:
        return None
    if isinstance(v, (np.floating, float)):
        v = float(v)
        return v if np.isfinite(v) else ("inf" if v > 0 else "-inf")
    if isinstance(v, (np.integer, int)):
        return int(v)
    if isinstance(v, np.ndarray):
        return [_f(x) for x in v.tolist()]
    if isinstance(v, (list, tuple)):
        return [_f(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _f(x) for k, x in v.items()}
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    return v


def _hand(h: HandCheck) -> dict:
    return _f({"name": h.name, "passed": h.passed, "sf": h.sf, "detail": h.detail, "where": h.where,
               "suggestion": h.suggestion})


def _checks(c: Checks | None) -> dict | None:
    if c is None:
        return None
    return _f({"passed": c.passed, "passed_in_plane": c.passed_in_plane, "sf": c.sf, "sf_raw": c.sf_raw,
               "sf_target": c.sf_target, "stress_reported_MPa": c.stress_reported_MPa,
               "stress_raw_MPa": c.stress_raw_MPa, "stress_pass": c.stress_pass,
               "deflection_mm": c.deflection_mm, "deflection_limit_mm": c.deflection_limit_mm,
               "deflection_pass": c.deflection_pass, "mass_g": c.mass_g,
               "out_of_plane": [_hand(h) for h in c.out_of_plane], "bearing": [_hand(h) for h in c.bearing],
               "fail_reasons": c.fail_reasons, "notes": c.notes})


def _status(s: catalog.LevelStatus) -> dict:
    return _f({"fill": s.fill, "passed": s.passed, "stress_pass": s.stress_pass,
               "deflection_pass": s.deflection_pass, "connected": s.connected, "sf": s.sf,
               "deflection_ratio": s.deflection_ratio, "label": s.label})


# ----------------------------------------------------------------------------- pipeline
class Logger:
    def __init__(self, path: Path | None):
        self.path = path
        self.t0 = time.perf_counter()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, msg: str) -> None:
        el = time.perf_counter() - self.t0
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{el / 3600:5.2f} h] {msg}"
        print(line, flush=True)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")


def keep_awake(on: bool = True) -> None:
    """Ask Windows not to sleep while this process runs (cleared automatically when it exits).
    It does not stop sleep on lid close."""
    if sys.platform != "win32":
        return
    import ctypes

    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))


def restore_catalogs(problem: Problem, materials: dict, processes: dict, cap: int, cache_dir: Path,
                     pids: list[str], log=print) -> dict:
    """Rebuild catalogs from a cached part: every catalog and refinement level's density field is
    re-evaluated at the reference material (deterministic, so the numbers equal the original run).
    Design variables are not stored, so a restored catalog cannot warm-start new refinement runs."""
    with open(cache_dir / "results.json", encoding="utf-8") as f:
        old = json.load(f)
    with np.load(cache_dir / "densities.npz") as z:
        dens = {k: np.array(z[k]) for k in z.files}
    out = {}
    for pid in pids:
        proc = processes[pid]
        info = old["catalogs"][pid]
        dom = build_domain(problem, pid, proc.min_wall_mm, cap)
        assert [dom.mesh.nelx, dom.mesh.nely] == info["mesh"], (pid, info["mesh"])
        prob0 = dom.topopt_problem(config.CATALOG_REFERENCE_NU)
        weights = topopt.normalization_weights(prob0, config.NORMALIZATION_FILL)
        cat = catalog.Catalog(process=proc, domain=dom, weights=weights, sweep_mode=info["sweep_mode"],
                              main_levels=tuple(old["solver_settings"]["levels_used"]),
                              reused_from=old["code_version"])
        cat.notes = list(info["notes"]) + [f"restored from cache (code {old['code_version'][:8]})"]
        cat.early_stopped, cat.seconds = info["early_stopped"], info["seconds"]
        meta = {(round(lv["fill"], 4), lv["kind"]): lv for lv in info["levels"]}
        for key, xPhys in dens.items():
            parts = key.split("/")
            if len(parts) != 3 or parts[0] != pid:
                continue
            kind, fill = parts[1], float(parts[2])
            m = meta[(round(fill, 4), kind)]
            mech = evaluate.analyze_design(dom, xPhys, config.CATALOG_REFERENCE_E, config.CATALOG_REFERENCE_NU)
            run = catalog.LevelRun(fill=fill, xPhys=xPhys, x=None, mech=mech, iterations=m["iterations"],
                                   converged=m["converged"], converged_by=m["converged_by"], seconds=m["seconds"],
                                   seconds_per_iter=m["seconds"] / max(m["iterations"], 1), mode=m["mode"],
                                   kind=kind)
            (cat.levels if kind == "catalog" else cat.refined)[fill] = run
        log(f"  restored catalog {pid}: {len(cat.levels)} levels, {len(cat.refined)} refined "
            f"(from {old['code_version'][:8]})")
        out[pid] = cat
    return out


def _recheck_with_step_up(design: catalog.Design, cat: catalog.Catalog, out_dir: Path, log) -> dict:
    """Geometry export + smoothed re-check (spec 9). If the smoothed shape fails where the grid
    shape passed, move to the next passing fill level, re-export, and add a note (spec 8)."""
    material, dom = design.material, cat.domain
    sf = dom.problem.safety_factor
    candidates = [(design.fill, design.density)]
    if design.status == "pass":
        ups = sorted({s.fill for s in design.pick.refinement if s.passed and s.fill > design.fill}
                     | {s.fill for s in design.pick.levels if s.passed and s.fill > design.fill})
        candidates += [(f, cat.run_at(f).xPhys) for f in ups if cat.run_at(f) is not None]
    first = None
    for fill, dens in candidates:
        try:
            geom = geometry.build_geometry(dom, dens)
        except geometry.GeometryError as exc:
            log(f"    {material.id}: geometry failed at {fill:.1%}: {exc}")
            continue
        frac, mech, checks = geometry.smoothed_recheck(dom, geom, material, sf)
        rec = {"fill": fill, "geom": geom, "fraction": frac, "mech": mech, "checks": checks, "density": dens}
        if first is None:
            first = rec
        if design.status != "pass" or checks.passed:
            if fill != design.fill:
                design.notes.append(f"smoothed re-check failed at {design.fill:.1%}; moved to {fill:.1%}")
            return rec
        log(f"    {material.id}: smoothed re-check fails at {fill:.1%} ({'; '.join(checks.fail_reasons)})")
    if first is not None and design.status == "pass":
        design.notes.append("smoothed re-check fails at every passing level; grid result marked failed")
    return first or {}


def precompute_part(part_path: Path, out_root: Path = CACHE_DIR, cap: int = config.ELEMENT_CAP_CACHED,
                    sweep_mode: str = config.ELEMENT_CAP_CACHED_SWEEP, levels=config.FILL_LEVELS,
                    log=print, save_catalog_snapshots: bool = True, version: str | None = None,
                    recompute: list[str] | None = None) -> Path:
    """recompute: if given, only these processes are re-run; the other catalogs are restored from
    the existing cache of this part (partial update)."""
    t0 = time.perf_counter()
    with open(part_path, encoding="utf-8") as f:
        problem = problem_from_dict(json.load(f))
    materials, processes = load_materials(), load_processes()
    stem = Path(part_path).stem
    out = Path(out_root) / stem
    out.mkdir(parents=True, exist_ok=True)
    settings = config.solver_settings() | {"cap_used": cap, "sweep_mode_used": sweep_mode,
                                           "levels_used": list(levels), "format_version": FORMAT_VERSION}
    version = version or code_version()
    key = cache_key(problem, settings, version)
    log(f"PART {stem}: {problem.name} | cap {cap}, {sweep_mode} per level, {len(levels)} levels | key {key[:12]}")
    prebuilt = {}
    if recompute is not None:
        procs_used = sorted({materials[m].process for m in problem.materials})
        keep = [p for p in procs_used if p not in recompute]
        log(f"  partial update: re-run {sorted(recompute)}, restore {keep}")
        prebuilt = restore_catalogs(problem, materials, processes, cap, out, keep, log)

    last_beat = {"t": 0.0}

    def cb(info, xPhys):
        it = info["iter"]
        if it == 1:
            log(f"  {info['process']} {info['kind']} fill {info['fill']:.4f} start")
        if time.perf_counter() - last_beat["t"] > 120:  # heartbeat every 2 min
            last_beat["t"] = time.perf_counter()
            log(f"  {info['process']} {info['kind']} fill {info['fill']:.4f} it {it} beta {info['beta']} "
                f"obj {info['objective']:.4f} change {info['change']:.3f}")

    res = catalog.run_all(problem, materials, processes, cap, sweep_mode=sweep_mode, rerun="per_process",
                          levels=levels, callback=cb, prebuilt=prebuilt)
    for pid, cat in res.catalogs.items():
        log(f"  catalog {pid}: mesh {cat.domain.mesh.nelx} x {cat.domain.mesh.nely}, {cat.seconds / 60:.1f} min, "
            f"levels {sorted(cat.levels)}, refined {sorted(cat.refined)}")
    for d in res.designs:
        log(f"  pick {d.material.id:9s} {d.status:4s} fill {d.fill if d.fill is None else round(d.fill, 4)} "
            f"mass {d.mass_g if d.mass_g is None else round(d.mass_g, 2)} g"
            + (f" | rerun {d.rerun['iterations']} it, replaced={d.rerun['replaced']}" if d.rerun else ""))

    # baselines, geometry + smoothed re-check (its numbers replace the grid numbers)
    baselines, extra = {}, {}
    for d in res.designs:
        cat = res.catalogs[d.process.id]
        b = strut_baseline(cat.domain, d.material, problem.safety_factor)
        baselines[d.material.id] = b
        grid_checks = d.checks
        rec = _recheck_with_step_up(d, cat, out, log) if d.density is not None else {}
        if rec:
            d.fill, d.density = rec["fill"], rec["density"]
            d.mech, d.checks = rec["mech"], rec["checks"]
            d.status = "pass" if (d.status == "pass" and rec["checks"].passed) else "fail"
            d.reasons = rec["checks"].fail_reasons
            files = geometry.export_all(rec["geom"], out / d.material.id, cat.domain)
            extra[d.material.id] = {"grid_checks": grid_checks, "geometry": rec["geom"], "files": files}
        log(f"  {d.material.id:9s} strut {b.strut_width_mm and round(b.strut_width_mm, 2)} mm "
            f"mass {b.mass_strut_g and round(b.mass_strut_g, 2)} g | smoothed: "
            + (f"{d.status}, SF {d.checks.sf:.2f}, mass {d.checks.mass_g:.2f} g" if rec else "no geometry"))
    ranking = rank.rank_designs(res, baselines)

    # ---- write
    dens, util = {}, {}
    for pid, cat in res.catalogs.items():
        for fill, run in list(cat.levels.items()) + list(cat.refined.items()):
            dens[f"{pid}/{run.kind}/{fill:.4f}"] = run.xPhys
        if save_catalog_snapshots and not cat.reused_from:  # keep the original file of a restored catalog
            snaps = {f"{run.kind}_{fill:.4f}_it{it}": a for fill, run in
                     list(cat.levels.items()) + list(cat.refined.items()) for it, a in run.snapshots}
            np.savez_compressed(out / f"catalog_{pid}.npz", **snaps)
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
        "format_version": FORMAT_VERSION, "key": key, "code_version": version, "materials_hash": library_hash(),
        "solver_settings": settings, "problem": problem_to_dict(problem), "seconds": time.perf_counter() - t0,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"), "catalogs": catalogs_json, "designs": designs_json,
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
    log(f"PART {stem} done in {(time.perf_counter() - t0) / 60:.1f} min -> {out} | winner {results['ranking']['winner']}")
    return out


def load_cached(stem: str, root: Path = CACHE_DIR) -> dict:
    """Load a precomputed part's results (numbers only; arrays load lazily from the .npz files)."""
    with open(Path(root) / stem / "results.json", encoding="utf-8") as f:
        return json.load(f)


def precompute_all(parts: list[str], log_path: Path | None, cap: int, out_root: Path = CACHE_DIR,
                   levels=config.FILL_LEVELS, recompute: dict | None = None) -> int:
    """recompute: {part stem: [process ids]} for a partial update; parts not named run in full."""
    log = Logger(log_path)
    keep_awake(True)
    version = code_version()
    log(f"precompute start: {len(parts)} part(s), cap {cap}, code {version}")
    failed = 0
    for part in parts:
        try:
            rc = (recompute or {}).get(Path(part).stem)
            precompute_part(Path(part), out_root, cap, levels=levels, log=log, version=version, recompute=rc)
        except Exception:
            failed += 1
            log(f"PART {part} FAILED:\n{traceback.format_exc()}")
    log(f"precompute finished: {len(parts) - failed} ok, {failed} failed")
    keep_awake(False)
    return 1 if failed else 0
