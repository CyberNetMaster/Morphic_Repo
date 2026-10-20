"""Baselines (spec 6.9): full block and the automatic strut design.

Strut baseline: straight, constant-width solid struts from each load pad centre to
its nearest support pad(s), going around keep-out zones (shortest path on the grid
if the straight line is blocked). The smallest width that meets the same safety
factor and deflection limits is found by bisection with the same FE evaluator.
Same material and thickness.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from . import config, evaluate
from .domain import Domain
from .materials import Material


@dataclass
class BaselineResult:
    material_id: str
    mass_block_g: float
    strut_width_mm: float | None
    mass_strut_g: float | None
    strut_passed: bool
    strut_density: np.ndarray | None
    checks: evaluate.Checks | None
    note: str = "constant-width straight struts, sized by the same solver to the same limits"
    struts: list = field(default_factory=list)  # (load_pad_id, support_pad_id)

    def weight_saved_vs_strut(self, mass_g: float) -> float | None:
        if self.mass_strut_g is None or self.mass_strut_g <= 0:
            return None
        return 1.0 - mass_g / self.mass_strut_g

    def weight_saved_vs_block(self, mass_g: float) -> float:
        return 1.0 - mass_g / self.mass_block_g


def full_block_mass(domain: Domain, material: Material) -> float:
    """The whole design space minus keep-out zones and holes."""
    n_solid = int((~domain.passive_void).sum())
    area = n_solid * domain.mesh.h ** 2
    return area * domain.problem.thickness_mm * material.density / 1000.0


# ----------------------------------------------------------------------------- strut geometry
def _segment_mask(domain: Domain, pts: np.ndarray, width: float) -> np.ndarray:
    """Elements whose centre lies within width/2 of the polyline through pts."""
    mesh = domain.mesh
    mask = np.zeros(mesh.nel, dtype=bool)
    half = width / 2.0
    for a, b in zip(pts[:-1], pts[1:]):
        ab = b - a
        L2 = float(ab @ ab)
        px = mesh.xc - a[0]
        py = mesh.yc - a[1]
        t = np.clip((px * ab[0] + py * ab[1]) / L2, 0.0, 1.0) if L2 > 0 else np.zeros(mesh.nel)
        dx = px - t * ab[0]
        dy = py - t * ab[1]
        mask |= dx * dx + dy * dy <= half * half
    return mask


def _blocked_straight(domain: Domain, a: np.ndarray, b: np.ndarray) -> bool:
    """True if the straight line from a to b crosses a keep-out zone."""
    n = int(np.ceil(np.hypot(*(b - a)) / domain.mesh.h)) + 1
    s = np.linspace(0.0, 1.0, n)
    xs = a[0] + s * (b[0] - a[0])
    ys = a[1] + s * (b[1] - a[1])
    for z in domain.problem.zones:
        if z.kind == "keep_out" and z.contains(xs, ys).any():
            return True
    return False


def _grid_path(domain: Domain, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Shortest 4-connected path on the element grid around keep-out zones (BFS)."""
    mesh = domain.mesh
    blocked = np.zeros((mesh.nelx, mesh.nely), dtype=bool)
    for z in domain.problem.zones:
        if z.kind == "keep_out":
            blocked |= mesh.element_grid(z.contains(mesh.xc, mesh.yc))
    start = (min(int(a[0] / mesh.h), mesh.nelx - 1), min(int(a[1] / mesh.h), mesh.nely - 1))
    goal = (min(int(b[0] / mesh.h), mesh.nelx - 1), min(int(b[1] / mesh.h), mesh.nely - 1))
    prev = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        i, j = cur
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (i + di, j + dj)
            if 0 <= nxt[0] < mesh.nelx and 0 <= nxt[1] < mesh.nely and nxt not in prev and not blocked[nxt]:
                prev[nxt] = cur
                q.append(nxt)
    if goal not in prev:
        return np.array([a, b])  # no path: fall back to the straight line (it will fail the check)
    path = []
    cur = goal
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    pts = [a] + [np.array([(i + 0.5) * mesh.h, (j + 0.5) * mesh.h]) for i, j in path[1:-1]] + [b]
    return np.array(pts)


def strut_pairs(domain: Domain) -> list[tuple[str, str]]:
    """Each load pad to its nearest support pad, and to the second nearest if there is one
    (two struts make a stable triangle; a single strut to a slide would be a mechanism)."""
    p = domain.problem
    pairs = []
    sups = [p.pad(s) for s in p.support_pad_ids]
    for lid in p.load_pad_ids:
        pl = p.pad(lid)
        order = sorted(sups, key=lambda s: np.hypot(s.cx - pl.cx, s.cy - pl.cy))
        for s in order[:2]:
            pairs.append((lid, s.id))
    return pairs


def strut_density(domain: Domain, width: float) -> np.ndarray:
    mesh = domain.mesh
    mask = np.zeros(mesh.nel, dtype=bool)
    p = domain.problem
    for lid, sid in strut_pairs(domain):
        a = np.array([p.pad(lid).cx, p.pad(lid).cy])
        b = np.array([p.pad(sid).cx, p.pad(sid).cy])
        pts = _grid_path(domain, a, b) if _blocked_straight(domain, a, b) else np.array([a, b])
        mask |= _segment_mask(domain, pts, width)
    mask |= domain.passive_solid
    mask &= ~domain.passive_void
    return mask.astype(float)


# ----------------------------------------------------------------------------- sizing
def strut_baseline(domain: Domain, material: Material, sf_target: float, steps: int = 10) -> BaselineResult:
    block = full_block_mass(domain, material)
    w_lo = domain.effective_min_wall_mm
    w_hi = max(domain.mesh.width, domain.mesh.height)

    def passes(w: float):
        dens = strut_density(domain, w)
        mech, checks = evaluate.evaluate(domain, dens, material, sf_target)
        return checks.passed_in_plane, dens, checks

    ok_hi, dens_hi, checks_hi = passes(w_hi)
    if not ok_hi:
        return BaselineResult(material_id=material.id, mass_block_g=block, strut_width_mm=None,
                              mass_strut_g=None, strut_passed=False, strut_density=None, checks=checks_hi,
                              struts=strut_pairs(domain))
    ok_lo, dens_lo, checks_lo = passes(w_lo)
    if ok_lo:
        best = (w_lo, dens_lo, checks_lo)
    else:
        best = (w_hi, dens_hi, checks_hi)
        lo, hi = w_lo, w_hi
        for _ in range(steps):
            mid = 0.5 * (lo + hi)
            ok, dens, checks = passes(mid)
            if ok:
                hi = mid
                best = (mid, dens, checks)
            else:
                lo = mid
    w, dens, checks = best
    return BaselineResult(material_id=material.id, mass_block_g=block, strut_width_mm=float(w),
                          mass_strut_g=checks.mass_g, strut_passed=True, strut_density=dens, checks=checks,
                          struts=strut_pairs(domain))
