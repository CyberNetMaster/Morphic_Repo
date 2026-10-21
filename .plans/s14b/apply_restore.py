"""One-off edit script: restore unaffected catalogs from the cache for a partial precompute."""
import io


def edit(path, pairs):
    s = io.open(path, encoding="utf-8").read()
    for o, n in pairs:
        assert s.count(o) == 1, (path, o[:60])
        s = s.replace(o, n)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


edit("morphic/catalog.py", [
    ("""            run = _run_level(cat, mid, "refine", base.x, config.SNAPSHOT_EVERY_CATALOG, "refine", callback)""",
     """            if base.x is None:  # a catalog restored from a cache has no design variables to warm-start from
                raise RuntimeError(f"restored catalog {cat.process.id} needs a new refinement run at {mid:.4f}; "
                                   "re-run this catalog instead of restoring it")
            run = _run_level(cat, mid, "refine", base.x, config.SNAPSHOT_EVERY_CATALOG, "refine", callback)"""),
    ("""            sweep_mode: str = "warm", quick: bool = False, rerun: str = "winner", levels=config.FILL_LEVELS,
            callback=None) -> RunResult:""",
     """            sweep_mode: str = "warm", quick: bool = False, rerun: str = "winner", levels=config.FILL_LEVELS,
            callback=None, prebuilt: dict | None = None) -> RunResult:"""),
    ("""        cat = run_catalog(problem, proc, mats, cap, sweep_mode=sweep_mode, levels=levels,
                          snapshot_every=0 if quick else config.SNAPSHOT_EVERY_CATALOG, callback=callback)""",
     """        if prebuilt and pid in prebuilt:  # restored from a cache (precompute partial update)
            cat = prebuilt[pid]
        else:
            cat = run_catalog(problem, proc, mats, cap, sweep_mode=sweep_mode, levels=levels,
                              snapshot_every=0 if quick else config.SNAPSHOT_EVERY_CATALOG, callback=callback)"""),
])

edit("morphic/precompute.py", [
    ("""def _recheck_with_step_up(""",
     '''def restore_catalogs(problem: Problem, materials: dict, processes: dict, cap: int, cache_dir: Path,
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


def _recheck_with_step_up('''),
    ("""from . import catalog, config, geometry, rank
from .baseline import strut_baseline""",
     """from . import catalog, config, evaluate, geometry, rank, topopt
from .baseline import strut_baseline
from .domain import build_domain"""),
    ("""                    log=print, save_catalog_snapshots: bool = True, version: str | None = None) -> Path:""",
     '''                    log=print, save_catalog_snapshots: bool = True, version: str | None = None,
                    recompute: list[str] | None = None) -> Path:
    """recompute: if given, only these processes are re-run; the other catalogs are restored from
    the existing cache of this part (partial update)."""'''),
    ("""    log(f"PART {stem}: {problem.name} | cap {cap}, {sweep_mode} per level, {len(levels)} levels | key {key[:12]}")
""",
     """    log(f"PART {stem}: {problem.name} | cap {cap}, {sweep_mode} per level, {len(levels)} levels | key {key[:12]}")
    prebuilt = {}
    if recompute is not None:
        procs_used = sorted({materials[m].process for m in problem.materials})
        keep = [p for p in procs_used if p not in recompute]
        log(f"  partial update: re-run {sorted(recompute)}, restore {keep}")
        prebuilt = restore_catalogs(problem, materials, processes, cap, out, keep, log)
"""),
    ("""    res = catalog.run_all(problem, materials, processes, cap, sweep_mode=sweep_mode, rerun="per_process",
                          levels=levels, callback=cb)""",
     """    res = catalog.run_all(problem, materials, processes, cap, sweep_mode=sweep_mode, rerun="per_process",
                          levels=levels, callback=cb, prebuilt=prebuilt)"""),
    ("""        if save_catalog_snapshots:""",
     """        if save_catalog_snapshots and not cat.reused_from:  # keep the original file of a restored catalog"""),
    ("""        "early_stopped": cat.early_stopped, "notes": cat.notes, "seconds": cat.seconds,""",
     """        "early_stopped": cat.early_stopped, "notes": cat.notes, "seconds": cat.seconds,
        "reused_from": cat.reused_from, "main_levels": list(cat.main_levels),"""),
    ("""def precompute_all(parts: list[str], log_path: Path | None, cap: int, out_root: Path = CACHE_DIR,
                   levels=config.FILL_LEVELS) -> int:""",
     '''def precompute_all(parts: list[str], log_path: Path | None, cap: int, out_root: Path = CACHE_DIR,
                   levels=config.FILL_LEVELS, recompute: dict | None = None) -> int:
    """recompute: {part stem: [process ids]} for a partial update; parts not named run in full."""'''),
    ("""            precompute_part(Path(part), out_root, cap, levels=levels, log=log, version=version)""",
     """            rc = (recompute or {}).get(Path(part).stem)
            precompute_part(Path(part), out_root, cap, levels=levels, log=log, version=version, recompute=rc)"""),
])

edit("morphic/cli.py", [
    ("""    pc.add_argument("--levels", type=int, default=0, help="only the first N fill levels (0 = all; for tests)")""",
     """    pc.add_argument("--levels", type=int, default=0, help="only the first N fill levels (0 = all; for tests)")
    pc.add_argument("--recompute", action="append", default=[],
                    help="partial update PART:PROC[,PROC] (e.g. rc_arm:fdm); the other catalogs of PART are "
                         "restored from its cache; PART: restores every catalog")"""),
    ("""    return precompute_all(args.parts, Path(args.log) if args.log else None, args.cap,
                          Path(args.out) if args.out else CACHE_DIR, levels=levels)""",
     """    recompute = {}
    for item in args.recompute:
        part, _, procs = item.partition(":")
        recompute[part] = [p for p in procs.split(",") if p]
    return precompute_all(args.parts, Path(args.log) if args.log else None, args.cap,
                          Path(args.out) if args.out else CACHE_DIR, levels=levels, recompute=recompute or None)"""),
])
print("ok")
