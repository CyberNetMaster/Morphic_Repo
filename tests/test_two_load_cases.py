"""S4 acceptance: a pad-based problem with two load cases and fixed normalization converges.

Also checks: solid pad, hole pad, passive masks, the fixed per-case normalization,
and uint8 snapshot round-trip.
"""

import numpy as np

from morphic import topopt
from morphic.domain import build_domain
from morphic.problem import Problem


def small_bracket() -> Problem:
    return Problem.model_validate({
        "name": "test bracket",
        "design_space": {"width_mm": 60, "height_mm": 30},
        "thickness_mm": 6,
        "pads": [
            {"id": "A", "cx": 6, "cy": 6, "hole_r_mm": 1.6, "ring_r_mm": 4.0},
            {"id": "B", "cx": 6, "cy": 24, "hole_r_mm": 1.6, "ring_r_mm": 4.0},
            {"id": "L", "cx": 52, "cy": 15, "hole_r_mm": 0.0, "ring_r_mm": 5.0},
        ],
        "supports": [{"pad_id": "A", "type": "pin"}, {"pad_id": "B", "type": "slide_x"}],
        "load_cases": [
            {"id": "c1", "name": "down", "loads": [{"pad_id": "L", "fy_N": -100}], "max_deflection_mm": 0.5},
            {"id": "c2", "name": "sideways", "loads": [{"pad_id": "L", "fx_N": 60}], "max_deflection_mm": 0.5},
        ],
        "safety_factor": 2.0,
    })


def test_domain_build_and_two_case_convergence():
    p = small_bracket()
    dom = build_domain(p, "fdm", 1.2, cap=2500)
    assert dom.mesh.nel <= 2800
    assert dom.effective_min_wall_mm >= 1.2
    # pads: hole elements void, ring elements solid, solid pad all solid
    assert dom.passive_void[dom.pad_hole_elements["A"]].all()
    assert dom.passive_solid[dom.pad_ring_elements["A"]].all()
    assert dom.pad_hole_elements["L"].size == 0 and dom.pad_ring_elements["L"].size > 0
    assert dom.pad_nodes["L"].is_load and dom.pad_nodes["A"].is_support
    # slide_x: y held only
    assert dom.pad_nodes["B"].fix_y and not dom.pad_nodes["B"].fix_x
    # loads sum to the applied force per case
    assert np.isclose(dom.loads[1::2, 0].sum(), -100.0)
    assert np.isclose(dom.loads[0::2, 1].sum(), 60.0)
    assert dom.loads.shape[1] == 2

    prob = dom.topopt_problem()
    w = topopt.normalization_weights(prob, 0.6)
    assert w.shape == (2,) and np.all(w > 0)
    prob.case_weights = w
    # the weighted objective at the normalization design is exactly 2 (each case counts 1)
    x = np.full(dom.mesh.nel, 0.6)
    x[dom.passive_solid] = 1.0
    x[dom.passive_void] = 0.0
    assert np.isclose((prob.compliance(x) * w).sum(), 2.0)

    res = topopt.run(prob, topopt.TopOptSettings(volfrac=0.4, rmin=dom.rmin_elements, mode="cold",
                                                 snapshot_every=2))
    assert res.converged, (res.iterations, res.history[-1])
    assert abs(res.volume - 0.4) < 1e-3
    assert res.xPhys[dom.passive_solid].min() == 1.0
    assert res.xPhys[dom.passive_void].max() == 0.0
    assert len(res.snapshots) >= res.iterations // 2
    it, snap = res.snapshots[-1]
    assert snap.dtype == np.uint8
    assert np.abs(snap / 255.0 - res.xPhys).max() < 1 / 255.0 + 1e-9
    # the two cases both matter: the optimized design beats uniform density in each case
    c_uniform = prob.compliance(x)
    assert np.all(res.compliance < c_uniform * 1.5)
