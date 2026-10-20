"""S10: schema, defaults, sanity checks, parse flow (retry once, fallback), manual form.

All parse tests use a fake LLM; the live Gemini run is a script (see the S10 report),
not a test, so the suite never depends on the network.
"""

import json
import time

import pytest

from morphic import config, form, parse, sanity
from morphic.problem import Problem, problem_from_dict


def base(**over):
    d = {
        "name": "t",
        "design_space": {"width_mm": 60, "height_mm": 30},
        "thickness_mm": 6,
        "pads": [{"id": "A", "cx": 6, "cy": 6, "hole_r_mm": 1.6, "ring_r_mm": 3.6},
                 {"id": "B", "cx": 6, "cy": 24, "hole_r_mm": 1.6, "ring_r_mm": 3.6},
                 {"id": "L", "cx": 52, "cy": 15, "hole_r_mm": 1.6, "ring_r_mm": 3.6}],
        "supports": [{"pad_id": "A", "type": "pin"}, {"pad_id": "B", "type": "pin"}],
        "load_cases": [{"id": "c1", "name": "down", "loads": [{"pad_id": "L", "fy_N": -100}],
                        "max_deflection_mm": 0.5}],
        "safety_factor": 2.0,
    }
    d.update(over)
    return problem_from_dict(d)


def codes(p, **kw):
    return {m.code for m in sanity.check(p, **kw)}


# ----------------------------------------------------------------------------- schema
def test_schema_rejects_unknown_pad_reference():
    with pytest.raises(ValueError):
        base(supports=[{"pad_id": "Z", "type": "pin"}])


def test_schema_rejects_ring_inside_hole():
    with pytest.raises(ValueError):
        base(pads=[{"id": "A", "cx": 6, "cy": 6, "hole_r_mm": 3, "ring_r_mm": 2}])


def test_demo_json_files_validate():
    for name in form.DEMOS:
        p = form.load_demo(name)
        assert isinstance(p, Problem) and p.load_cases


# ----------------------------------------------------------------------------- sanity
def test_clean_problem_has_no_blocking_messages():
    assert sanity.blocking(sanity.check(base())) == []


def test_pad_outside():
    p = base(pads=[{"id": "A", "cx": 6, "cy": 6, "hole_r_mm": 1.6, "ring_r_mm": 3.6},
                   {"id": "B", "cx": 6, "cy": 24, "hole_r_mm": 1.6, "ring_r_mm": 3.6},
                   {"id": "L", "cx": 58, "cy": 15, "hole_r_mm": 1.6, "ring_r_mm": 3.6}])
    assert "pad_outside" in codes(p)


def test_rigid_motion_single_pin_and_two_slides():
    p = base(supports=[{"pad_id": "A", "type": "pin"}])
    assert "rigid_motion" in codes(p)
    p = base(supports=[{"pad_id": "A", "type": "slide_x"}, {"pad_id": "B", "type": "slide_x"}])
    assert "rigid_motion" in codes(p)  # nothing holds x
    p = base(supports=[{"pad_id": "A", "type": "pin"}, {"pad_id": "B", "type": "slide_y"}])
    assert "rigid_motion" not in codes(p)  # B (same x as A) holds x at another height: stops rotation


def test_no_force():
    p = base(load_cases=[{"id": "c1", "name": "Landing", "loads": [{"pad_id": "L"}], "max_deflection_mm": 1}])
    msgs = sanity.check(p)
    assert any(m.code == "no_force" and "Landing" in m.message for m in msgs)


def test_keep_out_over_pad_and_no_path():
    z = [{"id": "K1", "kind": "keep_out", "shape": "rect", "rect": {"x": 48, "y": 10, "w": 8, "h": 10}}]
    assert "keep_out_on_pad" in codes(base(zones=z))
    wall = [{"id": "W", "kind": "keep_out", "shape": "rect", "rect": {"x": 30, "y": 0, "w": 4, "h": 30}}]
    assert "no_path" in codes(base(zones=wall))
    gap = [{"id": "W", "kind": "keep_out", "shape": "rect", "rect": {"x": 30, "y": 0, "w": 4, "h": 25}}]
    assert "no_path" not in codes(base(zones=gap))


def test_keep_in_full():
    z = [{"id": "K", "kind": "keep_in", "shape": "rect", "rect": {"x": 0, "y": 0, "w": 60, "h": 30}}]
    assert "keep_in_full" in codes(base(zones=z))


def test_yellow_units_and_thin_and_out_of_plane_banner():
    p = base(design_space={"width_mm": 2500, "height_mm": 30})
    assert "units_size" in codes(p)
    p = base(load_cases=[{"id": "c1", "name": "x", "loads": [{"pad_id": "L", "fy_N": -2e6}], "max_deflection_mm": 1}])
    assert "units_force" in codes(p)
    p = base(thickness_mm=40)
    assert "units_thickness" in codes(p)
    p = base(thickness_mm=1)  # span ~46 mm / 20 = 2.3 mm
    assert "thin" in codes(p)
    p = base(load_cases=[{"id": "c1", "name": "x", "loads": [{"pad_id": "L", "fz_N_out_of_plane": 10}],
                          "max_deflection_mm": 1}])
    msgs = sanity.check(p)
    oop = [m for m in msgs if m.code == "out_of_plane"]
    assert oop and oop[0].level == "red" and not oop[0].blocking
    assert "no_force" not in {m.code for m in msgs}  # out-of-plane only is allowed
    assert sanity.blocking(msgs) == []


def test_min_wall_message():
    from morphic.materials import load_materials, load_processes

    p = base(design_space={"width_mm": 600, "height_mm": 300})
    msgs = sanity.check(p, load_processes(), load_materials())
    assert any(m.code == "min_wall" and not m.blocking for m in msgs)


# ----------------------------------------------------------------------------- defaults
def draft_dict(**over):
    d = {"name": "t", "design_space": {"width_mm": 60, "height_mm": 30},
         "pads": [{"id": "A", "cx": 6, "cy": 6}, {"id": "B", "cx": 6, "cy": 24},
                  {"id": "L", "cx": 52, "cy": 15, "solid": True}],
         "supports": [{"pad_id": "A", "type": "pin"}, {"pad_id": "B", "type": "pin"}],
         "load_cases": [{"id": "c1", "name": "down", "loads": [{"pad_id": "L", "fy_N": -100}]}],
         "original_text": {"load_cases[0].loads[0].fy_N": "100 N down"}}
    d.update(over)
    return d


def test_defaults_are_filled_and_marked():
    p = parse.complete_draft(parse.Draft.model_validate(draft_dict()), min_walls=[0.8, 0.4])
    assert p.thickness_mm == config.DEFAULT_THICKNESS_MM
    assert p.safety_factor == config.DEFAULT_SAFETY_FACTOR
    assert p.printer == "any" and len(p.materials) == 6
    a = p.pad("A")
    assert a.hole_r_mm == 1.6 and a.ring_r_mm == pytest.approx(3.6)  # ring width max(2, 2 x 0.8)
    assert p.pad("L").hole_r_mm == 0 and p.pad("L").ring_r_mm == pytest.approx(2.0)
    span = p.span_mm
    assert p.load_cases[0].max_deflection_mm == pytest.approx(span / 100)
    for path in ("thickness_mm", "safety_factor", "printer", "materials", "pads[0].hole_r_mm",
                 "load_cases[0].max_deflection_mm"):
        assert p.source_of(path).source == "default", path
    assert p.source_of("pads[2].hole_r_mm").source == "user"
    assert p.source_of("load_cases[0].loads[0].fy_N").original_text == "100 N down"


def test_span_ratio_deflection():
    p = parse.complete_draft(parse.Draft.model_validate(draft_dict(deflection_span_ratio=200)))
    assert p.load_cases[0].max_deflection_mm == pytest.approx(p.span_mm / 200)
    assert p.source_of("load_cases[0].max_deflection_mm").source == "user"


def test_ring_width_uses_two_min_walls_when_larger():
    assert parse.default_ring_width([1.2]) == pytest.approx(2.4)
    assert parse.default_ring_width([0.8]) == pytest.approx(2.0)


# ----------------------------------------------------------------------------- parse flow
class FakeLLM:
    def __init__(self, answers, delay=0.0, exc=None):
        self.answers = list(answers)
        self.calls = []
        self.delay = delay
        self.exc = exc

    def __call__(self, system, user, timeout_s):
        self.calls.append(user)
        if self.delay:
            time.sleep(self.delay)
        if self.exc:
            raise self.exc
        return self.answers.pop(0)


def test_parse_valid_first_time():
    llm = FakeLLM([json.dumps(draft_dict())])
    r = parse.parse_text("text", llm_call=llm)
    assert len(llm.calls) == 1 and r.problem.pads[0].id == "A"


def test_parse_retries_once_with_the_error():
    bad = draft_dict(supports=[{"pad_id": "Q", "type": "pin"}])
    llm = FakeLLM(["not json at all", json.dumps(draft_dict())])
    r = parse.parse_text("text", llm_call=llm)
    assert len(llm.calls) == 2 and "previous answer was not valid" in llm.calls[1]
    llm = FakeLLM([json.dumps(bad), json.dumps(draft_dict())])
    parse.parse_text("text", llm_call=llm)
    assert "unknown pad" in llm.calls[1]


def test_parse_fails_after_one_retry():
    llm = FakeLLM(["{}", "{}", json.dumps(draft_dict())])
    with pytest.raises(parse.ParseFailed) as e:
        parse.parse_text("text", llm_call=llm)
    assert len(llm.calls) == 2 and len(e.value.attempts) == 2


def test_api_error_is_not_retried():
    llm = FakeLLM([], exc=ConnectionError("no route"))
    with pytest.raises(parse.ParseFailed, match="ConnectionError"):
        parse.parse_text("text", llm_call=llm)
    assert len(llm.calls) == 1


def test_timeout_goes_to_fallback():
    llm = FakeLLM([json.dumps(draft_dict())], delay=1.0)
    t = time.perf_counter()
    with pytest.raises(parse.ParseFailed, match="did not answer"):
        parse.parse_text("text", llm_call=llm, timeout_s=0.2)
    assert time.perf_counter() - t < 0.9


def test_compare_problems_reports_differences():
    a = form.load_demo("aero_bracket")
    b = a.model_copy(deep=True)
    assert parse.compare_problems(b, a) == []
    b.load_cases[0].loads[0].fy_N = 30000
    b.thickness_mm = 20
    d = parse.compare_problems(b, a)
    assert any("thickness" in x for x in d) and any("Vertical" in x for x in d)


# ----------------------------------------------------------------------------- manual form
def test_form_round_trip_and_errors():
    p = form.load_demo("rc_arm")
    f = form.problem_to_form(p)
    q, errs = form.form_to_problem(f)
    assert errs == [] and parse.compare_problems(q, p) == []
    assert q.notes == p.notes
    f2 = form.blank_form()
    q, errs = form.form_to_problem(f2)
    assert q is None and any("width_mm" in e for e in errs)
    f["supports"].append({"pad_id": "nope", "type": "pin"})
    q, errs = form.form_to_problem(f)
    assert q is None and errs
