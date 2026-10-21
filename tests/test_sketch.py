"""Sketch to design: photo preparation, the image request through the adapter (Gemini and Claude),
a fake-LLM reading of a sample sketch drawn in code, retry and failure paths, the command line, and
the Describe-step upload control. No test makes a network call."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from morphic import config, llm, parse, sanity, sketch
from morphic.materials import load_materials, load_processes
from morphic.problem import problem_from_dict
from tests.sketch_sample import APPROVED_JSON, FAKE_ANSWER, SAMPLE_PNG, sample_png

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
IMAGE = llm.Image(b"\xff\xd8 jpeg bytes", "image/jpeg")


class FakeVisionLLM:
    """Gives fixed answers in order and records every request."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, system, user, image, timeout_s):
        self.calls.append(SimpleNamespace(system=system, user=user, image=image, timeout_s=timeout_s))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return llm.LLMResult(answer, "fake", "fake-vision")


@pytest.fixture(scope="module")
def png() -> bytes:
    return sample_png()


def approved():
    return problem_from_dict(json.loads(APPROVED_JSON.read_text(encoding="utf-8")))


def decoded(image: llm.Image):
    with Image.open(io.BytesIO(image.data)) as im:
        return im.format, im.mode, im.size


def encoded(img: Image.Image, fmt: str = "PNG", **kw) -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt, **kw)
    return buf.getvalue()


# ----------------------------------------------------------------------------- the sample sketch
def test_sample_sketch_is_deterministic_and_matches_the_committed_file(png):
    assert png == sample_png()
    with Image.open(io.BytesIO(png)) as a, Image.open(SAMPLE_PNG) as b:
        assert a.size == b.size == (1800, 1150)
        diff = np.abs(np.asarray(a.convert("L"), float) - np.asarray(b.convert("L"), float))
    assert diff.mean() < 0.5  # same drawing; allows tiny font-rasterizer differences
    ink = np.asarray(Image.open(io.BytesIO(png)).convert("L")) < 120
    assert 0.01 < ink.mean() < 0.2  # pencil strokes on paper, not a blank or black image


# ----------------------------------------------------------------------------- photo preparation
def test_prepare_image_gives_an_rgb_jpeg_within_the_size_limits():
    img = Image.new("RGBA", (5000, 3000), (0, 0, 0, 0))
    img.paste((40, 40, 40, 255), (100, 100, 400, 400))
    out = sketch.prepare_image(encoded(img))
    fmt, mode, (w, h) = decoded(out)
    assert out.mime_type == "image/jpeg" and fmt == "JPEG" and mode == "RGB"
    assert max(w, h) <= sketch.MAX_EDGE_PX and w * h <= sketch.MAX_PIXELS and len(out.data) <= sketch.MAX_IMAGE_BYTES
    assert abs(w / h - 5 / 3) < 0.01
    with Image.open(io.BytesIO(out.data)) as im:
        assert min(im.getpixel((w - 5, h - 5))) > 245  # transparent became white, not black
        assert max(im.getpixel((100, 100))) < 80


def test_prepare_image_keeps_a_small_enough_photo_at_full_size(png):
    assert decoded(sketch.prepare_image(png))[2] == (1800, 1150)


def test_prepare_image_applies_the_camera_rotation():
    exif = Image.Exif()
    exif[0x0112] = 6  # stored sideways; turn 90 degrees clockwise to view
    data = encoded(Image.new("RGB", (640, 480), "white"), "JPEG", exif=exif)
    assert decoded(sketch.prepare_image(data))[2] == (480, 640)


@pytest.mark.parametrize("make,words", [
    (lambda: b"", "empty"),
    (lambda: b"just some notes", "not a PNG, JPEG or WebP"),
    (lambda: b"\0" * (sketch.MAX_UPLOAD_MB * 1024 * 1024 + 1), "limit is 20 MB"),
    (lambda: encoded(Image.new("RGB", (400, 200), "white")), "too small"),
], ids=["empty", "not-an-image", "too-large", "too-small"])
def test_prepare_image_rejects_unusable_files(make, words):
    with pytest.raises(sketch.SketchImageError, match=words):
        sketch.prepare_image(make())


# ----------------------------------------------------------------------------- adapter: one image, both providers
def test_gemini_sends_the_image_part_before_the_text(monkeypatch):
    from google import genai
    from google.genai import types

    sent = {}

    def client(**kwargs):
        def generate_content(**k):
            sent.update(k)
            return SimpleNamespace(text="{}")
        return SimpleNamespace(close=lambda: None, models=SimpleNamespace(generate_content=generate_content))

    monkeypatch.setattr(llm, "_key", lambda name: "unused-test-value")
    monkeypatch.setattr(genai, "Client", client)
    assert llm.complete("system", "user", 30, image=IMAGE, provider="gemini").provider == "gemini"
    part, text = sent["contents"]
    assert isinstance(part, types.Part) and text == "user"
    assert part.inline_data.data == IMAGE.data and part.inline_data.mime_type == "image/jpeg"
    llm.complete("system", "user", 30, provider="gemini")
    assert sent["contents"] == "user"  # text requests are unchanged


def test_claude_sends_a_base64_image_block_before_the_text(monkeypatch):
    import anthropic

    sent = {}

    def client(**kwargs):
        assert kwargs["max_retries"] == 0
        def create(**k):
            sent.update(k)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="{}")])
        return SimpleNamespace(close=lambda: None, messages=SimpleNamespace(create=create))

    monkeypatch.setattr(llm, "_key", lambda name: "unused-test-value")
    monkeypatch.setattr(anthropic, "Anthropic", client)
    res = llm.complete("system", "user", 30, image=IMAGE, provider="claude")
    assert (res.provider, res.model, res.text) == ("claude", config.LLM_MODELS["claude"], "{}")
    block, text = sent["messages"][0]["content"]
    assert block == {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                 "data": base64.standard_b64encode(IMAGE.data).decode()}}
    assert text == {"type": "text", "text": "user"} and sent["max_tokens"] == 16000
    llm.complete("system", "user", 30, provider="claude")
    assert sent["messages"] == [{"role": "user", "content": "user"}] and sent["max_tokens"] == 4096


def test_provider_override_keeps_the_text_call_signature(monkeypatch):
    calls = []
    monkeypatch.setitem(llm._PROVIDERS, "claude",
                        lambda *a, **k: calls.append((a, k)) or llm.LLMResult("{}", "claude", "m"))
    llm.complete("s", "u", 5, image=IMAGE, provider="claude")
    llm.complete("s", "u", 5, provider="claude")
    assert calls == [(("s", "u", 5), {"image": IMAGE}), (("s", "u", 5), {})]
    assert config.LLM_PROVIDER == "gemini"  # the override does not change the configured provider
    with pytest.raises(llm.LLMError, match="unknown"):
        llm.complete("s", "u", provider="nope")


def test_transport_retry_resends_the_image(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    seen = []

    def provider(system, user, timeout_s, image=None):
        seen.append(image)
        if len(seen) == 1:
            busy = RuntimeError("overloaded")
            busy.code = 503
            raise busy
        return llm.LLMResult("{}", "gemini", "m")

    monkeypatch.setitem(llm._PROVIDERS, "gemini", provider)
    llm.complete("s", "u", 5, image=IMAGE, provider="gemini")
    assert seen == [IMAGE, IMAGE]


# ----------------------------------------------------------------------------- reading the sample with a fake LLM
def test_fake_llm_reading_of_the_sample_matches_the_approved_problem(png):
    fake = FakeVisionLLM([FAKE_ANSWER])
    materials, processes = load_materials(), load_processes()
    r = sketch.read_sketch(png, llm_call=fake, min_walls=[p.min_wall_mm for p in processes.values()])
    p = r.problem
    assert parse.compare_problems(p, approved()) == []
    assert p.zones[0].kind == "keep_out" and p.zones[0].circle.model_dump() == {"cx": 60, "cy": 20, "r": 8}
    assert sanity.blocking(sanity.check(p, processes, materials)) == []

    (call,) = fake.calls  # the normalized photo, the sketch rules, the parser's rules and schema
    assert call.image == r.image and decoded(call.image)[2] == (1800, 1150)
    assert call.system.endswith(parse.schema_text())
    assert "y UP" in call.system and "hole_r_mm is the hole RADIUS" in call.system
    assert "You turn a plain-English description" not in call.system
    assert "There is no typed note." in call.user and call.timeout_s == sketch.SKETCH_TIMEOUT_S
    assert r.upload_sha256 == hashlib.sha256(png).hexdigest()

    # provenance as the text parser records it, with labels read from the sketch marked
    assert p.source_of("thickness_mm").original_text == "sketch: t = 6 mm"
    assert p.source_of("pads[2].hole_r_mm").original_text == "sketch: Ø6"
    assert p.source_of("load_cases[0].max_deflection_mm").original_text == "sketch: max deflection 0.5 mm"
    for path in ("safety_factor", "printer", "materials", "pads[0].ring_r_mm"):
        assert p.source_of(path).source == "default"
    assert len(p.warnings) == 2 and all("scaled from the drawing" in w for w in p.warnings)


def test_typed_note_goes_with_the_photo_and_keeps_its_own_quotes(png):
    answer = json.loads(FAKE_ANSWER)
    answer["printer"] = "desktop_fdm"
    answer["original_text"]["printer"] = "desktop FDM printer"
    fake = FakeVisionLLM([json.dumps(answer)])
    r = sketch.read_sketch(png, "Printed on a desktop FDM printer.", llm_call=fake)
    assert '"""\nPrinted on a desktop FDM printer.\n"""' in fake.calls[0].user
    assert r.problem.printer == "desktop_fdm"
    assert r.problem.source_of("printer").original_text == "desktop FDM printer"  # from the note
    assert r.problem.source_of("thickness_mm").original_text == "sketch: t = 6 mm"


def test_invalid_answer_is_retried_once_with_the_error_and_the_same_photo(png):
    fake = FakeVisionLLM(["Here is the part you drew.", "```json\n" + FAKE_ANSWER + "\n```"])
    r = sketch.read_sketch(png, llm_call=fake)
    assert len(r.attempts) == 2 and "error" in r.attempts[0] and "error" not in r.attempts[1]
    assert "not valid" in fake.calls[1].user and "Here is the part you drew." in fake.calls[1].user
    assert fake.calls[0].image == fake.calls[1].image
    assert parse.compare_problems(r.problem, approved()) == []


def test_answer_that_never_validates_raises_parse_failed(png):
    bad = json.dumps({**json.loads(FAKE_ANSWER), "supports": [{"pad_id": "Z", "type": "pin"}]})
    fake = FakeVisionLLM([bad, bad])
    with pytest.raises(parse.ParseFailed, match="did not validate") as caught:
        sketch.read_sketch(png, llm_call=fake)
    assert len(caught.value.attempts) == 2 and len(fake.calls) == 2


def test_photo_that_is_not_a_sketch_stops_without_a_retry(png):
    fake = FakeVisionLLM(['{"not_a_sketch": "The photo shows a cat."}', FAKE_ANSWER])
    with pytest.raises(parse.ParseFailed, match=r"does not look like a part sketch \(The photo shows a cat\)$"):
        sketch.read_sketch(png, llm_call=fake)
    assert len(fake.calls) == 1


def test_llm_failure_and_timeout_raise_parse_failed(png):
    fake = FakeVisionLLM([llm.LLMError("gemini request failed (ServerError, status 500; 1 attempts)")])
    with pytest.raises(parse.ParseFailed, match="status 500"):
        sketch.read_sketch(png, llm_call=fake)

    def slow(*args):
        time.sleep(0.5)
        return FAKE_ANSWER

    with pytest.raises(parse.ParseFailed, match="did not answer within 0.05 s"):
        sketch.read_sketch(png, llm_call=slow, timeout_s=0.05)


def test_unusable_file_fails_before_any_llm_call():
    fake = FakeVisionLLM([FAKE_ANSWER])
    with pytest.raises(sketch.SketchImageError):
        sketch.read_sketch(b"just some notes", llm_call=fake)
    assert fake.calls == []


def test_default_call_goes_through_the_adapter_with_the_chosen_provider(monkeypatch, png):
    seen = []

    def provider(system, user, timeout_s, image=None):
        seen.append((timeout_s, image))
        return llm.LLMResult(FAKE_ANSWER, "claude", config.LLM_MODELS["claude"])

    monkeypatch.setitem(llm._PROVIDERS, "claude", provider)
    r = sketch.read_sketch(png, provider="claude")
    assert (r.provider, r.model) == ("claude", config.LLM_MODELS["claude"])
    assert seen == [(sketch.SKETCH_TIMEOUT_S, r.image)]


def test_reader_waits_for_the_adapter_retry_budget(monkeypatch, png):
    waits = []

    class Future:
        def result(self, timeout):
            waits.append(timeout)
            raise llm.LLMError("exhausted")

    monkeypatch.setattr(sketch._POOL, "submit", lambda *a: Future())
    with pytest.raises(parse.ParseFailed, match="exhausted"):
        sketch.read_sketch(png)
    assert waits == [515]  # five 90-second attempts + 60 s backoff + 5 s overhead


# ----------------------------------------------------------------------------- command line
def test_command_line_reads_a_photo_and_compares_with_the_approved_problem(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sketch, "_default_llm", lambda *a, **k: llm.LLMResult(FAKE_ANSWER, "fake", "fake-vision"))
    out = tmp_path / "problem.json"
    assert sketch.main([str(SAMPLE_PNG), "--out", str(out), "--expect", str(APPROVED_JSON)]) == 0
    text = capsys.readouterr().out
    assert "Matches the approved problem." in text and "warning: Pad L height scaled" in text
    saved = problem_from_dict(json.loads(out.read_text(encoding="utf-8")))
    assert parse.compare_problems(saved, approved()) == []


def test_command_line_reports_differences(monkeypatch, capsys):
    answer = json.loads(FAKE_ANSWER)
    answer["load_cases"][0]["loads"][0]["fy_N"] = -25
    monkeypatch.setattr(sketch, "_default_llm", lambda *a, **k: llm.LLMResult(json.dumps(answer), "fake", "fake"))
    assert sketch.main([str(SAMPLE_PNG), "--expect", str(APPROVED_JSON)]) == 2
    assert "Differences:" in capsys.readouterr().out


# ----------------------------------------------------------------------------- the Describe-step control
def describe_app():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


def upload_and_read(at, name: str, data: bytes):
    at.file_uploader(key="sketch_file").upload(name, data, "image/png").run()
    assert not at.button(key="sketch_btn").disabled
    at.button(key="sketch_btn").click().run()
    assert not at.exception, at.exception


def test_describe_step_reads_an_uploaded_sketch_into_the_check_step(monkeypatch, png):
    prompts = []

    def fake(system, user, image, timeout_s, provider=None):
        prompts.append(user)
        return llm.LLMResult(FAKE_ANSWER, "fake", "fake-vision")

    monkeypatch.setattr(sketch, "_default_llm", fake)
    at = describe_app()
    assert at.button(key="sketch_btn").disabled  # nothing uploaded yet
    at.text_area[0].input("Bolted to a steel wall.").run()
    next(s for s in at.selectbox if s.label == "Printer").set_value("desktop_fdm").run()
    upload_and_read(at, "bracket.png", png)
    S = at.session_state
    assert S["step"] == 1 and S["parse_fail"] is None
    assert parse.compare_problems(S["problem"], approved()) == ["printer: parsed desktop_fdm, approved any"]
    assert S["problem"].source_of("printer").original_text == "printer selector"
    assert '"""\nBolted to a steel wall.\n"""' in prompts[0]
    assert any("Check the problem" in m.value for m in at.markdown)
    assert not any("Stops the run" in m.value for m in at.markdown)  # no red check blocks it


def test_unusable_upload_stays_on_describe_with_a_message(monkeypatch):
    calls = []
    monkeypatch.setattr(sketch, "_default_llm", lambda *a, **k: calls.append(a))
    at = describe_app()
    upload_and_read(at, "notes.png", b"just some notes")
    assert at.session_state["step"] == 0 and calls == []
    assert any("Could not open the photo" in m.value for m in at.markdown)


def test_failed_sketch_reading_opens_the_manual_form(monkeypatch, png):
    monkeypatch.setattr(sketch, "_default_llm", lambda *a, **k: llm.LLMResult("no JSON here", "fake", "fake"))
    at = describe_app()
    upload_and_read(at, "bracket.png", png)
    assert at.session_state["step"] == 1 and at.session_state["problem"] is None
    assert "did not validate" in at.session_state["parse_fail"]
    assert any("Could not read the description" in m.value for m in at.markdown)


def test_upload_control_styles_come_from_theme_tokens():
    from app import sketch_upload, theme

    css = sketch_upload.css()
    assert ".st-key-sketch_upload" in css and "var(--mx-input)" in css
    assert f"{theme.RADIUS_MD}px" in css and f"{theme.RADIUS_PILL}px" in css
    stray = re.findall(r"#[0-9A-Fa-f]{3,8}\b", css.replace(theme.MUTED, "").replace(theme.ACCENT, ""))
    assert stray == []  # no colors other than theme tokens
