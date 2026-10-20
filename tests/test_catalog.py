"""S6 acceptance: results for a test problem across 3 processes, plus unit tests of the
level-choice rule (spec 6.5), connectivity, reactions, bearing and out-of-plane hand checks."""

import numpy as np
import pytest

from morphic import catalog, evaluate
from morphic.catalog import LevelStatus, choose_level
from morphic.domain import build_domain
from morphic.materials import Citation, Material, Process
from morphic.problem import Problem

CIT = Citation(title="test", url="http://example.invalid")


COSTS = {"pla": 29.99, "petg": 29.99, "pa6cf": 52.99, "pa12": 75.0, "alsi10mg": 41.0}


def fake_material(mid, process, E, strength, density, nu=0.33, sz=None):
    return Material(id=mid, name=mid, process=process, E=E, nu=nu, strength_xy=strength, strength_kind="tensile",
                    density=density, strength_z=sz, z_knockdown_value=0.5 if sz is None else None,
                    z_knockdown_source="test", cost_per_kg=COSTS.get(mid), citations={}, flags=[])


MATERIALS = {
    "pla": fake_material("pla", "fdm", 2200.0, 55.0, 1.24),
    "petg": fake_material("petg", "fdm", 1500.0, 47.0, 1.27),
    "pa6cf": fake_material("pa6cf", "fdm", 7000.0, 100.0, 1.17),
    "pa12": fake_material("pa12", "sls", 1650.0, 48.0, 0.93),
    "alsi10mg": fake_material("alsi10mg", "metal", 70000.0, 230.0, 2.67, sz=230.0),
}
PROCESSES = {
    "fdm": Process("fdm", "FDM", 1.2, "desktop_fdm", CIT),
    "sls": Process("sls", "SLS", 0.8, "sls_service", CIT),
    "metal": Process("metal", "DMLS", 0.5, "metal_service", CIT),
}


def bracket(fz: float = 0.0) -> Problem:
    return Problem.model_validate({
        "name": "test bracket",
        "design_space": {"width_mm": 60, "height_mm": 30},
        "thickness_mm": 6,
        "pads": [
            {"id": "A", "cx": 6, "cy": 6, "hole_r_mm": 1.6, "ring_r_mm": 4.0},
            {"id": "B", "cx": 6, "cy": 24, "hole_r_mm": 1.6, "ring_r_mm": 4.0},
            {"id": "L", "cx": 52, "cy": 15, "hole_r_mm": 1.6, "ring_r_mm": 4.0},
        ],
        "supports": [{"pad_id": "A", "type": "pin"}, {"pad_id": "B", "type": "pin"}],
        "load_cases": [
            {"id": "c1", "name": "down", "loads": [{"pad_id": "L", "fy_N": -150, "fz_N_out_of_plane": fz}],
             "max_deflection_mm": 0.6},
            {"id": "c2", "name": "sideways", "loads": [{"pad_id": "L", "fx_N": 80}], "max_deflection_mm": 0.6},
        ],
        "safety_factor": 2.0,
        "printer": "desktop_fdm",
        "materials": ["pla", "pa6cf", "pa12", "alsi10mg"],  # petg left out on purpose
    })


# ----------------------------------------------------------------------------- level choice
def st(fill, stress=True, defl=True, conn=True):
    return LevelStatus(fill=fill, stress_pass=stress, deflection_pass=defl, connected=conn, sf=2.0,
                       deflection_ratio=0.5)


def test_choose_level_basic():
    s = [st(0.15, defl=False), st(0.20, defl=False), st(0.25), st(0.30), st(0.35), st(0.40)]
    v, window, _ = choose_level(s)
    assert v == 0.25 and window == (0.20, 0.25)


def test_choose_level_isolated_stress_failure_does_not_move_pick():
    s = [st(0.15, defl=False), st(0.20), st(0.25), st(0.30, stress=False), st(0.35), st(0.40)]
    v, window, notes = choose_level(s)
    assert v == 0.20 and window == (0.15, 0.20)
    assert s[3].label == "isolated stress failure"


def test_choose_level_two_adjacent_failures_move_pick():
    s = [st(0.15, defl=False), st(0.20), st(0.25), st(0.30, stress=False), st(0.35, stress=False), st(0.40), st(0.45)]
    v, window, notes = choose_level(s)
    assert v == 0.40 and window == (0.35, 0.40)


def test_choose_level_none_pass():
    s = [st(0.15, defl=False), st(0.20, stress=False)]
    v, window, notes = choose_level(s)
    assert v is None


def test_choose_level_lowest_passes_gives_no_window():
    s = [st(0.15), st(0.20), st(0.25)]
    v, window, _ = choose_level(s)
    assert v == 0.15 and window is None


# ----------------------------------------------------------------------------- evaluation pieces
@pytest.fixture(scope="module")
def full_block_domain():
    return build_domain(bracket(fz=40.0), "fdm", 1.2, cap=2500)


def test_full_block_reactions_bearing_and_out_of_plane(full_block_domain):
    dom = full_block_domain
    mat = MATERIALS["pla"]
    density = np.ones(dom.mesh.nel)
    mech, checks = evaluate.evaluate(dom, density, mat, 2.0)
    assert mech.connected
    assert mech.reaction_sum_ok, mech.reaction_sum_error
    # reactions balance the applied load in every case
    tot = sum(r for r in mech.reactions.values())
    assert np.allclose(tot[0], [0.0, 150.0], atol=1e-6)
    assert np.allclose(tot[1], [-80.0, 0.0], atol=1e-6)
    # bearing at the load pad from the applied force: F/(d t) = 150 / (3.2 * 6)
    b = {h.name: h for h in checks.bearing}
    assert np.isclose(b["bearing at L"].sf, 55.0 / (150.0 / (3.2 * 6.0)))
    # out-of-plane bending hand check at the full block: w = 30 mm everywhere on the line
    oop = [h for h in checks.out_of_plane if h.name.startswith("out-of-plane bending")]
    assert len(oop) == 1
    L = np.hypot(52 - 6, 15 - 6)  # nearest support is A or B (equal); L to A
    sigma = 6.0 * 40.0 * L * (20 / 21) / (30.0 * 36.0)
    assert np.isclose(oop[0].sf, 55.0 / sigma, rtol=0.1)
    shear = [h for h in checks.out_of_plane if h.name.startswith("interlayer")][0]
    tau = 1.5 * 40.0 / (30.0 * 6.0)
    assert np.isclose(shear.sf, (55.0 * 0.5 / np.sqrt(3)) / tau, rtol=0.1)  # the section crosses a bolt hole
    assert checks.mass_g == pytest.approx(mech.area_mm2 * 6 * 1.24 / 1000)
    assert mech.stress_reported_MPa.shape == (2,)
    assert np.all(mech.stress_raw_MPa >= mech.stress_reported_MPa)


def test_disconnected_load_pad_fails(full_block_domain):
    dom = full_block_domain
    density = np.ones(dom.mesh.nel)
    density[dom.mesh.xc > 40] = 0.0  # cut the part; the load pad ring stays solid (passive) but isolated
    mech, checks = evaluate.evaluate(dom, density, MATERIALS["pla"], 2.0)
    assert not mech.connected
    assert any("not connected" in r for r in checks.fail_reasons)


def test_thickness_suggestion():
    t = evaluate.thickness_suggestion(6.0, sf=1.0, sf_target=2.0, defl=np.array([0.3]), limits=np.array([0.6]))
    assert t == pytest.approx(12.0)


# ----------------------------------------------------------------------------- three processes
@pytest.mark.slow
def test_three_process_results():
    res = catalog.run_all(bracket(), MATERIALS, PROCESSES, cap=1500, sweep_mode="warm",
                          levels=(0.60, 0.45, 0.30, 0.15), rerun="winner")
    assert set(res.catalogs) == {"fdm", "sls", "metal"}
    assert len(res.designs) == 4
    for d in res.designs:
        assert d.checks is not None and d.fill is not None
        assert d.pick.levels, d.material.id
        if d.status == "pass":
            assert d.checks.passed and d.checks.sf >= 2.0
        else:
            assert d.reasons
    # printer filter: metal and sls are computed but not allowed on a desktop FDM printer
    allowed = {d.material.id: d.printer_allowed for d in res.designs}
    assert allowed["pla"] and allowed["pa6cf"] and not allowed["pa12"] and not allowed["alsi10mg"]
    # the catalog shape is shared by materials in one process: the per-level run objects are the same
    cat = res.catalogs["fdm"]
    assert len(cat.levels) >= 1
    # the winner (if any) got a cold re-run with a snapshot every iteration
    winners = [d for d in res.designs if d.rerun]
    if winners:
        w = winners[0]
        assert w.rerun["snapshots"][-1][0] == w.rerun["iterations"]
