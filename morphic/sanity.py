"""Sanity checks on a parsed or edited problem (spec section 4.5).

Each failed check gives a plain message. Red stops the solve; yellow does not.
The out-of-plane banner is red but not blocking.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from . import config
from .problem import Problem


@dataclass
class SanityMessage:
    level: str  # "red" | "yellow"
    code: str
    message: str
    blocking: bool = True

    def __str__(self) -> str:
        return f"[{self.level}] {self.message}"


def _raster(problem: Problem, n: int = 200):
    W, H = problem.design_space.width_mm, problem.design_space.height_mm
    h = max(W, H) / n
    nx, ny = max(2, int(np.ceil(W / h))), max(2, int(np.ceil(H / h)))
    xs = (np.arange(nx) + 0.5) * W / nx
    ys = (np.arange(ny) + 0.5) * H / ny
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    return X, Y


def _zone_mask(problem: Problem, kind: str, X, Y) -> np.ndarray:
    m = np.zeros(X.shape, dtype=bool)
    for z in problem.zones:
        if z.kind == kind:
            m |= z.contains(X, Y)
    return m


def _zone_hits_circle(zone, cx: float, cy: float, r: float) -> bool:
    if zone.shape == "circle":
        c = zone.circle
        return float(np.hypot(c.cx - cx, c.cy - cy)) < c.r + r
    rc = zone.rect
    nx = min(max(cx, rc.x), rc.x + rc.w)
    ny = min(max(cy, rc.y), rc.y + rc.h)
    return float(np.hypot(nx - cx, ny - cy)) < r


def support_rank(problem: Problem) -> int:
    """Rank of the support constraints against the 3 rigid-body modes (u, v, rotation),
    with each support acting at its pad centre."""
    rows = []
    for s in problem.supports:
        p = problem.pad(s.pad_id)
        if s.fix_x:
            rows.append([1.0, 0.0, -p.cy])
        if s.fix_y:
            rows.append([0.0, 1.0, p.cx])
    if not rows:
        return 0
    return int(np.linalg.matrix_rank(np.array(rows), tol=1e-9))


def check(problem: Problem, processes: dict | None = None, materials: dict | None = None,
          cap: int = config.ELEMENT_CAP_LIVE) -> list[SanityMessage]:
    msgs: list[SanityMessage] = []
    W, H = problem.design_space.width_mm, problem.design_space.height_mm
    tol = 1e-6

    # Every pad fully inside the design space
    for p in problem.pads:
        if (p.cx - p.ring_r_mm < -tol or p.cy - p.ring_r_mm < -tol
                or p.cx + p.ring_r_mm > W + tol or p.cy + p.ring_r_mm > H + tol):
            msgs.append(SanityMessage("red", "pad_outside",
                                      f"Pad {p.id} is outside the design area (its ring, radius "
                                      f"{p.ring_r_mm:g} mm at ({p.cx:g}, {p.cy:g}), does not fit in "
                                      f"{W:g} x {H:g} mm)."))

    # Supports stop all rigid motion
    if support_rank(problem) < 3:
        msgs.append(SanityMessage("red", "rigid_motion",
                                  "The part can still slide or spin. Add a support or change a slide to a pin."))

    # Every load case has a force
    for lc in problem.load_cases:
        if not lc.has_in_plane and not lc.has_out_of_plane:
            msgs.append(SanityMessage("red", "no_force", f"Load case '{lc.name}' has no force."))

    # Keep-out zones over pads or supports
    for z in problem.zones:
        if z.kind != "keep_out":
            continue
        for p in problem.pads:
            if _zone_hits_circle(z, p.cx, p.cy, p.ring_r_mm):
                role = "support" if p.id in problem.support_pad_ids else (
                    "load" if p.id in problem.load_pad_ids else "")
                msgs.append(SanityMessage("red", "keep_out_on_pad",
                                          f"Keep-out zone {z.id} covers {role + ' ' if role else ''}pad {p.id}."))

    X, Y = _raster(problem)
    keep_in = _zone_mask(problem, "keep_in", X, Y)
    if keep_in.mean() > config.KEEP_IN_MAX_FRACTION:
        msgs.append(SanityMessage("red", "keep_in_full",
                                  f"Keep-in zones fill {keep_in.mean():.0%} of the design space: nothing left to optimize."))

    # Free path from every load pad to some support pad
    free = ~_zone_mask(problem, "keep_out", X, Y)
    labels, _ = ndimage.label(free)

    def label_at(pad):
        d = np.hypot(X - pad.cx, Y - pad.cy)
        near = (d <= pad.ring_r_mm) & free
        return set(np.unique(labels[near]).tolist()) - {0}

    sup_labels = set()
    for sid in problem.support_pad_ids:
        sup_labels |= label_at(problem.pad(sid))
    for lid in problem.load_pad_ids:
        if not (label_at(problem.pad(lid)) & sup_labels):
            msgs.append(SanityMessage("red", "no_path", "Keep-out zones block every path from load to support."))
            break

    # Units (yellow)
    for name, v in (("width", W), ("height", H)):
        if v < config.SIZE_MIN_MM or v > config.SIZE_MAX_MM:
            msgs.append(SanityMessage("yellow", "units_size",
                                      f"Check units: the design {name} is {v:g} mm. Did you mean "
                                      f"{v * 25.4:g} mm (inches) or {v / 10:g} mm?", blocking=False))
    for lc in problem.load_cases:
        for ld in lc.loads:
            f = max(abs(ld.fx_N), abs(ld.fy_N), abs(ld.fz_N_out_of_plane))
            if f > config.FORCE_MAX_N:
                msgs.append(SanityMessage("yellow", "units_force",
                                          f"Check units: load case '{lc.name}' has {f:g} N.", blocking=False))
    if problem.thickness_mm > min(W, H):
        msgs.append(SanityMessage("yellow", "units_thickness",
                                  f"Check units: thickness {problem.thickness_mm:g} mm is more than the shorter "
                                  f"side of the design space ({min(W, H):g} mm).", blocking=False))

    span = problem.span_mm
    if span > 0 and problem.thickness_mm < span / config.THIN_SPAN_RATIO:
        msgs.append(SanityMessage("yellow", "thin",
                                  f"Thin part ({problem.thickness_mm:g} mm over a {span:.0f} mm span): may buckle "
                                  "or twist sideways. The 2D model cannot check this.", blocking=False))

    # Out-of-plane banner: red, not blocking
    if any(lc.has_out_of_plane for lc in problem.load_cases):
        msgs.append(SanityMessage("red", "out_of_plane",
                                  "Out-of-plane load: not part of the optimization. Checked by hand formula only.",
                                  blocking=False))

    # Process min wall vs element cap (yellow)
    if processes:
        from .domain import choose_mesh

        used = None
        if materials:
            used = {materials[m].process for m in problem.materials if m in materials}
        for proc in processes.values():
            if used is not None and proc.id not in used:
                continue
            _, eff = choose_mesh(W, H, proc.min_wall_mm, cap)
            if eff > proc.min_wall_mm + 1e-9:
                msgs.append(SanityMessage("yellow", "min_wall",
                                          f"{proc.id}: {eff:.2f} mm min wall enforced (process allows "
                                          f"{proc.min_wall_mm:g} mm) because of the element cap.", blocking=False))
    return msgs


def blocking(msgs: list[SanityMessage]) -> list[SanityMessage]:
    return [m for m in msgs if m.level == "red" and m.blocking]
