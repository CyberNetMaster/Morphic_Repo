"""Evaluation of a chosen design (spec section 6.8).

`analyze_design` does the mechanics (clean-up, connectivity, re-analysis, deflection,
nodal stress with the mm exclusion zone, reactions). `check_design` applies a
material and the limits (safety factor, deflection, mass, out-of-plane hand checks,
bearing hand checks). `evaluate` does both.

Density input modes:
- "binary":   SIMP output; solid = density >= 0.5; E_e = E (solid) or E_min (void)
- "fraction": smoothed re-check; E_e = E x area fraction (linear, no penalty);
              solid for stress purposes = fraction >= 0.5
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from . import config, fe
from .domain import Domain
from .materials import Material


# ----------------------------------------------------------------------------- clean-up
def clean_solid_mask(domain: Domain, density: np.ndarray, mode: str = "binary") -> tuple[np.ndarray, list[str]]:
    """Threshold at 0.5, force passive elements, drop islands not connected to any pad."""
    solid = np.asarray(density) >= config.SOLID_THRESHOLD
    solid = solid | domain.passive_solid
    solid = solid & ~domain.passive_void
    notes: list[str] = []
    grid = domain.mesh.element_grid(solid)
    labels, n = ndimage.label(grid)  # 4-connectivity
    labels = labels.ravel()
    keep = set()
    for pid, pn in domain.pad_nodes.items():
        els = domain.pad_ring_elements[pid]
        keep.update(np.unique(labels[els][labels[els] > 0]).tolist())
    island = (labels > 0) & ~np.isin(labels, list(keep))
    if island.any():
        notes.append(f"removed {int(island.sum())} elements in islands not connected to any pad")
        solid = solid & ~island
    return solid, notes


def check_connectivity(domain: Domain, solid: np.ndarray) -> tuple[bool, list[str]]:
    """Every load pad must reach at least one support pad through solid."""
    labels, _ = ndimage.label(domain.mesh.element_grid(solid))
    labels = labels.ravel()
    support_labels = set()
    for pn in domain.support_pads():
        els = domain.pad_ring_elements[pn.pad_id]
        support_labels.update(np.unique(labels[els][labels[els] > 0]).tolist())
    problems = []
    for pn in domain.load_pads():
        els = domain.pad_ring_elements[pn.pad_id]
        mine = set(np.unique(labels[els][labels[els] > 0]).tolist())
        if not (mine & support_labels):
            problems.append(f"load pad {pn.pad_id} not connected to a support")
    return (not problems), problems


# ----------------------------------------------------------------------------- mechanics
@dataclass
class Mechanics:
    E: float
    nu: float
    mode: str
    solid: np.ndarray  # bool (nel,) after clean-up
    fraction: np.ndarray  # area fraction per element used for stiffness and mass
    connected: bool
    connectivity_problems: list[str]
    notes: list[str]
    area_mm2: float
    deflection_mm: np.ndarray  # per case, max |u| over the load pad nodes
    stress_reported_MPa: np.ndarray  # per case, max recovered vm outside exclusion zones
    stress_raw_MPa: np.ndarray  # per case, max recovered vm anywhere solid
    nodal_vm: np.ndarray  # (ncases, nnodes), NaN at masked nodes
    reactions: dict  # pad_id -> (ncases, 2) [Rx, Ry]
    reaction_sum_ok: bool
    reaction_sum_error: float
    U: np.ndarray | None = None  # (ndof, ncases)

    @property
    def ncases(self) -> int:
        return self.deflection_mm.size


def analyze_design(domain: Domain, density: np.ndarray, E: float, nu: float, mode: str = "binary",
                   keep_U: bool = False) -> Mechanics:
    mesh = domain.mesh
    density = np.asarray(density, dtype=float)
    notes: list[str] = []
    if mode == "binary":
        solid, notes = clean_solid_mask(domain, density, mode)
        fraction = solid.astype(float)
    elif mode == "fraction":
        fraction = np.clip(density, 0.0, 1.0)
        fraction[domain.passive_void] = 0.0
        fraction[domain.passive_solid] = np.maximum(fraction[domain.passive_solid], 1.0)
        solid, notes = clean_solid_mask(domain, fraction, mode)
        fraction = np.where(solid | (fraction >= 0), fraction, 0.0)
        fraction[~solid & (fraction >= config.SOLID_THRESHOLD)] = 0.0  # removed islands
    else:
        raise ValueError(mode)
    connected, problems = check_connectivity(domain, solid)

    Ee = E * np.maximum(fraction, config.E_MIN_RATIO)
    K = fe.Assembler(mesh, domain.KE_unit(nu)).assemble(Ee)
    ncases = domain.ncases
    U = np.zeros((mesh.ndof, ncases))
    try:
        U = fe.solve_system(K, domain.loads, domain.fixed_dofs)
    except fe.SingularSystem as exc:
        notes.append(f"FE solve failed: {exc}")
        connected = False
        problems = problems + ["the part can move freely (singular stiffness)"]
    if U.ndim == 1:
        U = U[:, None]

    # deflection per case: max displacement magnitude over the load pads' nodes
    defl = np.zeros(ncases)
    for c in range(ncases):
        best = 0.0
        for pn in domain.load_pads():
            ux = U[2 * pn.nodes, c]
            uy = U[2 * pn.nodes + 1, c]
            best = max(best, float(np.hypot(ux, uy).max()))
        defl[c] = best

    # stresses: full E for solid elements, nodal recovery over solid only
    nodal_vm = np.full((ncases, mesh.nnodes), np.nan)
    rep = np.zeros(ncases)
    raw = np.zeros(ncases)
    outside = ~domain.exclusion_nodes
    for c in range(ncases):
        gp = fe.gauss_stresses(mesh, U[:, c], E, nu)
        vm = fe.von_mises(fe.nodal_recovery(mesh, gp, solid))
        nodal_vm[c] = vm
        finite = np.isfinite(vm)
        raw[c] = float(np.nanmax(vm)) if finite.any() else 0.0
        sel = finite & outside
        rep[c] = float(np.nanmax(vm[sel])) if sel.any() else 0.0

    # reactions per support pad: K u - f at the constrained dofs
    R = fe.reactions(K, U, domain.loads)
    reactions: dict[str, np.ndarray] = {}
    total = np.zeros((ncases, 2))
    for pn in domain.support_pads():
        r = np.zeros((ncases, 2))
        if pn.fix_x:
            r[:, 0] = R[2 * pn.nodes].sum(axis=0)
        if pn.fix_y:
            r[:, 1] = R[2 * pn.nodes + 1].sum(axis=0)
        reactions[pn.pad_id] = r
        total += r
    applied = np.stack([domain.loads[0::2].sum(axis=0), domain.loads[1::2].sum(axis=0)], axis=1)
    scale = max(np.abs(applied).max(), 1e-12)
    err = float(np.abs(total + applied).max() / scale)
    reaction_ok = err < config.REACTION_SUM_RTOL * 10  # 1e-5 relative; the solve itself is ~1e-10

    area = float(fraction.sum() * mesh.h * mesh.h)
    return Mechanics(E=E, nu=nu, mode=mode, solid=solid, fraction=fraction, connected=connected,
                     connectivity_problems=problems, notes=notes, area_mm2=area, deflection_mm=defl,
                     stress_reported_MPa=rep, stress_raw_MPa=raw, nodal_vm=nodal_vm, reactions=reactions,
                     reaction_sum_ok=reaction_ok, reaction_sum_error=err, U=U if keep_U else None)


def scaled_mechanics(mech_ref: Mechanics, E_new: float) -> tuple[np.ndarray, np.ndarray]:
    """Catalog scaling (spec 6.4): deflection ~ 1/E, stress independent of E."""
    return mech_ref.deflection_mm * (mech_ref.E / E_new), mech_ref.stress_reported_MPa.copy()


# ----------------------------------------------------------------------------- hand checks
@dataclass
class HandCheck:
    name: str
    passed: bool
    sf: float
    detail: str
    where: str = ""
    suggestion: str = ""


def _section_width(domain: Domain, solid: np.ndarray, px: float, py: float, nx: float, ny: float) -> float:
    """Solid width (mm) across the section through (px, py) along the unit direction (nx, ny)."""
    mesh = domain.mesh
    grid = mesh.element_grid(solid)
    half = max(mesh.width, mesh.height)
    s = np.arange(-half, half + mesh.h, mesh.h)
    xs = px + s * nx
    ys = py + s * ny
    inside = (xs >= 0) & (xs < mesh.width) & (ys >= 0) & (ys < mesh.height)
    i = np.clip((xs[inside] / mesh.h).astype(int), 0, mesh.nelx - 1)
    j = np.clip((ys[inside] / mesh.h).astype(int), 0, mesh.nely - 1)
    return float(grid[i, j].sum() * mesh.h)


def out_of_plane_checks(domain: Domain, solid: np.ndarray, material: Material, sf_target: float) -> list[HandCheck]:
    """Bending through the thickness and interlayer shear, along the line from each
    load pad to its nearest support pad, at 20 sections (spec 6.8 step 8)."""
    problem = domain.problem
    t = problem.thickness_mm
    out: list[HandCheck] = []
    sz, z_note = material.strength_z_used()
    tau_allow, tau_note = material.interlayer_shear_used()
    for lc in problem.load_cases:
        fz_by_pad: dict[str, float] = {}
        for ld in lc.loads:
            if ld.fz_N_out_of_plane != 0.0:
                fz_by_pad[ld.pad_id] = fz_by_pad.get(ld.pad_id, 0.0) + ld.fz_N_out_of_plane
        for pid, fz in fz_by_pad.items():
            pl = problem.pad(pid)
            sup = min((problem.pad(s) for s in problem.support_pad_ids),
                      key=lambda p: np.hypot(p.cx - pl.cx, p.cy - pl.cy))
            L = float(np.hypot(sup.cx - pl.cx, sup.cy - pl.cy))
            if L <= 0:
                continue
            dx, dy = (sup.cx - pl.cx) / L, (sup.cy - pl.cy) / L
            nx, ny = -dy, dx
            worst_b, worst_s = np.inf, np.inf
            where_b = where_s = ""
            for k in range(1, config.OUT_OF_PLANE_SECTIONS + 1):
                frac = k / (config.OUT_OF_PLANE_SECTIONS + 1)
                px, py = pl.cx + dx * L * frac, pl.cy + dy * L * frac
                w = _section_width(domain, solid, px, py, nx, ny)
                if w <= 0:
                    continue
                M = abs(fz) * L * frac
                sigma = 6.0 * M / (w * t * t)  # M (t/2) / (w t^3 / 12)
                tau = 1.5 * abs(fz) / (w * t)
                sf_b = material.strength / sigma if sigma > 0 else np.inf
                sf_s = tau_allow / tau if tau > 0 else np.inf
                if sf_b < worst_b:
                    worst_b, where_b = sf_b, f"{L * frac:.1f} mm from pad {pid}, width {w:.1f} mm"
                if sf_s < worst_s:
                    worst_s, where_s = sf_s, f"{L * frac:.1f} mm from pad {pid}, width {w:.1f} mm"
            out.append(HandCheck(name=f"out-of-plane bending ({lc.name})", passed=worst_b >= sf_target,
                                 sf=float(worst_b), where=where_b,
                                 detail=f"approximate hand check: beam through the thickness, XY strength "
                                        f"{material.strength:g} MPa"))
            out.append(HandCheck(name=f"interlayer shear ({lc.name})", passed=worst_s >= sf_target,
                                 sf=float(worst_s), where=where_s,
                                 detail=f"approximate hand check: 1.5 Fz / (w t) vs {tau_allow:.1f} MPa "
                                        f"({tau_note})"))
    return out


def bearing_checks(domain: Domain, mech: Mechanics, material: Material, sf_target: float) -> list[HandCheck]:
    """Pin bearing F / (d t) at every pad with a hole: load pads from the applied force,
    support pads from the FE reaction (spec 6.8 step 9)."""
    problem = domain.problem
    t = problem.thickness_mm
    out: list[HandCheck] = []
    for pad in problem.pads:
        pn = domain.pad_nodes[pad.id]
        if pad.is_solid:
            out.append(HandCheck(name=f"bearing at {pad.id}", passed=True, sf=np.inf,
                                 detail="n/a (solid mount)"))
            continue
        d = 2.0 * pad.hole_r_mm
        worst, where = np.inf, ""
        for c, lc in enumerate(problem.load_cases):
            if pn.is_support:
                r = mech.reactions.get(pad.id)
                F = float(np.hypot(r[c, 0], r[c, 1])) if r is not None else 0.0
                src = "FE reaction"
            else:
                F = sum(ld.in_plane_resultant for ld in lc.loads if ld.pad_id == pad.id)
                src = "applied force"
            if F <= 0:
                continue
            sigma_b = F / (d * t)
            sf = material.strength / sigma_b
            if sf < worst:
                worst, where = sf, f"{lc.name}: {src} {F:.0f} N, {sigma_b:.1f} MPa vs {material.strength:g} MPa"
        passed = worst >= sf_target
        sug = ""
        if not passed:
            need = d * t * sf_target / worst
            sug = (f"required pin diameter x thickness = {need:.1f} mm^2 (now {d * t:.1f}): "
                   f"a {need / t:.1f} mm pin at this thickness, or {need / d:.1f} mm thick at this pin, or a bushing")
        out.append(HandCheck(name=f"bearing at {pad.id}", passed=passed, sf=float(worst), where=where,
                             suggestion=sug,
                             detail="full XY strength used as an approximation; bearing allowables are "
                                    "often higher, so this errs on the safe side"))
    return out


# ----------------------------------------------------------------------------- checks
@dataclass
class Checks:
    material_id: str
    sf_target: float
    passed: bool  # all in-plane limits, connectivity, out-of-plane and bearing
    passed_in_plane: bool  # SF + deflection + connectivity only (used for the fill-level search)
    sf: float  # worst case, reported stress
    sf_raw: float
    stress_reported_MPa: float
    stress_raw_MPa: float
    stress_pass: bool
    deflection_mm: np.ndarray
    deflection_limit_mm: np.ndarray
    deflection_pass: bool
    mass_g: float
    out_of_plane: list[HandCheck]
    bearing: list[HandCheck]
    fail_reasons: list[str]
    notes: list[str]
    utilization: np.ndarray = field(default=None)  # (ncases, nnodes) vm * SF_target / strength

    @property
    def deflection_case(self) -> int:
        return int(np.argmax(self.deflection_mm / self.deflection_limit_mm))


def check_design(domain: Domain, mech: Mechanics, material: Material, sf_target: float,
                 deflection_mm: np.ndarray | None = None, stress_MPa: np.ndarray | None = None) -> Checks:
    """Apply the limits. Optional deflection/stress override lets the catalog use scaled values."""
    problem = domain.problem
    defl = mech.deflection_mm if deflection_mm is None else np.asarray(deflection_mm, dtype=float)
    stress = mech.stress_reported_MPa if stress_MPa is None else np.asarray(stress_MPa, dtype=float)
    limits = np.array([lc.max_deflection_mm for lc in problem.load_cases])
    in_plane = np.array([lc.has_in_plane for lc in problem.load_cases])
    smax = float(stress[in_plane].max()) if in_plane.any() else 0.0
    sf = material.strength / smax if smax > 0 else np.inf
    sraw = float(mech.stress_raw_MPa[in_plane].max()) if in_plane.any() else 0.0
    sf_raw = material.strength / sraw if sraw > 0 else np.inf
    stress_pass = sf >= sf_target
    defl_pass = bool(np.all(defl[in_plane] <= limits[in_plane])) if in_plane.any() else True
    mass = mech.area_mm2 * problem.thickness_mm * material.density / 1000.0  # mm3 * g/cm3 / 1000

    reasons: list[str] = []
    if not mech.connected:
        reasons += mech.connectivity_problems
    if not stress_pass:
        reasons.append(f"safety factor {sf:.2f} < {sf_target:g}")
    if not defl_pass:
        c = int(np.argmax(defl / limits))
        reasons.append(f"deflection {defl[c]:.3f} mm > {limits[c]:g} mm ({problem.load_cases[c].name})")
    passed_in_plane = mech.connected and stress_pass and defl_pass

    oop = out_of_plane_checks(domain, mech.solid, material, sf_target) if any(
        lc.has_out_of_plane for lc in problem.load_cases) else []
    brg = bearing_checks(domain, mech, material, sf_target)
    for hc in oop + brg:
        if not hc.passed:
            reasons.append(f"{hc.name}: SF {hc.sf:.2f} < {sf_target:g}")
    notes = list(mech.notes)
    if not mech.reaction_sum_ok:
        notes.append(f"reactions do not balance the load (rel. error {mech.reaction_sum_error:.1e}); solve flagged")
    util = mech.nodal_vm * sf_target / material.strength
    return Checks(material_id=material.id, sf_target=sf_target,
                  passed=passed_in_plane and all(h.passed for h in oop + brg),
                  passed_in_plane=passed_in_plane, sf=float(sf), sf_raw=float(sf_raw),
                  stress_reported_MPa=smax, stress_raw_MPa=sraw, stress_pass=stress_pass,
                  deflection_mm=defl, deflection_limit_mm=limits, deflection_pass=defl_pass, mass_g=float(mass),
                  out_of_plane=oop, bearing=brg, fail_reasons=reasons, notes=notes, utilization=util)


def evaluate(domain: Domain, density: np.ndarray, material: Material, sf_target: float,
             mode: str = "binary") -> tuple[Mechanics, Checks]:
    mech = analyze_design(domain, density, material.E, material.nu, mode)
    return mech, check_design(domain, mech, material, sf_target)


def thickness_suggestion(problem_thickness: float, sf: float, sf_target: float,
                         defl: np.ndarray, limits: np.ndarray) -> float:
    """In-plane deflection and stress both scale 1/t for the same shape (spec section 8)."""
    ratio = max(sf_target / sf if np.isfinite(sf) and sf > 0 else 1.0,
                float(np.max(defl / limits)) if defl.size else 1.0, 1.0)
    return problem_thickness * ratio
