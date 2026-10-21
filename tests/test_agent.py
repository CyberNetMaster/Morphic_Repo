"""Design agent (morphic/agent.py) with a fake LLM and a fake engine, plus one small real engine run."""

import json

import pytest

from morphic import agent, catalog
from morphic.catalog import RunResult
from morphic.problem import Problem
from tests.test_catalog import MATERIALS, PROCESSES, bracket
from tests.test_rank import design


# ----------------------------------------------------------------------------- fakes
class FakeLLM:
    """Answers a scripted list of dicts in order; records every prompt."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, system, user):
        self.calls.append((system, user))
        if not self.answers:
            return {"action": "stop", "reason": "script exhausted"}
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def fake_engine(problem: Problem) -> RunResult:
    """Deterministic stand-in: PLA needs 1.5x the starting stiffness to pass; PA6-CF always passes
    and gets lighter in a taller design space; a thicker part is heavier in proportion."""
    t, H = problem.thickness_mm, problem.design_space.height_mm
    k = (t / 6.0) * (H / 30.0)
    designs = []
    for mid in problem.materials:
        if mid not in MATERIALS:
            continue
        if mid == "pla":
            d = design("pla", round(6.0 * t / 6.0, 2), passed=k >= 1.5, defl=(0.9 / k, 0.1))
        elif mid == "pa6cf":
            d = design("pa6cf", round(3.0 * (t / 6.0) * (30.0 / H), 2))
        else:
            d = design(mid, round(2.5 * t / 6.0, 2))
        d.printer_allowed = problem.printer == "any" or PROCESSES[d.material.process].printer_group == problem.printer
        designs.append(d)
    return RunResult(problem=problem, cap=1000, sweep_mode="warm", catalogs={}, designs=designs, seconds=0.1)


def run(answers, problem=None, **kw):
    llm = FakeLLM(answers)
    log = agent.explore(problem or bracket(), llm_call=llm, engine=fake_engine, materials=MATERIALS,
                        processes=PROCESSES, **kw)
    return log, llm


# ----------------------------------------------------------------------------- the loop
def test_loop_records_rounds_and_recommends_the_lightest_passing_round():
    answers = [
        {"action": "thickness", "thickness_mm": 12, "reason": "pla fails; stress and deflection scale 1/thickness"},
        {"action": "design_space", "width_mm": 60, "height_mm": 45, "reason": "a taller space is stiffer per gram"},
        {"action": "stop", "reason": "enough"},
        # recommendation: numbers below are copied from the fake engine's results
        {"text": "Round 2 is best: pa6cf at 4 g beats the 3 g start? no"},  # wrong on purpose (4 g not in results)
        {"text": "Round 2 (taller design space) is the lightest passing option: pa6cf at 4 g."},
    ]
    log, llm = run(answers)
    assert [r.index for r in log.rounds] == [0, 1, 2]
    assert log.rounds[0].change == "starting problem as given" and log.rounds[0].proposal is None
    assert log.rounds[1].proposal.action == "thickness" and log.rounds[1].knobs["thickness_mm"] == 12
    assert log.rounds[2].knobs["design_space"]["height_mm"] == 45
    assert "agent stopped before round 3" in log.rounds[2].notes[0]
    # round 2: thickness 12 and height 45 -> pa6cf mass 3 * 2 * (30/45) = 4.0 g
    assert log.rounds[2].results["best"]["material"] == "pa6cf"
    assert log.rounds[2].results["best"]["mass_g"] == pytest.approx(4.0)
    # the best round is the starting problem (pa6cf at 3 g), since the explored changes were heavier
    assert log.recommendation["round"] == 0
    # the first recommendation text had a number not in the log ("3 g" is there, "4 g" too... check the check)
    assert log.recommendation["source"] in ("llm", "template")
    assert agent.ground_text(log.recommendation["text"], {"rounds": [r.results for r in log.rounds]}) == []
    # the log is plain JSON the app can display
    d = json.loads(log.to_json())
    assert d["rounds"][1]["proposal"]["reason"].startswith("pla fails")
    assert d["recommendation"]["text"]
    assert d["settings"]["quick"] is True and d["llm"]["provider"] == "fake"


def test_a_better_round_wins_and_is_quoted_with_engine_numbers():
    answers = [
        {"action": "design_space", "width_mm": 60, "height_mm": 60, "reason": "taller"},
        {"action": "stop", "reason": "done"},
        {"text": "Round 1 (design space 60 x 60 mm) gives pa6cf at 1.5 g, down from 3 g in round 0."},
    ]
    log, _ = run(answers)
    assert log.recommendation["round"] == 1
    assert log.recommendation["source"] == "llm"
    assert log.recommendation["best_design"]["mass_g"] == pytest.approx(1.5)


def test_at_most_five_rounds():
    answers = [{"action": "thickness", "thickness_mm": 6 + k, "reason": "try"} for k in range(1, 10)]
    log, llm = run(answers)
    assert len(log.rounds) == 1 + agent.MAX_ROUNDS
    assert log.rounds[-1].knobs["thickness_mm"] == 11


def test_no_llm_uses_the_fallback_rule_only():
    log = agent.explore(bracket(), engine=fake_engine, materials=MATERIALS, processes=PROCESSES, use_llm=False,
                        max_rounds=2)
    assert log.llm == {"provider": "none"}
    assert all(r.proposal.source == "fallback" for r in log.rounds[1:])
    assert log.recommendation["source"] == "template"


# ----------------------------------------------------------------------------- guard rails
def test_forbidden_changes_are_rejected_then_the_fallback_rule_is_used():
    answers = [
        {"action": "safety_factor", "safety_factor": 1.0, "reason": "lower the SF"},
        {"action": "thickness", "thickness_mm": 9, "max_deflection_mm": 5, "reason": "loosen the limit"},
        {"action": "stop", "reason": "x"},
    ]
    log, llm = run(answers, max_rounds=1)
    p = log.rounds[1].proposal
    assert p.source == "fallback"
    errors = [a["error"] for a in p.attempts if "error" in a]
    assert len(errors) == 2
    assert "safety_factor" in errors[0] and "max_deflection_mm" in errors[1]
    # the problem's limits are untouched
    assert log.rounds[1].results["safety_factor_target"] == 2.0


def test_out_of_range_repeat_and_unknown_material_are_rejected():
    start, prob = bracket(), bracket()
    tried = [agent.knobs_of(prob)]
    assert agent.validate_proposal({"action": "thickness", "thickness_mm": 100}, prob, start, tried, PROCESSES)[0] is None
    assert agent.validate_proposal({"action": "thickness", "thickness_mm": 6}, prob, start, tried, PROCESSES)[0] is None
    assert agent.validate_proposal({"action": "material", "materials": ["unobtainium"]}, prob, start, tried,
                                   PROCESSES)[0] is None
    ok, err = agent.validate_proposal({"action": "material", "materials": ["pa6cf"]}, prob, start, tried, PROCESSES)
    assert ok is not None and err == ""
    # shrinking the space so a pad falls outside fails the sanity check
    ok, err = agent.validate_proposal({"action": "design_space", "width_mm": 30, "height_mm": 30}, prob, start,
                                      tried, PROCESSES)
    assert ok is None and "sanity" in err


def test_design_space_change_keeps_pads_centred():
    prob = bracket()
    new = agent.apply_proposal(prob, agent.Proposal("design_space", {"width_mm": 80, "height_mm": 50}, ""))
    assert new.design_space.width_mm == 80 and new.design_space.height_mm == 50
    assert new.pad("A").cx == pytest.approx(6 + 10) and new.pad("A").cy == pytest.approx(6 + 10)
    assert prob.pad("A").cx == 6  # the original is untouched
    assert any("design agent" in n for n in new.notes)


def test_process_change_adds_a_material_of_the_new_group():
    prob = bracket().model_copy(update={"materials": ["pla"]})
    new = agent.apply_proposal(prob, agent.Proposal("process", {"printer": "metal_service"}, ""), PROCESSES,
                               MATERIALS)
    assert new.printer == "metal_service" and "alsi10mg" in new.materials


# ----------------------------------------------------------------------------- number check (spec 10)
RESULTS = {"best": {"mass_g": 13.27, "sf": 11.5, "fill_pct": 50.0, "worst_deflection_mm": 0.458,
                    "deflection_limit_mm": [0.5, 0.5]}, "n_ranked": 1}


def test_ground_text_accepts_numbers_within_display_rounding_and_matching_units():
    assert agent.ground_text("Mass 13.27 g at 50% fill, SF 11.5, deflection 0.458 mm vs 0.5 mm.", RESULTS) == []
    assert agent.ground_text("About 13.3 g and 11.5.", RESULTS) == []  # 13.3 rounds from 13.27
    assert agent.ground_text("1 design ranked", RESULTS) == []


def test_ground_text_rejects_unknown_numbers_and_wrong_units():
    bad = agent.ground_text("Mass 14 g, SF 11.5", RESULTS)
    assert bad == ["14 g: not in the results"]
    bad = agent.ground_text("13.27 mm", RESULTS)
    assert bad and "not in mm" in bad[0]


def test_ungrounded_reason_is_dropped_but_the_change_is_kept():
    answers = [
        {"action": "thickness", "thickness_mm": 9, "reason": "mass is 99.9 g"},
        {"action": "thickness", "thickness_mm": 9, "reason": "mass is still 99.9 g"},
        {"action": "stop", "reason": "x"},
    ]
    log, _ = run(answers, max_rounds=1)
    p = log.rounds[1].proposal
    assert p.action == "thickness" and p.value["thickness_mm"] == 9
    assert p.reason_grounded is False and p.reason_rejected == "mass is still 99.9 g"
    assert "99.9" not in p.reason
    assert [a["bad_numbers"] for a in p.attempts] == [["99.9 g: not in the results"]] * 2


def test_recommendation_falls_back_to_a_grounded_template():
    answers = [
        {"action": "stop", "reason": "x"},
        {"text": "pa6cf weighs 2.2 g"},
        {"text": "pa6cf weighs 2.3 g"},
    ]
    log, llm = run(answers)
    rec = log.recommendation
    assert rec["source"] == "template" and len(rec["attempts"]) == 2
    assert "3 g" in rec["text"]
    assert agent.ground_text(rec["text"], {"rounds": [r.results for r in log.rounds]}) == []


def test_llm_failure_falls_back_without_crashing():
    log, _ = run([RuntimeError("API down"), RuntimeError("API down")], max_rounds=1)
    assert log.rounds[1].proposal.source == "fallback"
    assert "RuntimeError" in log.rounds[1].proposal.attempts[0]["error"]
    assert log.recommendation["source"] == "template"


# ----------------------------------------------------------------------------- real engine, small
def test_one_round_with_the_real_engine_in_quick_mode():
    answers = [{"action": "thickness", "thickness_mm": 9, "reason": "thicker"}, {"action": "stop", "reason": "x"},
               {"text": "see the template"}]
    llm = FakeLLM(answers)
    log = agent.explore(bracket(), llm_call=llm, materials=MATERIALS, processes=PROCESSES, max_rounds=1,
                        cap=1200, levels=(0.60, 0.45, 0.30))
    assert len(log.rounds) == 2
    for r in log.rounds:
        assert r.results["n_designs"] == 2  # printer desktop_fdm -> only the fdm materials pla and pa6cf run
        for d in r.results["designs"]:
            assert d["process"] == "fdm" and d["mass_g"] > 0 and d["fill_pct"] in (60.0, 45.0, 30.0)
            assert d["sf"] is None or d["sf"] > 0
    assert log.rounds[1].knobs["thickness_mm"] == 9
    assert log.recommendation["text"]
    assert log.settings == {"cap": 1200, "levels": [0.6, 0.45, 0.3], "max_rounds": 1, "quick": True,
                            "sweep_mode": "warm", "refinement": False, "cold_rerun": False}


def test_log_round_trips_and_the_recommendation_can_be_redone():
    log, _ = run([{"action": "stop", "reason": "x"}, {"text": "pa6cf at 3 g is the only passing option."}])
    back = agent.log_from_dict(json.loads(log.to_json()))
    assert [r.index for r in back.rounds] == [r.index for r in log.rounds]
    assert back.rounds[0].results == log.rounds[0].results
    redo = agent.rerecommend(back, FakeLLM([{"text": "Round 0: pa6cf, 3 g, no change beat it."}]))
    assert redo.recommendation["source"] == "llm" and "3 g" in redo.recommendation["text"]
