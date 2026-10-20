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
                     "stalled": run.stalled, "seconds": run.seconds, "seconds_per_iter": run.seconds_per_iter})
        print(f"  level {fill:.2f} {run.mode:5s} {run.iterations:4d} it  {run.seconds:7.1f} s  "
              f"{run.seconds_per_iter:.3f} s/it  conv={run.converged} stalled={run.stalled}", flush=True)
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
    for name in ("precompute", "rerun", "render"):
        s = sub.add_parser(name, help=f"{name} (built in a later step)")
        s.set_defaults(fn=lambda a, n=name: print(f"{n}: not built yet") or 1)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
