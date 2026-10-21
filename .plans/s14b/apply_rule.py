"""One-off edit script: per-material extension rule, loose-message fix, spec 6.3 text."""
import io


def edit(path, pairs):
    s = io.open(path, encoding="utf-8").read()
    for o, n in pairs:
        assert s.count(o) == 1, (path, o[:60])
        s = s.replace(o, n)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)


edit("morphic/catalog.py", [
    ("""    seconds: float = 0.0
    early_stopped: bool = False
""",
     """    seconds: float = 0.0
    early_stopped: bool = False
    main_levels: tuple = config.FILL_LEVELS  # the levels swept before any extension below them
    reused_from: str = ""  # code version, when the catalog was restored from a cache
"""),
    ("""def _all_pass(cat: Catalog, fill: float, materials: list[Material], sf_target: float) -> bool:
    for m in materials:
        st = level_statuses({fill: cat.levels[fill]}, cat.domain, m, sf_target)[0]
        if not st.passed:
            return False
    return True
""",
     '''def _passes(cat: Catalog, fill: float, material: Material, sf_target: float) -> bool:
    return level_statuses({fill: cat.levels[fill]}, cat.domain, material, sf_target)[0].passed


def material_levels(cat: Catalog, material: Material, sf_target: float) -> dict:
    """The catalog levels that count for one material (spec 6.3, per-material extension).

    Below the main levels, a material follows the extension only while it passes: the first
    extension level it fails at is kept (as the bottom of its refinement window) and lower
    levels, computed for other materials, are dropped for it. A material that fails at the
    lowest main level gets no extension levels.
    """
    main_min = min(cat.main_levels)
    out = {f: r for f, r in cat.levels.items() if f >= main_min - 1e-12}
    if main_min not in cat.levels or not _passes(cat, main_min, material, sf_target):
        return out
    for f in sorted((f for f in cat.levels if f < main_min - 1e-12), reverse=True):
        out[f] = cat.levels[f]
        if not _passes(cat, f, material, sf_target):
            break
    return out
'''),
    ("""    prev: LevelRun | None = None
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
""",
     """    cat.main_levels = tuple(levels)
    prev: LevelRun | None = None

    def run_one(fill):
        nonlocal prev
        mode = "cold" if (sweep_mode == "cold" or prev is None) else "warm"
        run = _run_level(cat, fill, mode, None if mode == "cold" else prev.x, snapshot_every, "catalog", callback)
        cat.levels[fill] = run
        prev = run

    for idx, fill in enumerate(levels):
        run_one(fill)
        if early_stop and idx == 0 and _all_fail_everything(cat, fill, materials, sf):
            cat.early_stopped = True
            cat.notes.append(f"{fill:.0%} fails every limit for every material: sweep stopped")
            break
    if extend_low and not cat.early_stopped:
        # Per-material extension (spec 6.3): keep going down while at least one material still
        # passes; a material leaves the extension at the first level it fails.
        current = min(levels)
        still = [m for m in materials if _passes(cat, current, m, sf)]
        for fill in [f for f in config.FILL_LEVELS_EXTRA_LOW if f < current]:
            if not still:
                break
            cat.notes.append(f"{', '.join(m.id for m in still)} still pass at {current:.0%}: "
                             f"extending down to {fill:.0%}")
            run_one(fill)
            still = [m for m in still if _passes(cat, fill, m, sf)]
            current = fill
        if still and current <= min(config.FILL_LEVELS_EXTRA_LOW) + 1e-12:
            cat.notes.append(f"{', '.join(m.id for m in still)} pass at {current:.0%}: limits are loose for "
                             "these materials; part size is set by the minimum wall")
    cat.seconds = time.perf_counter() - t0
    return cat
"""),
    ("""    statuses = level_statuses(cat.levels, cat.domain, material, sf)
    v, window, notes = choose_level(statuses)""",
     """    statuses = level_statuses(material_levels(cat, material, sf), cat.domain, material, sf)
    v, window, notes = choose_level(statuses)"""),
    ("""    if window is None:
        pick.notes.append("passes at the lowest level computed; limits are loose")
        pick.status = "loose"
""",
     """    if window is None:
        if v <= min(config.FILL_LEVELS_EXTRA_LOW) + 1e-12:
            pick.notes.append(f"passes at {v:.0%}, the lowest level: limits are loose; part size is set "
                              "by the minimum wall")
            pick.status = "loose"
        else:  # the sweep did not reach the floor for this material (e.g. a short level list)
            pick.notes.append(f"passes at the lowest level computed ({v:.0%}); lower levels were not computed")
"""),
])

edit("morphic/rank.py", [(
    """    if any(c.design.pick.status == "loose" for c in cards):
        msgs.append("Limits are loose; part size is set by the minimum wall. Results shown at the lowest fill level.")
""",
    """    # Spec 6.3 / section 8: the global message only when every material passes at the lowest
    # level (8%); single materials that do carry the note on their own card.
    if cards and all(c.design.pick.status == "loose" for c in cards):
        msgs.append("Limits are loose; part size is set by the minimum wall. Results shown at the lowest fill level.")
""")])

edit(".plans/morphic-spec.md", [
    ("- If every material passes at 15%: continue down to 12%, 10%, 8%. If they still pass, report \"limits are loose; part size is set by the minimum wall\".\n",
     "- **Extension below 15%, per material** (decided 2026-10-21): if at least one material passes at 15%, continue down to 12%, 10%, 8% while at least one material still passes. Each material follows the extension only while it passes: the first lower level it fails at is the bottom of its refinement window, and levels computed below that (for other materials) do not count for it. A material that fails at 15% gets no extension levels. A material that passes at 8% carries the card note \"limits are loose; part size is set by the minimum wall\". The global message is shown only when every material passes at 8%. (Before this change the sweep only extended when every material passed, so a lighter pick could be missed when another material failed at a lower level.)\n"),
    ("| All pass at 8% | Report the loose-limits message (section 6.3). Show results at the lowest level. |\n",
     "| A material passes at 8% | Card note: limits are loose for that material. If every material passes at 8%, also the global loose-limits message (section 6.3). Show results at the lowest level. |\n"),
])
print("ok")
