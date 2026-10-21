"""Small HTML pieces for the app (cards, pills, gauges, messages). All style values come from theme.py."""

from __future__ import annotations

import html
import math

import streamlit as st

from app import theme

STEPS = ("Describe", "Check", "Compare", "Export")


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def inject_css(dark: bool) -> None:
    st.markdown(theme.css(dark), unsafe_allow_html=True)


def topbar(step: int | None, tab: str) -> None:
    pills = []
    for i, name in enumerate(STEPS):
        cls = "on" if step == i else ("done" if step is not None and i < step else "")
        pills.append(f'<span class="mx-step {cls}"><b>{i + 1}</b>{name}</span>')
    steps_html = f'<div class="mx-steps">{"".join(pills)}</div>' if tab == "Design" else ""
    st.markdown(f'<div class="mx-topbar"><div class="mx-brand">Morphic<small>{esc(tab)}</small></div>'
                f'{steps_html}</div>', unsafe_allow_html=True)


def title(text: str, sub: str = "") -> None:
    st.markdown(f'<div class="mx-title">{esc(text)}</div>'
                + (f'<div class="mx-sub">{esc(sub)}</div>' if sub else ""), unsafe_allow_html=True)


def eyebrow(text: str) -> str:
    return f'<div class="mx-eyebrow">{esc(text)}</div>'


def pill(text: str, kind: str = "") -> str:
    return f'<span class="mx-pill {kind}">{esc(text)}</span>'


def msg(text: str, level: str = "info", label: str = "") -> None:
    lab = f"<b>{esc(label)}</b>" if label else ""
    st.markdown(f'<div class="mx-msg {level}">{lab}<span>{esc(text)}</span></div>', unsafe_allow_html=True)


def hero(value: str, unit: str, label: str) -> str:
    return (f'<div class="mx-hero">{esc(value)}<small>{esc(unit)}</small></div>'
            f'<div class="mx-label">{esc(label)}</div>')


def row(label: str, value: str) -> str:
    return f'<div class="mx-row"><span>{esc(label)}</span><span class="mx-num">{value}</span></div>'


def meter(frac: float, passed: bool | None = None) -> str:
    frac = 0.0 if frac is None or not math.isfinite(frac) else max(0.0, min(1.0, frac))
    kind = "" if passed is None else ("pass" if passed else "fail")
    return f'<div class="mx-meter {kind}"><i style="width:{frac * 100:.1f}%"></i></div>'


def gauge(value: float, target: float, label: str, unit: str = "", passed: bool | None = None,
          vmax: float | None = None, size: int = 72) -> str:
    """Instrument-style arc: the needle sweep shows value against a scale that puts the target
    at two thirds of the arc, so 'above target' reads at a glance."""
    vmax = vmax or max(target * 1.5, 1e-9)
    frac = 0.0 if value is None or not math.isfinite(value) else max(0.0, min(1.0, value / vmax))
    tfrac = max(0.0, min(1.0, target / vmax))
    color = theme.MUTED if passed is None else (theme.PASS if passed else theme.FAIL)
    r, cx, cy = size / 2 - 6, size / 2, size / 2 + 4
    start = math.pi * 1.15
    sweep = -math.pi * 1.3

    def pt(f):
        a = start + sweep * f
        return cx + r * math.cos(a), cy - r * math.sin(a)

    def arc(f0, f1):
        x0, y0 = pt(f0)
        x1, y1 = pt(f1)
        large = 1 if abs(f1 - f0) * 1.3 > 1 else 0
        return f"M{x0:.1f},{y0:.1f} A{r:.1f},{r:.1f} 0 {large} 1 {x1:.1f},{y1:.1f}"

    tx, ty = pt(tfrac)
    shown = "—" if value is None or not math.isfinite(value) else (f"{value:.2g}" if value < 10 else f"{value:.0f}")
    if value is not None and math.isfinite(value) and value >= 100:
        shown = ">99"
    svg = (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
           f'<path d="{arc(0, 1)}" fill="none" stroke="currentColor" stroke-opacity="0.12" stroke-width="6" stroke-linecap="round"/>'
           + (f'<path d="{arc(0, frac)}" fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round"/>' if frac > 0 else "")
           + f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="2.6" fill="currentColor" fill-opacity="0.7"/>'
           f'<text x="{cx}" y="{cy + 5}" text-anchor="middle" font-size="{size * 0.26:.0f}" font-weight="650" '
           f'fill="currentColor" font-family="{theme.FONT_SANS}">{shown}</text></svg>')
    txt = (f'<div><div style="font-size:{theme.TEXT_SM}px;color:var(--mx-text-2)">{esc(label)}</div>'
           f'<div style="font-size:{theme.TEXT_SM}px" class="mx-num">{esc(unit)}</div></div>')
    return f'<div class="mx-gauge" style="color:var(--mx-text)">{svg}{txt}</div>'


def lc_pill(text: str, color: str) -> str:
    """A load-case pill in that case's arrow color: a lit dot and the name, force and limit."""
    return f'<span class="mx-lc" style="color:{color};background:{theme.rgba(color, 0.14)}"><i></i>{esc(text)}</span>'


def readout(label: str, value: str, unit: str = "", sub: str = "", frac: float | None = None,
            scale: tuple[str, str] | None = None, color: str | None = None, extra_html: str = "") -> str:
    """Instrument-style readout: eyebrow label, one hero number, its context in words, and a strip of
    ticks lit up to the value on a stated scale (so the number has a place, not just a size)."""
    ticks = ""
    if frac is not None and math.isfinite(frac):
        n = theme.READOUT_TICKS
        lit = int(round(max(0.0, min(1.0, frac)) * n))
        ticks = (f'<div class="mx-ticks" style="color:{color or "var(--mx-text)"}">'
                 + "".join(f'<i class="{("on tip" if i == lit - 1 else "on") if i < lit else ""}"></i>' for i in range(n))
                 + "</div>")
        if scale:
            ticks += f'<div class="mx-scale"><span>{esc(scale[0])}</span><span>{esc(scale[1])}</span></div>'
    return (f'<div class="mx-readout"><div class="mx-eyebrow">{esc(label)}</div>'
            f'<div class="mx-hero">{esc(value)}<small>{esc(unit)}</small></div>'
            f'<div class="mx-sub2">{esc(sub)}{extra_html}</div>{ticks}</div>')


def check_icon(ok: bool) -> str:
    if ok:
        return (f'<svg class="mx-check" viewBox="0 0 20 20"><circle cx="10" cy="10" r="9" fill="{theme.PASS_SOFT}"/>'
                f'<path d="M5.5 10.5l3 3 6-7" fill="none" stroke="{theme.PASS}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    return (f'<svg class="mx-check" viewBox="0 0 20 20"><circle cx="10" cy="10" r="9" fill="{theme.FAIL_SOFT}"/>'
            f'<path d="M6.5 6.5l7 7M13.5 6.5l-7 7" fill="none" stroke="{theme.FAIL}" stroke-width="2" stroke-linecap="round"/></svg>')


def card(inner: str, cls: str = "", style: str = "") -> None:
    st.markdown(f'<div class="mx-card {cls}" style="{style}">{inner}</div>', unsafe_allow_html=True)


def funnel(f: dict) -> None:
    cells = [("candidate designs evaluated", f["candidates"]), ("met the limits", f["met_limits"]),
             ("printable with your printer", f["printable"]), ("ranked by mass", f["ranked"])]
    parts = "".join(f'<div><div class="n">{n}</div><div class="mx-label">{esc(t)}</div></div>' for t, n in cells)
    if f.get("isolated_stress_failures"):
        parts += (f'<div style="opacity:0.6"><div class="n">{f["isolated_stress_failures"]}</div>'
                  f'<div class="mx-label">isolated stress failures (ignored, see funnel)</div></div>')
    st.markdown(f'<div class="mx-funnel">{parts}</div>', unsafe_allow_html=True)


def foot(text: str) -> None:
    st.markdown(f'<div class="mx-foot">{esc(text)}</div>', unsafe_allow_html=True)


def table(headers: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="mx-table"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'


def fmt(x, nd: int = 2) -> str:
    if x is None:
        return "—"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return esc(x)
    if not math.isfinite(v):
        return "∞" if v > 0 else "−∞"
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    return f"{v:.{nd}f}"


def pct(x, nd: int = 0) -> str:
    return "—" if x is None else f"{float(x) * 100:.{nd}f}%"
