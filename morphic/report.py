"""One A4 page per reported design, using only saved, computed results."""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from .cache import load_results
from .materials import load_materials, load_processes

LIMITS = (
    "Static check only; fatigue, impact toughness, buckling and physical testing are not evaluated. "
    "2D plane stress, linear elastic, small deflections, room temperature. Printed flat at 100% infill; "
    "standing the part up invalidates these in-plane strengths. Von Mises with one strength is a "
    "simplification for plastics. PA6-CF is anisotropic within a layer; perimeters are assumed to follow members. "
    "Nodal stress recovery reduces edge under-reading; sharp-corner peaks remain mesh dependent. "
    "The hole validation measured about 6% remaining smooth-edge error at 8 elements per radius. "
    "The pad ring plus one ring width is excluded from reported stress; the raw peak is also shown. "
    "Out-of-plane bending and interlayer shear are hand checks only. Hole bearing uses full strength "
    "as a conservative approximation; pin shear and edge tear-out are not checked."
)


def _text(value) -> str:
    return str(value).translate(str.maketrans({"≥": ">=", "≤": "<=", "×": "x", "−": "-",
        "–": "-", "—": "-", "σ": "stress", "β": "beta", "³": "3", "²": "2"})).encode("latin-1", "replace").decode("latin-1")


def _num(value, digits=3) -> str:
    return "n/a" if value is None else f"{float(value):.{digits}g}"


def _figure(data: dict, design: dict, directory: Path, densities, utilization) -> io.BytesIO:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.patches import Circle, Rectangle, PathPatch
    from matplotlib.path import Path as PlotPath
    from matplotlib import colormaps

    p = data["problem"]
    width, height = p["design_space"]["width_mm"], p["design_space"]["height_mm"]
    fig = Figure(figsize=(10, 4.2), layout="constrained")
    FigureCanvasAgg(fig)
    grid = fig.add_gridspec(2, 2, height_ratios=(1, 1.3))
    axes = [fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1]), fig.add_subplot(grid[1, :])]
    for ax in axes:
        ax.set(xlim=(-1, width + 1), ylim=(-1, height + 1), aspect="equal")
        ax.tick_params(labelsize=6)
        ax.set_ylabel("mm", fontsize=7)
    axes[0].set_title("Checked problem: supports, pads and loads", fontsize=9, loc="left")
    axes[0].add_patch(Rectangle((0, 0), width, height, fill=False, edgecolor="#93a4b5"))
    for z in p["zones"]:
        color = "#f4b7ab" if z["kind"] == "keep_out" else "#b6ded5"
        if z["shape"] == "circle":
            c = z["circle"]
            patch = Circle((c["cx"], c["cy"]), c["r"], color=color)
        else:
            r = z["rect"]
            patch = Rectangle((r["x"], r["y"]), r["w"], r["h"], color=color)
        axes[0].add_patch(patch)
    pads = {pad["id"]: pad for pad in p["pads"]}
    for pad in pads.values():
        axes[0].add_patch(Circle((pad["cx"], pad["cy"]), pad["ring_r_mm"], fill=False, color="#365568"))
        axes[0].add_patch(Circle((pad["cx"], pad["cy"]), pad["hole_r_mm"], color="white", ec="#365568"))
        axes[0].text(pad["cx"], pad["cy"] + pad["ring_r_mm"], pad["id"], fontsize=6)
    for sup in p["supports"]:
        pad = pads[sup["pad_id"]]
        axes[0].plot(pad["cx"], pad["cy"], "^" if sup["type"] == "pin" else "o", color="#153e57", ms=5)
        axes[0].text(pad["cx"], pad["cy"] - pad["ring_r_mm"], sup["type"], fontsize=5)
    for i, case in enumerate(p["load_cases"]):
        for ld in case["loads"]:
            pad = pads[ld["pad_id"]]
            fx, fy = ld["fx_N"], ld["fy_N"]
            norm = np.hypot(fx, fy)
            if norm:
                scale = min(width, height) * .45 / norm
                # Arrowheads act on the pad. Keep tails inside the drawing even
                # when a loaded pad lies next to the design-space boundary.
                if fx:
                    scale = min(scale, (pad["cx"] if fx > 0 else width - pad["cx"]) * .9 / abs(fx))
                if fy:
                    scale = min(scale, (pad["cy"] if fy > 0 else height - pad["cy"]) * .9 / abs(fy))
                axes[0].annotate("", xy=(pad["cx"], pad["cy"]),
                    xytext=(pad["cx"] - fx * scale, pad["cy"] - fy * scale),
                    arrowprops={"arrowstyle": "->", "color": f"C{i}"})
    axes[1].set_title("Exported, smoothed shape", fontsize=9, loc="left")
    mid = design["material"]
    if design.get("geometry"):
        svg = ET.parse(directory / design["geometry"]["files"]["svg"])
        for element in svg.iter("{http://www.w3.org/2000/svg}path"):
            verts, codes = [], []
            for ring in re.findall(r"M\s*([^Z]+)Z", element.attrib["d"]):
                values = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", ring)]
                pts = list(zip(values[::2], values[1::2]))
                verts.extend([(x, height - y) for x, y in pts] + [(pts[0][0], height - pts[0][1])])
                codes.extend([PlotPath.MOVETO] + [PlotPath.LINETO] * (len(pts) - 1) + [PlotPath.CLOSEPOLY])
            axes[1].add_patch(PathPatch(PlotPath(verts, codes), facecolor="#256e78", edgecolor="#17414a", lw=.3))
    else:
        axes[1].text(width / 2, height / 2, "No exportable shape", ha="center", fontsize=9)
    axes[2].set_title("Recovered nodal utilization: worst load case; red > 1", fontsize=9, loc="left")
    if mid in utilization:
        nx, ny = data["catalogs"][design["process"]]["mesh"]
        values = np.asarray(utilization[mid])
        # fmax ignores masked voids without all-NaN warnings.
        values = np.fmax.reduce(values, axis=0).reshape(nx + 1, ny + 1).T
        cmap = colormaps["viridis"].with_extremes(over="#e3342f")
        h = design["mesh_h_mm"]
        im = axes[2].pcolormesh(np.arange(nx + 1) * h, np.arange(ny + 1) * h,
            np.ma.masked_invalid(values), shading="gouraud", cmap=cmap, vmin=0, vmax=1)
        fig.colorbar(im, ax=axes[2], fraction=.02, pad=.01, extend="max").ax.tick_params(labelsize=6)
    else:
        axes[2].text(width / 2, height / 2, "No stress field available", ha="center", fontsize=9)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180)
    buf.seek(0)
    return buf


def write_report(directory: Path | str, output: Path | str, *, material: str | None = None,
                 materials_path=None, processes_path=None) -> Path:
    """Write exactly one page per design (or one selected material). No LLM calls."""
    from fpdf import FPDF
    directory, output = Path(directory), Path(output)
    data = load_results(directory)
    materials = load_materials(materials_path) if materials_path else load_materials()
    processes = load_processes(processes_path) if processes_path else load_processes()
    designs = [d for d in data["designs"] if material is None or d["material"] == material]
    if not designs:
        raise ValueError("material is not present in this run")
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(False)
    pdf.set_margins(12, 10, 12)

    def block(text, size=8, bold=False, link=""):
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.multi_cell(186, size * .40, _text(text), new_x="LMARGIN", new_y="NEXT", link=link, align="L")

    with np.load(directory / "densities.npz", allow_pickle=False) as densities:
        util_path = directory / "utilization.npz"
        util = {}
        if util_path.exists():
            with np.load(util_path, allow_pickle=False) as z:
                util = {k: z[k] for k in z.files}
        for d in designs:
            pdf.add_page()
            m, proc = materials[d["material"]], processes[d["process"]]
            p = data["problem"]
            block(f"MORPHIC  /  {p['name']}", 16, True)
            block(f"{m.name}  |  {proc.name}  |  {d['status'].upper()}" +
                ("  |  printer filtered" if not d["printer_allowed"] else ""), 10, True)
            block(f"{p['design_space']['width_mm']:g} x {p['design_space']['height_mm']:g} mm; "
                f"thickness {p['thickness_mm']:g} mm | mesh {_num(d['mesh_h_mm'])} mm | {d['effective_min_wall']}")
            block("Lowest passing fill level among stiffness-optimized shapes; not a stress-constrained mass optimum.", 7)
            pdf.image(_figure(data, d, directory, densities, util), x=12, y=pdf.get_y()+1, w=186, h=78)
            pdf.set_y(pdf.get_y() + 81)
            checks = d.get("checks")
            card = next(c for c in data["ranking"]["cards"] if c["material"] == m.id)
            if checks:
                block(f"Mass {_num(checks['mass_g'], 5)} g  |  fill {_num(100*d['fill'])}%  |  "
                    f"SF {_num(checks['sf'])} / target {_num(checks['sf_target'])}  |  raw SF {_num(checks['sf_raw'])}", 10, True)
                block(f"Saved vs strut: {_num(None if card['weight_saved_vs_strut'] is None else 100*card['weight_saved_vs_strut'])}%  |  "
                    f"vs block: {_num(100*card['weight_saved_vs_block'])}%  |  "
                    f"${_num(card['material_cost_usd'])} material cost only, not print cost")
                for i, case in enumerate(p["load_cases"]):
                    forces = "; ".join(f"{ld['pad_id']}: ({ld['fx_N']:g}, {ld['fy_N']:g}, {ld['fz_N_out_of_plane']:g}) N" for ld in case["loads"])
                    block(f"{case['name']} | {forces} | deflection {_num(checks['deflection_mm'][i])} / "
                        f"{_num(checks['deflection_limit_mm'][i])} mm", 7.3)
                block(f"Worst reported stress {_num(checks['stress_reported_MPa'])} MPa; "
                      f"raw peak {_num(checks['stress_raw_MPa'])} MPa.", 7.3)
                for hand in checks["out_of_plane"] + checks["bearing"]:
                    block(f"{'PASS' if hand['passed'] else 'FAIL'}: {hand['name']} | SF {_num(hand['sf'])} | {hand['where']}", 7)
            else:
                block("No evaluable design. " + "; ".join(d["reasons"]), 9, True)
            if not d["converged"]:
                block("Not fully converged at the iteration limit.", 8, True)
            if d["reasons"]:
                block("Result notes: " + "; ".join(d["reasons"]), 7)
            block(f"Material: E {m.E:g} MPa; nu {m.nu:g}; XY {m.strength:g} MPa ({m.strength_kind}); "
                f"Z {m.strength_z_used()[0]:g} MPa ({m.strength_z_used()[1]}); density {m.density:g} g/cm3. "
                + m.condition_note, 7)
            shear_note = "datasheet value" if m.interlayer_shear is not None else "Z / sqrt(3), conservative stand-in"
            block(f"Interlayer shear allowable: {_num(m.interlayer_shear_used()[0])} MPa ({shear_note}).", 7)
            block("Sources (click titles for original citations)", 8, True)
            seen = set()
            for cit in [*m.citations.values(), proc.citation]:
                if (cit.short(), cit.url) in seen:
                    continue
                seen.add((cit.short(), cit.url))
                block(cit.short(), 7, link=cit.url)
            block("Limits", 8, True)
            block(LIMITS, 8)
            if "bracket" in p["name"].lower() and "aero" in p["name"].lower():
                block("25 mm 2D slice carrying the full challenge load; not comparable to the GE 3D challenge results.", 7)
            if pdf.get_y() > 282:
                raise ValueError(f"report content exceeds one page for {m.id}; shorten text or adjust layout")
            pdf.set_y(285)
            block(f"Code {data['code_version'][:48]} | cache {data['key'][:16]} | {pdf.page_no()}/{len(designs)}", 6)
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output))
    return output
