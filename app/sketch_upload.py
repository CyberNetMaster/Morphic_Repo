"""Describe step: a small upload control that reads a photo of a hand sketch.

Self-contained so the Describe screen can change around it: page_describe makes one call,
`control(note, printer)`. The result goes to the Check step exactly like a parsed description.
All style values come from theme.py.
"""

from __future__ import annotations

import streamlit as st

from app import theme, ui
from morphic import form as formmod
from morphic import parse, sketch
from morphic.materials import load_processes
from morphic.problem import Provenance

KEY = "sketch_upload"


def css() -> str:
    k = f".st-key-{KEY}"
    return f"""<style>
{k} {{ gap: {theme.SPACE_2}px; margin: {theme.SPACE_1}px 0 {theme.SPACE_2}px; }}
{k} [data-testid="stFileUploaderDropzone"] {{ background: var(--mx-input); border: 1px dashed {theme.MUTED};
  border-radius: {theme.RADIUS_MD}px; padding: {theme.SPACE_2}px {theme.SPACE_3}px;
  transition: background 160ms {theme.EASE}, border-color 160ms {theme.EASE}; }}
{k} [data-testid="stFileUploaderDropzone"]:hover {{ background: var(--mx-accent-soft); border-color: {theme.ACCENT}; }}
{k} [data-testid="stFileUploaderDropzoneInstructions"] span {{ font-size: {theme.TEXT_SM}px; color: var(--mx-text); }}
{k} [data-testid="stFileUploaderDropzoneInstructions"] small {{ font-size: {theme.TEXT_XS}px; color: var(--mx-text-2); }}
{k} [data-testid="stFileUploaderDropzone"] button {{ border: none; border-radius: {theme.RADIUS_PILL}px;
  background: var(--mx-card); color: var(--mx-text); box-shadow: var(--mx-shadow); font-weight: 550;
  font-size: {theme.TEXT_SM}px; padding: {theme.SPACE_1}px {theme.SPACE_4}px; }}
</style>"""


def control(note: str, printer: str | None) -> None:
    """The upload box and its button. ``note`` (the description text) is sent with the photo;
    ``printer`` is the Describe selector's choice, or None for "from the text"."""
    with st.container(key=KEY):
        st.markdown(css() + ui.eyebrow("Or a sketch")
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
