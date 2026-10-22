"""Images and charts: shape and stress maps (PNG), the problem drawing, the Pareto chart,
the 3D view and the validation plots. Colors and fonts come from theme.py."""

from __future__ import annotations

import io
import math

import numpy as np
import plotly.graph_objects as go
from PIL import Image

from app import theme
from morphic.problem import Problem


# ----------------------------------------------------------------------------- color helpers
def _hex(c: str) -> tuple[float, float, float, float]:
    c = c.strip()
    if c.startswith("rgba"):
        r, g, b, a = [float(v) for v in c[5:-1].split(",")]
        return r, g, b, a * 255
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255.0


def sig(x: float, n: int = 3) -> str:
    """A number to ``n`` significant figures with thousands separators: 42271.1 -> '42,300', 32 -> '32', 0.5 -> '0.5'."""
    x = float(x)
    if x == 0 or not math.isfinite(x):
        return f"{x:g}"
    d = n - int(math.floor(math.log10(abs(x)))) - 1
    s = f"{round(x, d):,.{max(d, 0)}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def _lut(scale: list, n: int = 256) -> np.ndarray:
    pos = np.array([p for p, _ in scale])
    cols = np.array([_hex(c) for _, c in scale])
    t = np.linspace(0, 1, n)
    out = np.stack([np.interp(t, pos, cols[:, k]) for k in range(4)], axis=1)
    return out.astype(np.uint8)


def to_grid(values: np.ndarray, nelx: int, nely: int) -> np.ndarray:
    """Element or node vector (x-major, as in fe.Mesh) -> image rows (y down), columns (x)."""
    return np.asarray(values).reshape(nelx, nely).T[::-1]


def _png(rgba: np.ndarray, scale: int) -> bytes:
    im = Image.fromarray(rgba, "RGBA")
    if scale > 1:
        im = im.resize((im.width * scale, im.height * scale), Image.BICUBIC)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _scale_for(nelx: int, target_px: int = 900) -> int:
    return max(1, min(6, round(target_px / max(nelx, 1))))


def density_png(density: np.ndarray, nelx: int, nely: int, dark: bool = True, target_px: int = 900) -> bytes:
    """The shape: transparent void, material in light grey (dark stage) or near-black (light)."""
    g = np.clip(to_grid(density, nelx, nely).astype(float), 0, 1)
    lut = _lut(theme.DENSITY_SCALE if dark else theme.DENSITY_SCALE_LIGHT)
    idx = (g * 255).astype(np.uint8)
    rgba = lut[idx]
    # void transparent, low density faint (so a uniform 10% start frame still reads as a block), solid opaque
    rgba[..., 3] = (np.clip(g, 0, 1) ** 0.6 * 255).astype(np.uint8)
    return _png(rgba, _scale_for(nelx, target_px))


def utilization_png(util: np.ndarray, nelx: int, nely: int, target_px: int = 900) -> bytes:
    """Recovered nodal utilization on a shared 0..1 scale; above 1 in the over-limit red; void masked."""
    g = to_grid(util, nelx + 1, nely + 1).astype(float)
    mask = np.isfinite(g)
    lut = _lut(theme.UTIL_SCALE)
    v = np.where(mask, g, 0.0)
    idx = (np.clip(v, 0, 1) * 255).astype(np.uint8)
    rgba = lut[idx].copy()
    over = mask & (v > 1.0)
    rgba[over] = np.array(_hex(theme.OVER_LIMIT), dtype=np.uint8)
    rgba[..., 3] = np.where(mask, 255, 0).astype(np.uint8)
    # node grid -> image pixels; bicubic upscale gives the smooth shading between nodes
    return _png(rgba, _scale_for(nelx + 1, target_px))


def utilization_legend(dark: bool) -> str:
    stops = ", ".join(f"{c} {p * 100:.0f}%" for p, c in theme.UTIL_SCALE)
    txt = "var(--mx-text-2)"
    return (f'<div style="display:flex;align-items:center;gap:10px;font-size:{theme.TEXT_XS}px;color:{txt}">'
            f'<span>0</span><div style="flex:1;height:6px;border-radius:999px;background:linear-gradient(90deg,{stops})"></div>'
            f'<span>1.0 = limit</span><span style="display:inline-block;width:10px;height:10px;border-radius:3px;'
            f'background:{theme.OVER_LIMIT}"></span><span>above limit</span>'
            f'<span style="margin-left:auto">utilization = σ<sub>vm</sub> × SF<sub>target</sub> / strength</span></div>')


# ----------------------------------------------------------------------------- problem drawing
def _circle(cx, cy, r, n=48):
    t = np.linspace(0, 2 * np.pi, n)
    return cx + r * np.cos(t), cy + r * np.sin(t)


def _pad_label(p, side: str) -> dict:
    """Where a pad's name goes: just outside the ring on the given side, a few pixels clear of it."""
    r = p.ring_r_mm
    if side == "above":
        return dict(x=p.cx, y=p.cy + r, xanchor="center", yanchor="bottom", yshift=4)
    if side == "right":
        return dict(x=p.cx + r, y=p.cy, xanchor="left", yanchor="middle", xshift=6)
    if side == "left":
        return dict(x=p.cx - r, y=p.cy, xanchor="right", yanchor="middle", xshift=-6)
    return dict(x=p.cx, y=p.cy - r, xanchor="center", yanchor="top", yshift=-4)


def pad_label_side(support: str | None, busy: set[str]) -> str:
    """The first free side for a pad's name. A pin and a slide_x draw their symbol under the pad, a slide_y
    draws it to the left; ``busy`` holds the sides a load arrow comes from. Below is the default."""
    taken = set(busy)
    if support in ("pin", "slide_x"):
        taken.add("below")
    elif support == "slide_y":
        taken.add("left")
    return next((sd for sd in ("below", "above", "right", "left") if sd not in taken), "below")


def problem_drawing(problem: Problem, dark: bool = True, height: int = 420) -> go.Figure:
    """Spec 11, step 2: pads, supports (pins as triangles, slides as rollers with the free direction),
    loads as arrows scaled by size with one color per case, keep-in solid, keep-out hatched, dimensions.
    Defaults are drawn in the amber tint. On the dark stage every pad carries a soft glow and each
    load arrow a faint wide stroke beneath it, so the drawing reads like a lit instrument panel.
    Pad names move to a free side of the pad so they never sit on a support symbol or an arrow, and
    the axes are widened so every arrow tail and force label stays inside the drawing."""
    s = theme.surface(dark)
    W, H = problem.design_space.width_mm, problem.design_space.height_mm
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=W, y1=H, line=dict(color=s["text_2"], width=1.2),
                  fillcolor=s["card_alt"], layer="below")
    scale = max(W, H)
    pad = 0.12 * scale
    # the drawing is about 520 px wide at the default layout: labels need this much room in mm
    mm_per_px = (W + 1.6 * pad) / 520

    def room(text: str) -> float:
        return (0.62 * (theme.TEXT_XS + 1) * len(text) + 10) * mm_per_px

    # the load arrows as geometry first: their tails decide where pad names go and how wide the axes are
    fmax = max((abs(ld.fx_N) + abs(ld.fy_N)) for lc in problem.load_cases for ld in lc.loads) or 1.0
    arrows, out_of_plane, busy = [], [], {}
    lab_x, lab_y = [], []  # where labels need the axes to reach
    for ci, lc in enumerate(problem.load_cases):
        col = theme.LOAD_CASE_COLORS[ci % len(theme.LOAD_CASE_COLORS)]
        for ld in lc.loads:
            p = problem.pad(ld.pad_id)
            mag = float(np.hypot(ld.fx_N, ld.fy_N))
            if mag > 0:
                L = 0.12 * scale * (0.35 + 0.65 * mag / fmax)
                ux, uy = ld.fx_N / mag, ld.fy_N / mag
                x0, y0 = p.cx - ux * (L + p.ring_r_mm), p.cy - uy * (L + p.ring_r_mm)
                arrows.append((p, col, ux, uy, x0, y0, mag))
                sides = busy.setdefault(p.id, set())
                if uy < -0.3:
                    sides.add("above")  # the arrow comes down onto the pad
                if uy > 0.3:
                    sides.add("below")
                if ux > 0.3:
                    sides.add("left")
                if ux < -0.3:
                    sides.add("right")
            if ld.fz_N_out_of_plane:
                out_of_plane.append((p, col, lc, ld))
    # pad glows first so everything else draws on top of them
    for i, p in enumerate(problem.pads):
        ring_default = problem.source_of(f"pads[{i}].ring_r_mm").source == "default"
        base = theme.DEFAULT_AMBER if ring_default else s["text"]
        for k, alpha in theme.PAD_GLOW_RINGS:
            x, y = _circle(p.cx, p.cy, p.ring_r_mm * k, 40)
            fig.add_trace(go.Scatter(x=x, y=y, fill="toself", mode="lines", line=dict(width=0),
                                     fillcolor=theme.rgba(base, alpha), hoverinfo="skip", showlegend=False))
    for z in problem.zones:
        if z.shape == "circle":
            x, y = _circle(z.circle.cx, z.circle.cy, z.circle.r)
        else:
            r = z.rect
            x = [r.x, r.x + r.w, r.x + r.w, r.x, r.x]
            y = [r.y, r.y, r.y + r.h, r.y + r.h, r.y]
        if z.kind == "keep_in":
            fig.add_trace(go.Scatter(x=x, y=y, fill="toself", mode="lines", line=dict(color=s["text_2"], width=1),
                                     fillcolor="rgba(120,120,128,0.35)", name=f"keep-in {z.id}", hoverinfo="name"))
        else:
            fig.add_trace(go.Scatter(x=x, y=y, fill="toself", mode="lines", line=dict(color=s["text_2"], width=1),
                                     fillcolor="rgba(120,120,128,0.18)",
                                     fillpattern=dict(shape="/", fgcolor=s["text_2"], bgcolor="rgba(0,0,0,0)", size=6),
                                     name=f"keep-out {z.id}", hoverinfo="name"))
    sup = {sp.pad_id: sp.type for sp in problem.supports}
    for i, p in enumerate(problem.pads):
        hole_default = problem.source_of(f"pads[{i}].hole_r_mm").source == "default"
        ring_default = problem.source_of(f"pads[{i}].ring_r_mm").source == "default"
        x, y = _circle(p.cx, p.cy, p.ring_r_mm)
        fig.add_trace(go.Scatter(x=x, y=y, fill="toself", mode="lines",
                                 line=dict(color=theme.DEFAULT_AMBER if ring_default else s["text_2"], width=1),
                                 fillcolor=theme.DEFAULT_AMBER_SOFT if ring_default else s["pad_fill"],
                                 name=f"pad {p.id}: ring r {p.ring_r_mm:g} mm", hoverinfo="name"))
        if p.hole_r_mm > 0:
            x, y = _circle(p.cx, p.cy, p.hole_r_mm)
            fig.add_trace(go.Scatter(x=x, y=y, fill="toself", mode="lines",
                                     line=dict(color=theme.DEFAULT_AMBER if hole_default else s["text_2"], width=1),
                                     fillcolor=theme.DEFAULT_AMBER_SOFT if hole_default else s["bg"],
                                     name=f"pad {p.id}: hole r {p.hole_r_mm:g} mm" + (" (default)" if hole_default else ""),
                                     hoverinfo="name"))
        t = sup.get(p.id)
        side = pad_label_side(t, busy.get(p.id, set()))
        fig.add_annotation(**_pad_label(p, side), text=p.id, showarrow=False,
                           font=dict(size=theme.TEXT_XS + 1, color=s["text"]))
        if side == "right":
            lab_x.append(p.cx + p.ring_r_mm + room(p.id))
        elif side == "left":
            lab_x.append(p.cx - p.ring_r_mm - room(p.id))
        elif side == "above":
            lab_y.append(p.cy + p.ring_r_mm + 18 * mm_per_px)
        else:
            lab_y.append(p.cy - p.ring_r_mm - 18 * mm_per_px)
        if t == "pin":
            a = 0.05 * scale
            fig.add_trace(go.Scatter(x=[p.cx, p.cx - a / 2, p.cx + a / 2, p.cx], y=[p.cy, p.cy - a, p.cy - a, p.cy],
                                     fill="toself", mode="lines", line=dict(color=s["text"], width=1),
                                     fillcolor=s["text"], name=f"{p.id}: pin (x and y held)", hoverinfo="name"))
        elif t in ("slide_x", "slide_y"):
            a = 0.05 * scale
            r = a * 0.22
            if t == "slide_x":  # free in x, y held: rollers under the pad, arrow along x
                cx1, cy1 = p.cx - r * 1.4, p.cy - a * 0.55
                cx2, cy2 = p.cx + r * 1.4, p.cy - a * 0.55
                ax, ay = (p.cx - a, p.cy - a * 1.25), (p.cx + a, p.cy - a * 1.25)
            else:  # free in y, x held
                cx1, cy1 = p.cx - a * 0.55, p.cy - r * 1.4
                cx2, cy2 = p.cx - a * 0.55, p.cy + r * 1.4
                ax, ay = (p.cx - a * 1.25, p.cy - a), (p.cx - a * 1.25, p.cy + a)
            for cx, cy in ((cx1, cy1), (cx2, cy2)):
                x, y = _circle(cx, cy, r, 24)
                fig.add_trace(go.Scatter(x=x, y=y, fill="toself", mode="lines", line=dict(color=s["text"], width=1),
                                         fillcolor=s["text"], name=f"{p.id}: {t} (free along {t[-1]})", hoverinfo="name"))
            fig.add_annotation(x=ay[0], y=ay[1], ax=ax[0], ay=ax[1], xref="x", yref="y", axref="x", ayref="y",
                               showarrow=True, arrowhead=3, arrowsize=1.1, arrowwidth=1.2, arrowcolor=s["text_2"],
                               startarrowhead=3, text="")
    # loads: one color per case, arrow length scaled by force; the force sits at the tail, the case name
    # and limit are in the pill of the same color under the drawing
    for p, col, ux, uy, x0, y0, mag in arrows:
        tip = dict(x=p.cx - ux * p.ring_r_mm, y=p.cy - uy * p.ring_r_mm, ax=x0, ay=y0,
                   xref="x", yref="y", axref="x", ayref="y", showarrow=True, text="")
        if dark:  # the glow: a wide, faint stroke under the crisp arrow
            fig.add_annotation(**tip, arrowhead=0, arrowwidth=theme.ARROW_GLOW_WIDTH, arrowcolor=col,
                               opacity=theme.ARROW_GLOW_OPACITY)
        fig.add_annotation(**tip, arrowhead=2, arrowsize=1.2, arrowwidth=2.2, arrowcolor=col)
        text = f"{sig(mag)} N"
        if uy > 0.3 and y0 < 0:  # the tail hangs below the part, where the dimension texts are: label beside it
            xa, ya, xs, ys = "left", "middle", 8, 0
        else:
            xa = "right" if ux > 0.3 else ("left" if ux < -0.3 else "center")
            ya = "top" if uy > 0.3 else ("bottom" if uy < -0.3 else "middle")
            xs = -6 if ux > 0.3 else (6 if ux < -0.3 else 0)
            ys = -4 if uy > 0.3 else (4 if uy < -0.3 else 0)
        fig.add_annotation(x=x0, y=y0, text=text, showarrow=False, xanchor=xa, yanchor=ya, xshift=xs, yshift=ys,
                           font=dict(family=theme.FONT_MONO, size=theme.TEXT_XS + 1, color=col))
        # the room the label needs around the tail
        w = room(text)
        lab_x += [x0 - (w if xa == "right" else w / 2), x0 + (w if xa == "left" else w / 2)]
        lab_y += [y0 - (18 if ya == "top" else 9) * mm_per_px, y0 + (18 if ya == "bottom" else 9) * mm_per_px]
    for p, col, lc, ld in out_of_plane:
        fig.add_trace(go.Scatter(x=[p.cx], y=[p.cy], mode="markers",
                                 marker=dict(symbol="circle-open-dot", size=16, color=col, line=dict(width=2)),
                                 name=f"{lc.name}: {ld.fz_N_out_of_plane:g} N out of plane (hand check)",
                                 hoverinfo="name"))
    # dimensions
    off = 0.06 * scale
    for (x0, y0, x1, y1, text, xs, ys) in ((0, -off, W, -off, f"{W:g} mm", 0, -16), (-off, 0, -off, H, f"{H:g} mm", -22, 0)):
        fig.add_shape(type="line", x0=x0, y0=y0, x1=x1, y1=y1, line=dict(color=s["text_2"], width=1))
        fig.add_annotation(x=(x0 + x1) / 2, y=(y0 + y1) / 2, text=text, showarrow=False, xshift=xs, yshift=ys,
                           font=dict(family=theme.FONT_MONO, size=theme.TEXT_XS, color=s["text_2"]), textangle=0 if ys else -90)
    # the thickness note sits under the width, centred, so the bottom-right corner stays free for arrow labels
    fig.add_annotation(x=W / 2, y=-off, text=f"thickness {problem.thickness_mm:g} mm (extruded)", showarrow=False,
                       xanchor="center", yshift=-31, font=dict(family=theme.FONT_MONO, size=theme.TEXT_XS, color=s["text_2"]))
    x_lo, x_hi = min([-pad] + lab_x), max([W + pad * 0.5] + lab_x)
    y_lo, y_hi = min([-pad, -off - 42 * mm_per_px] + lab_y), max([H + pad * 0.5] + lab_y)
    # fit the height to the part's aspect so a long thin part does not sit in empty space
    height = int(max(240, min(height, 700 * (y_hi - y_lo) / (x_hi - x_lo))))
    fig.update_layout(**theme.plotly_layout(dark, height=height, margin=dict(l=4, r=4, t=4, b=4)))
    fig.update_xaxes(range=[x_lo, x_hi], visible=False, constrain="domain")
    fig.update_yaxes(range=[y_lo, y_hi], visible=False, scaleanchor="x", scaleratio=1)
    return fig


# ----------------------------------------------------------------------------- pareto
# label slots in order of preference: (Plotly textposition, x direction, y direction with y down)
_LABEL_SLOTS = (("top center", 0, -1), ("bottom center", 0, 1), ("middle right", 1, 0), ("middle left", -1, 0),
                ("top right", 1, -1), ("top left", -1, -1), ("bottom right", 1, 1), ("bottom left", -1, 1))


def _overlap(a: tuple, b: tuple) -> float:
    """Overlap area of two boxes (x0, y0, x1, y1)."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def place_labels(points: list[tuple[float, float, str, float]], plot_w: float, plot_h: float,
                 font_px: float = theme.TEXT_XS) -> list[str]:
    """One Plotly textposition per point so the labels do not sit on each other, on other markers or
    outside the plot. Works in approximate pixel space: ``points`` are (px, py, text, marker radius)
    with py measured downward. Greedy, in the given order (put the important points first): each
    label takes the first slot with no overlap, otherwise the slot with the least."""
    markers = [(px - r, py - r, px + r, py + r) for px, py, _, r in points]
    taken: list[tuple] = []
    out = []
    for i, (px, py, text, r) in enumerate(points):
        w, h = 0.62 * font_px * len(text) + 4, font_px * 1.3
        others = [m for j, m in enumerate(markers) if j != i] + taken
        best, best_box, best_cost = _LABEL_SLOTS[0][0], None, None
        for name, hx, hy in _LABEL_SLOTS:
            gap = r + 2 if (hx == 0 or hy == 0) else r * 0.75
            cx, cy = px + hx * (gap + w / 2), py + hy * (gap + h / 2)
            box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            cost = sum(_overlap(box, b) for b in others)
            cost += (max(0.0, -box[0]) + max(0.0, box[2] - plot_w)) * h + (max(0.0, -box[1]) + max(0.0, box[3] - plot_h)) * w
            if best_cost is None or cost < best_cost - 1e-9:
                best, best_box, best_cost = name, box, cost
            if cost == 0:
                break
        taken.append(best_box)
        out.append(best)
    return out


def pareto_chart(points: list[dict], dark: bool, caption: str, height: int = 320, winner: str | None = None,
                 plot_w: int = 640) -> go.Figure:
    """Mass against material cost, one point per material. Ranked designs are filled in their process
    color, the rest hollow and grey; the winner gets a soft halo and a bold name. Labels are placed
    so they do not overlap (``plot_w`` is the plot width the placement assumes, in px)."""
    s = theme.surface(dark)
    fig = go.Figure()
    pts = [p for p in points if p["mass_g"] is not None and p["cost_usd"] is not None]
    pts.sort(key=lambda p: (p["state"] != "ranked", p["mass_g"]))  # the important points place their labels first
    front = sorted([p for p in pts if p.get("on_front")], key=lambda p: p["mass_g"])
    if len(front) > 1:
        fig.add_trace(go.Scatter(x=[p["mass_g"] for p in front], y=[p["cost_usd"] for p in front], mode="lines",
                                 line=dict(color=s["text_2"], width=1, dash="dot"), hoverinfo="skip"))
    if pts:
        xs, ys = [p["mass_g"] for p in pts], [p["cost_usd"] for p in pts]
        xspan = max(max(xs) - min(xs), 0.2 * abs(max(xs)), 1e-9)
        yspan = max(max(ys) - min(ys), 0.2 * abs(max(ys)), 1e-9)
        xr = [min(xs) - 0.16 * xspan, max(xs) + 0.16 * xspan]
        yr = [min(ys) - 0.22 * yspan, max(ys) + 0.22 * yspan]
        if min(ys) >= 0:
            yr[0] = max(0.0, yr[0])
    else:
        xr, yr = [0, 1], [0, 1]
    plot_h = max(120, height - 80)
    px = [(p["mass_g"] - xr[0]) / (xr[1] - xr[0]) * plot_w for p in pts]
    py = [(1 - (p["cost_usd"] - yr[0]) / (yr[1] - yr[0])) * plot_h for p in pts]
    sizes = [13 if p["state"] == "ranked" else 11 for p in pts]
    positions = place_labels([(x, y, p["material_id"], sz / 2) for x, y, p, sz in zip(px, py, pts, sizes)], plot_w, plot_h)
    for p, sz, pos in zip(pts, sizes, positions):
        pc = theme.PROCESS.get(p["process_id"], {}).get("color", theme.MUTED)
        ranked = p["state"] == "ranked"
        win = winner is not None and p["material_id"] == winner
        if win:  # the highlighted point: a soft halo in its process color, fading outward
            for k, alpha in theme.POINT_HALO_RINGS:
                fig.add_trace(go.Scatter(x=[p["mass_g"]], y=[p["cost_usd"]], mode="markers", hoverinfo="skip",
                                         marker=dict(size=sz * k, color=theme.rgba(pc, alpha), line=dict(width=0))))
        fig.add_trace(go.Scatter(
            x=[p["mass_g"]], y=[p["cost_usd"]], mode="markers+text",
            text=[f"<b>{p['material_id']}</b>" if win else p["material_id"]], textposition=pos,
            textfont=dict(size=theme.TEXT_XS, color=s["text"] if ranked else s["text_2"]),
            marker=dict(size=sz, color=pc if ranked else "rgba(0,0,0,0)",
                        line=dict(color=pc if ranked else s["text_2"], width=1.5 if ranked else 1.2),
                        opacity=1.0 if ranked else 0.7),
            hovertemplate=(f"<b>{p['material_id']}</b> · {theme.PROCESS.get(p['process_id'], {}).get('label', p['process_id'])}"
                           f"<br>{p['mass_g']:.2f} g · ${p['cost_usd']:.2f}"
                           + (f"<br>{p['reason']}" if p.get("reason") else "") + "<extra></extra>")))
    fig.add_annotation(xref="paper", yref="paper", x=1, y=1, xanchor="right", yanchor="bottom", yshift=6, text=caption,
                       showarrow=False, font=dict(size=theme.TEXT_XS, color=s["text_2"]))
    fig.update_layout(**theme.plotly_layout(dark, height=height, margin=dict(l=8, r=8, t=30, b=8)))
    fig.update_xaxes(**theme.plotly_axis(dark, "mass (g)"), range=xr, nticks=6)
    fig.update_yaxes(**theme.plotly_axis(dark, "material cost per part ($)"), range=yr, nticks=6)
    return fig


# ----------------------------------------------------------------------------- 3D
def part_3d(stl_path, util_nodes: np.ndarray, nelx: int, nely: int, h: float, dark: bool = True,
            height: int = 560) -> go.Figure:
    import trimesh

    m = trimesh.load_mesh(str(stl_path))
    v, f = np.asarray(m.vertices), np.asarray(m.faces)
    # nearest node utilization for each vertex (node grid is x-major, spacing h)
    g = np.asarray(util_nodes, dtype=float).reshape(nelx + 1, nely + 1)
    i = np.clip(np.rint(v[:, 0] / h).astype(int), 0, nelx)
    j = np.clip(np.rint(v[:, 1] / h).astype(int), 0, nely)
    u = g[i, j]
    # a vertex on the boundary may sit next to a masked node: take the nearest finite neighbour
    bad = ~np.isfinite(u)
    if bad.any():
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            ii = np.clip(i[bad] + di, 0, nelx)
            jj = np.clip(j[bad] + dj, 0, nely)
            cand = g[ii, jj]
            fill = np.isfinite(cand)
            idx = np.nonzero(bad)[0][fill]
            u[idx] = cand[fill]
            bad = ~np.isfinite(u)
            if not bad.any():
                break
        u[bad] = 0.0
    scale = [[p, c] for p, c in theme.UTIL_SCALE]
    cmax = max(1.0, float(np.nanmax(u)) if u.size else 1.0)
    if cmax > 1.0:
        scale = [[p / cmax, c] for p, c in theme.UTIL_SCALE] + [[min(1.0, 1.0001 / cmax), theme.OVER_LIMIT], [1.0, theme.OVER_LIMIT]]
    s = theme.surface(dark)
    fig = go.Figure(go.Mesh3d(x=v[:, 0], y=v[:, 1], z=v[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2],
                              intensity=u, colorscale=scale, cmin=0, cmax=cmax, flatshading=False,
                              lighting=dict(ambient=0.55, diffuse=0.7, specular=0.25, roughness=0.6, fresnel=0.1),
                              lightposition=dict(x=200, y=300, z=600),
                              colorbar=dict(title=dict(text="utilization", font=dict(size=theme.TEXT_XS)),
                                            thickness=8, len=0.5, tickfont=dict(size=theme.TEXT_XS, color=s["text_2"])),
                              hovertemplate="utilization %{intensity:.2f}<extra></extra>"))
    ax = dict(visible=False, showbackground=False)
    fig.update_layout(**theme.plotly_layout(dark, height=height, margin=dict(l=0, r=0, t=0, b=0)),
                      scene=dict(xaxis=ax, yaxis=ax, zaxis=ax, aspectmode="data", bgcolor="rgba(0,0,0,0)",
                                 camera=dict(eye=dict(x=1.4, y=-1.6, z=1.1))))
    return fig


# ----------------------------------------------------------------------------- validation plots
def _legend_above(dark: bool) -> dict:
    """A legend row above the plot area, so it never sits on a line."""
    return dict(orientation="h", x=0, xanchor="left", y=1.0, yanchor="bottom", bgcolor="rgba(0,0,0,0)",
                font=dict(size=theme.TEXT_XS, color=theme.surface(dark)["text_2"]), itemwidth=30)


def mesh_refinement_plot(rows: list[dict], dark: bool, height: int = 300) -> go.Figure:
    s = theme.surface(dark)
    x = [r["elements_through_depth"] for r in rows]
    fig = go.Figure()
    for key, name, col in (("delta_error", "tip deflection", theme.ACCENT), ("sigma_error", "surface stress (recovered)", s["text"]),
                           ("sigma_centre_error", "element-centre stress", s["text_2"])):
        fig.add_trace(go.Scatter(x=x, y=[max(r[key], 1e-6) for r in rows], mode="lines+markers", name=name,
                                 line=dict(color=col, width=1.5), marker=dict(size=7, color=col),
                                 hovertemplate=f"{name}<br>%{{x}} elements: %{{y:.2%}}<extra></extra>"))
    tol = rows[0]["tolerance"]
    fig.add_hline(y=tol, line=dict(color=theme.PASS, width=1, dash="dot"))
    fig.add_annotation(xref="paper", x=1, xanchor="right", yref="y", y=np.log10(tol), yanchor="top", yshift=-2,
                       text=f"{tol:.0%} target", showarrow=False, font=dict(size=theme.TEXT_XS, color=theme.PASS))
    fig.update_layout(**theme.plotly_layout(dark, height=height, showlegend=True, legend=_legend_above(dark),
                                            margin=dict(l=8, r=8, t=44, b=8)))
    fig.update_xaxes(**theme.plotly_axis(dark, "elements through the depth"), type="log", tickvals=x,
                     ticktext=[str(v) for v in x])
    lo = min(max(r[k], 1e-6) for r in rows for k in ("delta_error", "sigma_error", "sigma_centre_error"))
    ticks = [t for t in (1e-5, 1e-4, 1e-3, 1e-2, 1e-1, 1.0) if t >= lo * 0.5]
    fig.update_yaxes(**theme.plotly_axis(dark, "error"), type="log", tickvals=ticks,
                     ticktext=[f"{t:.{max(0, -int(np.floor(np.log10(t))) - 2)}%}" for t in ticks],
                     range=[np.log10(lo * 0.5), np.log10(max(max(r["delta_error"] for r in rows) * 3, tol * 3))])
    return fig


def hole_plot(rows: list[dict], dark: bool, height: int = 300) -> go.Figure:
    s = theme.surface(dark)
    x = [r["elements_per_radius"] for r in rows]
    fig = go.Figure()
    for key, name, col in (("error_without_recovery", "element centre (no recovery)", s["text_2"]),
                           ("error_with_recovery", "recovered nodal, boundary max", theme.ACCENT),
                           ("error_at_90deg_node", "recovered nodal at the 90° node", s["text"])):
        fig.add_trace(go.Scatter(x=x, y=[r[key] for r in rows], mode="lines+markers", name=name,
                                 line=dict(color=col, width=1.5), marker=dict(size=7, color=col),
                                 hovertemplate=f"{name}<br>%{{x}} per radius: %{{y:.1%}}<extra></extra>"))
    fig.add_hline(y=0.05, line=dict(color=theme.PASS, width=1, dash="dot"), annotation_text="5% target",
                  annotation_position="bottom left", annotation_font=dict(size=theme.TEXT_XS, color=theme.PASS))
    fig.update_layout(**theme.plotly_layout(dark, height=height, showlegend=True, legend=_legend_above(dark),
                                            margin=dict(l=8, r=8, t=44, b=8)))
    fig.update_xaxes(**theme.plotly_axis(dark, "elements per hole radius"), type="log", tickvals=x,
                     ticktext=[str(v) for v in x])
    fig.update_yaxes(**theme.plotly_axis(dark, "error vs K_t (finite width)"), tickformat=".0%", rangemode="tozero", nticks=5)
    return fig
