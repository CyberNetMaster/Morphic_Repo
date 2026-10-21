"""The one place for every color, font, radius, shadow and spacing value in the app.

Every other app module reads its styling from here: the CSS injected into Streamlit,
the Plotly layouts, and the color scales for stress and density maps.
"""

from __future__ import annotations

# ----------------------------------------------------------------------------- fonts
FONT_SANS = ("Inter, 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI Variable Text', "
             "'Segoe UI', system-ui, sans-serif")
FONT_MONO = "'JetBrains Mono', 'SF Mono', 'Cascadia Mono', Consolas, monospace"

# type scale (px)
TEXT_XS = 11
TEXT_SM = 13
TEXT_MD = 15
TEXT_LG = 19
TEXT_XL = 28
TEXT_HERO = 44
EYEBROW_TRACKING = "0.08em"

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

# ----------------------------------------------------------------------------- light surfaces
LIGHT = {
    "bg": "#F5F5F7",
    "card": "#FFFFFF",
    "card_alt": "#FAFAFB",
    "text": "#1D1D1F",
    "text_2": "#86868B",
    "line": "rgba(0,0,0,0.06)",
    "shadow": "0 1px 2px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.06)",
    "shadow_hover": "0 2px 4px rgba(0,0,0,0.05), 0 14px 36px rgba(0,0,0,0.09)",
    "glass": "rgba(255,255,255,0.72)",
    "input": "#F2F2F5",
}

# ----------------------------------------------------------------------------- dark stage
DARK = {
    "bg": "#050506",
    "card": "#141416",
    "card_alt": "#1C1C1F",
    "text": "#F5F5F7",
    "text_2": "#8E8E93",
    "line": "rgba(255,255,255,0.07)",
    "shadow": "0 1px 0 rgba(255,255,255,0.04) inset, 0 12px 32px rgba(0,0,0,0.55)",
    "shadow_hover": "0 1px 0 rgba(255,255,255,0.06) inset, 0 18px 44px rgba(0,0,0,0.7)",
    "glass": "rgba(28,28,31,0.66)",
    "input": "#1C1C1F",
}

# ----------------------------------------------------------------------------- the one accent + status
ACCENT = "#0A84FF"
ACCENT_SOFT = "rgba(10,132,255,0.12)"
PASS = "#30B35A"
PASS_SOFT = "rgba(48,179,90,0.12)"
FAIL = "#E5484D"
FAIL_SOFT = "rgba(229,72,77,0.12)"
DEFAULT_AMBER = "#F2A93B"
DEFAULT_AMBER_SOFT = "rgba(242,169,59,0.16)"
MUTED = "#A1A1A6"

# one color per load case (drawing arrows, deflection rows)
LOAD_CASE_COLORS = ["#FF5A4E", "#FF9F0A", "#BF5AF2", "#64D2FF"]

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

# ----------------------------------------------------------------------------- motion
EASE = "cubic-bezier(0.22, 1, 0.36, 1)"
RISE_MS = 420


def surface(dark: bool) -> dict:
    return DARK if dark else LIGHT


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
    return dict(title=dict(text=title, font=dict(size=TEXT_XS, color=s["text_2"])), showgrid=grid,
                gridcolor=s["line"], gridwidth=1, zeroline=False, showline=False,
                tickfont=dict(size=TEXT_XS, color=s["text_2"]), ticks="")


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
  font-family: {FONT_SANS}; font-feature-settings: "tnum" 1, "cv11" 1; -webkit-font-smoothing: antialiased;
}}
.stApp {{ transition: background {RISE_MS}ms {EASE}; }}
[data-testid="stHeader"] {{ background: transparent; height: 0; }}
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer {{ display: none !important; }}
.block-container {{ padding-top: {SPACE_5}px !important; padding-bottom: {SPACE_7 * 2}px !important;
  max-width: 1280px; }}
.stApp p, .stApp li, .stApp label, .stApp span, .stApp div {{ font-family: {FONT_SANS}; }}
.stApp code {{ font-family: {FONT_MONO}; }}
.stApp [data-testid="stIconMaterial"], .stApp .material-symbols-rounded, .stApp span[class*="material-symbols"] {{
  font-family: "Material Symbols Rounded" !important; }}
h1, h2, h3, h4 {{ font-family: {FONT_SANS} !important; color: {s['text']} !important;
  letter-spacing: -0.02em; font-weight: 650 !important; }}
[data-testid="stMarkdownContainer"] p {{ color: {s['text']}; }}
[data-testid="stCaptionContainer"], .stCaption {{ color: {s['text_2']} !important; }}
hr {{ border-color: {s['line']} !important; }}

/* ---- buttons: soft, lit, physical */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
  border-radius: {RADIUS_PILL}px; border: none; padding: {SPACE_2}px {SPACE_5}px;
  background: {s['card']}; color: {s['text']}; font-weight: 550; font-size: {TEXT_SM + 1}px;
  box-shadow: {s['shadow']}; transition: transform 160ms {EASE}, box-shadow 160ms {EASE};
}}
.stButton > button:hover, .stDownloadButton > button:hover {{ transform: translateY(-1px);
  box-shadow: {s['shadow_hover']}; color: {s['text']}; border: none; }}
.stButton > button:active {{ transform: translateY(0) scale(0.98); }}
.stButton > button:focus:not(:active) {{ color: {s['text']}; border: none; }}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
  background: linear-gradient(180deg, #2D95FF, {ACCENT}); color: #fff;
  box-shadow: 0 1px 0 rgba(255,255,255,0.25) inset, 0 8px 22px rgba(10,132,255,0.32); }}
.stButton > button[kind="primary"]:hover {{ color: #fff; }}
.stButton > button:disabled {{ opacity: 0.45; transform: none; box-shadow: none; }}
.stButton > button[kind="tertiary"] {{ background: transparent; box-shadow: none; color: {s['text_2']};
  padding: {SPACE_1}px {SPACE_3}px; }}
.stButton > button[kind="tertiary"]:hover {{ color: {s['text']}; box-shadow: none; transform: none; }}

/* ---- inputs */
.stTextArea textarea, .stTextInput input, .stNumberInput input, [data-baseweb="select"] > div {{
  background: {s['input']} !important; color: {s['text']} !important; border: none !important;
  border-radius: {RADIUS_MD}px !important; font-family: {FONT_SANS} !important; }}
.stTextArea textarea {{ font-size: {TEXT_MD + 1}px; line-height: 1.55; padding: {SPACE_4}px {SPACE_5}px !important; }}
.stTextArea [data-baseweb="textarea"], .stTextInput [data-baseweb="input"], .stNumberInput [data-baseweb="input"] {{
  border: none !important; border-radius: {RADIUS_MD}px !important; background: {s['input']} !important; }}
[data-testid="stWidgetLabel"] p {{ color: {s['text_2']} !important; font-size: {TEXT_SM}px !important; }}

/* ---- toggles */
[data-testid="stToggle"] label div[role="switch"], .stToggle [role="checkbox"] {{ box-shadow: inset 0 1px 2px rgba(0,0,0,0.12); }}

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
[data-testid="stExpander"] summary:hover {{ color: {s['text']}; }}

/* ---- data editor / dataframe */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {{ border-radius: {RADIUS_MD}px; overflow: hidden;
  box-shadow: {s['shadow']}; }}

/* ---- bordered containers become cards */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{ }}
div[data-testid="stVerticalBlockBorderWrapper"][data-mx-card], .st-key-mxcard {{ }}
[class*="st-key-card"] {{ background: {s['card']}; border-radius: {RADIUS_LG}px; padding: {SPACE_5}px;
  box-shadow: {s['shadow']}; animation: mxrise {RISE_MS}ms {EASE} both; }}
[class*="st-key-stage"] {{ background: radial-gradient(120% 90% at 50% 0%, #17171B 0%, {DARK['bg']} 70%);
  border-radius: {RADIUS_XL}px; padding: {SPACE_5}px; box-shadow: {DARK['shadow']};
  animation: mxrise {RISE_MS}ms {EASE} both; }}
[class*="st-key-card"][class*="_win"] {{ box-shadow: {s['shadow']}, 0 0 0 1px rgba(10,132,255,0.35), 0 0 42px rgba(10,132,255,0.22); }}
[class*="st-key-card"][class*="_quiet"] {{ opacity: 0.6; filter: saturate(0.25); }}
[class*="st-key-card"][class*="_quiet"]:hover {{ opacity: 1; filter: none; }}
[class*="st-key-card_fdm"] {{ background-image: {PROCESS['fdm']['tint_dark' if dark else 'tint_light']}; }}
[class*="st-key-card_sls"] {{ background-image: {PROCESS['sls']['tint_dark' if dark else 'tint_light']}; }}
[class*="st-key-card_metal"] {{ background-image: {PROCESS['metal']['tint_dark' if dark else 'tint_light']}; }}
[class*="st-key-card_fdm"] .mx-eyebrow-proc {{ color: {PROCESS['fdm']['color']}; }}
[class*="st-key-card_sls"] .mx-eyebrow-proc {{ color: {PROCESS['sls']['color']}; }}
[class*="st-key-card_metal"] .mx-eyebrow-proc {{ color: {PROCESS['metal']['color']}; }}
[class*="st-key-agent"] {{ background: {s['glass']}; backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
  border-radius: {RADIUS_XL}px; padding: {SPACE_5}px; border: 1px dashed {s['line']};
  box-shadow: {s['shadow']}; }}

/* ---- Morphic HTML components */
.mx-topbar {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: {SPACE_4}px; }}
.mx-brand {{ font-size: {TEXT_LG + 3}px; font-weight: 700; letter-spacing: -0.03em; color: {s['text']}; }}
.mx-brand small {{ font-size: {TEXT_SM}px; font-weight: 500; color: {s['text_2']}; letter-spacing: 0;
  margin-left: {SPACE_3}px; }}
.mx-steps {{ display: flex; gap: {SPACE_1}px; background: {s['card']}; padding: {SPACE_1}px;
  border-radius: {RADIUS_PILL}px; box-shadow: {s['shadow']}; }}
.mx-step {{ padding: 6px {SPACE_4}px; border-radius: {RADIUS_PILL}px; font-size: {TEXT_SM}px; font-weight: 550;
  color: {s['text_2']}; white-space: nowrap; }}
.mx-step b {{ font-weight: 650; margin-right: 6px; opacity: 0.55; }}
.mx-step.on {{ background: {s['text']}; color: {s['bg']}; }}
.mx-step.done {{ color: {s['text']}; }}
.mx-title {{ font-size: {TEXT_XL + 6}px; font-weight: 700; letter-spacing: -0.03em; color: {s['text']};
  margin: {SPACE_3}px 0 {SPACE_1}px 0; line-height: 1.1; }}
.mx-sub {{ font-size: {TEXT_MD + 1}px; color: {s['text_2']}; margin-bottom: {SPACE_5}px; max-width: 720px; }}
.mx-eyebrow {{ font-size: {TEXT_XS}px; letter-spacing: {EYEBROW_TRACKING}; text-transform: uppercase;
  color: {s['text_2']}; font-weight: 600; }}
.mx-card {{ background: {s['card']}; border-radius: {RADIUS_LG}px; padding: {SPACE_5}px; box-shadow: {s['shadow']};
  animation: mxrise {RISE_MS}ms {EASE} both; position: relative; overflow: hidden; }}
.mx-card.quiet {{ opacity: 0.55; filter: saturate(0.2); transform: scale(0.98); }}
.mx-card.win {{ box-shadow: {s['shadow']}, 0 0 0 1px rgba(10,132,255,0.35), 0 0 42px rgba(10,132,255,0.22); }}
.mx-hero {{ font-size: {TEXT_HERO}px; font-weight: 650; letter-spacing: -0.035em; line-height: 1; color: {s['text']};
  font-variant-numeric: tabular-nums; }}
.mx-hero small {{ font-size: {TEXT_LG}px; font-weight: 500; color: {s['text_2']}; margin-left: 4px; letter-spacing: 0; }}
.mx-label {{ font-size: {TEXT_SM}px; color: {s['text_2']}; }}
.mx-num {{ font-variant-numeric: tabular-nums; }}
.mx-row {{ display: flex; justify-content: space-between; gap: {SPACE_3}px; font-size: {TEXT_SM}px;
  padding: 5px 0; color: {s['text']}; }}
.mx-row span:first-child {{ color: {s['text_2']}; }}
.mx-note {{ font-size: {TEXT_XS + 1}px; color: {s['text_2']}; line-height: 1.5; }}
.mx-pill {{ display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: {RADIUS_PILL}px;
  font-size: {TEXT_XS + 1}px; font-weight: 600; background: {s['card_alt']}; color: {s['text_2']};
  margin: 0 6px 6px 0; white-space: nowrap; }}
.mx-pill.pass {{ background: var(--mx-pass-soft); color: {PASS}; }}
.mx-pill.fail {{ background: var(--mx-fail-soft); color: {FAIL}; }}
.mx-pill.accent {{ background: var(--mx-accent-soft); color: {ACCENT}; }}
.mx-pill.amber {{ background: var(--mx-amber-soft); color: #B7791F; }}
.mx-pill.win {{ background: {ACCENT}; color: #fff; box-shadow: 0 0 18px rgba(10,132,255,0.55); }}
.mx-msg {{ border-radius: {RADIUS_MD}px; padding: {SPACE_3}px {SPACE_4}px; font-size: {TEXT_SM + 1}px;
  margin-bottom: {SPACE_2}px; display: flex; gap: {SPACE_3}px; align-items: baseline; }}
.mx-msg.red {{ background: var(--mx-fail-soft); color: {s['text']}; }}
.mx-msg.red b {{ color: {FAIL}; }}
.mx-msg.yellow {{ background: var(--mx-amber-soft); color: {s['text']}; }}
.mx-msg.yellow b {{ color: #B7791F; }}
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
.mx-funnel .n {{ font-size: {TEXT_XL}px; font-weight: 650; letter-spacing: -0.02em; color: {s['text']};
  font-variant-numeric: tabular-nums; }}
.mx-foot {{ font-size: {TEXT_XS + 1}px; color: {s['text_2']}; border-top: 1px solid {s['line']};
  padding-top: {SPACE_3}px; margin-top: {SPACE_5}px; }}
.mx-check {{ display: inline-block; width: 18px; height: 18px; vertical-align: -3px; }}
.mx-check path {{ stroke-dasharray: 24; stroke-dashoffset: 24; animation: mxdraw 700ms {EASE} 200ms forwards; }}
.mx-kv {{ display: grid; grid-template-columns: auto 1fr; gap: 4px {SPACE_4}px; font-size: {TEXT_SM}px; }}
.mx-kv span:nth-child(odd) {{ color: {s['text_2']}; }}
.mx-table {{ width: 100%; border-collapse: collapse; font-size: {TEXT_SM}px; font-variant-numeric: tabular-nums; }}
.mx-table th {{ text-align: left; font-weight: 600; color: {s['text_2']}; font-size: {TEXT_XS}px;
  letter-spacing: {EYEBROW_TRACKING}; text-transform: uppercase; padding: 6px 8px; }}
.mx-table td {{ padding: 8px; border-top: 1px solid {s['line']}; color: {s['text']}; }}
.mx-swatch {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: 0; }}
.mx-other {{ color: {other['text']}; }}
{proc_css}

@keyframes mxrise {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
@keyframes mxgrow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
@keyframes mxdraw {{ to {{ stroke-dashoffset: 0; }} }}
@media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; transition: none !important; }} }}
</style>
"""
