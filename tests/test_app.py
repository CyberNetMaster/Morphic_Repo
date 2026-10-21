"""S11: the app's data layer and images work on the cached demo parts, and the app script runs
headless without an exception (Streamlit's AppTest)."""

from __future__ import annotations

import numpy as np
import pytest

from app import data, maps, theme, ui
from morphic.precompute import CACHE_DIR

PARTS = [s for s in data.DEMOS.values() if (CACHE_DIR / s / "results.json").exists()]
pytestmark = pytest.mark.skipif(not PARTS, reason="cache not built yet (run `morphic precompute`)")


def test_theme_css_has_both_modes():
    for dark in (False, True):
        css = theme.css(dark)
        assert "<style>" in css and theme.ACCENT in css and theme.FONT_SANS.split(",")[0] in css


def test_match_demo_and_estimate():
    for stem in PARTS:
        p = data.demo_problem(stem)
        assert data.match_demo(p) == stem
        est = data.estimate_runtime(p, quick=False)
        assert est["seconds"] > 0 and est["rows"]
        q = data.estimate_runtime(p, quick=True)
        assert q["seconds"] < est["seconds"] and len(q["rows"]) == 1


def test_images_and_template_from_cache():
    r = data.load_results(CACHE_DIR / PARTS[0])
    dens = data.load_npz(CACHE_DIR / PARTS[0], "densities.npz")
    util = data.load_npz(CACHE_DIR / PARTS[0], "utilization.npz")
    win = r["ranking"]["winner"]
    d = next(x for x in r["designs"] if x["material"] == win)
    nelx, nely = r["catalogs"][d["process"]]["mesh"]
    png = maps.density_png(dens[f"design/{win}"], nelx, nely, True)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    u = util[win]
    worst = np.nanmax(np.where(np.isfinite(u), u, -np.inf), axis=0)
    worst[~np.isfinite(worst)] = np.nan
    assert maps.utilization_png(worst, nelx, nely)[:4] == b"\x89PNG"
    text = data.template_explanation(r)
    assert win in text and f"{d['checks']['mass_g']:.1f} g" in text
    fig = maps.pareto_chart(r["ranking"]["pareto"], True, "material cost only")
    assert fig.data
    fig = maps.problem_drawing(data.demo_problem(PARTS[0]))
    assert fig.layout.shapes


def test_ui_pieces():
    assert "mx-pill" in ui.pill("Lightest", "win")
    assert "<svg" in ui.gauge(2.9, 2.0, "safety factor", "2.9 vs 2.0", True)
    assert ui.fmt(float("inf")) == "∞" and ui.pct(0.386) == "39%"


@pytest.mark.parametrize("state", [{}, {"demo": PARTS[0], "step": "1"}, {"demo": PARTS[0], "step": "2"},
                                   {"demo": PARTS[0], "step": "3"}, {"tab": "validation"}])
def test_app_runs_headless(state):
    from streamlit.testing.v1 import AppTest

    from pathlib import Path

    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"), default_timeout=120)
    at.query_params.update(state)
    at.run()
    assert not at.exception, at.exception
