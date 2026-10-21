"""Images and charts: shape and stress maps (PNG), the problem drawing, the Pareto chart,
the 3D view and the validation plots. Colors and fonts come from theme.py."""

from __future__ import annotations

import io

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


def problem_drawing(problem: Problem, dark: bool = False, height: int = 420) -> go.Figure:
    """Spec 11, step 2: pads, supports (pins as triangles, slides as rollers with the free direction),
    loads as arrows scaled by size with one color per case, keep-in solid, keep-out hatched, dimensions.
    Defaults are drawn in the amber tint."""
    s = theme.surface(dark)
    W, H = problem.design_space.width_mm, problem.design_space.height_mm
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=W, y1=H, line=dict(color=s["text_2"], width=1.2),
                  fillcolor=s["card_alt"], layer="below")
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
    scale = max(W, H)
    for i, p in enumerate(problem.pads):
        hole_default = problem.source_of(f"pads[{i}].hole_r_mm").source == "default"
        ring_default = problem.source_of(f"pads[{i}].ring_r_mm").source == "default"
        x, y = _circle(p.cx, p.cy, p.ring_r_mm)
        fig.add_trace(go.Scatter(x=x, y=y, fill="toself", mode="lines",
                                 line=dict(color=theme.DEFAULT_AMBER if ring_default else s["text_2"], width=1),
                                 fillcolor=theme.DEFAULT_AMBER_SOFT if ring_default else "rgba(120,120,128,0.30)",
                                 name=f"pad {p.id}: ring r {p.ring_r_mm:g} mm", hoverinfo="name"))
        if p.hole_r_mm > 0:
            x, y = _circle(p.cx, p.cy, p.hole_r_mm)
            fig.add_trace(go.Scatter(x=x, y=y, fill="toself", mode="lines",
                                     line=dict(color=theme.DEFAULT_AMBER if hole_default else s["text_2"], width=1),
                                     fillcolor=theme.DEFAULT_AMBER_SOFT if hole_default else s["card"],
                                     name=f"pad {p.id}: hole r {p.hole_r_mm:g} mm" + (" (default)" if hole_default else ""),
                                     hoverinfo="name"))
        fig.add_annotation(x=p.cx, y=p.cy, text=p.id, showarrow=False,
                           font=dict(size=theme.TEXT_XS, color=s["text"]), yshift=-p.ring_r_mm / scale * 300 - 10)
        t = sup.get(p.id)
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
    # loads: one color per case, arrow length scaled by force
    fmax = max((abs(ld.fx_N) + abs(ld.fy_N)) for lc in problem.load_cases for ld in lc.loads) or 1.0
    for ci, lc in enumerate(problem.load_cases):
        col = theme.LOAD_CASE_COLORS[ci % len(theme.LOAD_CASE_COLORS)]
        for ld in lc.loads:
            p = problem.pad(ld.pad_id)
            mag = np.hypot(ld.fx_N, ld.fy_N)
            if mag > 0:
                L = 0.12 * scale * (0.35 + 0.65 * mag / fmax)
                ux, uy = ld.fx_N / mag, ld.fy_N / mag
                x0, y0 = p.cx - ux * (L + p.ring_r_mm), p.cy - uy * (L + p.ring_r_mm)
                fig.add_annotation(x=p.cx - ux * p.ring_r_mm, y=p.cy - uy * p.ring_r_mm, ax=x0, ay=y0,
                                   xref="x", yref="y", axref="x", ayref="y", showarrow=True, arrowhead=2,
                                   arrowsize=1.2, arrowwidth=2.2, arrowcolor=col, text="")
                # label beyond the arrow tail, on the side the arrow comes from
                fig.add_annotation(x=x0, y=y0, text=f"{lc.name}: {mag:g} N", showarrow=False,
                                   font=dict(size=theme.TEXT_XS, color=col),
                                   xanchor="right" if ux > 0.3 else ("left" if ux < -0.3 else "center"),
                                   yanchor="top" if uy > 0.3 else ("bottom" if uy < -0.3 else "middle"),
                                   xshift=-6 if ux > 0.3 else (6 if ux < -0.3 else 0),
                                   yshift=-4 if uy > 0.3 else (4 if uy < -0.3 else 0))
            if ld.fz_N_out_of_plane:
                fig.add_trace(go.Scatter(x=[p.cx], y=[p.cy], mode="markers",
                                         marker=dict(symbol="circle-open-dot", size=16, color=col, line=dict(width=2)),
                                         name=f"{lc.name}: {ld.fz_N_out_of_plane:g} N out of plane (hand check)",
                                         hoverinfo="name"))
    # dimensions
    off = 0.06 * scale
    for (x0, y0, x1, y1, text, xs, ys) in ((0, -off, W, -off, f"{W:g} mm", 0, -16), (-off, 0, -off, H, f"{H:g} mm", -22, 0)):
        fig.add_shape(type="line", x0=x0, y0=y0, x1=x1, y1=y1, line=dict(color=s["text_2"], width=1))
        fig.add_annotation(x=(x0 + x1) / 2, y=(y0 + y1) / 2, text=text, showarrow=False, xshift=xs, yshift=ys,
                           font=dict(size=theme.TEXT_XS, color=s["text_2"]), textangle=0 if ys else -90)
    fig.add_annotation(x=W, y=-off, text=f"thickness {problem.thickness_mm:g} mm (extruded)", showarrow=False,
                       xanchor="right", yshift=-16, font=dict(size=theme.TEXT_XS, color=s["text_2"]))
    pad = 0.12 * scale
    # fit the height to the part's aspect so a long thin part does not sit in empty space
    height = int(max(240, min(height, 700 * (H + 1.6 * pad) / (W + 1.6 * pad))))
    fig.update_layout(**theme.plotly_layout(dark, height=height, margin=dict(l=4, r=4, t=4, b=4)))
    fig.update_xaxes(range=[-pad, W + pad * 0.5], visible=False, constrain="domain")
    fig.update_yaxes(range=[-pad, H + pad * 0.5], visible=False, scaleanchor="x", scaleratio=1)
    return fig


# ----------------------------------------------------------------------------- pareto
def pareto_chart(points: list[dict], dark: bool, caption: str, height: int = 320) -> go.Figure:
    s = theme.surface(dark)
    fig = go.Figure()
    front = sorted([p for p in points if p.get("on_front")], key=lambda p: p["mass_g"])
    if len(front) > 1:
        fig.add_trace(go.Scatter(x=[p["mass_g"] for p in front], y=[p["cost_usd"] for p in front], mode="lines",
                                 line=dict(color=s["text_2"], width=1, dash="dot"), hoverinfo="skip"))
    for p in points:
        if p["mass_g"] is None or p["cost_usd"] is None:
            continue
        pc = theme.PROCESS.get(p["process_id"], {}).get("color", theme.MUTED)
        ranked = p["state"] == "ranked"
        fig.add_trace(go.Scatter(
            x=[p["mass_g"]], y=[p["cost_usd"]], mode="markers+text",
            text=[p["material_id"]], textposition="top center",
            textfont=dict(size=theme.TEXT_XS, color=s["text"] if ranked else s["text_2"]),
            marker=dict(size=13 if ranked else 11, color=pc if ranked else "rgba(0,0,0,0)",
                        line=dict(color=pc if ranked else s["text_2"], width=1.5 if ranked else 1.2),
                        opacity=1.0 if ranked else 0.7),
            hovertemplate=(f"<b>{p['material_id']}</b> · {theme.PROCESS.get(p['process_id'], {}).get('label', p['process_id'])}"
                           f"<br>{p['mass_g']:.2f} g · ${p['cost_usd']:.2f}"
                           + (f"<br>{p['reason']}" if p.get("reason") else "") + "<extra></extra>")))
    fig.update_layout(**theme.plotly_layout(dark, height=height, margin=dict(l=8, r=8, t=24, b=8)))
    fig.update_xaxes(**theme.plotly_axis(dark, "mass (g)"))
    fig.update_yaxes(**theme.plotly_axis(dark, f"material cost per part ($) · {caption}"))
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
def mesh_refinement_plot(rows: list[dict], dark: bool, height: int = 300) -> go.Figure:
    s = theme.surface(dark)
    x = [r["elements_through_depth"] for r in rows]
    fig = go.Figure()
    for key, name, col in (("delta_error", "tip deflection", theme.ACCENT), ("sigma_error", "surface stress (recovered)", s["text"]),
                           ("sigma_centre_error", "element-centre stress", s["text_2"])):
        fig.add_trace(go.Scatter(x=x, y=[max(r[key], 1e-6) for r in rows], mode="lines+markers", name=name,
                                 line=dict(color=col, width=1.5), marker=dict(size=7, color=col),
                                 hovertemplate=f"{name}<br>%{{x}} elements: %{{y:.2%}}<extra></extra>"))
    fig.add_hline(y=rows[0]["tolerance"], line=dict(color=theme.PASS, width=1, dash="dot"),
                  annotation_text="3% target", annotation_font=dict(size=theme.TEXT_XS, color=theme.PASS))
    fig.update_layout(**theme.plotly_layout(dark, height=height, showlegend=True,
                                            legend=dict(orientation="h", y=1.08, font=dict(size=theme.TEXT_XS))))
    fig.update_xaxes(**theme.plotly_axis(dark, "elements through the depth"), type="log")
    fig.update_yaxes(**theme.plotly_axis(dark, "error"), type="log", tickformat=".1%")
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
                  annotation_font=dict(size=theme.TEXT_XS, color=theme.PASS))
    fig.update_layout(**theme.plotly_layout(dark, height=height, showlegend=True,
                                            legend=dict(orientation="h", y=1.08, font=dict(size=theme.TEXT_XS))))
    fig.update_xaxes(**theme.plotly_axis(dark, "elements per hole radius"), type="log", tickvals=x)
    fig.update_yaxes(**theme.plotly_axis(dark, "error vs K_t (finite width)"), tickformat=".0%", rangemode="tozero")
    return fig
