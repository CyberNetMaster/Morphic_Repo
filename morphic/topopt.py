"""SIMP topology optimization (spec section 6.2), based on Andreassen et al. (2011).

One run = one process, one fill level. Material inside a run is the reference
material (E0 = 1 by default); results are scaled per material afterward.

Modes
-----
- "cold":  beta 1 -> 2 -> 4 -> 8 -> 16 from uniform density, up to 300 iterations.
- "warm":  beta from 4, warm-started from a given design, up to 100 iterations.
- "refine": like warm, up to 60 iterations.
- "paper": the published 88-line setup for the MBB benchmark only: density filter,
  no projection, stop when change < 0.01, no beta schedule.

Densities are kept on the flat element vector of `fe.Mesh` (index i * nely + j).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from . import config, fe


# ----------------------------------------------------------------------------- filter
class DensityFilter:
    """Linear (hat) density filter of radius rmin (in elements), as in top88.

    xTilde = (H x) / Hs, with H_ij = max(0, rmin - dist(i, j)). Implemented as a
    convolution on the (nelx, nely) grid; Hs is the convolution of ones, which
    gives exactly the boundary treatment of the 88-line code.
    """

    def __init__(self, mesh: fe.Mesh, rmin: float):
        self.mesh = mesh
        self.rmin = float(rmin)
        k = int(np.ceil(self.rmin)) - 1
        ii, jj = np.meshgrid(np.arange(-k, k + 1), np.arange(-k, k + 1), indexing="ij")
        self.kernel = np.maximum(0.0, self.rmin - np.sqrt(ii**2 + jj**2))
        self.Hs = self._conv(np.ones(mesh.nel))

    def _conv(self, v: np.ndarray) -> np.ndarray:
        g = self.mesh.element_grid(v)
        return ndimage.convolve(g, self.kernel, mode="constant", cval=0.0).ravel()

    def apply(self, x: np.ndarray) -> np.ndarray:
        return self._conv(x) / self.Hs

    def chain(self, dfdxTilde: np.ndarray) -> np.ndarray:
        """Sensitivity w.r.t. x given the sensitivity w.r.t. xTilde (H is symmetric)."""
        return self._conv(dfdxTilde / self.Hs)


def heaviside(xTilde: np.ndarray, beta: float) -> tuple[np.ndarray, np.ndarray]:
    """Heaviside projection of Andreassen et al. (2011), section 5.4.

    xPhys = 1 - exp(-beta xTilde) + xTilde exp(-beta); returns (xPhys, dxPhys/dxTilde).
    """
    e = np.exp(-beta * xTilde)
    xPhys = 1.0 - e + xTilde * np.exp(-beta)
    d = beta * e + np.exp(-beta)
    return xPhys, d


# ----------------------------------------------------------------------------- problem
@dataclass
class TopOptProblem:
    mesh: fe.Mesh
    KE_unit: np.ndarray  # element stiffness for E = 1 (real nu and thickness)
    fixed_dofs: np.ndarray
    loads: np.ndarray  # (ndof, ncases)
    passive_solid: np.ndarray | None = None  # bool (nel,)
    passive_void: np.ndarray | None = None  # bool (nel,)
    case_weights: np.ndarray | None = None  # 1 / normalization per case; None = 1
    E0: float = config.CATALOG_REFERENCE_E
    Emin: float | None = None  # default E_MIN_RATIO * E0
    penal: float = config.SIMP_PENALTY

    def __post_init__(self) -> None:
        n = self.mesh.nel
        if self.loads.ndim == 1:
            self.loads = self.loads[:, None]
        if self.passive_solid is None:
            self.passive_solid = np.zeros(n, dtype=bool)
        if self.passive_void is None:
            self.passive_void = np.zeros(n, dtype=bool)
        if self.Emin is None:
            self.Emin = config.E_MIN_RATIO * self.E0
        if self.case_weights is None:
            self.case_weights = np.ones(self.loads.shape[1])
        self.active = ~(self.passive_solid | self.passive_void)
        self.fixed_dofs = np.unique(np.asarray(self.fixed_dofs, dtype=np.int64))
        self.free_dofs = np.setdiff1d(np.arange(self.mesh.ndof), self.fixed_dofs, assume_unique=True)
        self.assembler = fe.Assembler(self.mesh, self.KE_unit)

    @property
    def ncases(self) -> int:
        return self.loads.shape[1]

    def modulus(self, xPhys: np.ndarray) -> np.ndarray:
        return self.Emin + xPhys**self.penal * (self.E0 - self.Emin)

    def analyze(self, xPhys: np.ndarray, solver: fe.Solver | None = None):
        """Solve all load cases. Returns (U (ndof, ncases), ce (nel, ncases), K)."""
        K = self.assembler.assemble(self.modulus(xPhys))
        K_ff = K[self.free_dofs][:, self.free_dofs]
        own = solver is None
        solver = solver or fe.Solver()
        solver.factorize(K_ff)
        U = np.zeros((self.mesh.ndof, self.ncases))
        U[self.free_dofs] = solver.solve(self.loads[self.free_dofs])
        if own:
            solver.free()
        ue = U[self.mesh.edof]  # (nel, 8, ncases)
        ce = np.einsum("eac,ab,ebc->ec", ue, self.KE_unit, ue)
        return U, ce, K

    def compliance(self, xPhys: np.ndarray) -> np.ndarray:
        """Raw compliance per load case (no weights)."""
        _, ce, _ = self.analyze(xPhys)
        return (self.modulus(xPhys)[:, None] * ce).sum(axis=0)


def normalization_weights(problem: TopOptProblem, fill: float = config.NORMALIZATION_FILL) -> np.ndarray:
    """1 / compliance of each case at uniform density `fill` (fixed once per catalog)."""
    x = np.full(problem.mesh.nel, fill)
    x[problem.passive_solid] = 1.0
    x[problem.passive_void] = 0.0
    c = problem.compliance(x)
    return 1.0 / c


# ----------------------------------------------------------------------------- settings/result
@dataclass
class TopOptSettings:
    volfrac: float
    rmin: float  # filter radius in elements
    mode: str = "cold"  # cold | warm | refine | paper
    x0: np.ndarray | None = None  # starting design variables (warm/refine)
    beta_schedule: tuple = config.BETA_SCHEDULE_COLD
    beta_step_iters: int = config.BETA_STEP_ITERS
    change_tol: float = config.CHANGE_TOL
    max_iters: int = config.MAX_ITERS_COLD
    move: float = config.OC_MOVE
    snapshot_every: int = 0  # 0 = no snapshots
    paper_max_iters: int = 2000  # safety cap in paper mode (the paper has none)

    def __post_init__(self) -> None:
        if self.mode == "warm":
            self.beta_schedule = config.BETA_SCHEDULE_WARM
            self.max_iters = config.MAX_ITERS_WARM
        elif self.mode == "refine":
            self.beta_schedule = config.BETA_SCHEDULE_WARM
            self.max_iters = config.MAX_ITERS_REFINE
        elif self.mode == "paper":
            self.beta_schedule = ()
            self.max_iters = self.paper_max_iters


@dataclass
class TopOptResult:
    x: np.ndarray  # design variables
    xPhys: np.ndarray  # physical (projected) densities
    compliance: np.ndarray  # raw compliance per case, final design
    objective: float  # weighted sum
    iterations: int
    converged: bool  # either stop rule met at the last beta
    converged_by: str | None  # "change" (max design change < tol) | "plateau" (objective) | None
    beta_final: float
    volume: float  # mean xPhys over active elements
    history: list = field(default_factory=list)  # dicts per iteration
    snapshots: list = field(default_factory=list)  # (iteration, uint8 array)
    seconds: float = 0.0
    seconds_per_iter: float = 0.0

    def save_snapshots(self, path) -> None:
        """uint8 (density x 255), zlib-compressed .npz."""
        iters = np.array([i for i, _ in self.snapshots], dtype=np.int32)
        arrs = {f"d{k}": a for k, (_, a) in enumerate(self.snapshots)}
        np.savez_compressed(path, iterations=iters, **arrs)


def objective_plateau(history: list, window: int = config.PLATEAU_WINDOW, rtol: float = config.PLATEAU_RTOL) -> bool:
    """Second stop rule: the weighted objective changed less than rtol (relative) over the last
    `window` consecutive iterations, all at the same (final) beta."""
    if len(history) < window:
        return False
    tail = history[-window:]
    if any(h["beta"] != tail[-1]["beta"] for h in tail):
        return False
    objs = np.array([h["objective"] for h in tail])
    return bool((objs.max() - objs.min()) / max(abs(objs[-1]), 1e-300) < rtol)


def to_uint8(xPhys: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(xPhys * 255.0), 0, 255).astype(np.uint8)


# ----------------------------------------------------------------------------- run
def run(problem: TopOptProblem, settings: TopOptSettings, callback=None) -> TopOptResult:
    """Run SIMP with OC updates. `callback(info_dict, xPhys)` is called every iteration."""
    mesh = problem.mesh
    nel = mesh.nel
    active = problem.active
    n_active = int(active.sum())
    paper = settings.mode == "paper"
    filt = DensityFilter(mesh, settings.rmin)

    # design variables
    if settings.x0 is not None:
        x = np.asarray(settings.x0, dtype=float).copy()
    else:
        x = np.full(nel, settings.volfrac)
    x[problem.passive_solid] = 1.0
    x[problem.passive_void] = 0.0

    betas = list(settings.beta_schedule) if not paper else [None]
    beta_idx = 0
    beta = betas[0]
    iters_at_beta = 0

    def physical(xv: np.ndarray):
        xT = filt.apply(xv)
        if paper:
            xP, dxP = xT, np.ones(nel)
        else:
            xP, dxP = heaviside(xT, beta)
        xP = xP.copy()
        xP[problem.passive_solid] = 1.0
        xP[problem.passive_void] = 0.0
        return xP, dxP

    xPhys, dxP = physical(x)
    solver = fe.Solver()
    history = []
    snapshots = []
    t0 = time.perf_counter()
    loop = 0
    converged = False
    converged_by = None
    change = 1.0
    c_raw = np.zeros(problem.ncases)
    while True:
        loop += 1
        iters_at_beta += 1
        # FE analysis
        U, ce, _ = problem.analyze(xPhys, solver)
        Ee = problem.modulus(xPhys)
        c_raw = (Ee[:, None] * ce).sum(axis=0)
        w = problem.case_weights
        obj = float((c_raw * w).sum())
        dc_dxPhys = -problem.penal * (problem.E0 - problem.Emin) * xPhys ** (problem.penal - 1) * (ce * w).sum(axis=1)
        dv_dxPhys = np.ones(nel)
        # chain through projection and filter
        dc = filt.chain(dc_dxPhys * dxP)
        dv = filt.chain(dv_dxPhys * dxP)
        dc[~active] = 0.0
        dv[~active] = 1.0  # harmless placeholder; passive elements are not updated

        # OC update with bisection on the Lagrange multiplier (volume on projected densities)
        l1, l2 = 0.0, 1e9
        move = settings.move
        target = settings.volfrac * n_active
        xa = x[active]
        dca = dc[active]
        dva = dv[active]
        xnew = x.copy()
        while (l2 - l1) / (l1 + l2) > 1e-3:
            lmid = 0.5 * (l2 + l1)
            cand = xa * np.sqrt(np.maximum(-dca / dva / lmid, 0.0))
            xna = np.maximum(0.0, np.maximum(xa - move, np.minimum(1.0, np.minimum(xa + move, cand))))
            xnew[active] = xna
            xPhys_new, dxP_new = physical(xnew)
            if xPhys_new[active].sum() > target:
                l1 = lmid
            else:
                l2 = lmid
        change = float(np.abs(xnew[active] - xa).max()) if n_active else 0.0
        x = xnew
        xPhys, dxP = xPhys_new, dxP_new

        vol = float(xPhys[active].mean()) if n_active else 0.0
        info = {"iter": loop, "beta": beta, "objective": obj, "compliance": c_raw.tolist(),
                "volume": vol, "change": change, "elapsed": time.perf_counter() - t0}
        history.append(info)
        if settings.snapshot_every and loop % settings.snapshot_every == 0:
            snapshots.append((loop, to_uint8(xPhys)))
        if callback is not None:
            callback(info, xPhys)

        # stop / continuation rules
        if paper:
            if change < settings.change_tol:
                converged, converged_by = True, "change"
                break
            if loop >= settings.max_iters:
                break
            continue
        last_beta = beta_idx == len(betas) - 1
        if last_beta and objective_plateau(history):
            converged, converged_by = True, "plateau"
            break
        if change < settings.change_tol or iters_at_beta >= settings.beta_step_iters:
            if last_beta:
                if change < settings.change_tol:
                    converged, converged_by = True, "change"
                    break
            else:
                beta_idx += 1
                beta = betas[beta_idx]
                iters_at_beta = 0
                xPhys, dxP = physical(x)
        if loop >= settings.max_iters:
            break

    solver.free()
    seconds = time.perf_counter() - t0
    # final compliance of the final physical design
    c_final = problem.compliance(xPhys)
    if settings.snapshot_every and (not snapshots or snapshots[-1][0] != loop):
        snapshots.append((loop, to_uint8(xPhys)))
    return TopOptResult(
        x=x, xPhys=xPhys, compliance=c_final, objective=float((c_final * problem.case_weights).sum()),
        iterations=loop, converged=converged, converged_by=converged_by,
        beta_final=(beta if beta is not None else 0.0),
        volume=float(xPhys[active].mean()) if n_active else 0.0, history=history,
        snapshots=snapshots, seconds=seconds, seconds_per_iter=seconds / max(loop, 1),
    )


# ----------------------------------------------------------------------------- paper mode (MBB)
def mbb_problem(nelx: int, nely: int, nu: float = 0.3) -> TopOptProblem:
    """Half MBB beam exactly as in top88: unit downward load at the top-left node,
    x fixed along the left edge (symmetry), y fixed at the bottom-right node."""
    mesh = fe.Mesh(nelx, nely, 1.0)
    KE = fe.element_stiffness(1.0, nu, 1.0)
    F = np.zeros(mesh.ndof)
    F[2 * mesh.node(0, nely) + 1] = -1.0
    fixed = np.concatenate([fe.fix_nodes(mesh.nodes_on_x(0.0), x=True, y=False),
                            np.array([2 * mesh.node(nelx, 0) + 1])])
    return TopOptProblem(mesh=mesh, KE_unit=KE, fixed_dofs=fixed, loads=F, E0=1.0, Emin=1e-9, penal=3.0)


def run_mbb_paper(nelx: int = 60, nely: int = 20, volfrac: float = 0.5, penal: float = 3.0,
                  rmin: float = 2.4, callback=None) -> TopOptResult:
    """top88(nelx, nely, volfrac, penal, rmin, 2): density filter, no projection."""
    problem = mbb_problem(nelx, nely)
    problem.penal = penal
    settings = TopOptSettings(volfrac=volfrac, rmin=rmin, mode="paper")
    return run(problem, settings, callback)
