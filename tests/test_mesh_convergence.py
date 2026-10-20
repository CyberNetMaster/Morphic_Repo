"""Spec 13.2: mesh refinement 2, 4, 8, 16, 32 elements through the depth. Error must shrink steadily."""

import numpy as np

from morphic.validation import mesh_refinement


def test_errors_shrink_with_refinement():
    rows = mesh_refinement((2, 4, 8, 16, 32))
    d_err = np.array([r["delta_error"] for r in rows])
    s_err = np.array([r["sigma_error"] for r in rows])
    assert np.all(np.diff(d_err) < 0), d_err
    assert np.all(np.diff(s_err) < 0), s_err
    assert d_err[-1] < 0.01 and s_err[-1] < 0.01
