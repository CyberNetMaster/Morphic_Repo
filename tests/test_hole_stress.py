"""Spec 13.4: plate with a central hole in tension, with and without nodal recovery.

Target: the finite-width stress concentration factor from Pilkey, W. D., Peterson's
Stress Concentration Factors, Chart 4.1 (circular hole in a finite-width element in
tension, Howland 1929-30): K_tn = 3.000 - 3.140 x + 3.667 x^2 - 1.527 x^3, x = d/W,
net section, valid for d/W <= 0.5; gross factor K_tg = K_tn / (1 - d/W). At d/W = 0.1
the gross factor is 3.02, within 1% of the infinite-plate value 3.0.

"With recovery" is the maximum recovered nodal von Mises over the hole boundary,
the number production uses for the safety factor (spec 13.4, decided 2026-10-20).

Pass rules:
- recovered error < element-centre error at every mesh
- recovered error < 5% at 16 elements per radius
- element check < 5% at 8 elements per radius
The recovered error at 8 elements per radius is the live-mesh error in the Limits note.
"""

import pytest

from morphic.validation import hole_stress_check, kt_finite_width

MESHES = (8, 16, 32)


@pytest.fixture(scope="module")
def results():
    return {n: hole_stress_check(n) for n in MESHES}


def test_kt_value_near_three():
    kt = kt_finite_width(0.1)
    assert abs(kt["Ktg"] - 3.0) / 3.0 < 0.02


def test_recovery_beats_element_centre_at_every_mesh(results):
    for n, r in results.items():
        assert r["error_with_recovery"] < r["error_without_recovery"], (n, r)


def test_element_check_at_8_per_radius(results):
    assert results[8]["element_check_error"] < 0.05, results[8]


def test_recovered_error_below_5pct_at_16_per_radius(results):
    assert results[16]["error_with_recovery"] < 0.05, results[16]


def test_live_mesh_error_is_reported(results):
    # about 6% at 8 elements per radius; it goes into the Limits note
    assert 0.0 < results[8]["error_with_recovery"] < 0.10, results[8]
