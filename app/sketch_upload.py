"""Describe step: a small upload control that reads a photo of a hand sketch.

Self-contained so the Describe screen can change around it: page_describe makes one call,
`control(note, printer)`. The result goes to the Check step exactly like a parsed description.
All style values come from theme.py.
"""

from __future__ import annotations

from urllib.parse import quote

import streamlit as st

from app import theme, ui
from morphic import form as formmod
from morphic import parse, sketch
from morphic.materials import load_processes
from morphic.problem import Provenance

KEY = "sketch_upload"


def _sketch_icon() -> str:
    """An original glyph for the drop zone: a pencil finishing a short strut between two nodes."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 22 22" fill="none" stroke="{theme.MUTED}" '
           'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
           '<path d="M4 16.5 L12.5 8"/><circle cx="4" cy="16.5" r="1.7"/><circle cx="13" cy="7.5" r="1.7"/>'
           '<path d="M14.5 3.5 l3.5 3.5 -2.2 2.2 -3.5 -3.5 z"/><path d="M5 20 h12"/></svg>')
    return 'url("data:image/svg+xml,' + quote(svg, safe="") + '")'


def css() -> str:
    k = f".st-key-{KEY}"
    zone = f'{k} [data-testid="stFileUploaderDropzone"]'
    return f"""<style>
{k} {{ gap: {theme.SPACE_2}px; margin: {theme.SPACE_1}px 0 {theme.SPACE_2}px; }}
{zone} {{ background: rgba(255,255,255,0.03); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border: 1px dashed rgba(255,255,255,0.2); border-radius: {theme.RADIUS_MD}px; padding: {theme.SPACE_3}px {theme.SPACE_4}px;
  transition: background {theme.HOVER_MS}ms {theme.EASE_OUT}, border-color {theme.HOVER_MS}ms {theme.EASE_OUT}; }}
@media (hover: hover) {{ {zone}:hover {{ background: var(--mx-accent-soft); border-color: {theme.ACCENT}; }} }}
{zone} [data-testid="stFileUploaderDropzoneInstructions"] {{ display: flex; align-items: center; gap: {theme.SPACE_2}px; }}
{zone} [data-testid="stFileUploaderDropzoneInstructions"]::before {{ content: ""; width: 22px; height: 22px; flex: none;
  background: {_sketch_icon()} center / contain no-repeat; }}
{zone} [data-testid="stFileUploaderDropzoneInstructions"] span {{ font-size: {theme.TEXT_SM}px; color: var(--mx-text); }}
{zone} [data-testid="stFileUploaderDropzoneInstructions"] small {{ font-size: {theme.TEXT_XS}px; color: var(--mx-text-2); }}
{zone} button {{ border: none; border-radius: {theme.RADIUS_PILL}px; background: var(--mx-input); color: var(--mx-text);
  box-shadow: var(--mx-shadow); font-weight: {theme.WEIGHT_MEDIUM}; font-size: {theme.TEXT_SM}px;
  padding: {theme.SPACE_1}px {theme.SPACE_4}px; }}
</style>"""


def control(note: str, printer: str | None) -> None:
    """The upload box and its button. ``note`` (the description text) is sent with the photo;
    ``printer`` is the Describe selector's choice, or None for "from the text"."""
    with st.container(key=KEY):
        st.markdown(css() + ui.eyebrow("Sketch photo")
                    + f'<div class="mx-note" style="margin-bottom:{theme.SPACE_3}px">A photo of a hand sketch: '
                      'outline, holes, load arrows and written dimensions. Any text above is sent with it.</div>',
                    unsafe_allow_html=True)
        left, right = st.columns([2.2, 1], vertical_alignment="center")
        with left:
            photo = st.file_uploader("Sketch photo", type=list(sketch.ACCEPTED_TYPES), key="sketch_file",
                                     max_upload_size=sketch.MAX_UPLOAD_MB, label_visibility="collapsed")
        with right:
            clicked = st.button("Read my sketch", key="sketch_btn", disabled=photo is None, width="stretch")
        if clicked and photo is not None:
            _read(photo.getvalue(), note, printer)


def _read(data: bytes, note: str, printer: str | None) -> None:
    S = st.session_state
    with st.spinner("Reading your sketch… if this takes too long, a manual form will open."):
        try:
            r = sketch.read_sketch(data, note, min_walls=[p.min_wall_mm for p in load_processes().values()])
        except sketch.SketchImageError as exc:
            ui.msg(str(exc), "red", "Could not open the photo")
            return
        except parse.ParseFailed as exc:
            S.parse_fail = str(exc)
            S.problem, S.form, S.results = None, formmod.blank_form(), None
            S.step = 1
            st.rerun()
    # the same hand-off as read_description in streamlit_app.py
    p = r.problem
    if printer and printer != p.printer:
        p.printer = printer
        p.provenance["printer"] = Provenance(source="user", original_text="printer selector")
    S.problem, S.form, S.parse_fail, S.results = p, formmod.problem_to_form(p), None, None
    S.step = 1
    st.rerun()
