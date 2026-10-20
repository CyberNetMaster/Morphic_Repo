"""Spec 13.1: cantilever beam vs. beam theory at the validation mesh (20 elements through the depth)."""

from morphic import config
from morphic.validation import cantilever_check


def test_cantilever_deflection_and_stress_at_validation_mesh():
    r = cantilever_check(20)
    assert r["elements_through_depth"] == 20
    assert r["delta_error"] < config.VALIDATION_TOL_BEAM, r
    assert r["sigma_error"] < config.VALIDATION_TOL_BEAM, r
    # the element-centre value of the top row against M y / I at the centre height
    assert r["sigma_centre_error"] < config.VALIDATION_TOL_BEAM, r
