"""2D plane-stress finite elements on a regular grid of square Q4 elements.

Used by the optimizer, the evaluation, the baseline, and the validation tests.
Units: mm, N, MPa.

Grid convention
---------------
- Origin at the bottom-left corner, x to the right, y up.
- `nelx` x `nely` square elements of size `h`.
- Node (i, j) with i in 0..nelx, j in 0..nely has index  i * (nely + 1) + j.
- Element (i, j) with i in 0..nelx-1, j in 0..nely-1 has index  i * nely + j.
  Its corners, counter-clockwise from the bottom-left, are nodes
  (i, j), (i+1, j), (i+1, j+1), (i, j+1), which map to natural coordinates
  (-1,-1), (1,-1), (1,1), (-1,1).
- Degrees of freedom: node n has dofs 2n (x) and 2n + 1 (y).

Node-level loads and supports exist here for the validation tests. The
production path (pads, rings) is built on top of these in topopt/evaluate.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp

try:  # PyPardiso is the preferred solver; SciPy is the fallback.
    import pypardiso  # type: ignore

    HAVE_PARDISO = True
except Exception:  # pragma: no cover - depends on the machine
    pypardiso = None
    HAVE_PARDISO = False

_SQ3 = np.sqrt(3.0)
# Natural coordinates of the 4 corners (and the matching Gauss point quadrants).
_CORNER_XI = np.array([-1.0, 1.0, 1.0, -1.0])
_CORNER_ETA = np.array([-1.0, -1.0, 1.0, 1.0])
_GAUSS_A = 1.0 / _SQ3


# ----------------------------------------------------------------------------- mesh
@dataclass
class Mesh:
    nelx: int
    nely: int
    h: float  # element size in mm

    nnodes: int = field(init=False)
    ndof: int = field(init=False)
    nel: int = field(init=False)
    edof: np.ndarray = field(init=False)  # (nel, 8) dof indices
    enodes: np.ndarray = field(init=False)  # (nel, 4) node indices
    xn: np.ndarray = field(init=False)  # node x (mm)
    yn: np.ndarray = field(init=False)  # node y (mm)
    xc: np.ndarray = field(init=False)  # element centre x (mm)
    yc: np.ndarray = field(init=False)  # element centre y (mm)

    def __post_init__(self) -> None:
        nx, ny = self.nelx, self.nely
        self.nnodes = (nx + 1) * (ny + 1)
        self.ndof = 2 * self.nnodes
        self.nel = nx * ny
        ii, jj = np.meshgrid(np.arange(nx), np.arange(ny), indexing="ij")
        ii = ii.ravel()
        jj = jj.ravel()
        n0 = ii * (ny + 1) + jj
        n1 = (ii + 1) * (ny + 1) + jj
        n2 = (ii + 1) * (ny + 1) + jj + 1
        n3 = ii * (ny + 1) + jj + 1
        self.enodes = np.stack([n0, n1, n2, n3], axis=1)
        self.edof = np.empty((self.nel, 8), dtype=np.int64)
        self.edof[:, 0::2] = 2 * self.enodes
        self.edof[:, 1::2] = 2 * self.enodes + 1
        ni, nj = np.meshgrid(np.arange(nx + 1), np.arange(ny + 1), indexing="ij")
        self.xn = (ni.ravel() * self.h).astype(float)
        self.yn = (nj.ravel() * self.h).astype(float)
        self.xc = (ii + 0.5) * self.h
        self.yc = (jj + 0.5) * self.h

    # -- lookups ------------------------------------------------------------
    @property
    def width(self) -> float:
        return self.nelx * self.h

    @property
    def height(self) -> float:
        return self.nely * self.h

    def node(self, i: int, j: int) -> int:
        return i * (self.nely + 1) + j

    def element(self, i: int, j: int) -> int:
        return i * self.nely + j

    def node_at(self, x: float, y: float) -> int:
        """Index of the node nearest to (x, y)."""
        i = int(round(x / self.h))
        j = int(round(y / self.h))
        i = min(max(i, 0), self.nelx)
        j = min(max(j, 0), self.nely)
        return self.node(i, j)

    def nodes_where(self, cond: np.ndarray) -> np.ndarray:
        return np.nonzero(cond)[0]

    def nodes_on_x(self, x: float, tol: float | None = None) -> np.ndarray:
        tol = self.h * 1e-6 if tol is None else tol
        return self.nodes_where(np.abs(self.xn - x) <= tol)

    def nodes_on_y(self, y: float, tol: float | None = None) -> np.ndarray:
        tol = self.h * 1e-6 if tol is None else tol
        return self.nodes_where(np.abs(self.yn - y) <= tol)

    def element_grid(self, values: np.ndarray) -> np.ndarray:
        """Reshape a per-element vector to a (nelx, nely) grid (x along axis 0)."""
        return np.asarray(values).reshape(self.nelx, self.nely)

    def node_grid(self, values: np.ndarray) -> np.ndarray:
        return np.asarray(values).reshape(self.nelx + 1, self.nely + 1)


def mesh_for_box(width: float, height: float, h: float) -> Mesh:
    """Mesh a width x height box with elements of size h (rounded to whole elements)."""
    nelx = max(1, int(round(width / h)))
    nely = max(1, int(round(height / h)))
    return Mesh(nelx, nely, h)


def element_size_for_cap(width: float, height: float, min_wall: float, cap: int,
                         ratio: float = 2.5) -> float:
    """h = max(min_wall / ratio, the size that fits `cap` elements in the box)."""
    h_wall = min_wall / ratio
    h_cap = np.sqrt(width * height / cap)
    return max(h_wall, h_cap)


# ----------------------------------------------------------------------------- element
def plane_stress_D(E: float, nu: float) -> np.ndarray:
    c = E / (1.0 - nu * nu)
    return c * np.array([[1.0, nu, 0.0], [nu, 1.0, 0.0], [0.0, 0.0, (1.0 - nu) / 2.0]])


def shape_derivs(xi: float, eta: float, h: float) -> tuple[np.ndarray, np.ndarray]:
    """dN/dx and dN/dy of the 4 bilinear shape functions at (xi, eta) for a square of size h."""
    dN_dxi = 0.25 * _CORNER_XI * (1.0 + eta * _CORNER_ETA)
    dN_deta = 0.25 * _CORNER_ETA * (1.0 + xi * _CORNER_XI)
    scale = 2.0 / h  # dxi/dx for a square element of size h
    return dN_dxi * scale, dN_deta * scale


def B_matrix(xi: float, eta: float, h: float) -> np.ndarray:
    dNdx, dNdy = shape_derivs(xi, eta, h)
    B = np.zeros((3, 8))
    B[0, 0::2] = dNdx
    B[1, 1::2] = dNdy
    B[2, 0::2] = dNdy
    B[2, 1::2] = dNdx
    return B


def gauss_B_matrices(h: float) -> np.ndarray:
    """B at the 2x2 Gauss points, ordered like the corners (point g in corner g's quadrant). (4, 3, 8)"""
    return np.stack([B_matrix(_GAUSS_A * _CORNER_XI[g], _GAUSS_A * _CORNER_ETA[g], h) for g in range(4)])


def element_stiffness(E: float, nu: float, thickness: float, h: float = 1.0) -> np.ndarray:
    """8x8 Q4 plane-stress stiffness by 2x2 Gauss integration (exact for the bilinear element).

    In 2D the result does not depend on h for a square element; h is accepted for clarity.
    """
    D = plane_stress_D(E, nu)
    Bs = gauss_B_matrices(h)
    detJ = (h / 2.0) ** 2
    KE = np.zeros((8, 8))
    for g in range(4):
        KE += Bs[g].T @ D @ Bs[g] * detJ
    return KE * thickness


# Extrapolation from the 4 Gauss points to the 4 corner nodes (rows: corners, cols: Gauss points).
# Weights: 1 + sqrt(3)/2 (nearest), -1/2 (adjacent), 1 - sqrt(3)/2 (opposite).
GAUSS_TO_NODE = np.array(
    [[0.25 * (1.0 + _SQ3 * _CORNER_XI[k] * _CORNER_XI[g]) * (1.0 + _SQ3 * _CORNER_ETA[k] * _CORNER_ETA[g])
      for g in range(4)] for k in range(4)]
)


# ----------------------------------------------------------------------------- assembly
class Assembler:
    """Assembles K = sum_e Ee[e] * KE_unit with a precomputed sparsity pattern.

    `KE_unit` is the element stiffness for E = 1 (with the real nu and thickness).
    """

    def __init__(self, mesh: Mesh, KE_unit: np.ndarray):
        self.mesh = mesh
        self.KE = np.asarray(KE_unit, dtype=float)
        self.KE_flat = self.KE.ravel()
        edof = mesh.edof
        iK = np.repeat(edof, 8, axis=1).ravel()  # row index of each KE entry
        jK = np.tile(edof, (1, 8)).ravel()  # col index
        n = mesh.ndof
        # Build the CSC pattern once, then a map from each (e, a, b) entry to its slot.
        pattern = sp.coo_matrix((np.ones(iK.size), (iK, jK)), shape=(n, n)).tocsc()
        pattern.sum_duplicates()
        pattern.sort_indices()
        self.indptr = pattern.indptr.copy()
        self.indices = pattern.indices.copy()
        self.nnz = pattern.nnz
        keys_csc = np.repeat(np.arange(n, dtype=np.int64), np.diff(self.indptr)) * n + self.indices
        keys_coo = jK.astype(np.int64) * n + iK.astype(np.int64)
        self.slot = np.searchsorted(keys_csc, keys_coo)
        assert np.all(keys_csc[self.slot] == keys_coo)

    def assemble(self, Ee: np.ndarray) -> sp.csc_matrix:
        sK = (self.KE_flat[None, :] * np.asarray(Ee, dtype=float)[:, None]).ravel()
        data = np.bincount(self.slot, weights=sK, minlength=self.nnz)
        return sp.csc_matrix((data, self.indices, self.indptr), shape=(self.mesh.ndof, self.mesh.ndof))


# ----------------------------------------------------------------------------- solve
class SingularSystem(RuntimeError):
    """The stiffness system is singular: the part can move freely."""


class Solver:
    """Factorize once, back-solve for several right-hand sides. Pardiso if available."""

    def __init__(self, use_pardiso: bool | None = None):
        self.use_pardiso = HAVE_PARDISO if use_pardiso is None else (use_pardiso and HAVE_PARDISO)
        self._pardiso = pypardiso.PyPardisoSolver() if self.use_pardiso else None
        self._lu = None
        self.K_ff = None

    def factorize(self, K_ff: sp.csc_matrix) -> None:
        self.K_ff = K_ff
        if self.use_pardiso:
            self._pardiso.factorize(sp.csr_matrix(K_ff))
        else:
            from scipy.sparse.linalg import splu

            self._lu = splu(K_ff.tocsc())

    def solve(self, F_f: np.ndarray) -> np.ndarray:
        F_f = np.asarray(F_f, dtype=float)
        if self.use_pardiso:
            out = self._pardiso.solve(sp.csr_matrix(self.K_ff), F_f)
        else:
            out = self._lu.solve(F_f)
        out = np.asarray(out)
        if not np.all(np.isfinite(out)):
            raise SingularSystem("non-finite displacements: the part can move freely")
        return out

    def free(self) -> None:
        if self._pardiso is not None:
            try:
                self._pardiso.free_memory(everything=True)
            except Exception:  # pragma: no cover
                pass


def solve_system(K: sp.csc_matrix, F: np.ndarray, fixed: np.ndarray,
                 solver: Solver | None = None) -> np.ndarray:
    """Solve K U = F with the given fixed dofs (set to zero). F may be (ndof,) or (ndof, ncases)."""
    n = K.shape[0]
    fixed = np.unique(np.asarray(fixed, dtype=np.int64))
    free = np.setdiff1d(np.arange(n), fixed, assume_unique=True)
    F = np.asarray(F, dtype=float)
    single = F.ndim == 1
    if single:
        F = F[:, None]
    U = np.zeros((n, F.shape[1]))
    K_ff = K[free][:, free]
    own = solver is None
    solver = solver or Solver()
    solver.factorize(K_ff)
    U[free] = solver.solve(F[free])
    if own:
        solver.free()
    # crude singularity check: a rigid-body mode gives absurd displacements
    scale = max(np.abs(F).max(), 1e-300)
    if np.abs(U).max() > 1e12 * scale * max(1.0, 1.0 / max(K_ff.diagonal().min(), 1e-300)):
        raise SingularSystem("displacements blow up: the part can move freely")
    return U[:, 0] if single else U


def reactions(K: sp.csc_matrix, U: np.ndarray, F: np.ndarray) -> np.ndarray:
    """R = K U - F for every dof (non-zero only at constrained dofs, up to round-off)."""
    return np.asarray(K @ U) - np.asarray(F, dtype=float)


# ----------------------------------------------------------------------------- stresses
def gauss_stresses(mesh: Mesh, U: np.ndarray, E_elem: np.ndarray | float, nu: float) -> np.ndarray:
    """Stress components (sx, sy, txy) at the 2x2 Gauss points of every element. (nel, 4, 3)

    `E_elem` is the modulus used per element (a scalar or an array of length nel).
    The strain comes from the FE displacement field U (one load case, shape (ndof,)).
    """
    Bs = gauss_B_matrices(mesh.h)  # (4, 3, 8)
    D1 = plane_stress_D(1.0, nu)
    DB = np.einsum("ij,gjk->gik", D1, Bs)  # (4, 3, 8)
    ue = np.asarray(U, dtype=float)[mesh.edof]  # (nel, 8)
    sig = np.einsum("gik,ek->egi", DB, ue)  # (nel, 4, 3)
    E_elem = np.asarray(E_elem, dtype=float)
    if E_elem.ndim == 0:
        return sig * float(E_elem)
    return sig * E_elem[:, None, None]


def element_center_stresses(mesh: Mesh, U: np.ndarray, E_elem: np.ndarray | float, nu: float) -> np.ndarray:
    """Stress components at the element centre (mean of the Gauss points for a bilinear field). (nel, 3)"""
    return gauss_stresses(mesh, U, E_elem, nu).mean(axis=1)


def nodal_recovery(mesh: Mesh, sig_gp: np.ndarray, solid: np.ndarray) -> np.ndarray:
    """Recover nodal stress components by Gauss-point extrapolation and averaging.

    Only elements flagged `solid` enter the average. Nodes touched by no solid
    element are NaN (masked). Returns (nnodes, 3).
    """
    solid = np.asarray(solid, dtype=bool)
    corner = np.einsum("kg,egi->eki", GAUSS_TO_NODE, sig_gp)  # (nel, 4, 3)
    nodes = mesh.enodes[solid].ravel()
    vals = corner[solid].reshape(-1, 3)
    out = np.zeros((mesh.nnodes, 3))
    for c in range(3):
        out[:, c] = np.bincount(nodes, weights=vals[:, c], minlength=mesh.nnodes)
    count = np.bincount(nodes, minlength=mesh.nnodes).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        out /= count[:, None]
    out[count == 0] = np.nan
    return out


def von_mises(sig: np.ndarray) -> np.ndarray:
    """Von Mises stress from (…, 3) components (sx, sy, txy) under plane stress."""
    sx, sy, t = sig[..., 0], sig[..., 1], sig[..., 2]
    return np.sqrt(sx * sx - sx * sy + sy * sy + 3.0 * t * t)


def nodal_von_mises(mesh: Mesh, U: np.ndarray, E_elem: np.ndarray | float, nu: float,
                    solid: np.ndarray) -> np.ndarray:
    """Convenience: recovered nodal von Mises (nnodes,), NaN at masked nodes."""
    return von_mises(nodal_recovery(mesh, gauss_stresses(mesh, U, E_elem, nu), solid))


# ----------------------------------------------------------------------------- raster helpers
def raster_area_fraction(mesh: Mesh, inside, supersample: int = 4) -> np.ndarray:
    """Area fraction of each element inside the region given by `inside(x, y) -> bool array`.

    Uses supersample x supersample sample points per element (production: 4 x 4).
    """
    s = supersample
    offs = (np.arange(s) + 0.5) / s * mesh.h
    frac = np.zeros(mesh.nel)
    x0 = mesh.xc - 0.5 * mesh.h
    y0 = mesh.yc - 0.5 * mesh.h
    for dx in offs:
        for dy in offs:
            frac += inside(x0 + dx, y0 + dy).astype(float)
    return frac / (s * s)


def circle_fraction(mesh: Mesh, cx: float, cy: float, r: float, supersample: int = 4) -> np.ndarray:
    """Area fraction of each element inside the circle."""
    return raster_area_fraction(mesh, lambda x, y: (x - cx) ** 2 + (y - cy) ** 2 < r * r, supersample)


# ----------------------------------------------------------------------------- helpers for tests
def consistent_edge_load(mesh: Mesh, nodes: np.ndarray, total_force: float, direction: int) -> np.ndarray:
    """Spread `total_force` along a straight line of nodes as a uniform traction.

    Interior nodes get equal shares; the two end nodes get half shares
    (consistent nodal loads for a uniform traction on linear edges).
    Returns a global force vector (ndof,).
    """
    nodes = np.asarray(nodes)
    n = nodes.size
    F = np.zeros(mesh.ndof)
    if n == 1:
        F[2 * nodes[0] + direction] = total_force
        return F
    w = np.ones(n)
    w[0] = w[-1] = 0.5
    w /= w.sum()
    F[2 * nodes + direction] = total_force * w
    return F


def fix_nodes(nodes: np.ndarray, x: bool = True, y: bool = True) -> np.ndarray:
    nodes = np.asarray(nodes, dtype=np.int64)
    parts = []
    if x:
        parts.append(2 * nodes)
    if y:
        parts.append(2 * nodes + 1)
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.int64)


def warn_if_no_pardiso() -> None:
    if not HAVE_PARDISO:
        warnings.warn("PyPardiso not available: falling back to scipy.sparse.linalg (slower)")
