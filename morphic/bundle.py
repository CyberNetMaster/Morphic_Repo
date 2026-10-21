"""Portable local run bundles and isolated strict/loose reproduction (spec 12).

Settings are restored in a fresh process BEFORE importing engine modules: several
engine default arguments bind config constants at import time. Bundles contain data,
never executable code. A manifest detects corruption; it is not a digital signature.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .cache import ROOT, artifact_names, code_version, load_results

FORMAT_VERSION = 1
STRICT_RTOL = .005
LOOSE_RTOL = .02


def _json(data) -> bytes:
    return (json.dumps(data, indent=2, allow_nan=False) + "\n").encode("utf-8")


def environment() -> str:
    """An explicit allowlist: never enumerate environment variables or read .env."""
    rows = ["Captured at bundle creation (historical solve environment was not stored by S14).",
            f"Python: {platform.python_version()}", f"Platform: {platform.platform()}",
            f"CPU logical count: {os.cpu_count()}"]
    for name in ("numpy", "scipy", "pypardiso", "mkl", "shapely", "scikit-image", "trimesh", "fpdf2"):
        try:
            value = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            value = "not installed"
        rows.append(f"{name}: {value}")
    try:
        import mkl
        rows.append(f"MKL maximum threads: {mkl.get_max_threads()}")
    except ImportError:
        rows.append("MKL maximum threads: unavailable")
    return "\n".join(rows) + "\n"


def create_bundle(cache_dir: Path | str, output: Path | str, *, materials_path=None,
                  processes_path=None) -> Path:
    from .materials import MATERIALS_PATH, PROCESSES_PATH, library_hash
    from .report import write_report
    source, output = Path(cache_dir), Path(output)
    results = load_results(source)
    materials_path = Path(materials_path or MATERIALS_PATH)
    processes_path = Path(processes_path or PROCESSES_PATH)
    if results["materials_hash"] != library_hash(materials_path, processes_path):
        raise ValueError("material/process library differs from the library used for this cache")
    files = {}
    for name in sorted(artifact_names(results)):
        path = source / name
        if not path.exists() and (name == "utilization.npz" or name.startswith("rerun_")):
            continue
        if path.is_symlink():
            raise ValueError("bundle artifacts must be regular files")
        files[name] = path.read_bytes()
    files.update({"problem.json": _json(results["problem"]),
        "materials.yaml": materials_path.read_bytes(), "processes.yaml": processes_path.read_bytes(),
        "solver_settings.json": _json(results["solver_settings"]),
        "code_version.txt": (results["code_version"] + "\n").encode(),
        "environment.txt": environment().encode()})
    with tempfile.TemporaryDirectory(prefix="morphic-report-") as tmp:
        report = write_report(source, Path(tmp) / "report.pdf", materials_path=materials_path,
                              processes_path=processes_path)
        files["report.pdf"] = report.read_bytes()
    files["manifest.json"] = _json({"format_version": FORMAT_VERSION, "exporter_version": code_version(),
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())}})
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".zip", delete=False) as f:
        temporary = Path(f.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


def _unpack(path: Path, directory: Path) -> dict:
    """Validate before writing. Reject traversal, duplicates, links, and oversized archives."""
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        if len(names) != len(set(names)) or len(names) > 128:
            raise ValueError("duplicate or excessive bundle members")
        for info in infos:
            if (not info.filename or Path(info.filename).name != info.filename
                    or "/" in info.filename or "\\" in info.filename or ":" in info.filename
                    or info.filename.startswith(".") or (info.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("unsafe bundle member")
        if sum(i.file_size for i in infos) > 2_000_000_000:
            raise ValueError("bundle exceeds 2 GB uncompressed limit")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format_version") != FORMAT_VERSION:
            raise ValueError("unsupported bundle format")
        if set(manifest["files"]) != set(names) - {"manifest.json"}:
            raise ValueError("bundle manifest member mismatch")
        results = json.loads(archive.read("results.json"))
        required = {"results.json", "densities.npz", "problem.json", "materials.yaml", "processes.yaml",
                    "solver_settings.json", "code_version.txt", "environment.txt", "report.pdf"}
        artifacts = artifact_names(results)
        required |= {n for n in artifacts if n != "utilization.npz" and not n.startswith("rerun_")}
        allowed = required | artifacts | {"manifest.json"}
        if not required <= set(names) or not set(names) <= allowed:
            raise ValueError("missing or unexpected bundle artifact")
        for name in names:
            content = archive.read(name)
            if name != "manifest.json" and hashlib.sha256(content).hexdigest() != manifest["files"][name]:
                raise ValueError(f"bundle checksum mismatch: {name}")
            (directory / name).write_bytes(content)
    results = load_results(directory)
    from .materials import library_hash
    if library_hash(directory / "materials.yaml", directory / "processes.yaml") != results["materials_hash"]:
        raise ValueError("bundled library hash mismatch")
    if json.loads((directory / "problem.json").read_text(encoding="utf-8")) != results["problem"]:
        raise ValueError("bundled problem mismatch")
    if json.loads((directory / "solver_settings.json").read_text(encoding="utf-8")) != results["solver_settings"]:
        raise ValueError("bundled settings mismatch")
    if (directory / "code_version.txt").read_text().strip() != results["code_version"]:
        raise ValueError("bundled code version mismatch")
    return results


@dataclass
class Comparison:
    path: str
    expected: object
    actual: object
    passed: bool
    relative_error: float | None = None


def compare(expected, actual, rtol: float, path="") -> list[Comparison]:
    """Symmetric schema traversal: missing/extra fields, NaNs and changed infinity fail."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        rows = []
        for key in sorted(expected.keys() | actual.keys()):
            here = f"{path}.{key}" if path else str(key)
            if key not in expected or key not in actual:
                rows.append(Comparison(here, expected.get(key), actual.get(key), False))
            else:
                rows.extend(compare(expected[key], actual[key], rtol, here))
        return rows
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [Comparison(path + ".length", len(expected), len(actual), False)]
        return [r for i, (a, b) in enumerate(zip(expected, actual)) for r in compare(a, b, rtol, f"{path}[{i}]")]
    if isinstance(expected, (int, float)) and not isinstance(expected, bool) and isinstance(actual, (int, float)):
        a, b = float(expected), float(actual)
        if not (math.isfinite(a) and math.isfinite(b)):
            return [Comparison(path, expected, actual, a == b and not math.isnan(a))]
        error = abs(a - b) / abs(a) if a else (0.0 if b == 0 else None)
        return [Comparison(path, expected, actual, abs(a - b) <= rtol * abs(a) + 1e-12, error)]
    return [Comparison(path, expected, actual, expected == actual)]


def reported_numbers(results: dict) -> dict:
    """UI physics, geometry, baselines and ranking; excludes historical optimizer telemetry.

    Targets/fill are replay inputs; iteration counts, timings, reference catalog
    histories, and pre-smoothing grid checks are not final reported measurements.
    Text prose is not a numerical measurement; structured hand-check SFs are checked.
    """
    def numerical(value):
        if isinstance(value, dict):
            out = {k: numerical(v) for k, v in value.items()
                    if k not in {"files", "notes", "note", "detail", "where", "suggestion", "fail_reasons",
                                 "reason", "name", "text", "struts", "badges"}}
            # Hand-check forces, stresses, widths and locations are embedded in
            # the current engine's prose; compare those displayed numbers too.
            for key in ("detail", "where", "suggestion"):
                if key in value:
                    out[key + "_numbers"] = [float(v) for v in
                        re.findall(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", value[key])]
            return out
        if isinstance(value, list):
            return [numerical(v) for v in value]
        return value
    return {"designs": {d["material"]: numerical({k: d[k] for k in
        ("process", "fill", "status", "printer_allowed", "checks", "baseline", "geometry", "mesh_h_mm", "effective_min_wall")})
        for d in results["designs"]}, "ranking": numerical({k: results["ranking"][k] for k in
        ("order", "cards", "pareto", "funnel", "winner")})}


def _strict(directory: Path, results: dict) -> dict:
    """Rebuild exported shapes, run FE, resize baselines, and rank from recomputed checks."""
    from dataclasses import asdict
    import numpy as np
    from . import catalog, evaluate, geometry, rank
    from .baseline import strut_baseline
    from .domain import build_domain
    from .materials import load_materials, load_processes, printer_allows
    from .precompute import _checks, _f
    from .problem import problem_from_dict
    p = problem_from_dict(results["problem"])
    mats = load_materials(directory / "materials.yaml")
    procs = load_processes(directory / "processes.yaml")
    fresh = copy.deepcopy(results)
    designs, baselines = [], {}
    domains = {}
    with np.load(directory / "densities.npz", allow_pickle=False) as z:
        for d in fresh["designs"]:
            mid, pid = d["material"], d["process"]
            if pid not in domains:
                domains[pid] = build_domain(p, pid, procs[pid].min_wall_mm, results["solver_settings"]["cap_used"])
            dom = domains[pid]
            if [dom.mesh.nelx, dom.mesh.nely] != results["catalogs"][pid]["mesh"]:
                raise ValueError("saved mesh is inconsistent with bundled settings")
            key = f"design/{mid}"
            dens = np.asarray(z[key], dtype=float) if key in z.files else None
            if dens is None and d["checks"] is not None:
                raise ValueError(f"missing stored density: {mid}")
            if dens is not None and (dens.shape != (dom.mesh.nel,) or not np.isfinite(dens).all()
                                     or np.any((dens < 0) | (dens > 1))):
                raise ValueError(f"invalid stored density: {mid}")
            mech = checks = None
            if dens is not None:
                if d["geometry"]:
                    geom = geometry.build_geometry(dom, dens)
                    _, mech, checks = geometry.smoothed_recheck(dom, geom, mats[mid], p.safety_factor)
                    d["geometry"].update(area_mm2=geom.area_mm2, volume_mm3=geom.volume_mm3,
                                         watertight=geom.watertight, volume_error=geom.volume_error)
                else:
                    mech, checks = evaluate.evaluate(dom, dens, mats[mid], p.safety_factor)
            d["checks"] = _checks(checks)
            d["mesh_h_mm"] = dom.h
            d["effective_min_wall"] = dom.describe_min_wall()
            d["printer_allowed"] = printer_allows(p.printer, procs[pid])
            # Selection history is input to evaluation mode, not a new optimization.
            pick = catalog.MaterialPick(**{**d["pick"], "material_id": mid})
            pick.levels = [catalog.LevelStatus(**{k: v for k, v in s.items() if k != "passed"}) for s in pick.levels]
            pick.refinement = [catalog.LevelStatus(**{k: v for k, v in s.items() if k != "passed"}) for s in pick.refinement]
            d["status"] = "pass" if checks and checks.passed and pick.status in {"pass", "loose"} else "fail"
            design = catalog.Design(mats[mid], procs[pid], dom, d["fill"], dens, mech, checks, pick, d["status"],
                reasons=checks.fail_reasons if checks else [], printer_allowed=d["printer_allowed"], rerun=d["rerun"])
            designs.append(design)
            b = strut_baseline(dom, mats[mid], p.safety_factor)
            baselines[mid] = b
            d["baseline"] = _f({k: getattr(b, k) for k in d["baseline"]})
    ranking = rank.rank_designs(catalog.RunResult(p, results["solver_settings"]["cap_used"],
                                results["solver_settings"]["sweep_mode_used"], {}, designs, 0), baselines)
    fresh["ranking"] = _f({"order": [c.design.material.id for c in ranking.cards],
        "cards": [{"material": c.design.material.id, "state": c.state, "rank": c.rank,
                   "material_cost_usd": c.material_cost_usd, "weight_saved_vs_strut": c.weight_saved_vs_strut,
                   "weight_saved_vs_block": c.weight_saved_vs_block} for c in ranking.cards],
        "pareto": [asdict(v) for v in ranking.pareto], "funnel": ranking.funnel,
        "winner": ranking.winner.material.id if ranking.winner else None})
    return fresh


def _install_settings(settings: dict):
    from . import config
    current = config.solver_settings()
    missing = set(current) - set(settings)
    extra = set(settings) - set(current) - {"cap_used", "sweep_mode_used", "levels_used", "format_version"}
    if missing or extra:
        raise ValueError(f"unsupported solver settings schema (missing: {sorted(missing)}, extra: {sorted(extra)})")
    for key, original in current.items():
        value = settings[key]
        if type(value) is not type(original):
            raise ValueError(f"invalid solver setting type: {key}")
        setattr(config, key, tuple(value) if isinstance(getattr(config, key), tuple) else value)
    if (not isinstance(settings["cap_used"], int) or settings["cap_used"] <= 0
            or settings["sweep_mode_used"] not in {"cold", "warm"}
            or not settings["levels_used"] or not all(0 < v <= 1 for v in settings["levels_used"])):
        raise ValueError("invalid replay controls")


def _worker(directory: Path, mode: str, output: Path):
    results = load_results(directory)
    _install_settings(results["solver_settings"])
    # Imports below intentionally occur only after config restoration.
    if mode == "evaluation":
        actual = _strict(directory, results)
        rows = compare(reported_numbers(results), reported_numbers(actual), STRICT_RTOL)
    else:
        from . import precompute
        from .materials import load_materials, load_processes, library_hash
        # Adapter injection is local to this disposable process; no engine code is changed.
        precompute.load_materials = lambda: load_materials(directory / "materials.yaml")
        precompute.load_processes = lambda: load_processes(directory / "processes.yaml")
        precompute.library_hash = lambda: library_hash(directory / "materials.yaml", directory / "processes.yaml")
        s = results["solver_settings"]
        fresh_dir = precompute.precompute_part(directory / "problem.json", directory / "optimization",
            cap=s["cap_used"], sweep_mode=s["sweep_mode_used"], levels=s["levels_used"],
            version=code_version(), save_catalog_snapshots=False)
        actual = load_results(fresh_dir)
        def picks(data):
            return {d["material"]: {"fill": d["fill"], "mass_g": d["checks"]["mass_g"] if d["checks"] else None}
                    for d in data["designs"]}
        rows = compare(picks(results), picks(actual), LOOSE_RTOL)
        for row in rows:
            if row.path.endswith(".fill"):
                row.passed = row.expected == row.actual
    from dataclasses import asdict
    output.write_bytes(_json({"mode": mode, "passed": bool(rows) and all(r.passed for r in rows),
        "rtol": STRICT_RTOL if mode == "evaluation" else LOOSE_RTOL,
        "source_code_version": results["code_version"], "running_code_version": code_version(),
        "comparisons": [asdict(r) for r in rows]}))


def rerun_bundle(path: Path | str, mode="both", *, progress=print) -> dict:
    if mode not in {"both", "evaluation", "optimization"}:
        raise ValueError("mode must be both, evaluation, or optimization")
    outcomes = {}
    with tempfile.TemporaryDirectory(prefix="morphic-rerun-") as tmp:
        directory = Path(tmp)
        try:
            data = _unpack(Path(path), directory)
        except (zipfile.BadZipFile, KeyError, TypeError) as exc:
            raise ValueError("invalid bundle structure") from exc
        progress(f"Bundle source code: {data['code_version']}; current code: {code_version()}")
        for name in (("evaluation", "optimization") if mode == "both" else (mode,)):
            progress(f"Starting {name} rerun", flush=True) if progress is print else progress(f"Starting {name} rerun")
            output = directory / f"{name}-diff.json"
            proc = subprocess.run([sys.executable, "-m", "morphic.bundle", "--worker", str(directory), name, str(output)],
                                  cwd=ROOT, check=False)
            if proc.returncode:
                raise RuntimeError(f"{name} rerun worker failed (exit {proc.returncode})")
            result = json.loads(output.read_text(encoding="utf-8"))
            outcomes[name] = result
            progress(f"{name}: {'PASS' if result['passed'] else 'FAIL'} ({len(result['comparisons'])} comparisons)")
    return {"passed": all(r["passed"] for r in outcomes.values()), "modes": outcomes}


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] != "--worker":
        raise SystemExit("internal worker: use morphic rerun BUNDLE.zip")
    _worker(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
