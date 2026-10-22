"""The one place for every color, font, radius, shadow and spacing value in the app.

Every other app module reads its styling from here: the CSS injected into Streamlit,
the Plotly layouts, and the color scales for stress and density maps.
"""

from __future__ import annotations

import base64
import functools
from pathlib import Path

# ----------------------------------------------------------------------------- fonts
# Geist for headings, labels and body; Geist Mono for every numeral, unit and technical value.
# Both are bundled under app/static/fonts (SIL Open Font License, see LICENSE.txt there) and loaded
# with @font-face from those files only. Nothing is fetched from a font service.
FONT_DIR = Path(__file__).resolve().parent / "static" / "fonts"
FONT_FILES = {"Geist": "Geist-Variable.woff2", "Geist Mono": "GeistMono-Variable.woff2"}
FONT_SANS = "Geist, 'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif"
FONT_MONO = "'Geist Mono', 'Cascadia Mono', Consolas, monospace"

# type scale (px): one display size for page titles, two heading sizes, body, small, and the eyebrow
TEXT_XS = 11  # eyebrow labels, chart ticks, scale marks
TEXT_SM = 13  # small: notes, table rows, pills
TEXT_MD = 15  # body
TEXT_LG = 19  # medium headings
TEXT_XL = 28  # large headings
TEXT_DISPLAY = 36  # page titles
TEXT_HERO = 44  # instrument hero numbers
LINE_BODY = 1.5
LINE_TIGHT = 1.1
WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500
WEIGHT_SEMIBOLD = 600
TRACK_DISPLAY = "-0.02em"  # page titles and the wordmark
TRACK_HEADING = "-0.01em"
EYEBROW_TRACKING = "0.08em"  # small uppercase labels

# ----------------------------------------------------------------------------- spacing and shape
SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_5 = 24
SPACE_6 = 32
SPACE_7 = 48

RADIUS_SM = 10
RADIUS_MD = 16
RADIUS_LG = 22
RADIUS_XL = 28
RADIUS_PILL = 999

# ----------------------------------------------------------------------------- the one accent + status
ACCENT = "#0A84FF"
ACCENT_LIGHT = "#2D95FF"  # the lit end of accent gradients (primary button, logomark)
ACCENT_SOFT = "rgba(10,132,255,0.12)"
PASS = "#30B35A"
PASS_SOFT = "rgba(48,179,90,0.12)"
FAIL = "#E5484D"
FAIL_SOFT = "rgba(229,72,77,0.12)"
DEFAULT_AMBER = "#F2A93B"
DEFAULT_AMBER_SOFT = "rgba(242,169,59,0.16)"
MUTED = "#A1A1A6"

# one color per load case (drawing arrows, deflection rows, load-case pills)
LOAD_CASE_COLORS = ["#FF5A4E", "#FF9F0A", "#BF5AF2", "#64D2FF"]

# ----------------------------------------------------------------------------- light surfaces
# Kept for the Plotly layouts, the PDF-style density image and the CSS test; the app itself is dark everywhere.
LIGHT = {
    "bg": "#F5F5F7",
    "card": "#FFFFFF",
    "card_alt": "#FAFAFB",
    "raised": "#FFFFFF",
    "text": "#1D1D1F",
    "text_2": "#86868B",
    "line": "rgba(0,0,0,0.06)",
    "shadow": "0 1px 2px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.06)",
    "shadow_hover": "0 2px 4px rgba(0,0,0,0.05), 0 14px 36px rgba(0,0,0,0.09)",
    "glass": "rgba(255,255,255,0.72)",
    "input": "#F2F2F5",
    "amber_text": "#B7791F",
    "glow": "rgba(29,29,31,0.18)",
    "pad_fill": "rgba(120,120,128,0.30)",
    "glass_input": "rgba(255,255,255,0.55)",
    "stage": "radial-gradient(120% 90% at 50% 0%, #FFFFFF 0%, #F5F5F7 70%)",
}

# ----------------------------------------------------------------------------- dark stage (the whole app)
DARK = {
    "bg": "#050506",
    "card": "#141416",
    "card_alt": "#1C1C1F",
    "raised": "#232327",
    "text": "#F5F5F7",
    "text_2": "#8E8E93",
    "line": "rgba(255,255,255,0.07)",
    "shadow": "0 1px 0 rgba(255,255,255,0.04) inset, 0 12px 32px rgba(0,0,0,0.55)",
    "shadow_hover": "0 1px 0 rgba(255,255,255,0.06) inset, 0 18px 44px rgba(0,0,0,0.7)",
    "glass": "rgba(28,28,31,0.66)",
    "input": "#1C1C1F",
    "amber_text": DEFAULT_AMBER,
    "glow": "rgba(245,245,247,0.22)",
    "pad_fill": "rgba(255,255,255,0.16)",
    "glass_input": "rgba(255,255,255,0.045)",  # the Describe box: frosted, a touch lighter than its card
    "stage": "radial-gradient(120% 90% at 50% 0%, #17171B 0%, #050506 70%)",
}

# soft glow rings around pads on the Check drawing: (radius factor, alpha), drawn largest first
PAD_GLOW_RINGS = [(3.0, 0.022), (2.6, 0.028), (2.25, 0.035), (1.95, 0.045), (1.65, 0.06), (1.35, 0.08)]
# the faint wide stroke under each load arrow on the dark stage
ARROW_GLOW_WIDTH = 9
ARROW_GLOW_OPACITY = 0.22
# the halo around the winning point on the Pareto chart: (marker size factor, alpha), drawn largest first
POINT_HALO_RINGS = [(3.4, 0.05), (2.5, 0.07), (1.8, 0.10)]

# instrument readouts (Check step): tick strip under the hero number
READOUT_TICKS = 24
# preview cards (Describe step): fixed height of the shape box so the three cards line up
PREVIEW_SHAPE_PX = 150

# ----------------------------------------------------------------------------- process identity
# soft gradient tint per process, used on cards and chart points
PROCESS = {
    "fdm": {"label": "FDM", "color": "#FF9F0A",
            "tint_light": "linear-gradient(160deg, rgba(255,159,10,0.10), rgba(255,159,10,0.00) 60%)",
            "tint_dark": "linear-gradient(160deg, rgba(255,159,10,0.16), rgba(255,159,10,0.00) 62%)"},
    "sls": {"label": "SLS", "color": "#30D5C8",
            "tint_light": "linear-gradient(160deg, rgba(48,213,200,0.11), rgba(48,213,200,0.00) 60%)",
            "tint_dark": "linear-gradient(160deg, rgba(48,213,200,0.15), rgba(48,213,200,0.00) 62%)"},
    "metal": {"label": "METAL", "color": "#9DB4D0",
              "tint_light": "linear-gradient(160deg, rgba(157,180,208,0.18), rgba(157,180,208,0.00) 60%)",
              "tint_dark": "linear-gradient(160deg, rgba(157,180,208,0.18), rgba(157,180,208,0.00) 62%)"},
}

# ----------------------------------------------------------------------------- maps
# utilization = sigma_vm * SF_target / strength on a shared 0..1 scale; above 1 is drawn in OVER_LIMIT
UTIL_SCALE = [
    [0.00, "#1B2A6B"],
    [0.25, "#1F6FD1"],
    [0.50, "#2EC4B6"],
    [0.75, "#F6D743"],
    [1.00, "#FF8A3D"],
]
OVER_LIMIT = "#FF2D55"
# density / growth: dark stage, material glows white
DENSITY_SCALE = [[0.0, "rgba(0,0,0,0)"], [0.35, "#3A3A40"], [1.0, "#F5F5F7"]]
DENSITY_SCALE_LIGHT = [[0.0, "rgba(0,0,0,0)"], [0.35, "#D2D2D7"], [1.0, "#1D1D1F"]]
# cinematic renders (render/cinematic.py): the slab on the dark stage, lit; opacity comes from density
DENSITY_SCALE_CINEMATIC = [[0.0, "#8E8E93"], [0.5, "#C7C7CC"], [1.0, "#E8E8ED"]]

# ----------------------------------------------------------------------------- motion
EASE = "cubic-bezier(0.22, 1, 0.36, 1)"  # the soft settle of meters and the growth strip (one-shot sequences)
EASE_OUT = "ease-out"  # entrances and the press
RISE_MS = 300  # cards fade and rise in: opacity, a small lift and a touch of blur
RISE_PX = 12
RISE_BLUR_PX = 4
PRESS_SCALE = 0.96  # a pressed button; a disabled one never scales
PRESS_MS = 150
HOVER_MS = 150  # hover lifts and color changes: instant feedback, never expressive motion


def surface(dark: bool) -> dict:
    return DARK if dark else LIGHT


@functools.lru_cache(maxsize=1)
def font_face_css() -> str:
    """The @font-face rules for the bundled Geist files, inlined as data URIs. Inlining keeps one path for
    the app and the screenshot fixtures (Streamlit's static server only serves the main script's own
    static folder) and means no font request ever leaves the page."""
    rules = []
    for family, name in FONT_FILES.items():
        b64 = base64.b64encode((FONT_DIR / name).read_bytes()).decode("ascii")
        rules.append(f'@font-face {{ font-family: "{family}"; font-style: normal; font-weight: 100 900; '
                     f'font-display: swap; src: url(data:font/woff2;base64,{b64}) format("woff2"); }}')
    return "<style>\n" + "\n".join(rules) + "\n</style>"


def rgba(hex_color: str, alpha: float) -> str:
    """'#RRGGBB' -> 'rgba(r,g,b,a)' for soft fills and glows derived from one theme color."""
    c = hex_color.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.2f})"


# ----------------------------------------------------------------------------- Plotly
def plotly_layout(dark: bool, **extra) -> dict:
    s = surface(dark)
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_SANS, size=TEXT_SM, color=s["text"]),
        margin=dict(l=8, r=8, t=8, b=8),
        hoverlabel=dict(bgcolor=s["card_alt"], bordercolor=s["card_alt"],
                        font=dict(family=FONT_SANS, size=TEXT_SM, color=s["text"])),
        showlegend=False,
    )
    base.update(extra)
    return base


def plotly_axis(dark: bool, title: str = "", grid: bool = True) -> dict:
    s = surface(dark)
    return dict(title=dict(text=title, font=dict(family=FONT_SANS, size=TEXT_XS, color=s["text_2"])), showgrid=grid,
                gridcolor=s["line"], gridwidth=1, zeroline=False, showline=False,
                tickfont=dict(family=FONT_MONO, size=TEXT_XS, color=s["text_2"]), ticks="")


PLOTLY_CONFIG = {"displaylogo": False, "displayModeBar": False, "responsive": True}
PLOTLY_CONFIG_3D = {"displaylogo": False, "displayModeBar": "hover", "responsive": True,
                    "modeBarButtonsToRemove": ["toImage", "resetCameraLastSave3d"]}


# ----------------------------------------------------------------------------- CSS
def css(dark: bool) -> str:
    s = surface(dark)
    other = LIGHT if dark else DARK
    proc_css = "\n".join(
        f".mx-proc-{pid} {{ background-image: {p['tint_dark' if dark else 'tint_light']}; }}\n"
        f".mx-proc-{pid} .mx-eyebrow-proc {{ color: {p['color']}; }}"
        for pid, p in PROCESS.items())
    return f"""
<style>
:root {{
  --mx-bg: {s['bg']}; --mx-card: {s['card']}; --mx-card-alt: {s['card_alt']};
  --mx-text: {s['text']}; --mx-text-2: {s['text_2']}; --mx-line: {s['line']};
  --mx-accent: {ACCENT}; --mx-accent-soft: {ACCENT_SOFT};
  --mx-pass: {PASS}; --mx-pass-soft: {PASS_SOFT}; --mx-fail: {FAIL}; --mx-fail-soft: {FAIL_SOFT};
  --mx-amber: {DEFAULT_AMBER}; --mx-amber-soft: {DEFAULT_AMBER_SOFT};
  --mx-shadow: {s['shadow']}; --mx-shadow-hover: {s['shadow_hover']};
  --mx-glass: {s['glass']}; --mx-input: {s['input']};
}}
html, body, .stApp, [data-testid="stAppViewContainer"] {{
  background: {s['bg']} !important; color: {s['text']};
  font-family: {FONT_SANS}; font-weight: {WEIGHT_REGULAR}; line-height: {LINE_BODY};
  font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1; -webkit-font-smoothing: antialiased;
}}
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {{ line-height: {LINE_BODY}; }}
.stApp {{ transition: background {RISE_MS}ms {EASE}; }}
[data-testid="stHeader"] {{ background: transparent; height: 0; }}
/* the two style-only markdown elements (fonts, theme) take no room in the flow */
[data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:only-child) {{ display: none; }}
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer {{ display: none !important; }}
.block-container {{ padding-top: 0 !important; padding-bottom: {SPACE_7 * 2}px !important;
  max-width: 1280px; }}
.stApp p, .stApp li, .stApp label, .stApp span, .stApp div {{ font-family: {FONT_SANS}; }}
.stApp code {{ font-family: {FONT_MONO}; }}
.stApp [data-testid="stIconMaterial"], .stApp .material-symbols-rounded, .stApp span[class*="material-symbols"] {{
  font-family: "Material Symbols Rounded" !important; }}
h1, h2, h3, h4 {{ font-family: {FONT_SANS} !important; color: {s['text']} !important;
  letter-spacing: {TRACK_HEADING}; font-weight: {WEIGHT_SEMIBOLD} !important; }}
[data-testid="stMarkdownContainer"] p {{ color: {s['text']}; }}
[data-testid="stCaptionContainer"], .stCaption {{ color: {s['text_2']} !important; }}
hr {{ border-color: {s['line']} !important; }}

/* ---- buttons: soft, lit, physical */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
  border-radius: {RADIUS_PILL}px; border: 1px solid transparent; padding: {SPACE_2}px {SPACE_5}px;
  background: {s['raised']}; color: {s['text']}; font-weight: 550; font-size: {TEXT_SM + 1}px;
  box-shadow: {s['shadow']}; -webkit-tap-highlight-color: transparent;
  transition: transform {HOVER_MS}ms {EASE_OUT}, box-shadow {HOVER_MS}ms {EASE_OUT}, color {HOVER_MS}ms {EASE_OUT};
}}
.stButton > button:not(:disabled):active, .stDownloadButton > button:not(:disabled):active {{
  transform: scale({PRESS_SCALE}); transition-duration: {PRESS_MS}ms; }}
.stButton > button:focus:not(:active) {{ color: {s['text']}; }}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
  background: linear-gradient(180deg, {ACCENT_LIGHT}, {ACCENT}); color: #fff;
  box-shadow: 0 1px 0 rgba(255,255,255,0.25) inset, 0 8px 22px rgba(10,132,255,0.32); }}
.stButton > button:disabled, .stDownloadButton > button:disabled {{ opacity: 0.5; transform: none;
  box-shadow: 0 0 0 1px {s['line']} inset; cursor: default; }}
.stButton > button[kind="tertiary"] {{ background: transparent; box-shadow: none; color: {s['text_2']};
  padding: {SPACE_1}px {SPACE_3}px; }}
@media (hover: hover) {{
  .stButton > button:not(:disabled):hover, .stDownloadButton > button:not(:disabled):hover {{
    transform: translateY(-1px); box-shadow: {s['shadow_hover']}; color: {s['text']}; }}
  .stButton > button[kind="primary"]:not(:disabled):hover {{ color: #fff;
    box-shadow: 0 1px 0 rgba(255,255,255,0.25) inset, 0 10px 26px rgba(10,132,255,0.4); }}
  .stButton > button[kind="tertiary"]:not(:disabled):hover {{ color: {s['text']}; box-shadow: none; transform: none; }}
}}

/* ---- inputs */
.stTextArea textarea, .stTextInput input, .stNumberInput input, [data-baseweb="select"] > div {{
  background: {s['input']} !important; color: {s['text']} !important; border: none !important;
  border-radius: {RADIUS_MD}px !important; font-family: {FONT_SANS} !important; }}
.stTextArea textarea {{ font-size: {TEXT_MD + 1}px; line-height: 1.55; padding: {SPACE_4}px {SPACE_5}px !important; }}
.stTextArea [data-baseweb="textarea"], .stTextInput [data-baseweb="input"], .stNumberInput [data-baseweb="input"] {{
  border: none !important; border-radius: {RADIUS_MD}px !important; background: {s['input']} !important; }}
[data-testid="stWidgetLabel"] p {{ color: {s['text_2']} !important; font-size: {TEXT_SM}px !important; }}
/* the Describe box: larger type, more air, a soft inner edge so it reads as a writing surface */
[class*="st-key-card_describe"] .stTextArea textarea {{ font-size: {TEXT_LG - 1}px; line-height: 1.6;
  padding: {SPACE_5}px {SPACE_6}px {SPACE_6}px !important; border-radius: {RADIUS_LG}px !important;
  background: {s['glass_input']} !important; backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  box-shadow: inset 0 2px 10px rgba(0,0,0,0.35), inset 0 0 0 1px {s['line']}; resize: none;
  transition: box-shadow {HOVER_MS}ms {EASE_OUT}; }}
[class*="st-key-card_describe"] .stTextArea textarea:focus {{ outline: none;
  box-shadow: inset 0 2px 10px rgba(0,0,0,0.35), 0 0 0 3px var(--mx-accent-soft), 0 0 28px rgba(10,132,255,0.22); }}
[class*="st-key-card_describe"] .stTextArea [data-baseweb="textarea"] {{ border-radius: {RADIUS_LG}px !important;
  background: transparent !important; }}
[class*="st-key-card_describe"] .stTextArea [data-baseweb="base-input"] {{ background: transparent !important; }}
/* the character count sits inside the bottom-right of the box; the row of example pills follows below it */
.mx-count {{ font-family: {FONT_MONO}; font-size: {TEXT_XS}px; color: {s['text_2']}; text-align: right; height: 0;
  margin: -{SPACE_6 + SPACE_3}px 0 {SPACE_6 + SPACE_3}px; padding-right: {SPACE_5}px; position: relative; z-index: 1;
  pointer-events: none; opacity: 0.8; }}
.st-key-examples .stButton > button {{ min-height: 0; height: auto; padding: 3px {SPACE_3}px; font-size: {TEXT_XS + 1}px;
  font-weight: {WEIGHT_MEDIUM}; background: {s['card_alt']}; color: {s['text_2']}; box-shadow: none;
  border: 1px solid {s['line']}; line-height: 1.6; }}
@media (hover: hover) {{ .st-key-examples .stButton > button:not(:disabled):hover {{ color: {s['text']};
  transform: none; box-shadow: none; border-color: rgba(255,255,255,0.18); }} }}
.mx-examples-label {{ font-size: {TEXT_XS + 1}px; color: {s['text_2']}; white-space: nowrap; }}
/* "or": a hairline with the word centered on it, between the two ways in */
.mx-or {{ display: flex; align-items: center; gap: {SPACE_3}px; margin: {SPACE_3}px 0 {SPACE_2}px; color: {s['text_2']};
  font-size: {TEXT_XS}px; font-weight: {WEIGHT_MEDIUM}; letter-spacing: {EYEBROW_TRACKING}; text-transform: uppercase; }}
.mx-or::before, .mx-or::after {{ content: ""; flex: 1; height: 1px; background: {s['line']}; }}
/* multiselect chips read as pills in the accent tint, not solid blocks */
[data-testid="stMultiSelectTagsContainer"] span[data-tag] {{ border-radius: {RADIUS_PILL}px !important;
  background: var(--mx-accent-soft) !important; color: {ACCENT} !important; }}
[data-testid="stMultiSelectTagsContainer"] span[data-tag] span, [data-testid="stMultiSelectTagsContainer"] span[data-tag] button {{
  color: {ACCENT} !important; font-weight: 600; }}
/* the growth scrubber: the iteration count sits beside it, so the thumb carries no value bubble */
[data-testid="stSlider"] [data-testid="stSliderThumbValue"] {{ display: none; }}
[data-testid="stSlider"] [data-testid="stSliderTickBar"] div {{ color: {s['text_2']}; font-size: {TEXT_XS}px;
  font-family: {FONT_SANS}; }}
[class*="st-key-card_describe"] .stTextArea textarea::placeholder {{ color: {s['text_2']}; opacity: 0.7; }}

/* ---- toggles: an inset track with a softly lit knob */
[data-testid="stCheckbox"] label:has(input[role="switch"]) > div:first-of-type {{
  box-shadow: inset 0 1px 2px rgba(0,0,0,0.45), 0 1px 0 rgba(255,255,255,0.05); }}
[data-testid="stCheckbox"] label:has(input[role="switch"]) > div:first-of-type > div {{
  box-shadow: 0 1px 3px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.06) inset; }}

/* ---- segmented controls and pills */
[data-testid="stButtonGroup"] button {{ border-radius: {RADIUS_PILL}px !important; border: none !important;
  background: {s['card']} !important; color: {s['text_2']} !important; box-shadow: {s['shadow']};
  font-weight: 550; }}
[data-testid="stButtonGroup"] button[aria-checked="true"], [data-testid="stButtonGroup"] button[kind*="Active"] {{
  background: {s['text']} !important; color: {s['bg']} !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] *, [data-testid="stButtonGroup"] button[kind*="Active"] * {{
  color: {s['bg']} !important; }}
[data-testid="stButtonGroup"] button * {{ font-family: {FONT_SANS} !important; }}

/* ---- tabs */
.stTabs [data-baseweb="tab-list"] {{ gap: {SPACE_2}px; border: none; }}
.stTabs [data-baseweb="tab"] {{ border-radius: {RADIUS_PILL}px; padding: {SPACE_1}px {SPACE_4}px;
  background: {s['card']}; color: {s['text_2']}; height: auto; }}
.stTabs [aria-selected="true"] {{ background: {s['text']} !important; color: {s['bg']} !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}

/* ---- expanders as quiet footnotes */
[data-testid="stExpander"] details {{ border: none !important; background: {s['card_alt']};
  border-radius: {RADIUS_MD}px; }}
[data-testid="stExpander"] summary {{ color: {s['text_2']}; font-size: {TEXT_SM}px; }}
@media (hover: hover) {{ [data-testid="stExpander"] summary:hover {{ color: {s['text']}; }} }}
[data-testid="stExpander"] summary {{ transition: color {HOVER_MS}ms {EASE_OUT}; }}

/* ---- Streamlit's own messages (info, error) take the message style of the app */
[data-testid="stAlert"] [data-testid="stAlertContainer"] {{ border-radius: {RADIUS_MD}px; border: none !important;
  padding: {SPACE_3}px {SPACE_4}px; background: {s['card_alt']}; color: {s['text']}; }}
[data-testid="stAlert"] [data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {{
  background: var(--mx-fail-soft); }}
[data-testid="stAlert"] [data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {{
  background: var(--mx-amber-soft); }}
[data-testid="stAlert"] [data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {{
  background: var(--mx-pass-soft); }}
[data-testid="stAlert"] [data-testid="stAlertContainer"] p {{ font-size: {TEXT_SM + 1}px; color: {s['text']}; }}
[data-testid="stText"] {{ font-family: {FONT_MONO}; font-size: {TEXT_XS + 1}px; color: {s['text_2']}; }}

/* ---- the 3D dialog: a raised card, its scroll contained */
[data-testid="stDialog"] [role="dialog"] {{ background: {s['card']}; border-radius: {RADIUS_XL}px;
  box-shadow: {s['shadow_hover']}; overscroll-behavior: contain; }}

/* ---- data editor / dataframe */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {{ border-radius: {RADIUS_MD}px; overflow: hidden;
  box-shadow: {s['shadow']}; }}
[data-testid="stDataFrame"] > div, [data-testid="stDataEditor"] > div {{ border: none !important; }}

/* ---- bordered containers become cards */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{ }}
div[data-testid="stVerticalBlockBorderWrapper"][data-mx-card], .st-key-mxcard {{ }}
[class*="st-key-card"] {{ background: {s['card']}; border-radius: {RADIUS_LG}px; padding: {SPACE_5}px;
  border: 1px solid transparent; box-shadow: {s['shadow']}; animation: mxrise {RISE_MS}ms {EASE_OUT} both; }}
[class*="st-key-stage"] {{ background: {DARK['stage']};
  border-radius: {RADIUS_XL}px; padding: {SPACE_5}px; box-shadow: {DARK['shadow']};
  animation: mxrise {RISE_MS}ms {EASE_OUT} both; }}
/* ---- Describe: one preview card per demo part, a small stage with the cached shape glowing on it */
[class*="st-key-preview"] {{ background: {DARK['stage']}; border-radius: {RADIUS_XL}px; padding: {SPACE_5}px;
  box-shadow: {DARK['shadow']}; animation: mxrise {RISE_MS}ms {EASE_OUT} both;
  transition: transform {HOVER_MS}ms {EASE_OUT}, box-shadow {HOVER_MS}ms {EASE_OUT}; }}
@media (hover: hover) {{
  [class*="st-key-preview"]:hover {{ transform: translateY(-2px); box-shadow: {DARK['shadow_hover']}; }}
}}
[class*="st-key-preview"] .stButton > button {{ width: 100%; margin-top: {SPACE_3}px; }}
.mx-preview-title {{ font-size: {TEXT_LG + 1}px; font-weight: {WEIGHT_SEMIBOLD}; letter-spacing: {TRACK_HEADING}; color: {DARK['text']};
  margin: 2px 0 {SPACE_3}px; }}
.mx-shape-box {{ height: {PREVIEW_SHAPE_PX}px; display: flex; align-items: center; justify-content: center;
  margin: {SPACE_2}px 0 {SPACE_3}px; }}
.mx-shape-box img {{ max-width: 100%; max-height: 100%; object-fit: contain; display: block;
  filter: drop-shadow(0 0 18px {DARK['glow']}); }}
[class*="st-key-preview"] .mx-hero {{ font-size: {TEXT_XL + 8}px; }}
/* ---- Check: instrument readouts (one hero number, its context, a tick strip with a pointer) */
.mx-readout {{ background: {s['card_alt']}; border-radius: {RADIUS_MD}px; padding: {SPACE_4}px {SPACE_5}px {SPACE_3}px;
  box-shadow: 0 1px 0 rgba(255,255,255,0.04) inset; height: 100%; }}
.mx-readout .mx-hero {{ font-size: {TEXT_XL + 8}px; margin-top: {SPACE_1}px; }}
.mx-readout .mx-sub2 {{ font-size: {TEXT_XS + 1}px; color: {s['text_2']}; margin-top: {SPACE_1}px; line-height: 1.4;
  min-height: 2.8em; }}
.mx-ticks {{ display: flex; align-items: flex-end; height: 16px; margin-top: {SPACE_3}px; }}
.mx-ticks i {{ flex: 1; height: 5px; border-left: 1.5px solid currentColor; opacity: 0.16; }}
.mx-ticks i:nth-child(6n+1) {{ height: 8px; }}
.mx-ticks i.on {{ height: 9px; opacity: 0.85; }}
.mx-ticks i.tip {{ height: 16px; opacity: 1; border-left-width: 2px; filter: drop-shadow(0 0 3px currentColor); }}
.mx-scale {{ display: flex; justify-content: space-between; font-family: {FONT_MONO}; font-size: {TEXT_XS}px; color: {s['text_2']};
  margin-top: 3px; font-variant-numeric: tabular-nums; }}
.mx-lc {{ display: inline-flex; align-items: center; gap: 7px; padding: 4px 11px; border-radius: {RADIUS_PILL}px;
  font-size: {TEXT_XS + 1}px; font-weight: 600; margin: 0 6px 6px 0; white-space: nowrap; }}
.mx-lc i {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: currentColor;
  box-shadow: 0 0 8px currentColor; }}
/* ---- Describe: the one-line "what happens next" */
.mx-flow {{ display: flex; align-items: center; flex-wrap: wrap; gap: {SPACE_2}px; margin: {SPACE_4}px 0 {SPACE_2}px;
  font-size: {TEXT_SM}px; color: {s['text_2']}; }}
.mx-flow .lead {{ color: {s['text']}; font-weight: {WEIGHT_SEMIBOLD}; margin-right: {SPACE_2}px; }}
.mx-flow .step {{ display: inline-flex; align-items: center; gap: 7px; padding: 3px {SPACE_3}px 3px 4px;
  border-radius: {RADIUS_PILL}px; background: {s['card_alt']}; color: {s['text_2']}; font-weight: {WEIGHT_MEDIUM};
  white-space: nowrap; }}
.mx-flow .step i {{ display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px;
  border-radius: 50%; font-style: normal; font-family: {FONT_MONO}; font-size: {TEXT_XS}px; color: {s['text']};
  background: rgba(255,255,255,0.08); }}
.mx-flow .step.on {{ background: var(--mx-accent-soft); color: {ACCENT}; }}
.mx-flow .step.on i {{ background: {ACCENT}; color: #fff; box-shadow: 0 0 10px rgba(10,132,255,0.5); }}
.mx-flow .link {{ width: 22px; height: 1px; background: rgba(255,255,255,0.16); flex: none; }}
[class*="st-key-card"][class*="_win"] {{ box-shadow: {s['shadow']}, 0 0 0 1px rgba(10,132,255,0.35), 0 0 42px rgba(10,132,255,0.22); }}
[class*="st-key-card"][class*="_quiet"] {{ opacity: 0.6; filter: blur(0) saturate(0.25);
  transition: opacity {HOVER_MS}ms {EASE_OUT}, filter {HOVER_MS}ms {EASE_OUT}; }}
@media (hover: hover) {{ [class*="st-key-card"][class*="_quiet"]:hover {{ opacity: 1; filter: blur(0) saturate(1); }} }}
[class*="st-key-card_fdm"] {{ background-image: {PROCESS['fdm']['tint_dark' if dark else 'tint_light']}; }}
[class*="st-key-card_sls"] {{ background-image: {PROCESS['sls']['tint_dark' if dark else 'tint_light']}; }}
[class*="st-key-card_metal"] {{ background-image: {PROCESS['metal']['tint_dark' if dark else 'tint_light']}; }}
[class*="st-key-card_fdm"] .mx-eyebrow-proc {{ color: {PROCESS['fdm']['color']}; }}
[class*="st-key-card_sls"] .mx-eyebrow-proc {{ color: {PROCESS['sls']['color']}; }}
[class*="st-key-card_metal"] .mx-eyebrow-proc {{ color: {PROCESS['metal']['color']}; }}
.st-key-agent_panel {{ background: {s['glass']}; backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
  border-radius: {RADIUS_XL}px; padding: {SPACE_5}px; border: 1px dashed {s['line']};
  box-shadow: {s['shadow']}; }}

/* ---- Morphic HTML components */
.st-key-topbar {{ position: sticky; top: 0; z-index: 40; margin: 0 0 {SPACE_2}px;
  padding: {SPACE_3}px {SPACE_4}px; background: {s['glass']}; backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px); border-bottom: 1px solid {s['line']};
  border-radius: 0 0 {RADIUS_LG}px {RADIUS_LG}px; }}
.mx-topbar {{ display: flex; align-items: center; justify-content: space-between; }}
.mx-brand {{ display: inline-flex; align-items: center; gap: {SPACE_2}px; font-size: {TEXT_LG + 3}px;
  font-weight: {WEIGHT_SEMIBOLD}; letter-spacing: {TRACK_DISPLAY}; color: {s['text']}; }}
.mx-brand .mx-mark {{ width: 22px; height: 22px; flex: none; filter: drop-shadow(0 0 6px rgba(10,132,255,0.35)); }}
.mx-brand small {{ font-size: {TEXT_SM}px; font-weight: {WEIGHT_MEDIUM}; color: {s['text_2']}; letter-spacing: 0;
  margin-left: {SPACE_2}px; }}
.mx-steps {{ display: flex; gap: {SPACE_1}px; background: {s['card']}; padding: {SPACE_1}px;
  border-radius: {RADIUS_PILL}px; box-shadow: {s['shadow']}; }}
.mx-step {{ padding: 6px {SPACE_4}px; border-radius: {RADIUS_PILL}px; font-size: {TEXT_SM}px; font-weight: 550;
  color: {s['text_2']}; white-space: nowrap; }}
.mx-step b {{ font-family: {FONT_MONO}; font-weight: {WEIGHT_MEDIUM}; margin-right: 6px; opacity: 0.55; }}
.mx-step.on {{ background: {s['text']}; color: {s['bg']}; }}
.mx-step.done {{ color: {s['text']}; }}
.mx-title {{ font-size: {TEXT_DISPLAY}px; font-weight: {WEIGHT_SEMIBOLD}; letter-spacing: {TRACK_DISPLAY};
  color: {s['text']}; margin: {SPACE_4}px 0 0; line-height: {LINE_TIGHT}; }}
/* the tagline under a title: one step above body, secondary tone, a comfortable measure, tucked under the title
   with the larger gap below it */
.mx-sub {{ font-size: {TEXT_MD + 2}px; font-weight: {WEIGHT_REGULAR}; line-height: {LINE_BODY}; color: {s['text_2']};
  margin: {SPACE_2}px 0 {SPACE_5}px; max-width: 60ch; }}
.mx-eyebrow {{ font-size: {TEXT_XS}px; letter-spacing: {EYEBROW_TRACKING}; text-transform: uppercase;
  color: {s['text_2']}; font-weight: {WEIGHT_MEDIUM}; }}
/* every section starts the same way: a short accent line before the label (process colors keep their own) */
.mx-eyebrow::before {{ content: ""; display: inline-block; width: 10px; height: 2px; border-radius: 1px;
  background: var(--mx-accent); margin-right: {SPACE_2}px; vertical-align: middle; position: relative; top: -1px; }}
.mx-eyebrow-proc::before, .mx-eyebrow[style*="color"]::before {{ background: currentColor; opacity: 0.8; }}
.mx-eyebrow.mx-top {{ margin-top: {SPACE_5}px; }}
.mx-pills {{ margin: {SPACE_2}px 0 {SPACE_1}px; }}
.mx-block {{ margin-top: {SPACE_3}px; }}
.mx-block-sm {{ margin-top: {SPACE_2}px; }}
.mx-img {{ border-radius: {RADIUS_SM}px; }}
.mx-card {{ background: {s['card']}; border-radius: {RADIUS_LG}px; padding: {SPACE_5}px; box-shadow: {s['shadow']};
  border: 1px solid transparent; animation: mxrise {RISE_MS}ms {EASE_OUT} both; position: relative; overflow: hidden; }}
.mx-card.quiet {{ opacity: 0.55; filter: blur(0) saturate(0.2); transform: scale(0.98); }}
.mx-card.win {{ box-shadow: {s['shadow']}, 0 0 0 1px rgba(10,132,255,0.35), 0 0 42px rgba(10,132,255,0.22); }}
.mx-hero {{ font-family: {FONT_MONO}; font-size: {TEXT_HERO}px; font-weight: {WEIGHT_MEDIUM}; letter-spacing: -0.03em;
  line-height: 1; color: {s['text']}; font-variant-numeric: tabular-nums; }}
.mx-hero small {{ font-size: {TEXT_LG}px; font-weight: {WEIGHT_REGULAR}; color: {s['text_2']}; margin-left: 4px;
  letter-spacing: 0; }}
.mx-label {{ font-size: {TEXT_SM}px; color: {s['text_2']}; }}
.mx-num {{ font-family: {FONT_MONO}; font-variant-numeric: tabular-nums; }}
.mx-pill.mx-num {{ font-size: {TEXT_XS}px; }}
.mx-row {{ display: flex; justify-content: space-between; gap: {SPACE_3}px; font-size: {TEXT_SM}px;
  padding: 5px 0; color: {s['text']}; }}
.mx-row span:first-child {{ color: {s['text_2']}; }}
.mx-note {{ font-size: {TEXT_XS + 1}px; color: {s['text_2']}; line-height: {LINE_BODY}; }}
/* a standalone note reads as a quiet footnote: a small info glyph, a faint bar and a barely tinted field */
.mx-footnote {{ display: flex; gap: {SPACE_2}px; align-items: flex-start; font-size: {TEXT_SM}px; line-height: {LINE_BODY};
  color: {s['text_2']}; padding: {SPACE_2}px {SPACE_3}px; margin: 0 0 {SPACE_3}px;
  border-left: 2px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.03);
  border-radius: 0 {RADIUS_SM}px {RADIUS_SM}px 0; }}
.mx-footnote svg {{ flex: none; width: 14px; height: 14px; margin-top: 3px; opacity: 0.75; }}
.mx-pill {{ display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: {RADIUS_PILL}px;
  font-size: {TEXT_XS + 1}px; font-weight: 600; background: {s['card_alt']}; color: {s['text_2']};
  margin: 0 6px 6px 0; white-space: nowrap; }}
.mx-pill.pass {{ background: var(--mx-pass-soft); color: {PASS}; }}
.mx-pill.fail {{ background: var(--mx-fail-soft); color: {FAIL}; }}
.mx-pill.accent {{ background: var(--mx-accent-soft); color: {ACCENT}; }}
.mx-pill.amber {{ background: var(--mx-amber-soft); color: {s['amber_text']}; }}
.mx-pill.win {{ background: {ACCENT}; color: #fff; box-shadow: 0 0 18px rgba(10,132,255,0.55); }}
.mx-pill.wrap {{ white-space: normal; text-align: left; line-height: 1.35; border-radius: {RADIUS_SM}px; }}
.mx-msg {{ border-radius: {RADIUS_MD}px; padding: {SPACE_3}px {SPACE_4}px; font-size: {TEXT_SM + 1}px;
  margin-bottom: {SPACE_2}px; display: flex; gap: {SPACE_3}px; align-items: baseline; }}
.mx-msg.red {{ background: var(--mx-fail-soft); color: {s['text']}; }}
.mx-msg.red b {{ color: {FAIL}; }}
.mx-msg.yellow {{ background: var(--mx-amber-soft); color: {s['text']}; }}
.mx-msg.yellow b {{ color: {s['amber_text']}; }}
.mx-msg.ok {{ background: var(--mx-pass-soft); color: {s['text']}; }}
.mx-msg.ok b {{ color: {PASS}; }}
.mx-msg.info {{ background: {s['card_alt']}; color: {s['text_2']}; }}
.mx-meter {{ height: 6px; border-radius: {RADIUS_PILL}px; background: {s['line']}; overflow: hidden; margin: 6px 0 2px; }}
.mx-meter > i {{ display: block; height: 100%; border-radius: {RADIUS_PILL}px; background: {s['text']};
  animation: mxgrow 900ms {EASE} both; transform-origin: left; }}
.mx-meter.pass > i {{ background: {PASS}; }}
.mx-meter.fail > i {{ background: {FAIL}; }}
.mx-gauge {{ display: flex; align-items: center; gap: {SPACE_3}px; }}
.mx-gauge svg {{ flex: none; }}
.mx-funnel {{ display: flex; align-items: stretch; gap: {SPACE_2}px; flex-wrap: wrap; }}
.mx-funnel > div {{ flex: 1; min-width: 140px; background: {s['card']}; border-radius: {RADIUS_MD}px;
  padding: {SPACE_4}px; box-shadow: {s['shadow']}; }}
.mx-funnel .n {{ font-family: {FONT_MONO}; font-size: {TEXT_XL}px; font-weight: {WEIGHT_MEDIUM}; letter-spacing: -0.02em;
  color: {s['text']}; font-variant-numeric: tabular-nums; }}
.mx-foot {{ font-size: {TEXT_XS + 1}px; color: {s['text_2']}; border-top: 1px solid {s['line']};
  padding-top: {SPACE_3}px; margin-top: {SPACE_5}px; }}
.mx-check {{ display: inline-block; width: 18px; height: 18px; vertical-align: -3px; }}
.mx-check path {{ stroke-dasharray: 24; stroke-dashoffset: 24; animation: mxdraw 700ms {EASE} 200ms forwards; }}
.mx-kv {{ display: grid; grid-template-columns: auto 1fr; gap: 4px {SPACE_4}px; font-size: {TEXT_SM}px; }}
.mx-kv span:nth-child(odd) {{ color: {s['text_2']}; }}
.mx-table {{ width: 100%; border-collapse: collapse; font-size: {TEXT_SM}px; font-variant-numeric: tabular-nums;
  border: 0 !important; margin: 0; }}
.mx-table th, .mx-table td {{ border: 0 !important; background: transparent !important; vertical-align: middle; }}
.mx-table th {{ text-align: left; font-weight: 600; color: {s['text_2']}; font-size: {TEXT_XS}px;
  letter-spacing: {EYEBROW_TRACKING}; text-transform: uppercase; padding: {SPACE_2}px {SPACE_3}px {SPACE_2}px 0;
  border-bottom: 1px solid {s['line']} !important; }}
.mx-table td.mx-num {{ font-size: {TEXT_SM - 1}px; }}
.mx-table td {{ padding: {SPACE_2 + 2}px {SPACE_3}px {SPACE_2 + 2}px 0; color: {s['text']};
  border-top: 1px solid {s['line']} !important; }}
.mx-table tbody tr:first-child td {{ border-top: 0 !important; }}
.mx-table th:last-child, .mx-table td:last-child {{ padding-right: 0; }}
.mx-table .mx-pill {{ margin: 0; }}
.mx-swatch {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: 0; }}
.mx-other {{ color: {other['text']}; }}
{proc_css}

/* entrances name only their start: the end is the element's own style, so a quiet card settles at its own
   opacity and tint instead of the keyframe's */
@keyframes mxrise {{ from {{ opacity: 0; transform: translateY({RISE_PX}px); filter: blur({RISE_BLUR_PX}px) saturate(1); }} }}
@keyframes mxfade {{ from {{ opacity: 0; }} }}
@keyframes mxgrow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
@keyframes mxdraw {{ to {{ stroke-dashoffset: 0; }} }}
@media (prefers-reduced-motion: reduce) {{
  * {{ transition: none !important; }}
  [class*="st-key-card"], [class*="st-key-stage"], [class*="st-key-preview"], .mx-card {{
    animation: mxfade {PRESS_MS}ms {EASE_OUT} both !important; }}
  .mx-meter > i {{ animation: none !important; }}
  .mx-check path {{ animation: none !important; stroke-dashoffset: 0; }}
  .stButton > button:not(:disabled):active, [class*="st-key-preview"]:hover {{ transform: none; }}
}}
</style>
"""
