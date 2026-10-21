"""Command line: morphic validate | bench | precompute | rerun | render.

bench (step S9): time one full catalog on this machine and record seconds per
iteration, iterations per level, and the total, so the cached cap can be chosen.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np

from . import config


def _load_problem(path: str):
    from .problem import problem_from_dict

    with open(path, encoding="utf-8") as f:
        return problem_from_dict(json.load(f))


def cmd_validate(args) -> int:
    from . import validation as v

    out = {"cantilever": v.cantilever_check(20), "mesh_refinement": v.mesh_refinement(),
           "scaling": v.scaling_law_check(), "hole": {n: v.hole_stress_check(n) for n in (8, 16, 32)}}
    if not args.skip_mbb:
        m = v.mbb_check()
        m.pop("density_grid", None)
        out["mbb"] = m
    print(json.dumps(out, indent=2, default=float))
    return 0


def cmd_bench(args) -> int:
    from . import catalog, fe
    from .domain import build_domain
    from .materials import load_materials, load_processes

    problem = _load_problem(args.part)
    materials = load_materials()
    processes = load_processes()
    proc = processes[args.process]
    mats = [m for m in materials.values() if m.process == proc.id and m.id in problem.materials]
    dom = build_domain(problem, proc.id, proc.min_wall_mm, args.cap)
    print(f"part {problem.name!r}, process {proc.id}, cap {args.cap}: mesh {dom.mesh.nelx} x {dom.mesh.nely} "
          f"= {dom.mesh.nel} elements, h = {dom.h:.3f} mm, {dom.describe_min_wall()}", flush=True)
    levels = config.FILL_LEVELS[: args.levels] if args.levels else config.FILL_LEVELS
    t0 = time.perf_counter()

    def cb(info, xPhys):
        if info["iter"] % 25 == 0 or info["iter"] == 1:
            print(f"  {info['kind']} fill {info['fill']:.2f} it {info['iter']:4d} beta {info['beta']} "
                  f"obj {info['objective']:.4f} change {info['change']:.3f} {info['elapsed']:.0f}s", flush=True)

    cat = catalog.run_catalog(problem, proc, mats, args.cap, sweep_mode=args.mode, levels=levels,
                              early_stop=False, extend_low=False, snapshot_every=2, callback=cb)
    total = time.perf_counter() - t0
    rows = []
    for fill, run in sorted(cat.levels.items(), reverse=True):
        rows.append({"fill": fill, "mode": run.mode, "iterations": run.iterations, "converged": run.converged,
                     "converged_by": run.converged_by, "seconds": run.seconds, "seconds_per_iter": run.seconds_per_iter})
        print(f"  level {fill:.2f} {run.mode:5s} {run.iterations:4d} it  {run.seconds:7.1f} s  "
              f"{run.seconds_per_iter:.3f} s/it  conv={run.converged} by={run.converged_by}", flush=True)
    iters = sum(r["iterations"] for r in rows)
    result = {
        "part": problem.name, "part_file": args.part, "process": proc.id, "cap": args.cap, "mode": args.mode,
        "elements": dom.mesh.nel, "mesh": [dom.mesh.nelx, dom.mesh.nely], "h_mm": dom.h,
        "effective_min_wall_mm": dom.effective_min_wall_mm, "levels": rows, "total_iterations": iters,
        "total_seconds": total, "mean_seconds_per_iter": total / max(iters, 1),
        "pardiso": fe.HAVE_PARDISO, "machine": platform.platform(), "python": sys.version.split()[0],
        "threads": __import__("os").cpu_count(), "numpy": np.__version__,
    }
    print(f"TOTAL {iters} iterations in {total:.0f} s ({total / 60:.1f} min), {total / max(iters, 1):.3f} s/it")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"written {args.out}")
    return 0


def cmd_meshes(args) -> int:
    """Element counts per part and process at a cap (no solving)."""
    from .domain import choose_mesh
    from .materials import load_processes

    processes = load_processes()
    for part in args.parts:
        p = _load_problem(part)
        W, H = p.design_space.width_mm, p.design_space.height_mm
        for proc in processes.values():
            mesh, eff = choose_mesh(W, H, proc.min_wall_mm, args.cap)
            print(f"{Path(part).stem:14s} {proc.id:6s} cap {args.cap:7d}: {mesh.nelx:4d} x {mesh.nely:4d} = "
                  f"{mesh.nel:7d} elements, h {mesh.h:.3f} mm, min wall {eff:.2f} mm")
    return 0


def cmd_parse(args) -> int:
    """Parse a description with the configured LLM; optionally compare with an approved JSON."""
    from . import parse, sanity
    from .materials import load_materials, load_processes
    from .problem import problem_to_dict

    text = Path(args.text).read_text(encoding="utf-8")
    procs, mats = load_processes(), load_materials()
    print(f"provider {config.LLM_PROVIDER}, model {config.LLM_MODELS[config.LLM_PROVIDER]}", flush=True)
    try:
        r = parse.parse_text(text, min_walls=[p.min_wall_mm for p in procs.values()],
                             status=lambda s: print(s, flush=True))
    except parse.ParseFailed as exc:
        print(f"PARSE FAILED: {exc}")
        for a in exc.attempts:
            print(f"  attempt {a['attempt']}: {a.get('error', 'ok')}  ({a.get('seconds', 0):.1f} s)")
        return 2
    print(f"parsed in {r.seconds:.1f} s, {len(r.attempts)} attempt(s)")
    for a in r.attempts:
        if a.get("error"):
            print(f"  attempt {a['attempt']} error: {a['error'][:300]}")
    if args.raw_out:
        Path(args.raw_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.raw_out).write_text(json.dumps({
            "provider": r.provider, "model": r.model, "seconds": r.seconds,
            "attempts": [{k: v for k, v in a.items()} for a in r.attempts],
            "problem": problem_to_dict(r.problem)}, indent=2), encoding="utf-8")
        print(f"written {args.raw_out}")
    for m in sanity.check(r.problem, procs, mats):
        print(f"  sanity {m}")
    if args.compare:
        want = _load_problem(args.compare)
        diffs = parse.compare_problems(r.problem, want)
        print("MATCHES the approved JSON" if not diffs else f"{len(diffs)} difference(s) from the approved JSON:")
        for d in diffs:
            print(f"  - {d}")
    return 0


def cmd_precompute(args) -> int:
    from .precompute import CACHE_DIR, precompute_all

    levels = config.FILL_LEVELS[: args.levels] if args.levels else config.FILL_LEVELS
    recompute = {}
    for item in args.recompute:
        part, _, procs = item.partition(":")
        recompute[part] = [p for p in procs.split(",") if p]
    return precompute_all(args.parts, Path(args.log) if args.log else None, args.cap,
                          Path(args.out) if args.out else CACHE_DIR, levels=levels, recompute=recompute or None)


def cmd_report(args) -> int:
    from .report import write_report
    print(write_report(args.cache, args.out, material=args.material))
    return 0


def cmd_bundle(args) -> int:
    from .bundle import create_bundle
    print(create_bundle(args.cache, args.out))
    return 0


def cmd_rerun(args) -> int:
    from .bundle import rerun_bundle
    result = rerun_bundle(args.bundle, args.mode)
    for name, outcome in result["modes"].items():
        print(f"{name}: {'PASS' if outcome['passed'] else 'FAIL'}; tolerance {outcome['rtol']:.1%}")
        for row in outcome["comparisons"]:
            if args.failures_only and row["passed"]:
                continue
            print(f"  {'PASS' if row['passed'] else 'FAIL'} {row['path']}: "
                  f"{row['expected']} -> {row['actual']} (relative diff {row['relative_error']})")
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    return 0 if result["passed"] else 1


def cmd_cache(args) -> int:
    from .cache import RunCache, DEFAULT_ROOT
    cache = RunCache(args.root or DEFAULT_ROOT)
    if args.key:
        data = cache.get(args.key)
        if data is None:
            print("cache miss")
            return 1
        print(cache.path(args.key))
    else:
        print(cache.put(args.source))
    return 0


def cmd_render(args) -> int:
    """Offline GIF of actual saved iterations; the cinematic MP4 renderer is S15."""
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.animation import FuncAnimation, PillowWriter
    from .cache import load_results
    directory = Path(args.cache)
    data = load_results(directory)
    if args.fps <= 0:
        raise ValueError("fps must be positive")
    output = Path(args.out)
    if output.suffix.lower() != ".gif":
        raise ValueError("snapshot render output must be .gif (cinematic MP4 is step S15)")
    with np.load(directory / f"rerun_{args.process}.npz", allow_pickle=False) as z:
        iterations = z["iterations"].tolist()
        snapshots = [np.array(z[f"it{i}"]) for i in iterations]
        material = str(z["material"])
    if not snapshots:
        raise ValueError("no recorded snapshots")
    nx, ny = data["catalogs"][args.process]["mesh"]
    h = data["catalogs"][args.process]["h_mm"]
    fig = Figure(figsize=(10, 4), layout="constrained")
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    im = ax.imshow(snapshots[0].reshape(nx, ny).T, origin="lower", cmap="gray_r", vmin=0, vmax=255,
                   extent=(0, nx*h, 0, ny*h))
    ax.set(xlabel="x (mm)", ylabel="y (mm)")
    title = ax.set_title("")
    fig.text(.5, .01, "Recorded cold run; may be independent of the exported design. No interpolated shapes.",
             ha="center", fontsize=8)
    def update(index):
        im.set_data(snapshots[index].reshape(nx, ny).T)
        title.set_text(f"{data['problem']['name']} / {material} / iteration {iterations[index]}")
        return im, title
    animation = FuncAnimation(fig, update, frames=len(iterations), blit=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    animation.save(str(output), writer=PillowWriter(fps=args.fps))
    print(output)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="morphic")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="run the validation suite and print JSON")
    v.add_argument("--skip-mbb", action="store_true")
    v.set_defaults(fn=cmd_validate)
    b = sub.add_parser("bench", help="time one full catalog on this machine")
    b.add_argument("--part", default="examples/aero_bracket.json")
    b.add_argument("--process", default="metal", choices=["fdm", "sls", "metal"])
    b.add_argument("--cap", type=int, default=config.ELEMENT_CAP_LIVE)
    b.add_argument("--mode", default="warm", choices=["warm", "cold"])
    b.add_argument("--levels", type=int, default=0, help="only the first N fill levels (0 = all 10)")
    b.add_argument("--out", default="")
    b.set_defaults(fn=cmd_bench)
    m = sub.add_parser("meshes", help="element counts per part and process at a cap")
    m.add_argument("--cap", type=int, default=config.ELEMENT_CAP_LIVE)
    m.add_argument("parts", nargs="+")
    m.set_defaults(fn=cmd_meshes)
    pp = sub.add_parser("parse", help="parse a plain-English description with the configured LLM")
    pp.add_argument("text")
    pp.add_argument("--compare", default="")
    pp.add_argument("--raw-out", default="")
    pp.set_defaults(fn=cmd_parse)
    pc = sub.add_parser("precompute", help="precompute demo parts into examples/cache (step S14)")
    pc.add_argument("parts", nargs="*", default=["examples/rc_arm.json", "examples/drone_arm.json",
                                                 "examples/aero_bracket.json"])
    pc.add_argument("--cap", type=int, default=config.ELEMENT_CAP_CACHED)
    pc.add_argument("--log", default="")
    pc.add_argument("--out", default="")
    pc.add_argument("--levels", type=int, default=0, help="only the first N fill levels (0 = all; for tests)")
    pc.add_argument("--recompute", action="append", default=[],
                    help="partial update PART:PROC[,PROC] (e.g. rc_arm:fdm); the other catalogs of PART are "
                         "restored from its cache; PART: restores every catalog")
    pc.set_defaults(fn=cmd_precompute)
    rp = sub.add_parser("report", help="one-page PDF per design from a cached run")
    rp.add_argument("cache")
    rp.add_argument("--out", required=True)
    rp.add_argument("--material", default=None)
    rp.set_defaults(fn=cmd_report)
    bu = sub.add_parser("bundle", help="package a cached run locally with report and checksums")
    bu.add_argument("cache")
    bu.add_argument("--out", required=True)
    bu.set_defaults(fn=cmd_bundle)
    rr = sub.add_parser("rerun", help="strict evaluation and fresh optimization of a run bundle")
    rr.add_argument("bundle")
    rr.add_argument("--mode", choices=("both", "evaluation", "optimization"), default="both")
    rr.add_argument("--out", default="", help="write the complete machine-readable diff")
    rr.add_argument("--failures-only", action="store_true", help="print only failed individual comparisons")
    rr.set_defaults(fn=cmd_rerun)
    ca = sub.add_parser("cache", help="import or look up a content-addressed local run")
    group = ca.add_mutually_exclusive_group(required=True)
    group.add_argument("--source")
    group.add_argument("--key")
    ca.add_argument("--root", default="")
    ca.set_defaults(fn=cmd_cache)
    re = sub.add_parser("render", help="render saved cold-run snapshots to a local GIF")
    re.add_argument("cache")
    re.add_argument("--process", choices=("fdm", "sls", "metal"), default="fdm")
    re.add_argument("--out", required=True)
    re.add_argument("--fps", type=int, default=15)
    re.set_defaults(fn=cmd_render)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"morphic {args.cmd}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
