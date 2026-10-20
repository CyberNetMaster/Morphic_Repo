"""S7 acceptance: unit tests for the ranking, badges, Pareto data, funnel, and each edge case in spec section 8."""

import numpy as np
import pytest

from morphic import rank
from morphic.baseline import BaselineResult, full_block_mass, strut_baseline, strut_density
from morphic.catalog import Design, LevelStatus, MaterialPick, RunResult
from morphic.domain import build_domain
from morphic.evaluate import Checks, HandCheck
from morphic.materials import Citation, Material, Process
from tests.test_catalog import MATERIALS, PROCESSES, bracket


def checks(material, mass, sf=3.0, defl=(0.3, 0.1), passed=True, oop_fail=False, bearing_fail=False):
    oop = [HandCheck("out-of-plane bending (down)", not oop_fail, 1.0 if oop_fail else 5.0, "")]
    brg = [HandCheck("bearing at L", not bearing_fail, 1.0 if bearing_fail else 6.0, "", suggestion="bigger pin")]
    reasons = []
    if not passed:
        reasons.append("safety factor 1.00 < 2")
    if oop_fail:
        reasons.append("out-of-plane bending (down): SF 1.00 < 2")
    if bearing_fail:
        reasons.append("bearing at L: SF 1.00 < 2")
    return Checks(material_id=material.id, sf_target=2.0, passed=passed and not oop_fail and not bearing_fail,
                  passed_in_plane=passed, sf=sf, sf_raw=sf * 0.8, stress_reported_MPa=10.0, stress_raw_MPa=12.0,
                  stress_pass=passed, deflection_mm=np.array(defl), deflection_limit_mm=np.array([0.6, 0.6]),
                  deflection_pass=True, mass_g=mass, out_of_plane=oop, bearing=brg, fail_reasons=reasons, notes=[])


def design(mid, mass, fill=0.3, **kw):
    m = MATERIALS[mid]
    proc = PROCESSES[m.process]
    c = checks(m, mass, **kw)
    status = "pass" if c.passed else "fail"
    pick = MaterialPick(material_id=mid, status=status, levels=[
        LevelStatus(0.15, False, False, True, 1.0, 2.0), LevelStatus(0.30, True, True, True, 3.0, 0.5),
        LevelStatus(0.45, True, True, True, 4.0, 0.3)], v_pick=0.30, v_final=fill, window=(0.15, 0.30))
    return Design(material=m, process=proc, domain=None, fill=fill, density=None, mech=None, checks=c, pick=pick,
                  status=status, reasons=c.fail_reasons, printer_allowed=True)


def run_result(designs, printer="desktop_fdm"):
    p = bracket()
    p = p.model_copy(update={"printer": printer})
    for d in designs:
        d.printer_allowed = printer == "any" or PROCESSES[d.material.process].printer_group == printer
    return RunResult(problem=p, cap=1000, sweep_mode="warm", catalogs={}, designs=designs, seconds=1.0)


def test_ranking_by_mass_badges_and_filter():
    ds = [design("pla", 6.0), design("pa6cf", 3.0), design("pa12", 2.5), design("alsi10mg", 5.0)]
    res = run_result(ds, "desktop_fdm")
    out = rank.rank_designs(res, baselines={})
    cards = {c.design.material.id: c for c in out.cards}
    assert cards["pa6cf"].rank == 1 and "Lightest" in cards["pa6cf"].badges
    assert cards["pla"].rank == 2
    assert cards["pa12"].state == "filtered" and "SLS" in cards["pa12"].reason
    assert cards["alsi10mg"].state == "filtered"
    # cheapest material among passing, allowed: pla 6 g * 29.99/kg = 0.18 vs pa6cf 3 g * 52.99/kg = 0.16
    assert "Cheapest material" in cards["pa6cf"].badges
    assert out.funnel["printable"] == 2 and out.funnel["ranked"] == 2
    assert out.winner.material.id == "pa6cf"


def test_cost_never_ranks():
    ds = [design("pla", 3.0), design("pa6cf", 3.5)]  # pla lighter and cheaper
    out = rank.rank_designs(run_result(ds), baselines={})
    assert out.winner.material.id == "pla"
    ds = [design("pla", 4.0), design("pa6cf", 3.5)]  # pa6cf lighter but costlier
    out = rank.rank_designs(run_result(ds), baselines={})
    assert out.winner.material.id == "pa6cf"
    cards = {c.design.material.id: c for c in out.cards}
    assert "Cheapest material" in cards["pla"].badges


def test_pareto_one_point_per_material_and_front():
    ds = [design("pla", 6.0), design("pa6cf", 3.0), design("petg", 7.0, passed=False)]
    out = rank.rank_designs(run_result(ds), baselines={})
    assert len(out.pareto) == 3
    pts = {p.material_id: p for p in out.pareto}
    assert pts["petg"].state == "failed" and not pts["petg"].on_front
    assert pts["pa6cf"].on_front  # lightest
    # pla is heavier and costs more per part than pa6cf (6 g * 29.99 vs 3 g * 52.99): dominated
    assert not pts["pla"].on_front


def test_no_material_passes_gives_numbers_and_fixes():
    ds = [design("pla", 6.0, sf=1.0, defl=(0.9, 0.2), passed=False), design("pa6cf", 3.0, sf=1.5, passed=False)]
    out = rank.rank_designs(run_result(ds), baselines={})
    assert out.winner is None
    msg = " ".join(out.messages)
    assert "No material" in msg
    # thickness suggestion from scaling: pla needs max(2/1, 0.9/0.6) = 2x -> 12 mm; pa6cf 2/1.5 -> 8 mm
    assert "12.0 mm" in msg and "8.0 mm" in msg


def test_all_allowed_fail_but_filtered_passes():
    ds = [design("pla", 6.0, sf=1.0, passed=False), design("alsi10mg", 5.0)]
    out = rank.rank_designs(run_result(ds, "desktop_fdm"), baselines={})
    assert out.winner is None
    assert any("Only alsi10mg" in m and "metal" in m for m in out.messages)


def test_out_of_plane_and_bearing_fail_are_shown_not_ranked():
    ds = [design("pla", 6.0, oop_fail=True), design("pa6cf", 3.0, bearing_fail=True), design("petg", 7.0)]
    out = rank.rank_designs(run_result(ds), baselines={})
    cards = {c.design.material.id: c for c in out.cards}
    assert cards["pla"].state == "failed" and "Out-of-plane: FAIL" in cards["pla"].reason
    assert cards["pa6cf"].state == "failed" and "Bearing: FAIL" in cards["pa6cf"].reason
    assert cards["petg"].rank == 1


def test_isolated_stress_failure_counted_in_funnel():
    d = design("pla", 6.0)
    d.pick.levels[2].label = "isolated stress failure"
    d.pick.levels[2].stress_pass = False
    out = rank.rank_designs(run_result([d]), baselines={})
    assert out.funnel["isolated_stress_failures"] == 1


def test_loose_limits_message():
    d = design("pla", 6.0)
    d.pick.status = "loose"
    d.pick.notes.append("passes at the lowest level computed; limits are loose")
    res = run_result([d])
    out = rank.rank_designs(res, baselines={})
    assert any("loose" in m for m in out.messages)


def test_not_converged_note_and_rerun_note():
    d = design("pla", 6.0)
    d.converged = False
    d.notes.append("not fully converged")
    d.rerun = {"replaced": False, "note": "animation shows an independent run at the same fill level"}
    out = rank.rank_designs(run_result([d]), baselines={})
    c = out.cards[0]
    assert "not fully converged" in c.design.notes
    assert c.state == "ranked"


# ----------------------------------------------------------------------------- baselines
@pytest.fixture(scope="module")
def dom():
    return build_domain(bracket(), "fdm", 1.2, cap=2000)


def test_full_block_and_strut_geometry(dom):
    m = MATERIALS["pa6cf"]
    block = full_block_mass(dom, m)
    expected_area = (~dom.passive_void).sum() * dom.mesh.h ** 2
    assert block == pytest.approx(expected_area * 6 * 1.17 / 1000)
    dens = strut_density(dom, 6.0)
    # struts from L to both supports A and B, plus the pad rings; far less than the block
    assert 0.1 < dens.mean() < 0.6
    assert dens[dom.passive_solid].min() == 1.0 and dens[dom.passive_void].max() == 0.0


def test_strut_baseline_sized_to_limits(dom):
    m = MATERIALS["pa6cf"]
    b = strut_baseline(dom, m, 2.0, steps=6)
    assert b.strut_passed and b.strut_width_mm is not None
    assert b.checks.passed_in_plane
    assert b.mass_strut_g < b.mass_block_g
    assert b.weight_saved_vs_strut(b.mass_strut_g * 0.5) == pytest.approx(0.5)
    assert set(b.struts) == {("L", "A"), ("L", "B")}


def test_strut_baseline_cannot_meet_limits(dom):
    weak = Material(id="weak", name="weak", process="fdm", E=10.0, nu=0.33, strength_xy=0.5, strength_kind="tensile",
                    density=1.0, strength_z=0.5)
    b = strut_baseline(dom, weak, 2.0, steps=3)
    assert not b.strut_passed and b.mass_strut_g is None and b.mass_block_g > 0
