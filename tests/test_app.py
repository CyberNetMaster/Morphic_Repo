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


def test_readout_and_load_case_pill():
    r = ui.readout("safety factor", "2", "", "required", frac=0.5, scale=("0", "4"))
    assert "mx-readout" in r and r.count("<i ") == theme.READOUT_TICKS
    assert r.count('class="on') == theme.READOUT_TICKS // 2 and r.count("tip") == 1 and "mx-scale" in r
    assert "mx-ticks" not in ui.readout("run time", "instant")
    pill = ui.lc_pill("Hard landing · 80 N", theme.LOAD_CASE_COLORS[0])
    assert "mx-lc" in pill and theme.LOAD_CASE_COLORS[0] in pill and "rgba(255,90,78,0.14)" in pill


def test_dark_everywhere():
    import tomllib
    from pathlib import Path

    cfg = tomllib.loads((Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert cfg["theme"]["base"] == "dark"
    assert cfg["theme"]["backgroundColor"] == theme.DARK["bg"] and cfg["theme"]["primaryColor"] == theme.ACCENT
    assert cfg["theme"]["secondaryBackgroundColor"] == theme.DARK["card"] and cfg["theme"]["textColor"] == theme.DARK["text"]
    # the data editor is the one Streamlit widget that draws lines: they take the theme's raised and inset tones
    assert cfg["theme"]["dataframeBorderColor"] == theme.DARK["raised"] == cfg["theme"]["borderColor"]
    assert cfg["theme"]["dataframeHeaderBackgroundColor"] == theme.DARK["card_alt"]
    assert cfg["theme"]["baseRadius"] == f"{theme.RADIUS_MD}px" and cfg["theme"]["showWidgetBorder"] is False
    css = theme.css(True)
    assert theme.DARK["bg"] in css and theme.DARK["amber_text"] in css and "#B7791F" not in css
    brief = (Path(__file__).resolve().parents[1] / "design-refs" / "brief.md").read_text(encoding="utf-8")
    assert "Dark everywhere" in brief and "Near-white is used" not in brief


def test_demo_preview_matches_cache():
    for stem in PARTS:
        pv = data.demo_preview(stem)
        r = data.load_results(CACHE_DIR / stem)
        win = r["ranking"]["winner"]
        d = next(x for x in r["designs"] if x["material"] == win)
        c = next(x for x in r["ranking"]["cards"] if x["material"] == win)
        assert pv["material"] == win and pv["process"] == d["process"]
        assert pv["mass_g"] == d["checks"]["mass_g"] and pv["saved_vs_strut"] == c["weight_saved_vs_strut"]
        dens = data.load_npz(CACHE_DIR / stem, "densities.npz")
        assert pv["density_key"] in dens and dens[pv["density_key"]].size == pv["nelx"] * pv["nely"]
    assert data.demo_preview("no_such_part") is None


def test_dark_drawing_glows():
    p = data.demo_problem(PARTS[0])
    fig = maps.problem_drawing(p, dark=True)
    glows = [t for t in fig.data if t.hoverinfo == "skip"]
    assert len(glows) == len(p.pads) * len(theme.PAD_GLOW_RINGS)
    arrows = [a for a in fig.layout.annotations if a.showarrow]
    crisp = [a for a in arrows if a.arrowwidth == 2.2]  # the load arrows
    soft = [a for a in arrows if a.arrowwidth == theme.ARROW_GLOW_WIDTH and a.opacity == theme.ARROW_GLOW_OPACITY]
    assert crisp and len(soft) == len(crisp)  # one glow stroke under every load arrow
    light = maps.problem_drawing(p, dark=False)
    assert not [a for a in light.layout.annotations if a.opacity is not None and a.opacity < 1]


@pytest.mark.parametrize("state", [{}, {"demo": PARTS[0], "step": "1"}, {"demo": PARTS[0], "step": "2"},
                                   {"demo": PARTS[0], "step": "3"}, {"tab": "validation"}])
def test_app_runs_headless(state, monkeypatch):
    from streamlit.testing.v1 import AppTest

    from pathlib import Path
    import json
    from morphic import explain, llm

    # Exercise the live explanation path without external requests in the suite.
    monkeypatch.setattr(llm, "complete_json", lambda system, user:
                        {"explanation": explain.template_explanation(json.loads(user))})

    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"), default_timeout=120)
    at.query_params.update(state)
    at.run()
    assert not at.exception, at.exception


def test_pareto_labels_do_not_overlap():
    for stem in PARTS:
        r = data.load_results(CACHE_DIR / stem)
        fig = maps.pareto_chart(r["ranking"]["pareto"], True, "material cost only", winner=r["ranking"]["winner"])
        labelled = [t for t in fig.data if t.mode == "markers+text"]
        assert labelled and all(t.textposition in {slot[0] for slot in maps._LABEL_SLOTS} for t in labelled)
        halo = [t for t in fig.data if t.mode == "markers" and t.hoverinfo == "skip"]
        assert len(halo) == len(theme.POINT_HALO_RINGS)  # the winner's halo
        assert fig.layout.xaxis.range is not None and fig.layout.yaxis.range[0] >= 0
    # the placement itself: four points on the same spot still get four different slots
    assert len(set(maps.place_labels([(100, 100, "aaaa", 6)] * 4, 400, 300))) == 4
    # a lone point keeps the preferred slot
    assert maps.place_labels([(200, 150, "pa6cf", 6)], 400, 300) == ["top center"]


def test_pad_labels_avoid_support_symbols_and_arrows():
    assert maps.pad_label_side("pin", set()) == "above"
    assert maps.pad_label_side("slide_x", set()) == "above"
    assert maps.pad_label_side("slide_y", set()) == "below"
    assert maps.pad_label_side(None, set()) == "below"
    assert maps.pad_label_side("pin", {"above"}) == "right"
    assert maps.pad_label_side(None, {"below"}) == "above"
    for stem in PARTS:
        p = data.demo_problem(stem)
        fig = maps.problem_drawing(p)
        ids = {q.id for q in p.pads}
        names = {a.text: a for a in fig.layout.annotations if a.text in ids}
        assert set(names) == ids
        for sp in p.supports:
            if sp.type in ("pin", "slide_x"):
                assert names[sp.pad_id].yanchor == "bottom"  # the name sits above the pad, clear of the symbol
        # every arrow tail (and so every force label) is inside the axes
        xr, yr = fig.layout.xaxis.range, fig.layout.yaxis.range
        tails = [(a.ax, a.ay) for a in fig.layout.annotations if a.showarrow and a.axref == "x"]
        assert tails and all(xr[0] <= ax <= xr[1] and yr[0] <= ay <= yr[1] for ax, ay in tails)
        forces = [a for a in fig.layout.annotations if a.text and a.text.endswith(" N")]
        assert forces and all(xr[0] <= a.x <= xr[1] and yr[0] <= a.y <= yr[1] for a in forces)


def test_polish_rules_in_css_and_no_deprecated_calls():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py").read_text(encoding="utf-8")
    assert "use_container_width" not in src
    css = theme.css(True)
    assert ".mx-table th, .mx-table td { border: 0 !important" in css  # no cell grid on the HTML tables
    assert f"scale({theme.PRESS_SCALE})" in css and f"{theme.PRESS_MS}ms" in css and "@media (hover: hover)" in css
    assert "prefers-reduced-motion" in css and "mxfade" in css
    assert "transition: all" not in css and "transition-all" not in css
    assert "mx-top" in ui.eyebrow("13.3", top=True) and "mx-top" not in ui.eyebrow("13.1")


def test_geist_is_bundled_and_inlined():
    import tomllib
    from pathlib import Path

    for name in theme.FONT_FILES.values():
        assert (theme.FONT_DIR / name).stat().st_size > 10_000
    assert "SIL Open Font License" in (theme.FONT_DIR / "LICENSE.txt").read_text(encoding="utf-8")
    css = theme.font_face_css()
    assert css.count("@font-face") == len(theme.FONT_FILES) == css.count("data:font/woff2;base64,")
    assert "http" not in css  # no font service, ever
    assert theme.FONT_SANS.startswith("Geist") and theme.FONT_MONO.startswith("'Geist Mono'")
    cfg = tomllib.loads((Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert cfg["theme"]["font"] == theme.FONT_SANS and cfg["theme"]["codeFont"] == theme.FONT_MONO
    main = theme.css(True)
    assert f"font-size: {theme.TEXT_DISPLAY}px" in main and f"letter-spacing: {theme.TRACK_DISPLAY}" in main
    assert f"letter-spacing: {theme.EYEBROW_TRACKING}" in main and f"line-height: {theme.LINE_BODY}" in main
    assert "font-variant-numeric: tabular-nums" in main and ".mx-eyebrow::before" in main


def test_numbers_use_the_mono_face():
    assert "mx-num" in ui.pill("-39% vs strut") and "mx-num" in ui.pill("#1 · passes")
    assert "mx-num" not in ui.pill("passes") and "mx-num" not in ui.pill("Lightest")
    t = ui.table(["q", "v"], [["tip deflection", "18.27 mm"], ["$0.21", "yes"], ["—", "<b>0.3</b> of 1 mm"]])
    assert t.count('<td class="mx-num">') == 3


def test_describe_pieces():
    f = ui.flow(["Check", "Generate", "Export"], 0, "What happens next")
    assert f.count('class="step') == 3 and f.count('class="step on"') == 1 and f.count('class="link"') == 2
    mark = ui.logomark()
    assert "<svg" in mark and theme.ACCENT in mark and theme.ACCENT_LIGHT in mark
    note = ui.footnote_html("a < b")
    assert "mx-footnote" in note and "&lt;" in note and "<svg" in note
    assert "mx-or" in ui.or_divider()


def test_example_pill_fills_the_description():
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"), default_timeout=120)
    at.run()
    at.button(key=f"ex_{PARTS[0]}").click().run()
    assert not at.exception, at.exception
    assert at.session_state["text"] == data.demo_text(PARTS[0]) and at.session_state["step"] == 0


def test_force_labels_plan_and_saved_parse():
    from morphic import parse

    assert maps.sig(42271.1) == "42,300" and maps.sig(32) == "32" and maps.sig(0.5) == "0.5"
    assert maps.sig(35600) == "35,600" and maps.sig(0) == "0"
    p = data.demo_problem("drone_arm")
    fig = maps.problem_drawing(p)
    xr, yr = fig.layout.xaxis.range, fig.layout.yaxis.range
    motor = next(a for a in fig.layout.annotations if a.text == "motor")
    assert motor.xanchor == "left" and motor.x + 12 <= xr[1]  # room for the name beyond the ring, never clipped
    forces = {a.text: a for a in fig.layout.annotations if a.text and a.text.endswith(" N")}
    assert set(forces) == {"32 N", "50 N"}
    # the thrust arrow comes from below the part: its label sits beside the tail, clear of the dimension texts
    assert forces["32 N"].xanchor == "left" and forces["32 N"].yanchor == "middle"
    thick = next(a for a in fig.layout.annotations if a.text and a.text.startswith("thickness"))
    assert thick.xanchor == "center" and thick.x == p.design_space.width_mm / 2
    assert yr[0] <= -0.06 * 120 - 42 * (120 + 1.6 * 0.12 * 120) / 520  # room for both dimension lines
    bracket = maps.problem_drawing(data.demo_problem("aero_bracket"))
    assert {a.text for a in bracket.layout.annotations if a.text and a.text.endswith(" N")} == {"35,600 N", "37,800 N", "42,300 N"}
    # every demo text maps to its stem and loads a checked parse without the network
    for stem in data.DEMOS.values():
        assert data.match_demo_text(data.demo_text(stem)) == stem and data.saved_parse(stem) is not None
    assert data.match_demo_text("a bracket 120 mm long") is None and data.match_demo_text("") is None
    saved = data.saved_parse("drone_arm")
    assert parse.compare_problems(saved, data.demo_problem("drone_arm")) == [] and data.match_demo(saved) == "drone_arm"
    assert "wrap" in ui.pill("refinement stopped", "amber", wrap=True) and "wrap" not in ui.pill("passes", "pass")


def test_demo_text_loads_saved_parse_without_llm(monkeypatch):
    from pathlib import Path

    from streamlit.testing.v1 import AppTest
    from morphic import llm

    def no_call(*a, **k):
        raise AssertionError("the demo text must not call the LLM")

    monkeypatch.setattr(llm, "complete", no_call)
    monkeypatch.setattr(llm, "complete_json", no_call)
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"), default_timeout=120)
    at.run()
    at.button(key="ex_drone_arm").click().run()
    at.button(key="read_btn").click().run()
    assert not at.exception, at.exception
    assert at.session_state["step"] == 1 and at.session_state["parse_source"] == "saved parse"
    assert data.match_demo(at.session_state["problem"]) == "drone_arm"
    assert any("saved parse" in m.value for m in at.markdown)

