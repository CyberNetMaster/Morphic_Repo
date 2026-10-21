"""Morphic app (spec section 11): Describe -> Check -> Compare -> Export, plus the Validation tab.

Run: uv run streamlit run app/streamlit_app.py
Query parameters (for screenshots and the video): ?demo=rc_arm&step=2  or  ?tab=validation
"""

from __future__ import annotations

import base64
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import data, integration, maps, theme, ui  # noqa: E402
from morphic import config, explain, form as formmod, parse, sanity, validation  # noqa: E402
from morphic.materials import load_materials, load_processes  # noqa: E402
from morphic.problem import MATERIAL_IDS, PRINTERS, Problem, Provenance, problem_from_dict  # noqa: E402

st.set_page_config(page_title="Morphic", page_icon="◐", layout="wide", initial_sidebar_state="collapsed")

PRINTER_LABELS = {"any": "Any process", "desktop_fdm": "Desktop FDM printer", "sls_service": "SLS service",
                  "metal_service": "Metal printing service"}
FROM_TEXT = "From the text"
FIXED_NOTE = ("Static check only. Fatigue and impact toughness are not evaluated. Printed flat at 100% infill. "
              "See Limits.")
GROWTH_CAPTION = ("The update rule adds material where strain energy is high and removes it where it is low, "
                  "the same idea as bone remodeling (Wolff's law).")
LIMITS = [
    "Static check only. Fatigue and impact toughness are not evaluated.",
    "Printed flat at 100% infill. In-plane stresses run along the layers. If the part is printed standing up, "
    "in-plane stresses in the vertical direction would see the lower Z strength, and these numbers would not apply.",
    "Von Mises with one strength value is a simplification for plastics. PA6-CF is anisotropic within a layer: the XY "
    "datasheet value is along the bead direction, and strength across beads in the same layer is lower. The result "
    "assumes slicer perimeters follow the member direction.",
    "Stresses are recovered to the nodes (Gauss-point extrapolation, averaged over solid elements), so edge values "
    "are not under-read the way element-center values are. A small error remains at the production mesh; the hole "
    "check measures it and the Validation tab shows it. Stress peaks at sharp inner corners still depend on mesh "
    "size. Stress is reported at the stated mesh size, from the smoothed shape that is exported.",
    "2D plane stress. Out-of-plane loads get a hand check only.",
    "Pin bearing at every pad with a hole (load pads from the applied force, support pads from the FE reaction) is a "
    "hand check using the full strength (bearing allowables are often higher, so it errs on the safe side). Pin "
    "shear and edge tear-out are not checked.",
    "Mesh note: stress is reported at the mesh size printed on the card. Nodal recovery removes most of the edge "
    "under-read; the remaining error at the production mesh is measured by the hole check. Sharp inner corners have "
    "peaks that grow with mesh refinement; the smoothing step removes most inner corners, and the final numbers come "
    "from the smoothed shape. Stair-stepped boundaries on the grid add local noise, which the smoothed re-check "
    "(area fractions) reduces.",
]
S = st.session_state


# ----------------------------------------------------------------------------- shared
@st.cache_resource
def libs():
    return load_materials(), load_processes()


@st.cache_data(show_spinner=False)
def live_mesh_error() -> float:
    return validation.live_mesh_stress_error()


@st.cache_data(show_spinner=False)
def cached_results(folder: str) -> dict:
    return data.load_results(Path(folder))


@st.cache_data(show_spinner=False)
def cached_npz(folder: str, name: str) -> dict:
    return data.load_npz(Path(folder), name)


@st.cache_data(show_spinner=False, ttl=3600, max_entries=32)
def grounded_explanation(payload: str, provider: str, model: str):
    return explain.explain(json.loads(payload), use_llm=True)


@st.cache_data(show_spinner=False, max_entries=6)
def prepared_downloads(folder: str, signature: tuple):
    return integration.export_downloads(folder)


@st.cache_data(show_spinner=False)
def png_density(folder: str, key: str, nelx: int, nely: int, dark: bool, px: int) -> bytes:
    return maps.density_png(cached_npz(folder, "densities.npz")[key], nelx, nely, dark, px)


@st.cache_data(show_spinner=False)
def png_util(folder: str, mid: str, nelx: int, nely: int, px: int) -> bytes:
    u = cached_npz(folder, "utilization.npz")[mid]
    worst = np.nanmax(np.where(np.isfinite(u), u, -np.inf), axis=0)
    worst[~np.isfinite(worst)] = np.nan
    return maps.utilization_png(worst, nelx, nely, px)


@st.cache_data(show_spinner=False)
def png_frame(folder: str, process: str, index: int, nelx: int, nely: int, px: int) -> bytes:
    z = cached_npz(folder, f"rerun_{process}.npz")
    it = int(z["iterations"][index])
    return maps.density_png(z[f"it{it}"].astype(float) / 255.0, nelx, nely, True, px)


def img(png: bytes, style: str = "width:100%;display:block") -> str:
    return f'<img src="data:image/png;base64,{base64.b64encode(png).decode()}" style="{style}">'


def init_state() -> None:
    defaults = dict(tab="Design", step=0, text="", printer_choice=FROM_TEXT, quick=False, problem=None, form=None,
                    parse_fail=None, results=None, live=None, view3d=None, growth_play=False, growth_i=0,
                    qp_done=False, stage_view="Shape", agent_jobs={})
    for k, v in defaults.items():
        S.setdefault(k, v)


def apply_query_params() -> None:
    """?demo=<stem>&step=<n>&tab=validation: jump straight to a state (screenshots, video)."""
    if S.qp_done:
        return
    S.qp_done = True
    qp = st.query_params
    if qp.get("demo") in data.DEMOS.values():
        load_demo(qp["demo"])
        if (data.CACHE_DIR / qp["demo"] / "results.json").exists():
            S.results = cached_results(str(data.CACHE_DIR / qp["demo"]))
    if qp.get("step", "").isdigit():
        S.step = max(0, min(3, int(qp["step"])))
    if qp.get("tab", "").lower() == "validation":
        S.tab = "Validation"


def load_demo(stem: str) -> None:
    p = data.demo_problem(stem)
    S.text = data.demo_text(stem)
    S.problem, S.form, S.parse_fail, S.results, S.live = p, formmod.problem_to_form(p), None, None, None
    S.printer_choice = FROM_TEXT
    S.growth_i, S.growth_play, S.view3d = 0, False, None


def go(step: int) -> None:
    S.step = step
    st.rerun()


# ----------------------------------------------------------------------------- step 1: describe
def page_describe() -> None:
    ui.title("Describe your part",
             "Say where it is held, where the loads act, the size limits, and the limits on stress and bending. "
             "Morphic turns the text into a problem you check on a drawing before anything runs.")
    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(key="card_describe"):
            st.markdown(ui.eyebrow("Plain English"), unsafe_allow_html=True)
            S.text = st.text_area("Description", value=S.text, height=320, label_visibility="collapsed",
                                  placeholder="A bracket 120 mm long and 40 mm tall, 8 mm thick. Two M4 bolts hold "
                                              "the left end at (10, 10) and (10, 30). A 200 N downward load at (110, 20). "
                                              "Safety factor 2, deflection under 0.5 mm. Desktop FDM printer.")
            c1, c2 = st.columns([2, 1])
            with c1:
                S.printer_choice = st.selectbox("Printer", [FROM_TEXT] + list(PRINTERS),
                                                index=([FROM_TEXT] + list(PRINTERS)).index(S.printer_choice),
                                                format_func=lambda k: PRINTER_LABELS.get(k, k),
                                                help="The selector wins over the text if you change it.")
            with c2:
                S.quick = st.toggle("Quick mode", value=S.quick,
                                    help="One process, 10k elements, no refinement or re-run. About a minute.")
            if st.button("Read my description", type="primary", disabled=not S.text.strip(), key="read_btn"):
                read_description()
    with right:
        with st.container(key="card_examples"):
            st.markdown(ui.eyebrow("Demo parts") + '<div class="mx-sub" style="margin-bottom:12px">Three checked '
                        'problems with precomputed results. They load without the network.</div>',
                        unsafe_allow_html=True)
            for label, stem in data.DEMOS.items():
                if st.button(label, key=f"demo_{stem}", use_container_width=True):
                    load_demo(stem)
                    go(1)
        with st.container(key="card_how"):
            st.markdown(ui.eyebrow("What happens next") + """
<div class="mx-kv" style="margin-top:10px">
<span>1</span><span>The text becomes a structured problem. Defaults are marked in amber.</span>
<span>2</span><span>You check supports, loads and limits on a drawing and fix anything wrong.</span>
<span>3</span><span>Morphic optimizes a shape for six cited materials across FDM, SLS and metal.</span>
<span>4</span><span>Results rank by mass. Export STL, SVG and DXF.</span>
</div>""", unsafe_allow_html=True)


def read_description() -> None:
    materials, processes = libs()
    holder = st.empty()
    with st.spinner("Reading your description… if this takes too long, a manual form will open."):
        try:
            r = parse.parse_text(S.text, min_walls=[p.min_wall_mm for p in processes.values()],
                                 status=lambda s: holder.caption(s))
        except parse.ParseFailed as exc:
            S.parse_fail = str(exc)
            S.problem, S.form, S.results = None, formmod.blank_form(), None
            go(1)
            return
    p = r.problem
    if S.printer_choice != FROM_TEXT and S.printer_choice != p.printer:
        p.printer = S.printer_choice
        p.provenance["printer"] = Provenance(source="user", original_text="printer selector")
    S.problem, S.form, S.parse_fail, S.results = p, formmod.problem_to_form(p), None, None
    go(1)


# ----------------------------------------------------------------------------- step 2: check
_PATH = re.compile(r"([a-z_]+)(?:\[(\d+)\])?")


def _get_path(p: Problem, path: str):
    obj = p
    for name, idx in _PATH.findall(path):
        if not name:
            continue
        obj = getattr(obj, name)
        if idx:
            obj = obj[int(idx)]
    return obj


def _merge_provenance(old: Problem | None, new: Problem) -> Problem:
    """Keep the parser's provenance; a default the user changed becomes 'user'."""
    if old is None:
        return new
    prov = dict(old.provenance)
    for path, pv in old.provenance.items():
        if pv.source != "default":
            continue
        try:
            a, b = _get_path(old, path), _get_path(new, path)
        except (AttributeError, IndexError):
            continue
        if a != b:
            prov[path] = Provenance(source="user", original_text="edited on the check screen")
    new.provenance = prov
    new.notes, new.references = old.notes, old.references
    new.warnings = old.warnings
    return new


def _records(df: pd.DataFrame, drop: tuple = ()) -> list[dict]:
    out = []
    for rec in df.to_dict("records"):
        rec = {k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in rec.items() if k not in drop}
        if all(v in (None, "") for v in rec.values()):
            continue
        out.append(rec)
    return out


def _default_pill(p: Problem | None, path: str) -> str:
    if p is None:
        return ""
    pv = p.source_of(path)
    if pv.source == "default":
        return ui.pill("default", "amber") + (f'<span class="mx-note">{ui.esc(pv.original_text)}</span>' if pv.original_text else "")
    if pv.original_text:
        return f'<span class="mx-note">from the text: “{ui.esc(pv.original_text)}”</span>'
    return ""


def editors(p: Problem | None, f: dict) -> dict:
    """The editable values (spec 11, step 2). Returns the edited form dict."""
    st.markdown(ui.eyebrow("Part"), unsafe_allow_html=True)
    f["name"] = st.text_input("Name", value=f.get("name") or "", key="ed_name")
    c = st.columns(3)
    f["width_mm"] = c[0].number_input("Width (mm)", value=float(f["width_mm"] or 0.0), min_value=0.0, key="ed_w")
    f["height_mm"] = c[1].number_input("Height (mm)", value=float(f["height_mm"] or 0.0), min_value=0.0, key="ed_h")
    f["thickness_mm"] = c[2].number_input("Thickness (mm)", value=float(f["thickness_mm"]), min_value=0.0, key="ed_t")
    c[2].markdown(_default_pill(p, "thickness_mm"), unsafe_allow_html=True)
    c = st.columns(3)
    f["safety_factor"] = c[0].number_input("Safety factor", value=float(f["safety_factor"]), min_value=0.1, key="ed_sf")
    c[0].markdown(_default_pill(p, "safety_factor"), unsafe_allow_html=True)
    f["printer"] = c[1].selectbox("Printer", list(PRINTERS), index=list(PRINTERS).index(f["printer"]),
                                  format_func=lambda k: PRINTER_LABELS.get(k, k), key="ed_printer")
    c[1].markdown(_default_pill(p, "printer"), unsafe_allow_html=True)
    f["materials"] = c[2].multiselect("Materials", list(MATERIAL_IDS), default=list(f["materials"]), key="ed_mats")
    c[2].markdown(_default_pill(p, "materials"), unsafe_allow_html=True)

    prov = f.get("_provenance") or {}

    def note(path):
        v = prov.get(path) or {}
        return ("default: " if v.get("source") == "default" else "") + (v.get("original_text") or "")

    st.markdown(ui.eyebrow("Pads (supports and loads attach here)"), unsafe_allow_html=True)
    pads = pd.DataFrame(f["pads"] or [], columns=["id", "cx", "cy", "hole_r_mm", "ring_r_mm"])
    pads["hole"] = [note(f"pads[{i}].hole_r_mm") for i in range(len(pads))]
    pads["ring"] = [note(f"pads[{i}].ring_r_mm") for i in range(len(pads))]
    pads = st.data_editor(pads, num_rows="dynamic", key="ed_pads", use_container_width=True, hide_index=True,
                          column_config={"hole": st.column_config.TextColumn("hole source", disabled=True),
                                         "ring": st.column_config.TextColumn("ring source", disabled=True),
                                         "hole_r_mm": st.column_config.NumberColumn("hole r (mm)", help="0 = solid pad"),
                                         "ring_r_mm": st.column_config.NumberColumn("ring r (mm)")})
    f["pads"] = _records(pads, drop=("hole", "ring"))
    pad_ids = [r["id"] for r in f["pads"] if r.get("id")]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(ui.eyebrow("Supports"), unsafe_allow_html=True)
        sup = pd.DataFrame(f["supports"] or [], columns=["pad_id", "type"])
        sup = st.data_editor(sup, num_rows="dynamic", key="ed_sup", use_container_width=True, hide_index=True,
                             column_config={"pad_id": st.column_config.SelectboxColumn("pad", options=pad_ids),
                                            "type": st.column_config.SelectboxColumn("type", options=["pin", "slide_x", "slide_y"],
                                                                                     help="pin: x and y held. slide_x: free in x, y held. slide_y: free in y, x held.")})
        f["supports"] = _records(sup)
    with c2:
        st.markdown(ui.eyebrow("Load cases"), unsafe_allow_html=True)
        lcs = pd.DataFrame(f["load_cases"] or [], columns=["id", "name", "reason", "max_deflection_mm"])
        lcs["limit source"] = [note(f"load_cases[{i}].max_deflection_mm") for i in range(len(lcs))]
        lcs = st.data_editor(lcs, num_rows="dynamic", key="ed_lcs", use_container_width=True, hide_index=True,
                             column_config={"limit source": st.column_config.TextColumn(disabled=True),
                                            "max_deflection_mm": st.column_config.NumberColumn("deflection limit (mm)")})
        f["load_cases"] = _records(lcs, drop=("limit source",))
    case_ids = [r["id"] for r in f["load_cases"] if r.get("id")]

    st.markdown(ui.eyebrow("Loads (N; x right, y up, z out of the plane)"), unsafe_allow_html=True)
    lds = pd.DataFrame(f["loads"] or [], columns=["case_id", "pad_id", "fx_N", "fy_N", "fz_N_out_of_plane"])
    srcs = []
    for i, lc in enumerate(f["load_cases"]):
        for j in range(sum(1 for r in f["loads"] if r.get("case_id") == lc.get("id"))):
            srcs.append(" / ".join(x for x in (note(f"load_cases[{i}].loads[{j}].fx_N"), note(f"load_cases[{i}].loads[{j}].fy_N"),
                                                note(f"load_cases[{i}].loads[{j}].fz_N_out_of_plane")) if x))
    lds["text"] = (srcs + [""] * len(lds))[:len(lds)]
    lds = st.data_editor(lds, num_rows="dynamic", key="ed_loads", use_container_width=True, hide_index=True,
                         column_config={"case_id": st.column_config.SelectboxColumn("case", options=case_ids),
                                        "pad_id": st.column_config.SelectboxColumn("pad", options=pad_ids),
                                        "text": st.column_config.TextColumn("from the text", disabled=True)})
    f["loads"] = _records(lds, drop=("text",))

    with st.expander("Keep-in and keep-out zones"):
        zs = pd.DataFrame(f["zones"] or [], columns=["id", "kind", "shape", "cx", "cy", "r", "x", "y", "w", "h"])
        zs = st.data_editor(zs, num_rows="dynamic", key="ed_zones", use_container_width=True, hide_index=True,
                            column_config={"kind": st.column_config.SelectboxColumn(options=["keep_in", "keep_out"]),
                                           "shape": st.column_config.SelectboxColumn(options=["circle", "rect"])})
        f["zones"] = _records(zs)
    return f


def page_check() -> None:
    materials, processes = libs()
    ui.title("Check the problem", "Everything below came from your text or a default. Fix anything wrong; "
                                  "the drawing and the checks update as you edit.")
    if S.parse_fail:
        ui.msg(f"{S.parse_fail}. The manual form below is open. You can also load a demo part.",
               "red", "Could not read the description")
        c = st.columns(3)
        for i, (label, stem) in enumerate(data.DEMOS.items()):
            if c[i].button(label, key=f"fail_demo_{stem}", use_container_width=True):
                load_demo(stem)
                st.rerun()
    if S.form is None:
        S.form = formmod.blank_form()

    # editors first (their values drive the drawing), shown to the right of the drawing
    left, right = st.columns([1.1, 1], gap="large")
    with right:
        with st.container(key="card_values"):
            new_form = editors(S.problem, dict(S.form))
            new_p, errors = formmod.form_to_problem(new_form)
            if new_p is not None:
                new_p = _merge_provenance(S.problem, new_p)
                S.problem = new_p
                S.form = formmod.problem_to_form(new_p)
            else:
                S.form = new_form
    p = S.problem
    with left:
        with st.container(key="card_drawing"):
            st.markdown(ui.eyebrow("Drawing"), unsafe_allow_html=True)
            if p is None:
                for e in errors:
                    ui.msg(e, "yellow", "Form")
                ui.msg("Fill in the part, at least one pad, one support and one load case to see the drawing.", "info")
            else:
                msgs = sanity.check(p, processes, materials)
                for m in msgs:
                    ui.msg(m.message, "red" if m.level == "red" else "yellow",
                           "Stops the run" if (m.level == "red" and m.blocking) else ("Note" if m.level == "red" else "Check"))
                if not msgs:
                    ui.msg("All sanity checks pass.", "ok", "✓")
                st.plotly_chart(maps.problem_drawing(p, dark=False), config=theme.PLOTLY_CONFIG, width="stretch",
                                key="drawing")
                st.markdown('<div class="mx-note">Pins are filled triangles; slides are rollers with the free direction '
                            'drawn. Arrow length scales with force; one color per load case. Amber marks a default.</div>',
                            unsafe_allow_html=True)
        if p is not None:
            with st.container(key="card_runplan"):
                est = data.estimate_runtime(p, S.quick, processes)
                stem = data.match_demo(p)
                st.markdown(ui.eyebrow("Run plan"), unsafe_allow_html=True)
                rows = [[r["process"], f'{r["effective_min_wall_mm"]:.2f} mm enforced' +
                         (f' (process allows {r["min_wall_mm"]:.2f} mm)' if r["effective_min_wall_mm"] > r["min_wall_mm"] + 1e-9 else ""),
                         f'{r["elements"]:,} elements · h {r["h_mm"]:.2f} mm', f'~{r["seconds"] / 60:.0f} min']
                        for r in est["rows"]]
                st.markdown(ui.table(["process", "effective min wall", "mesh", "time"], rows), unsafe_allow_html=True)
                if stem:
                    st.markdown(ui.pill("precomputed demo part: results load instantly", "accent"), unsafe_allow_html=True)
                else:
                    mins = est["seconds"] / 60
                    st.markdown(ui.pill(f"estimated run time ~{mins:.0f} min" + (" (quick mode)" if S.quick else ""), "accent")
                                + f'<span class="mx-note">From the timing model measured in step S9b '
                                  f'(0.37 s per iteration at 40k elements).</span>', unsafe_allow_html=True)
                S.quick = st.toggle("Quick mode", value=S.quick, key="quick_check",
                                    help="One process, 10k elements, no refinement or re-run.")
                blocked = p is None or bool(sanity.blocking(sanity.check(p, processes, materials)))
                if st.button("Generate designs", type="primary", disabled=blocked, key="gen_btn"):
                    S.growth_i, S.growth_play, S.view3d = 0, False, None
                    if stem:
                        S.results, S.live = cached_results(str(data.CACHE_DIR / stem)), None
                    else:
                        S.results, S.live = None, data.start_live(p, S.quick)
                    go(2)
                if blocked and p is not None:
                    st.markdown('<div class="mx-note">Fix the red checks to run.</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 6])
    if c1.button("← Describe", key="back1", type="tertiary"):
        go(0)


# ----------------------------------------------------------------------------- step 3: compare
def material_name(mid: str) -> str:
    materials, _ = libs()
    return materials[mid].name if mid in materials else mid


def proc_label(pid: str) -> str:
    return theme.PROCESS.get(pid, {}).get("label", pid.upper())


@st.fragment(run_every=1.0)
def live_progress() -> None:
    pr: data.Progress = S.live
    if pr.done:
        st.rerun(scope="app")
    with st.container(key="stage_progress"):
        st.markdown(ui.eyebrow("Live run") + f'<div class="mx-title" style="font-size:{theme.TEXT_XL}px">{ui.esc(pr.stage)}</div>',
                    unsafe_allow_html=True)
        c = st.columns(4)
        c[0].markdown(ui.hero(pr.process.upper() or "—", "", "process"), unsafe_allow_html=True)
        c[1].markdown(ui.hero(f"{pr.fill:.0%}" if pr.fill is not None else "—", "", "fill level"), unsafe_allow_html=True)
        c[2].markdown(ui.hero(str(pr.iteration), "", f"iteration · β {pr.beta or '—'}"), unsafe_allow_html=True)
        c[3].markdown(ui.hero(f"{pr.elapsed / 60:.1f}", "min", "elapsed"), unsafe_allow_html=True)
        if pr.preview is not None and S.results is None:
            arr, pid = pr.preview
            # mesh size comes from the live settings (same rule as the engine)
            _, processes = libs()
            W, H = S.problem.design_space.width_mm, S.problem.design_space.height_mm
            cap = config.ELEMENT_CAP_QUICK if S.quick else config.ELEMENT_CAP_LIVE
            mesh, _ = data.choose_mesh(W, H, processes[pid].min_wall_mm, cap)
            if mesh.nel == arr.size:
                st.markdown(img(maps.density_png(arr.astype(float) / 255.0, mesh.nelx, mesh.nely, True, 1000),
                                "width:100%;max-width:1000px;display:block;margin:12px auto"), unsafe_allow_html=True)
        st.markdown('<div class="mx-note">' + "<br>".join(ui.esc(x) for x in pr.log[-4:]) + "</div>", unsafe_allow_html=True)


def growth_player(folder: str, pid: str, nelx: int, nely: int, n: int, its: np.ndarray) -> None:
    if S.growth_play:
        S.growth_i = (S.growth_i + 1) % n
        if S.growth_i == n - 1:
            S.growth_play = False
    st.markdown(img(png_frame(folder, pid, int(S.growth_i), nelx, nely, 1100), "width:100%;display:block"),
                unsafe_allow_html=True)
    c1, c2 = st.columns([5, 1])
    with c1:
        i = st.slider("iteration", 0, n - 1, int(S.growth_i), key="growth_slider", label_visibility="collapsed")
        if i != S.growth_i and not S.growth_play:
            S.growth_i = i
    with c2:
        st.markdown(f'<div class="mx-hero" style="font-size:{theme.TEXT_XL}px;text-align:right">{int(its[int(S.growth_i)])}'
                    f'<small>of {int(its[-1])}</small></div><div class="mx-label" style="text-align:right">iteration</div>',
                    unsafe_allow_html=True)


def material_sources_html(mid: str) -> str:
    materials, processes = libs()
    m = materials[mid]
    rows = []
    for key, label, val in (("E", "E (in-plane)", f"{m.E:,.0f} MPa"), ("nu", "Poisson's ratio", f"{m.nu:g}"),
                            ("strength_xy", f"strength XY ({m.strength_kind})", f"{m.strength_xy:g} MPa"),
                            ("strength_z", "strength Z", f"{m.strength_z:g} MPa" if m.strength_z else "—"),
                            ("density", "density", f"{m.density:g} g/cm³"),
                            ("cost", "cost (material only)", f"${m.cost_per_kg:,.2f}/kg" if m.cost_per_kg else "not sourced")):
        c = m.citations.get(key)
        rows.append([ui.esc(label), ui.esc(val),
                     f'<a href="{ui.esc(c.url)}" target="_blank" style="color:var(--mx-accent)">{ui.esc(c.short())}</a>' if c else "—"])
    z, znote = m.strength_z_used()
    il, ilnote = m.interlayer_shear_used()
    extra = (f'<div class="mx-note" style="margin-top:8px">Z strength used: {z:.1f} MPa ({ui.esc(znote)}). It would '
             f'govern in-plane stresses if the part were printed standing up.<br>Interlayer shear used: {il:.1f} MPa '
             f'({ui.esc(ilnote)}).' + (f"<br>{ui.esc(m.condition_note)}" if m.condition_note else "")
             + (f"<br>{ui.esc(m.cost_note)}" if m.cost_note else "")
             + (("<br>Flags: " + "; ".join(ui.esc(x) for x in m.flags)) if m.flags else "") + "</div>")
    proc = processes[m.process]
    extra += (f'<div class="mx-note" style="margin-top:6px">Process min wall {proc.min_wall_mm:g} mm: '
              f'<a href="{ui.esc(proc.citation.url)}" target="_blank" style="color:var(--mx-accent)">{ui.esc(proc.citation.short())}</a></div>')
    return ui.table(["value", "used", "source"], rows) + extra


def limits_html(d: dict) -> str:
    err = live_mesh_error()
    items = LIMITS + [validation.LIMITS_NOTE_LIVE_MESH.format(err=err),
                      f"This design: {d['effective_min_wall']}; mesh {d['mesh_h_mm']:.2f} mm elements."]
    return "<ul class='mx-note' style='padding-left:18px'>" + "".join(f"<li>{ui.esc(x)}</li>" for x in items) + "</ul>"


def design_card(r: dict, d: dict, c: dict, dark: bool) -> None:
    folder, mid, pid = r["_dir"], d["material"], d["process"]
    nelx, nely = r["catalogs"][pid]["mesh"]
    ch = d.get("checks") or {}
    win = c["state"] == "ranked" and "Lightest" in c["badges"]
    quiet = c["state"] != "ranked"
    key = f"card_{pid}_{mid}_{'win' if win else ('quiet' if quiet else 'ok')}"
    cases = r["problem"]["load_cases"]
    with st.container(key=key):
        pills = "".join(ui.pill(b, "win" if b == "Lightest" else "accent") for b in c["badges"])
        if c["state"] == "ranked":
            pills += ui.pill(f"#{c['rank']} · passes", "pass")
        elif c["state"] == "filtered":
            pills += ui.pill(c["reason"], "")
            pills += ui.pill("passes" if d["status"] == "pass" else "fails", "pass" if d["status"] == "pass" else "fail")
        else:
            pills += ui.pill("Fails: " + c["reason"], "fail")
        if not d.get("converged", True):
            pills += ui.pill("not fully converged", "amber")
        if d["pick"]["status"] == "loose":
            pills += ui.pill("limits are loose", "amber")
        st.markdown(f'<div class="mx-eyebrow mx-eyebrow-proc">{proc_label(pid)} · {ui.esc(material_name(mid))}</div>'
                    f'<div style="margin:8px 0 4px">{pills}</div>', unsafe_allow_html=True)
        dens_key = f"design/{mid}"
        if dens_key in cached_npz(folder, "densities.npz") and ch:
            c1, c2 = st.columns(2)
            c1.markdown(img(png_density(folder, dens_key, nelx, nely, dark, 600)) + '<div class="mx-note" style="text-align:center">shape</div>',
                        unsafe_allow_html=True)
            if mid in cached_npz(folder, "utilization.npz"):
                c2.markdown(img(png_util(folder, mid, nelx, nely, 600)) + '<div class="mx-note" style="text-align:center">utilization</div>',
                            unsafe_allow_html=True)
        if not ch:
            st.markdown('<div class="mx-note">No design evaluated.</div>', unsafe_allow_html=True)
            return
        fill_txt = f"{d['fill']:.1%} fill" if d.get("fill") is not None else ""
        st.markdown(ui.hero(f"{ch['mass_g']:.1f}", "g", f"mass · {fill_txt}"), unsafe_allow_html=True)
        saved = ""
        if c.get("weight_saved_vs_strut") is not None:
            saved += ui.pill(f"{c['weight_saved_vs_strut'] * -100:+.0f}% vs strut", "pass" if c["weight_saved_vs_strut"] > 0 else "amber")
        elif d["baseline"].get("note"):
            saved += ui.pill("strut baseline cannot meet the limits", "amber")
        if c.get("weight_saved_vs_block") is not None:
            saved += ui.pill(f"{c['weight_saved_vs_block'] * -100:+.0f}% vs solid block", "")
        st.markdown(f'<div style="margin:8px 0">{saved}</div>', unsafe_allow_html=True)
        # safety factor gauge + deflection meters
        g = ui.gauge(ch["sf"], ch["sf_target"], "safety factor", f"{ch['sf']:.2f} vs {ch['sf_target']:g} target", ch["stress_pass"])
        st.markdown(g + f'<div class="mx-note">filtered stress {ch["stress_reported_MPa"]:.1f} MPa · raw peak {ch["stress_raw_MPa"]:.1f} MPa '
                    f'(SF {ch["sf_raw"]:.2f}). Raw peak includes stress spikes at load and support points, which are an artifact '
                    f'of the model. The filtered value is used for the safety factor.</div>', unsafe_allow_html=True)
        rows = ""
        for i, lc in enumerate(cases):
            if not any(ld["fx_N"] or ld["fy_N"] for ld in lc["loads"]):
                continue
            dv, lim = ch["deflection_mm"][i], ch["deflection_limit_mm"][i]
            col = theme.LOAD_CASE_COLORS[i % len(theme.LOAD_CASE_COLORS)]
            rows += (f'<div class="mx-row"><span><span class="mx-swatch" style="background:{col}"></span>{ui.esc(lc["name"])}</span>'
                     f'<span>{dv:.2f} of {lim:g} mm</span></div>' + ui.meter(dv / lim if lim else 0, dv <= lim))
        st.markdown(f'<div style="margin-top:10px"><div class="mx-label">deflection vs limit</div>{rows}</div>', unsafe_allow_html=True)
        hand = ""
        for h in ch.get("out_of_plane", []) + ch.get("bearing", []):
            hand += (f'<div class="mx-row"><span>{ui.check_icon(bool(h["passed"]))} {ui.esc(h["name"])}</span>'
                     f'<span>SF {ui.fmt(h["sf"])}</span></div>'
                     f'<div class="mx-note">{ui.esc(h.get("where", ""))}' + (f' · <b>{ui.esc(h["suggestion"])}</b>' if h.get("suggestion") else "") + "</div>")
        if hand:
            st.markdown(f'<div style="margin-top:10px"><div class="mx-label">hand checks (approximate)</div>{hand}'
                        f'<div class="mx-note">Bearing uses the full XY strength as an approximation; bearing allowables are '
                        f'often higher.</div></div>', unsafe_allow_html=True)
        cost = f"${c['material_cost_usd']:.2f} · material cost only, not print cost" if c.get("material_cost_usd") is not None else "cost not sourced"
        st.markdown(ui.row("min wall", ui.esc(d["effective_min_wall"])) + ui.row("mesh", f"{d['mesh_h_mm']:.2f} mm elements")
                    + ui.row("material cost", ui.esc(cost)), unsafe_allow_html=True)
        notes = [n for n in (d.get("notes") or []) + (d["pick"].get("notes") or [])
                 if n and n != "not fully converged"]  # that one is already a pill
        if notes:
            st.markdown('<div class="mx-note" style="margin-top:6px">' + "<br>".join(ui.esc(n) for n in dict.fromkeys(notes)) + "</div>",
                        unsafe_allow_html=True)
        with st.expander("Sources"):
            st.markdown(material_sources_html(mid), unsafe_allow_html=True)
        with st.expander("Limits"):
            st.markdown(limits_html(d), unsafe_allow_html=True)
        files = (d.get("geometry") or {}).get("files") or {}
        if files.get("stl") and mid in cached_npz(folder, "utilization.npz"):
            if st.button("View in 3D", key=f"3d_{mid}", use_container_width=True):
                S.view3d = mid
                st.rerun()


@st.dialog("Interactive 3D view", width="large")
def dialog_3d(r: dict, mid: str) -> None:
    d = next(x for x in r["designs"] if x["material"] == mid)
    pid = d["process"]
    nelx, nely = r["catalogs"][pid]["mesh"]
    u = cached_npz(r["_dir"], "utilization.npz")[mid]
    worst = np.nanmax(np.where(np.isfinite(u), u, -np.inf), axis=0)
    worst[~np.isfinite(worst)] = np.nan
    st.markdown(f'<div class="mx-eyebrow">{proc_label(pid)} · {ui.esc(material_name(mid))} · colored by utilization, worst load case</div>',
                unsafe_allow_html=True)
    stl = Path(r["_dir"]) / d["geometry"]["files"]["stl"]
    st.plotly_chart(maps.part_3d(stl, worst, nelx, nely, r["catalogs"][pid]["h_mm"], dark=True),
                    config=theme.PLOTLY_CONFIG_3D, width="stretch", key="fig3d")
    st.markdown(maps.utilization_legend(True), unsafe_allow_html=True)
    if st.button("Close", key="close3d"):
        S.view3d = None
        st.rerun()


@st.fragment(run_every=2.0)
def design_agent_panel(r: dict) -> None:
    key = r["key"]
    job = S.agent_jobs.get(key)
    running = job is not None and not job.done.is_set()
    any_running = any(not j.done.is_set() for j in S.agent_jobs.values())
    st.markdown(ui.eyebrow("Design agent"), unsafe_allow_html=True)
    st.caption("Explore up to five changes with the configured LLM. Loads, supports and safety limits stay fixed.")
    if st.button("Explore design changes" if job is None else "Explore again", key="agent_start",
                 type="primary", disabled=any_running):
        S.agent_jobs[key] = integration.start_agent(problem_from_dict(r["problem"]))
        st.rerun(scope="app")
    if job is None:
        if any_running:
            st.info("An exploration is running for another part in this session.")
        st.caption("Each trial uses quick mode. A complete exploration usually takes several minutes.")
        return
    state = job.snapshot()
    if running:
        st.info(f"{state['messages'][-1] if state['messages'] else 'Starting exploration'} · {state['seconds'] / 60:.1f} min")
    if state["error"]:
        st.error(state["error"])
    with st.expander("Exploration progress", expanded=running):
        for message in state["messages"]:
            st.text(message)
    log = state["log"]
    if log is None:
        return
    st.markdown(log.recommendation["text"])
    st.caption(f"Recommendation: {log.recommendation['source']}. Quick-mode results require a full solve before export.")
    rows = []
    for row in log.rounds:
        best = row.results.get("best") or {}
        rows.append({"Round": row.index, "Change": row.change,
                     "Proposal": row.proposal.source if row.proposal else "starting point",
                     "Material": best.get("material", "none passes"), "Mass (g)": best.get("mass_g")})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with st.expander("Reasons and trial details"):
        for row in log.rounds:
            if row.proposal:
                st.write(f"Round {row.index}: {row.proposal.reason}")
        st.json(log.to_dict(), expanded=False)
    st.download_button("Exploration log", job.path.read_bytes(), file_name="exploration.json",
                       mime="application/json", key="agent_log")
    if st.button("Review recommended design", key="agent_review"):
        try:
            p = integration.recommended_problem(job.problem, log)
        except ValueError as exc:
            st.error(str(exc))
            return
        S.problem, S.form = p, formmod.problem_to_form(p)
        for widget_key in list(S):
            if widget_key.startswith("ed_") or widget_key == "quick_check":
                del S[widget_key]
        S.results, S.live, S.parse_fail = None, None, None
        S.quick, S.view3d, S.growth_play, S.growth_i = False, None, False, 0
        S.printer_choice = p.printer
        S.step = 1
        st.rerun(scope="app")


def page_compare() -> None:
    if S.live is not None and S.results is None:
        pr: data.Progress = S.live
        if pr.done and pr.error:
            ui.title("The run failed")
            ui.msg(pr.error.strip().splitlines()[-1], "red", "Error")
            st.code(pr.error)
            if st.button("← Back to the check", key="back_err"):
                S.live = None
                go(1)
            return
        if pr.done and pr.result_dir:
            S.results = cached_results(str(pr.result_dir))
            S.live = None
        else:
            ui.title("Generating designs", "Three catalogs, one per process. Each fill level starts from the one above it.")
            live_progress()
            return
    r = S.results
    if r is None:
        ui.title("Nothing to compare yet")
        if st.button("← Describe a part", key="back_none"):
            go(0)
        return
    rk = r["ranking"]
    designs = {d["material"]: d for d in r["designs"]}
    cards = {c["material"]: c for c in rk["cards"]}
    folder = r["_dir"]
    win = rk.get("winner")
    ui.title("Compare materials and processes", f"{r['problem']['name']} · ranked by mass among designs that pass "
             f"every limit and fit your printer. Cost never ranks.")
    if S.view3d:
        dialog_3d(r, S.view3d)

    # ---- the stage: the winner large, and the growth animation
    if win:
        d, c = designs[win], cards[win]
        pid = d["process"]
        nelx, nely = r["catalogs"][pid]["mesh"]
        ch = d["checks"]
        with st.container(key="stage_hero"):
            top = st.columns([3, 1])
            top[0].markdown(f'<div class="mx-eyebrow" style="color:{theme.PROCESS[pid]["color"]}">{proc_label(pid)} · '
                            f'{ui.esc(material_name(win))}</div><div class="mx-title">{ui.pill("Lightest", "win")} '
                            f'{ch["mass_g"]:.1f} g at {d["fill"]:.0%} fill</div>', unsafe_allow_html=True)
            with top[1]:
                S.stage_view = st.segmented_control("view", ["Shape", "Stress"], default=S.stage_view, key="stage_seg",
                                                    label_visibility="collapsed") or S.stage_view
            if S.stage_view == "Stress" and win in cached_npz(folder, "utilization.npz"):
                st.markdown(img(png_util(folder, win, nelx, nely, 1400), "width:100%;display:block;margin:6px 0"), unsafe_allow_html=True)
                st.markdown(maps.utilization_legend(True), unsafe_allow_html=True)
            else:
                st.markdown(img(png_density(folder, f"design/{win}", nelx, nely, True, 1400), "width:100%;display:block;margin:6px 0"),
                            unsafe_allow_html=True)
            k = st.columns(4)
            k[0].markdown(ui.hero(f"{ch['sf']:.2f}", "", f"safety factor · {ch['sf_target']:g} target"), unsafe_allow_html=True)
            worst = int(np.argmax(np.array(ch["deflection_mm"]) / np.array(ch["deflection_limit_mm"])))
            k[1].markdown(ui.hero(f"{ch['deflection_mm'][worst]:.2f}", "mm", f"deflection · {ch['deflection_limit_mm'][worst]:g} mm limit"),
                          unsafe_allow_html=True)
            k[2].markdown(ui.hero(f"{(c.get('weight_saved_vs_strut') or 0) * 100:.0f}", "%", "lighter than a strut design sized to the same limits"),
                          unsafe_allow_html=True)
            k[3].markdown(ui.hero(f"{(c.get('weight_saved_vs_block') or 0) * 100:.0f}", "%", "lighter than the solid block"),
                          unsafe_allow_html=True)
        rerun_file = Path(folder) / f"rerun_{pid}.npz"
        if rerun_file.exists():
            z = cached_npz(folder, f"rerun_{pid}.npz")
            its = z["iterations"]
            with st.container(key="stage_growth"):
                hdr = st.columns([4, 1])
                hdr[0].markdown(ui.eyebrow("Growth · cold run from uniform density, every iteration") +
                                f'<div class="mx-note">{GROWTH_CAPTION}</div>', unsafe_allow_html=True)
                with hdr[1]:
                    S.growth_play = st.toggle("Play", value=S.growth_play, key="growth_toggle")
                rerun_mat = str(z.get("material", win))
                note = designs[rerun_mat]["rerun"].get("note") if rerun_mat in designs else ""
                st.fragment(run_every=0.12 if S.growth_play else None)(growth_player)(folder, pid, nelx, nely, len(its), its)
                if note or rerun_mat != win:
                    st.markdown(f'<div class="mx-note">{ui.esc(note or "")}' +
                                (f' Animation: {ui.esc(rerun_mat)} at {float(z["fill"]):.1%} fill (the top design of this process).' if rerun_mat != win else "")
                                + "</div>", unsafe_allow_html=True)
    else:
        with st.container(key="stage_hero"):
            st.markdown(ui.eyebrow("No ranked design") + '<div class="mx-title">No material meets the limits with your printer</div>',
                        unsafe_allow_html=True)

    # ---- grounded explanation + live design exploration
    e1, e2 = st.columns([3, 2], gap="medium")
    with e1:
        with st.container(key="card_explain"):
            payload = explain.saved_results_json(r)
            with st.spinner("Explaining the computed results…"):
                explanation = grounded_explanation(json.dumps(payload, sort_keys=True), config.LLM_PROVIDER,
                                                   config.LLM_MODELS[config.LLM_PROVIDER])
            st.markdown(ui.eyebrow("Why this wins") + f'<div style="font-size:{theme.TEXT_MD + 1}px;line-height:1.55;margin-top:8px">'
                        f'{ui.esc(explanation.text)}</div>', unsafe_allow_html=True)
            st.caption("LLM explanation · numbers checked against the computed results" if explanation.source == "llm"
                       else "Template fallback · the LLM was unavailable or its response failed validation")
            with st.expander("Facts used in the explanation"):
                for card in payload["cards"]:
                    if card.get("mass"):
                        cost = card.get("material_cost")
                        st.text(f"{card['name']}: {card['mass']['value']} g · {card['printer']} · {card['state']}"
                                + (f" · {cost['value']} USD material only" if cost else ""))
            for m in rk.get("messages") or []:
                ui.msg(m, "info")
    with e2:
        with st.container(key="agent_panel"):
            design_agent_panel(r)

    # ---- funnel and pareto
    st.markdown(ui.eyebrow("Funnel"), unsafe_allow_html=True)
    ui.funnel(rk["funnel"])
    p1, p2 = st.columns([3, 2], gap="medium")
    with p1:
        with st.container(key="card_pareto"):
            st.markdown(ui.eyebrow("Mass vs material cost · one point per material (its final pick)"), unsafe_allow_html=True)
            st.plotly_chart(maps.pareto_chart(rk["pareto"], True, rk.get("caption_cost", "material cost only")),
                            config=theme.PLOTLY_CONFIG, width="stretch", key="pareto")
            st.markdown('<div class="mx-note">Filled points pass and fit your printer; hollow grey points failed or are '
                        'filtered (hover for the reason). The dotted line joins the designs no other beats on both mass and cost. '
                        'Cost is material only, not print cost.</div>', unsafe_allow_html=True)
    with p2:
        with st.container(key="card_levels"):
            st.markdown(ui.eyebrow("Fill levels per material"), unsafe_allow_html=True)
            rows = []
            for mid in rk["order"]:
                d = designs[mid]
                lv = d["pick"]["levels"]
                dots = "".join(f'<span title="{s["fill"]:.0%}: {"pass" if s["passed"] else "fail"}{(" · " + s["label"]) if s["label"] else ""}" '
                               f'style="display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:3px;'
                               f'background:{theme.PASS if s["passed"] else (theme.MUTED if s["label"] else theme.FAIL)};'
                               f'opacity:{0.5 if s["label"] else 1}"></span>' for s in sorted(lv, key=lambda s: s["fill"]))
                rows.append([f'<span class="mx-swatch" style="background:{theme.PROCESS[d["process"]]["color"]}"></span>{mid}',
                             dots, f"{d['fill']:.1%}" if d.get("fill") is not None else "—",
                             f"{d['checks']['mass_g']:.1f} g" if d.get("checks") else "—"])
            st.markdown(ui.table(["material", "levels (low → high)", "pick", "mass"], rows)
                        + '<div class="mx-note">Green passes, red fails, grey is an isolated stress failure or a non-monotonic level (ignored).</div>',
                        unsafe_allow_html=True)

    # ---- card grid grouped by process
    for pid in ("fdm", "sls", "metal"):
        mids = [m for m in rk["order"] if designs[m]["process"] == pid]
        if not mids:
            continue
        st.markdown(f'<div class="mx-eyebrow" style="color:{theme.PROCESS[pid]["color"]};margin:{theme.SPACE_5}px 0 {theme.SPACE_2}px">'
                    f'{proc_label(pid)} · {r["catalogs"][pid]["min_wall_text"]} · mesh {r["catalogs"][pid]["mesh"][0]} × {r["catalogs"][pid]["mesh"][1]}</div>',
                    unsafe_allow_html=True)
        cols = st.columns(3, gap="medium")
        for i, mid in enumerate(mids):
            with cols[i % 3]:
                design_card(r, designs[mid], cards[mid], True)
    ui.foot(FIXED_NOTE)
    c1, c2, c3 = st.columns([1, 4, 1])
    if c1.button("← Check", key="back2", type="tertiary"):
        go(1)
    if c3.button("Export →", key="fwd3", type="primary"):
        go(3)


# ----------------------------------------------------------------------------- step 4: export
def page_export() -> None:
    r = S.results
    ui.title("Export", "STL, SVG and DXF of every design that has a shape. The numbers on the cards come from the "
                       "smoothed shape that is exported, so they match the STL.")
    if r is None:
        ui.msg("Generate designs first.", "info")
        if st.button("← Compare", key="back_exp"):
            go(2)
        return
    folder = Path(r["_dir"])
    cards = {c["material"]: c for c in r["ranking"]["cards"]}
    cols = st.columns(3, gap="medium")
    for i, mid in enumerate(r["ranking"]["order"]):
        d = next(x for x in r["designs"] if x["material"] == mid)
        c = cards[mid]
        files = (d.get("geometry") or {}).get("files") or {}
        with cols[i % 3]:
            with st.container(key=f"card_{d['process']}_{mid}_export"):
                pills = "".join(ui.pill(b, "win" if b == "Lightest" else "accent") for b in c["badges"])
                pills += ui.pill("passes" if d["status"] == "pass" else "fails", "pass" if d["status"] == "pass" else "fail")
                st.markdown(f'<div class="mx-eyebrow mx-eyebrow-proc">{proc_label(d["process"])} · {ui.esc(material_name(mid))}</div>'
                            f'<div style="margin:6px 0">{pills}</div>'
                            + (ui.hero(f"{d['checks']['mass_g']:.1f}", "g", f"{d['fill']:.1%} fill · {d['effective_min_wall']}") if d.get("checks") else ""),
                            unsafe_allow_html=True)
                if files:
                    b = st.columns(3)
                    for j, (ext, mime) in enumerate((("stl", "model/stl"), ("svg", "image/svg+xml"), ("dxf", "application/dxf"))):
                        path = folder / files.get(ext, "")
                        if files.get(ext) and path.exists():
                            b[j].download_button(ext.upper(), data=path.read_bytes(), file_name=f"{r['problem']['name'][:24].replace(' ', '_')}_{mid}.{ext}",
                                                 mime=mime, key=f"dl_{mid}_{ext}", use_container_width=True)
                    g = d["geometry"]
                    st.markdown(f'<div class="mx-note">watertight: {"yes" if g["watertight"] else "no"} · volume error '
                                f'{g["volume_error"]:.2%} · area {g["area_mm2"]:.0f} mm²</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="mx-note">No geometry: this design did not produce an exportable shape.</div>',
                                unsafe_allow_html=True)
    with st.container(key="card_bundle"):
        st.markdown(ui.eyebrow("Report and run bundle"), unsafe_allow_html=True)
        b = st.columns(3)
        b[0].download_button("results.json", data=(folder / "results.json").read_bytes(), file_name="results.json",
                             mime="application/json", key="dl_results", use_container_width=True)
        try:
            with st.spinner("Preparing the report and reproducible bundle…"):
                pdf, bundle = prepared_downloads(str(folder), integration.export_signature(str(folder)))
            b[1].download_button("PDF report", pdf, file_name="report.pdf", mime="application/pdf",
                                 key="dl_pdf", width="stretch")
            b[2].download_button("Run bundle (zip)", bundle, file_name="run.zip", mime="application/zip",
                                 key="dl_bundle", width="stretch")
        except Exception as exc:
            st.error(f"Report and bundle could not be prepared ({type(exc).__name__}). Geometry downloads remain available.")
        st.markdown(f'<div class="mx-note">Results folder: {ui.esc(folder)} · code {ui.esc(r["code_version"][:12])} · '
                    f'materials {ui.esc(r["materials_hash"])} · cap {r["solver_settings"]["cap_used"]:,} elements, '
                    f'{ui.esc(r["solver_settings"]["sweep_mode_used"])} sweep. The PDF contains one page per material. '
                    f'The bundle includes that same report and the inputs for morphic rerun.</div>', unsafe_allow_html=True)
    ui.foot(FIXED_NOTE)
    if st.button("← Compare", key="back3", type="tertiary"):
        go(2)


# ----------------------------------------------------------------------------- validation tab
@st.cache_data(show_spinner=False)
def run_checks() -> dict:
    out = {"cantilever": validation.cantilever_check(20), "mesh": validation.mesh_refinement(),
           "scaling": validation.scaling_law_check(),
           "hole": [validation.hole_stress_check(n) for n in (8, 16, 32)], "mbb": validation.mbb_check(),
           "when": time.strftime("%Y-%m-%d %H:%M")}
    out["mbb"]["density_grid"] = np.asarray(out["mbb"]["density_grid"])
    return out


def page_validation() -> None:
    ui.title("Validation", "Every check runs from the same finite element code the designs use. "
                           "Errors are stated at the mesh they were measured on.")
    top = st.columns([5, 1])
    if top[1].button("Run all checks", key="run_checks", type="primary", use_container_width=True):
        run_checks.clear()
    with st.spinner("Running the checks (about 10 s)…"):
        v = run_checks()
    ok_pill = lambda ok: ui.pill("pass", "pass") if ok else ui.pill("fail", "fail")  # noqa: E731

    c = v["cantilever"]
    with st.container(key="card_cantilever"):
        ok = c["delta_error"] < c["tolerance"] and c["sigma_error"] < c["tolerance"]
        st.markdown(ui.eyebrow("13.1 Cantilever beam vs beam theory") + f'<div style="margin:6px 0">{ok_pill(ok)} '
                    f'{ui.pill("validation mesh: " + c["mesh"], "")}</div>', unsafe_allow_html=True)
        rows = [["tip deflection (with shear, κ = 5/6)", f"{c['delta_fe_mm']:.4f} mm", f"{c['delta_theory_mm']:.4f} mm",
                 f"{c['delta_error']:.2%}", ok_pill(c["delta_error"] < c["tolerance"])],
                ["mid-span surface stress, recovered nodal", f"{c['sigma_node_MPa']:.3f} MPa", f"{c['sigma_surface_theory_MPa']:.3f} MPa",
                 f"{c['sigma_error']:.2%}", ok_pill(c["sigma_error"] < c["tolerance"])],
                ["element-centre stress, top row (element check)", f"{c['sigma_centre_MPa']:.3f} MPa", f"{c['sigma_centre_theory_MPa']:.3f} MPa",
                 f"{c['sigma_centre_error']:.2%}", ok_pill(c["sigma_centre_error"] < c["tolerance"])]]
        st.markdown(ui.table(["quantity", "FE", "theory", "error", f"< {c['tolerance']:.0%}"], rows), unsafe_allow_html=True)
        st.markdown('<div class="mx-note">L = 100 mm, depth 10 mm, thickness 10 mm, tip load spread over the end face, fixed face at x = 0. '
                    'Production meshes are finer (about 90 elements through 20 mm at the live cap).</div>', unsafe_allow_html=True)

    m1, m2 = st.columns(2, gap="medium")
    with m1:
        with st.container(key="card_mesh"):
            st.markdown(ui.eyebrow("13.2 Mesh refinement · error vs elements through the depth"), unsafe_allow_html=True)
            st.plotly_chart(maps.mesh_refinement_plot(v["mesh"], False), config=theme.PLOTLY_CONFIG, width="stretch", key="meshplot")
            errs = [r["delta_error"] for r in v["mesh"]]
            shrinks = all(b < a for a, b in zip(errs, errs[1:]))
            st.markdown(f'{ok_pill(shrinks)} <span class="mx-note">deflection error shrinks steadily: '
                        f'{" → ".join(f"{e:.1%}" for e in errs)}</span>', unsafe_allow_html=True)
    with m2:
        with st.container(key="card_scaling"):
            s = v["scaling"]
            ok = s["deflection_ratio_error"] < s["tolerance"] and s["stress_ratio_error"] < s["tolerance"]
            st.markdown(ui.eyebrow("13.5 Scaling laws (the catalog method)") + f'<div style="margin:6px 0">{ok_pill(ok)}</div>',
                        unsafe_allow_html=True)
            st.markdown(ui.table(["doubling E", "ratio", "expected", "error"],
                                 [["deflection", f"{s['deflection_ratio']:.9f}", "0.5", f"{s['deflection_ratio_error']:.1e}"],
                                  ["max stress", f"{s['stress_ratio']:.9f}", "1.0", f"{s['stress_ratio_error']:.1e}"]])
                        + f'<div class="mx-note">Tolerance {s["tolerance"]:.0e}. For a fixed shape, deflection scales 1/E and stress '
                          f'does not depend on E, so one catalog run per process serves every material.</div>', unsafe_allow_html=True)
            mb = v["mbb"]
            ok = mb["error"] < mb["tolerance"]
            st.markdown(ui.eyebrow("13.3 MBB benchmark (paper mode)") + f'<div style="margin:6px 0">{ok_pill(ok)}</div>',
                        unsafe_allow_html=True)
            grid = np.asarray(mb["density_grid"])
            st.markdown(img(maps.density_png(grid.ravel(), grid.shape[0], grid.shape[1], False, 700),
                            "width:100%;max-width:420px;display:block;border-radius:8px"), unsafe_allow_html=True)
            st.markdown(ui.table(["", "value"], [["call", ui.esc(mb["call"])], ["our compliance", f"{mb['compliance']:.2f}"],
                                                 ["published compliance", f"{mb['published_compliance']:.2f}"],
                                                 ["error", f"{mb['error']:.2%} (limit {mb['tolerance']:.0%})"],
                                                 ["iterations", str(mb["iterations"])]])
                        + f'<div class="mx-note">Our result (above) next to the published figure: {ui.esc(mb["source"])}. The published '
                          f'image is in the paper and is not redistributed here; compare the layout with Fig. 3 bottom-left.</div>',
                        unsafe_allow_html=True)

    with st.container(key="card_hole"):
        hs = v["hole"]
        h16 = next(h for h in hs if h["elements_per_radius"] == 16)
        h8 = next(h for h in hs if h["elements_per_radius"] == 8)
        ok = (all(h["error_with_recovery"] < h["error_without_recovery"] for h in hs)
              and h16["error_with_recovery"] < 0.05 and h8["element_check_error"] < 0.05)
        st.markdown(ui.eyebrow("13.4 Hole stress check · plate with a central hole, with and without nodal recovery")
                    + f'<div style="margin:6px 0">{ok_pill(ok)} {ui.pill(f"K_t finite width = {hs[0]["Ktg"]:.3f} (Pilkey, Chart 4.1)", "")}</div>',
                    unsafe_allow_html=True)
        c1, c2 = st.columns([3, 2], gap="medium")
        rows = [[str(h["elements_per_radius"]), f"{h['error_without_recovery']:.1%}", f"{h['error_with_recovery']:.1%}",
                 f"{h['error_at_90deg_node']:.1%} (max at {h['theta_of_max_deg']:.0f}°)", f"{h['element_check_error']:.1%}",
                 f"{h['stair_step_ratio']:.3f}"] for h in hs]
        c1.markdown(ui.table(["elements / radius", "element centre", "recovered (boundary max)", "recovered at 90° node",
                              "element check", "stair-step ratio"], rows)
                    + f'<div class="mx-note">Pass: recovered error below the element-centre error at every mesh; recovered error '
                      f'< 5% at 16 per radius; element check < 5% at 8 per radius. The recovered error at 8 per radius '
                      f'({h8["error_with_recovery"]:.1%}) is the remaining stress error at a smooth edge at the live mesh, and the '
                      f'Limits note on every card says so.</div>', unsafe_allow_html=True)
        with c2:
            st.plotly_chart(maps.hole_plot(hs, False), config=theme.PLOTLY_CONFIG, width="stretch", key="holeplot")
    ui.foot(f"Checks run {v['when']} on this machine. The same element, assembly and solver serve every design.")


# ----------------------------------------------------------------------------- main
def main() -> None:
    init_state()
    apply_query_params()
    dark = S.tab == "Design" and S.step == 2
    ui.inject_css(dark)
    head = st.columns([5, 1])
    with head[0]:
        ui.topbar(S.step if S.tab == "Design" else None, S.tab)
    with head[1]:
        choice = st.segmented_control("tab", ["Design", "Validation"], default=S.tab, key="tab_seg",
                                      label_visibility="collapsed")
        if choice and choice != S.tab:
            S.tab = choice
            st.rerun()
    if S.tab == "Validation":
        page_validation()
    else:
        (page_describe, page_check, page_compare, page_export)[S.step]()


main()
