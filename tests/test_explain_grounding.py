"""S12 acceptance, entirely offline: planted wrong numbers must be caught."""

import json

import pytest

from morphic import explain as explanation


@pytest.fixture
def results():
    return {"cards": [
        {"name": "PA6-CF", "printer": "FDM", "state": "ranked", "rank": 1,
         "mass": {"value": "12.30", "unit": "g"},
         "material_cost": {"value": "0.65", "unit": "USD"}},
        {"name": "PLA", "printer": "FDM", "state": "ranked", "rank": 2,
         "mass": {"value": "15.20", "unit": "g"}},
    ]}


def test_planted_wrong_number_is_caught(results):
    assert explanation.check_grounding("PA6-CF weighs 92.30 g.", results) == ["92.30 g"]


@pytest.mark.parametrize("text", ["12.30 kg", "12.30 mm", "12.30", "0.65 g", "12.31 g",
                                  "thirteen grams", "12.30 furlongs", "$12.30 g", "NaN g"])
def test_wrong_units_or_numbers_fail(results, text):
    assert explanation.check_grounding(text, results)


@pytest.mark.parametrize("text", ["PA6-CF weighs 12.30 g.", "12.304 grams", "1.230e1 g",
                                  "Material cost is 0.65 USD.", "$0.65."])
def test_display_rounding_and_names(results, text):
    assert explanation.check_grounding(text, results) == []


def test_retry_sends_bad_numbers_and_accepts_correction(monkeypatch, results):
    calls = []
    good = explanation.template_explanation(results)

    def complete(system, user):
        calls.append(json.loads(user))
        return {"explanation": "Mass is 92.30 g." if len(calls) == 1 else good}

    monkeypatch.setattr(explanation.llm, "complete_json", complete)
    out = explanation.explain(results, use_llm=True)
    assert out.source == "llm" and out.attempts == 2 and out.text == good
    assert calls[0] == results
    assert calls[1] == {"results": results, "bad_numbers": ["92.30 g"]}


def test_second_failure_uses_grounded_template(monkeypatch, results):
    calls = []

    def complete(*args):
        calls.append(args)
        return {"explanation": "Mass is 92.30 g."}

    monkeypatch.setattr(explanation.llm, "complete_json", complete)
    out = explanation.explain(results, use_llm=True)
    assert len(calls) == 2 and out.source == "template"
    assert "92.30" not in out.text
    assert explanation.check_grounding(out.text, results) == []


@pytest.mark.parametrize("response", [None, {}, {"explanation": 42}, {"explanation": ""}])
def test_malformed_response_falls_back(monkeypatch, results, response):
    monkeypatch.setattr(explanation.llm, "complete_json", lambda *a: response)
    assert explanation.explain(results, use_llm=True).source == "template"


def test_api_failure_and_offline_default(monkeypatch, results):
    calls = []

    def fail(*args):
        calls.append(args)
        raise TimeoutError("Provider failure")

    monkeypatch.setattr(explanation.llm, "complete_json", fail)
    assert explanation.explain(results).attempts == 0
    assert not calls
    out = explanation.explain(results, use_llm=True)
    assert out.source == "template" and out.attempts == 1
    assert len(calls) == 1


def test_no_winner_and_missing_cost(results):
    results["cards"][0]["state"] = "filtered"
    text = explanation.template_explanation(results)
    assert text.startswith("PLA") and "unavailable" in text
    results["cards"][1]["state"] = "failed"
    assert explanation.template_explanation(results).startswith("No design is ranked")


def test_rank_projection():
    from morphic.rank import rank_designs
    from tests.test_rank import design, run_result

    results = explanation.results_json(rank_designs(run_result([design("pla", 3.4567)])))
    assert results["cards"][0]["mass"] == {"value": "3.46", "unit": "g"}
    json.dumps(results, allow_nan=False)
    assert not explanation.check_grounding(explanation.template_explanation(results), results)


def test_percent_scientific_grouping_and_zero():
    results = {"quantities": [{"value": "25.0", "unit": "%"},
                              {"value": "1200.00", "unit": "MPa"},
                              {"value": "0.000", "unit": "mm"}]}
    assert not explanation.check_grounding("25.0%, 1,200.00 MPa, 0.000 mm", results)
    assert not explanation.check_grounding("1.2e3 MPa", results)
    for text in ("0.25%", "25 g", "1200 Pa", "0.001 mm", "-1200 MPa"):
        assert explanation.check_grounding(text, results)


def test_nonfinite_results_rejected(results):
    results["cards"][0]["mass"]["value"] = "NaN"
    with pytest.raises((ValueError, ArithmeticError)):
        explanation.explain(results)
