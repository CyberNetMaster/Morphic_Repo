"""Turn a Problem into an FE / topology-optimization setup for one process (spec 6.1).

- element size h = max(min_wall / 2.5, size that fits the element cap)
- effective min wall = max(process min wall, 2.5 h), always reported
- pad holes: passive void; pad rings: passive solid; solid pads: passive solid disc
- keep-in zones: passive solid; keep-out zones: passive void
- supports and loads act on the nodes on the inner edge of the pad ring
  (solid pad: the nodes within one element of the pad centre)
- exclusion zone per pad: ring plus one ring width beyond it, in mm
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import config, fe
from .problem import Pad, Problem


@dataclass
class PadNodes:
    pad_id: str
    nodes: np.ndarray  # nodes where loads / supports act
    fix_x: bool = False
    fix_y: bool = False
    is_support: bool = False
    is_load: bool = False


@dataclass
class Domain:
    problem: Problem
    process_id: str
    min_wall_mm: float
    cap: int
    mesh: fe.Mesh
    h: float
    effective_min_wall_mm: float
    rmin_elements: float
    passive_solid: np.ndarray
    passive_void: np.ndarray
    fixed_dofs: np.ndarray
    loads: np.ndarray  # (ndof, ncases)
    pad_nodes: dict[str, PadNodes]
    exclusion_nodes: np.ndarray  # bool (nnodes,)
    pad_hole_elements: dict[str, np.ndarray] = field(default_factory=dict)
    pad_ring_elements: dict[str, np.ndarray] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def ncases(self) -> int:
        return self.loads.shape[1]

    @property
    def active(self) -> np.ndarray:
        return ~(self.passive_solid | self.passive_void)

    def KE_unit(self, nu: float) -> np.ndarray:
        return fe.element_stiffness(1.0, nu, self.problem.thickness_mm)

    def topopt_problem(self, nu: float = config.CATALOG_REFERENCE_NU, case_weights=None):
        from .topopt import TopOptProblem

        return TopOptProblem(mesh=self.mesh, KE_unit=self.KE_unit(nu), fixed_dofs=self.fixed_dofs,
                             loads=self.loads, passive_solid=self.passive_solid,
                             passive_void=self.passive_void, case_weights=case_weights)

    def support_pads(self) -> list[PadNodes]:
        return [p for p in self.pad_nodes.values() if p.is_support]

    def load_pads(self) -> list[PadNodes]:
        return [p for p in self.pad_nodes.values() if p.is_load]

    def describe_min_wall(self) -> str:
        if self.effective_min_wall_mm > self.min_wall_mm + 1e-9:
            return (f"{self.process_id}: {self.effective_min_wall_mm:.2f} mm enforced "
                    f"(process allows {self.min_wall_mm:.2f} mm)")
        return f"{self.process_id}: {self.effective_min_wall_mm:.2f} mm enforced"


def choose_mesh(width: float, height: float, min_wall: float, cap: int) -> tuple[fe.Mesh, float]:
    """Element size per spec 6.1; the width is kept exact, the height rounds to whole elements."""
    h0 = fe.element_size_for_cap(width, height, min_wall, cap, config.MIN_WALL_TO_ELEMENT_RATIO)
    nelx = max(2, int(np.ceil(width / h0 - 1e-9)))
    h = width / nelx
    nely = max(2, int(round(height / h)))
    mesh = fe.Mesh(nelx, nely, h)
    eff = max(min_wall, config.MIN_WALL_TO_ELEMENT_RATIO * h)
    return mesh, eff


def _pad_elements(mesh: fe.Mesh, pad: Pad) -> tuple[np.ndarray, np.ndarray]:
    d = np.hypot(mesh.xc - pad.cx, mesh.yc - pad.cy)
    hole = d < pad.hole_r_mm
    ring = (d >= pad.hole_r_mm) & (d < pad.ring_r_mm)
    return hole, ring


def _pad_action_nodes(mesh: fe.Mesh, pad: Pad, hole: np.ndarray, ring: np.ndarray,
                      warnings: list[str]) -> np.ndarray:
    """Nodes on the inner edge of the ring: touched by a ring element and a hole element.
    Solid pad (or a hole too small to hold an element): nodes within one element of the centre."""
    if pad.is_solid or not hole.any():
        if not pad.is_solid and not hole.any():
            warnings.append(f"pad {pad.id}: hole radius {pad.hole_r_mm:.2f} mm is smaller than the "
                            f"element size {mesh.h:.2f} mm; loads act on the central nodes")
        d = np.hypot(mesh.xn - pad.cx, mesh.yn - pad.cy)
        nodes = np.nonzero(d <= mesh.h + 1e-9)[0]
        if nodes.size == 0:
            nodes = np.array([mesh.node_at(pad.cx, pad.cy)])
        return nodes
    ring_nodes = np.unique(mesh.enodes[ring])
    hole_nodes = np.unique(mesh.enodes[hole])
    nodes = np.intersect1d(ring_nodes, hole_nodes)
    if nodes.size == 0:  # ring and hole do not touch (should not happen on a regular grid)
        d = np.hypot(mesh.xn - pad.cx, mesh.yn - pad.cy)
        nodes = np.nonzero(np.abs(d - pad.hole_r_mm) <= mesh.h)[0]
    return nodes


def build_domain(problem: Problem, process_id: str, min_wall_mm: float, cap: int) -> Domain:
    W, H = problem.design_space.width_mm, problem.design_space.height_mm
    mesh, eff = choose_mesh(W, H, min_wall_mm, cap)
    h = mesh.h
    warnings: list[str] = []
    if eff > min_wall_mm + 1e-9:
        warnings.append(f"{process_id}: the element cap limits the min wall to {eff:.2f} mm "
                        f"(process allows {min_wall_mm:.2f} mm)")
    rmin = max(config.FILTER_RADIUS_MIN_ELEMENTS, (eff / 2.0) / h)

    passive_solid = np.zeros(mesh.nel, dtype=bool)
    passive_void = np.zeros(mesh.nel, dtype=bool)
    for z in problem.zones:
        inside = z.contains(mesh.xc, mesh.yc)
        if z.kind == "keep_in":
            passive_solid |= inside
        else:
            passive_void |= inside

    pad_nodes: dict[str, PadNodes] = {}
    hole_el: dict[str, np.ndarray] = {}
    ring_el: dict[str, np.ndarray] = {}
    exclusion = np.zeros(mesh.nnodes, dtype=bool)
    for pad in problem.pads:
        hole, ring = _pad_elements(mesh, pad)
        hole_el[pad.id] = np.nonzero(hole)[0]
        ring_el[pad.id] = np.nonzero(ring)[0]
        passive_void |= hole
        passive_solid |= ring
        nodes = _pad_action_nodes(mesh, pad, hole, ring, warnings)
        pad_nodes[pad.id] = PadNodes(pad_id=pad.id, nodes=nodes)
        dn = np.hypot(mesh.xn - pad.cx, mesh.yn - pad.cy)
        exclusion |= dn <= pad.ring_r_mm + config.EXCLUSION_RING_WIDTHS * pad.ring_width_mm + 1e-9
    # a hole wins over a ring where pads overlap; keep-out wins over keep-in
    passive_solid &= ~passive_void

    fixed = []
    for s in problem.supports:
        pn = pad_nodes[s.pad_id]
        pn.is_support = True
        pn.fix_x |= s.fix_x
        pn.fix_y |= s.fix_y
    for pn in pad_nodes.values():
        if pn.is_support:
            fixed.append(fe.fix_nodes(pn.nodes, x=pn.fix_x, y=pn.fix_y))
    fixed_dofs = np.unique(np.concatenate(fixed)) if fixed else np.zeros(0, dtype=np.int64)

    loads = np.zeros((mesh.ndof, len(problem.load_cases)))
    for c, lc in enumerate(problem.load_cases):
        for ld in lc.loads:
            pn = pad_nodes[ld.pad_id]
            pn.is_load = True
            n = pn.nodes.size
            loads[2 * pn.nodes, c] += ld.fx_N / n
            loads[2 * pn.nodes + 1, c] += ld.fy_N / n

    return Domain(problem=problem, process_id=process_id, min_wall_mm=min_wall_mm, cap=cap,
                  mesh=mesh, h=h, effective_min_wall_mm=eff, rmin_elements=rmin,
                  passive_solid=passive_solid, passive_void=passive_void, fixed_dofs=fixed_dofs,
                  loads=loads, pad_nodes=pad_nodes, exclusion_nodes=exclusion,
                  pad_hole_elements=hole_el, pad_ring_elements=ring_el, warnings=warnings)
