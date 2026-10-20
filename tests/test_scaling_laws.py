"""Spec 13.5: doubling E halves deflection and leaves stress unchanged (to 1e-6). Proves section 6.4."""

from morphic import config
from morphic.validation import scaling_law_check


def test_doubling_E_halves_deflection_and_keeps_stress():
    r = scaling_law_check()
    assert r["deflection_ratio_error"] < config.VALIDATION_TOL_SCALING, r
    assert r["stress_ratio_error"] < config.VALIDATION_TOL_SCALING, r
