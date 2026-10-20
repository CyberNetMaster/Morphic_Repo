"""Validation checks (spec section 13). Shared by pytest, `morphic validate`, and the app.

Each function returns a plain dict of numbers so the UI can show them and the
tests can assert on them.
"""

from __future__ import annotations

import numpy as np

from . import config, fe

# --------------------------------------------------------------------- 13.1 cantilever


def cantilever_check(elems_through_depth: int = 20, L: float = 100.0, depth: float = 10.0,
                     t: float = 10.0, E: float = 2200.0, nu: float = 0.3, P: float = 100.0) -> dict:
    """Cantilever beam: tip load spread over the end face, fixed face at x = 0.

    Compares tip deflection with beam theory including shear (kappa = 5/6) and
    mid-span bending stress with M c / I, using the recovered nodal stress at the
    top surface node. Also reports the element-centre value of the top row against
    M y / I at the centre height.
    """
    h = depth / elems_through_depth
    mesh = fe.mesh_for_box(L, depth, h)
    KE = fe.element_stiffness(1.0, nu, t)
    asm = fe.Assembler(mesh, KE)
    K = asm.assemble(np.full(mesh.nel, E))
    end_nodes = mesh.nodes_on_x(L)
    F = fe.consistent_edge_load(mesh, end_nodes, -P, direction=1)
    fixed = fe.fix_nodes(mesh.nodes_on_x(0.0))
    U = fe.solve_system(K, F, fixed)

    I = t * depth**3 / 12.0
    A = t * depth
    G = E / (2.0 * (1.0 + nu))
    kappa = 5.0 / 6.0
    delta_theory = P * L**3 / (3.0 * E * I) + P * L / (kappa * G * A)
    delta_fe = -U[2 * end_nodes + 1].mean()

    # Stress at mid-span, top surface node (x = L/2, y = depth).
    sig_gp = fe.gauss_stresses(mesh, U, E, nu)
    nodal = fe.nodal_recovery(mesh, sig_gp, np.ones(mesh.nel, dtype=bool))
    top_node = mesh.node_at(L / 2.0, depth)
    sx_node = abs(nodal[top_node, 0])
    c = depth / 2.0
    M = P * L / 2.0
    sigma_surface = M * c / I

    # Element-centre value of the top row at the element nearest mid-span.
    centres = fe.element_center_stresses(mesh, U, E, nu)
    i = int(L / 2.0 / h) - 1 if (L / 2.0 / h) == int(L / 2.0 / h) else int(L / 2.0 / h)
    e_top = mesh.element(i, mesh.nely - 1)
    x_e = mesh.xc[e_top]
    M_e = P * (L - x_e)
    y_e = c - h / 2.0
    sigma_centre_theory = M_e * y_e / I
    sx_centre = abs(centres[e_top, 0])

    return {
        "mesh": f"{mesh.nelx} x {mesh.nely} elements, h = {h:.4g} mm",
        "elements_through_depth": elems_through_depth,
        "delta_fe_mm": float(delta_fe),
        "delta_theory_mm": float(delta_theory),
        "delta_error": float(abs(delta_fe - delta_theory) / delta_theory),
        "sigma_node_MPa": float(sx_node),
        "sigma_surface_theory_MPa": float(sigma_surface),
        "sigma_error": float(abs(sx_node - sigma_surface) / sigma_surface),
        "sigma_centre_MPa": float(sx_centre),
        "sigma_centre_theory_MPa": float(sigma_centre_theory),
        "sigma_centre_error": float(abs(sx_centre - sigma_centre_theory) / sigma_centre_theory),
        "tolerance": config.VALIDATION_TOL_BEAM,
    }


def mesh_refinement(levels=(2, 4, 8, 16, 32)) -> list[dict]:
    return [cantilever_check(n) for n in levels]


# --------------------------------------------------------------------- 13.5 scaling laws


def scaling_law_check(E: float = 1000.0, nu: float = 0.33) -> dict:
    """Doubling E must halve deflection and leave stress unchanged for a fixed shape."""
    L, depth, t = 60.0, 20.0, 5.0
    mesh = fe.mesh_for_box(L, depth, 1.0)
    # A fixed shape: a cantilever with a central hole, boundary elements by area fraction.
    frac = 1.0 - fe.circle_fraction(mesh, 30.0, 10.0, 5.0)
    solid = frac >= config.SOLID_THRESHOLD
    end_nodes = mesh.nodes_on_x(L)
    F = fe.consistent_edge_load(mesh, end_nodes, -50.0, direction=1)
    fixed = fe.fix_nodes(mesh.nodes_on_x(0.0))

    def run(E_val: float):
        KE = fe.element_stiffness(1.0, nu, t)
        K = fe.Assembler(mesh, KE).assemble(E_val * np.maximum(frac, config.E_MIN_RATIO))
        U = fe.solve_system(K, F, fixed)
        d = np.abs(U[2 * end_nodes + 1]).max()
        s = fe.nodal_von_mises(mesh, U, E_val, nu, solid)
        return d, np.nanmax(s)

    d1, s1 = run(E)
    d2, s2 = run(2.0 * E)
    return {
        "deflection_ratio": float(d2 / d1),
        "deflection_ratio_error": float(abs(d2 / d1 - 0.5) / 0.5),
        "stress_ratio": float(s2 / s1),
        "stress_ratio_error": float(abs(s2 / s1 - 1.0)),
        "tolerance": config.VALIDATION_TOL_SCALING,
    }


# --------------------------------------------------------------------- 13.4 hole stress


def kt_finite_width(d_over_W: float) -> dict:
    """Stress concentration for a circular hole in a finite-width plate in tension.

    Net-section factor, curve fit of Howland's solution, from Pilkey, W. D.,
    Peterson's Stress Concentration Factors, Chart 4.1 (circular hole in a
    finite-width element in tension; Howland 1929-30), valid for d/W <= 0.5:

        K_tn = 3.000 - 3.140 (d/W) + 3.667 (d/W)^2 - 1.527 (d/W)^3

    with sigma_nom on the net section. Converted to the gross-section factor
    (sigma_nom = applied far-field stress) by K_tg = K_tn / (1 - d/W).
    """
    lam = d_over_W
    if lam > 0.5:
        raise ValueError("formula valid for d/W <= 0.5")
    ktn = 3.000 - 3.140 * lam + 3.667 * lam**2 - 1.527 * lam**3
    return {"Ktn": ktn, "Ktg": ktn / (1.0 - lam)}


def kirsch_stress(sigma: float, a: float, r: np.ndarray, theta: np.ndarray) -> tuple:
    """Kirsch field for a circular hole in an infinite plate, far-field tension `sigma`
    along x. theta measured from the load axis. Returns (sig_rr, sig_tt, tau_rt)."""
    a2 = (a / r) ** 2
    a4 = a2 * a2
    c2 = np.cos(2 * theta)
    s2 = np.sin(2 * theta)
    srr = sigma / 2 * (1 - a2) + sigma / 2 * (1 - 4 * a2 + 3 * a4) * c2
    stt = sigma / 2 * (1 + a2) - sigma / 2 * (1 + 3 * a4) * c2
    trt = -sigma / 2 * (1 + 2 * a2 - 3 * a4) * s2
    return srr, stt, trt


def hole_stress_check(elems_per_radius: int = 16, d: float = 10.0, W_over_d: float = 10.0,
                      t: float = 5.0, E: float = 2000.0, nu: float = 0.3,
                      sigma_nom: float = 1.0) -> dict:
    """Plate with a central hole in tension, quarter model, hole on the regular grid
    as void elements with area fractions at the boundary (the production representation).

    Reports: without recovery, the element-centre stress in the edge element at
    theta = 90 deg; with recovery, the maximum recovered nodal stress over the hole
    boundary (the number production uses), plus the value at the 90 deg node and
    the angle where the maximum sits; an element check against the Kirsch field at
    the edge element's centroid; and the stair-step ratio.
    """
    r = d / 2.0
    W = W_over_d * d
    length = 2.0 * W
    h = r / elems_per_radius
    nelx = int(round((length / 2.0) / h))
    nely = int(round((W / 2.0) / h))
    mesh = fe.Mesh(nelx, nely, h)

    solid_frac = 1.0 - fe.circle_fraction(mesh, 0.0, 0.0, r, config.RECHECK_SUPERSAMPLE)
    solid = solid_frac >= config.SOLID_THRESHOLD
    Ee = E * np.maximum(solid_frac, config.E_MIN_RATIO)
    KE = fe.element_stiffness(1.0, nu, t)
    K = fe.Assembler(mesh, KE).assemble(Ee)

    fixed = np.concatenate([fe.fix_nodes(mesh.nodes_on_x(0.0), x=True, y=False),
                            fe.fix_nodes(mesh.nodes_on_y(0.0), x=False, y=True)])
    end_nodes = mesh.nodes_on_x(mesh.width)
    F = fe.consistent_edge_load(mesh, end_nodes, sigma_nom * (W / 2.0) * t, direction=0)
    U = fe.solve_system(K, F, fixed)

    kt = kt_finite_width(d / W)
    sigma_edge_true = kt["Ktg"] * sigma_nom

    # Full E for every solid element in the stress recovery.
    sig_gp = fe.gauss_stresses(mesh, U, E, nu)
    nodal = fe.nodal_recovery(mesh, sig_gp, solid)
    vm_nodal = fe.von_mises(nodal)
    edge_node = mesh.node_at(0.0, r)
    vm_edge_node = float(vm_nodal[edge_node])

    centre = fe.element_center_stresses(mesh, U, E, nu)
    vm_centre = fe.von_mises(centre)
    e_edge = mesh.element(0, elems_per_radius)  # the element just above the hole top
    vm_edge_elem = float(vm_centre[e_edge])

    # Element check: Kirsch field (scaled by Ktg / 3) at the element centroid.
    xc, yc = mesh.xc[e_edge], mesh.yc[e_edge]
    rc = np.hypot(xc, yc)
    thc = np.arctan2(yc, xc)
    srr, stt, trt = kirsch_stress(sigma_nom * kt["Ktg"] / 3.0, r, np.array(rc), np.array(thc))
    vm_kirsch_centroid = float(np.sqrt(srr**2 - srr * stt + stt**2 + 3 * trt**2))

    # Recovered value used by production: the max over the hole boundary nodes.
    dist = np.hypot(mesh.xn, mesh.yn)
    on_boundary = (dist >= r - h) & (dist <= r + h) & np.isfinite(vm_nodal)
    k = int(np.nanargmax(np.where(on_boundary, vm_nodal, -np.inf)))
    vm_boundary_max = float(vm_nodal[k])
    theta_max_deg = float(np.degrees(np.arctan2(mesh.yn[k], mesh.xn[k])))

    return {
        "elements_per_radius": elems_per_radius,
        "mesh": f"{nelx} x {nely} elements, h = {h:.4g} mm (quarter model)",
        "Ktn": kt["Ktn"],
        "Ktg": kt["Ktg"],
        "sigma_edge_true_MPa": sigma_edge_true,
        "vm_edge_element_centre_MPa": vm_edge_elem,
        "error_without_recovery": float(abs(vm_edge_elem - sigma_edge_true) / sigma_edge_true),
        "vm_recovered_boundary_max_MPa": vm_boundary_max,
        "theta_of_max_deg": theta_max_deg,
        "error_with_recovery": float(abs(vm_boundary_max - sigma_edge_true) / sigma_edge_true),
        "vm_edge_node_90deg_MPa": vm_edge_node,
        "error_at_90deg_node": float(abs(vm_edge_node - sigma_edge_true) / sigma_edge_true),
        "vm_kirsch_at_centroid_MPa": vm_kirsch_centroid,
        "element_check_error": float(abs(vm_edge_elem - vm_kirsch_centroid) / vm_kirsch_centroid),
        "stair_step_ratio": float(vm_boundary_max / vm_edge_node),
    }


def live_mesh_stress_error() -> float:
    """The remaining stress error at a smooth edge at the live mesh (8 elements per
    radius for a 1.6 mm pad hole at the 40k cap), for the Limits note."""
    return hole_stress_check(8)["error_with_recovery"]


LIMITS_NOTE_LIVE_MESH = (
    "Stress is recovered to the nodes. The remaining stress error at a smooth edge "
    "at the live mesh (8 elements per hole radius) is about {err:.0%}, measured by "
    "the hole check on the Validation tab."
)


# --------------------------------------------------------------------- 13.3 MBB benchmark

# Andreassen et al. (2011), "Efficient topology optimization in MATLAB using 88 lines
# of code", Struct Multidisc Optim 43:1-16, section 3.4 and Fig. 3 (bottom left):
# top88(60, 20, 0.5, 3, 2.4, 2), density filtering, published compliance c = 233.71.
MBB_PUBLISHED = {"nelx": 60, "nely": 20, "volfrac": 0.5, "penal": 3.0, "rmin": 2.4, "ft": 2,
                 "compliance": 233.71,
                 "source": "Andreassen et al. 2011, Fig. 3 bottom-left, density filter, 60 x 20"}


def mbb_check() -> dict:
    """Run the published MBB case in paper mode and compare the compliance."""
    from . import topopt

    p = MBB_PUBLISHED
    r = topopt.run_mbb_paper(p["nelx"], p["nely"], p["volfrac"], p["penal"], p["rmin"])
    c = float(r.compliance[0])
    return {
        "call": f"top88({p['nelx']},{p['nely']},{p['volfrac']},{p['penal']},{p['rmin']},{p['ft']})",
        "compliance": c,
        "compliance_last_iteration": float(r.history[-1]["objective"]),
        "published_compliance": p["compliance"],
        "error": abs(c - p["compliance"]) / p["compliance"],
        "iterations": r.iterations,
        "converged": r.converged,
        "volume": r.volume,
        "tolerance": config.VALIDATION_TOL_MBB,
        "density_grid": r.xPhys.reshape(p["nelx"], p["nely"]),  # x along axis 0, y up along axis 1
        "source": p["source"],
    }
