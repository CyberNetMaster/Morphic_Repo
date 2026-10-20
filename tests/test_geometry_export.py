"""S8 acceptance: watertight STL, volume = area x thickness within 1%, and re-check numbers."""

import numpy as np
import pytest
import trimesh

from morphic import geometry
from morphic.baseline import strut_density
from morphic.domain import build_domain
from tests.test_catalog import MATERIALS, bracket


@pytest.fixture(scope="module")
def dom():
    return build_domain(bracket(), "fdm", 1.2, cap=3000)


@pytest.fixture(scope="module")
def geom(dom):
    return geometry.build_geometry(dom, strut_density(dom, 7.0))


def test_watertight_and_volume(geom, dom):
    assert geom.watertight
    assert geom.volume_error < 0.01
    assert abs(geom.volume_mm3 - geom.area_mm2 * 6.0) / geom.volume_mm3 < 0.01
    assert geom.max_smoothing_move_mm <= 0.5 * dom.mesh.h + 1e-9
    # the exact pad holes are present as interiors somewhere in the shape
    n_holes = sum(len(p.interiors) for p in geom.shape.geoms)
    assert n_holes >= 3


def test_exports(geom, dom, tmp_path):
    out = geometry.export_all(geom, tmp_path / "part", dom)
    m = trimesh.load(str(out["stl"]))
    assert m.is_watertight
    assert abs(m.volume - geom.volume_mm3) / geom.volume_mm3 < 1e-6
    svg = out["svg"].read_text(encoding="utf-8")
    assert "<path" in svg and "mm" in svg
    import ezdxf

    doc = ezdxf.readfile(str(out["dxf"]))
    assert sum(1 for _ in doc.modelspace().query("LWPOLYLINE")) >= 4


def test_smoothed_recheck_matches_grid_within_reason(geom, dom):
    from morphic import evaluate

    m = MATERIALS["pa6cf"]
    frac, mech, checks = geometry.smoothed_recheck(dom, geom, m, 2.0)
    assert frac.min() >= 0 and frac.max() <= 1
    # the rasterized area matches the polygon area closely
    assert abs(frac.sum() * dom.mesh.h ** 2 - geom.area_mm2) / geom.area_mm2 < 0.02
    mech0, checks0 = evaluate.evaluate(dom, strut_density(dom, 7.0), m, 2.0)
    assert mech.connected
    # the smoothed shape carries the load about as well as the grid shape
    assert np.allclose(mech.deflection_mm, mech0.deflection_mm, rtol=0.25)
    assert checks.mass_g == pytest.approx(geom.area_mm2 * 6 * 1.17 / 1000, rel=0.02)
    assert checks.sf > 0 and np.isfinite(checks.sf)
