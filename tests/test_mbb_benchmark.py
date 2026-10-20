"""Spec 13.3: the 88-line paper's MBB case in paper mode.

Andreassen et al. (2011), section 3.4, Fig. 3 bottom-left: top88(60,20,0.5,3,2.4,2)
(density filter), published compliance 233.71. Pass if within 2%.
"""

import numpy as np

from morphic import config
from morphic.validation import MBB_PUBLISHED, mbb_check


def test_mbb_compliance_matches_published():
    r = mbb_check()
    assert r["converged"], r
    assert r["error"] < config.VALIDATION_TOL_MBB, r
    assert abs(r["volume"] - MBB_PUBLISHED["volfrac"]) < 1e-3
    g = r["density_grid"]
    # layout features of the published figure: solid top chord and bottom-right support region
    assert g[:, -1].mean() > 0.6  # top row mostly solid (compression chord)
    assert g[-5:, :3].mean() > 0.8  # bottom-right corner solid (support)
    assert np.mean((g > 0.2) & (g < 0.8)) < 0.35  # mostly black-and-white
