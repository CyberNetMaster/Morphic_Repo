"""Integration boundaries: saved physics, live-provider defaults, review and downloads."""
import io
import json
import zipfile
from pathlib import Path

import pytest

from app import data, integration
from morphic import agent, explain, llm
from morphic.problem import problem_to_dict
from tests.test_agent import FakeLLM, fake_engine
from tests.test_catalog import MATERIALS, PROCESSES, bracket


def trial_log(problem):
    return agent.explore(problem, engine=fake_engine, materials=MATERIALS, processes=PROCESSES,
                         max_rounds=2, llm_call=FakeLLM([
                             {"action": "design_space", "width_mm": 60, "height_mm": 45, "reason": "taller"},
                             {"action": "thickness", "thickness_mm": 9, "reason": "thicker"},
                             {"text": "Review the lightest passing option."}]))


def test_saved_explanation_uses_final_checks_and_same_display_precision(monkeypatch):
    r = data.load_results(data.CACHE_DIR / "rc_arm")
    win = r["ranking"]["winner"]
    design = next(d for d in r["designs"] if d["material"] == win)
    design["checks"]["mass_g"] = 12.304
    payload = explain.saved_results_json(r)
    winner = next(c for c in payload["cards"] if c["state"] == "ranked" and c["rank"] == 1)
    assert winner["mass"] == {"value": "12.30", "unit": "g"}
    calls = []
    def complete(system, user):
        calls.append(json.loads(user))
        return {"explanation": f"{winner['name']} weighs 12.30 g."}
    monkeypatch.setattr(llm, "complete_json", complete)
    result = explain.explain(payload, use_llm=True)
    assert result.source == "llm" and calls == [payload]
    assert "problem" not in payload and "_dir" not in payload


def test_agent_job_uses_live_provider_saves_start_and_does_not_mutate(monkeypatch, tmp_path):
    p = bracket()
    before = problem_to_dict(p)
    log = trial_log(p)
    calls = []
    def explore(problem, **kwargs):
        calls.append(kwargs)
        kwargs["status"]("Round complete")
        problem.thickness_mm = 99
        return log
    monkeypatch.setattr(agent, "explore", explore)
    job = integration.AgentJob(p, path=tmp_path / "agent.json")
    job.run()
    assert job.done.is_set() and not job.error
    assert calls[0]["use_llm"] is True and calls[0]["max_rounds"] == 5
    assert job.snapshot()["messages"] == ["Round complete"]
    assert problem_to_dict(p) == before == problem_to_dict(job.problem)
    assert json.loads(job.path.read_text())["starting_problem"] == before


def test_agent_job_failure_is_finished_and_does_not_expose_request(monkeypatch, tmp_path):
    def fail(*args, **kwargs):
        raise RuntimeError("private request details")
    monkeypatch.setattr(agent, "explore", fail)
    job = integration.AgentJob(bracket(), path=tmp_path / "failed.json")
    job.run()
    assert job.done.is_set() and "RuntimeError" in job.error
    assert "private request details" not in job.error and not job.path.exists()


def test_isolated_worker_receives_only_problem_paths_and_returns_log(monkeypatch, tmp_path):
    job = integration.AgentJob(bracket(), path=tmp_path / "worker.json")
    log = trial_log(job.problem)
    commands = []
    class Process:
        def __init__(self, command, **kwargs):
            commands.append(command)
            assert command[:4] == [integration.sys.executable, "-u", "-m", "app.integration"]
            assert kwargs["stderr"] == integration.subprocess.DEVNULL
            assert json.loads(Path(command[5]).read_text()) == problem_to_dict(job.problem)
            Path(command[6]).write_text(log.to_json())
            self.stdout = ['{"message": "round completed"}\n']
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def wait(self):
            return 0
    monkeypatch.setattr(integration.subprocess, "Popen", Process)
    job.run_isolated()
    assert job.done.is_set() and not job.error and job.log.recommendation == log.recommendation
    assert job.snapshot()["messages"] == ["round completed"] and len(commands) == 1


def test_recommendation_replays_pad_translation_and_preserves_limits():
    p = bracket()
    log = trial_log(p)
    log.recommendation["round"] = 2
    revised = integration.recommended_problem(p, log)
    assert revised.design_space.height_mm == 45 and revised.thickness_mm == 9
    assert revised.pads[0].cy - p.pads[0].cy == 7.5
    assert revised.supports == p.supports and revised.load_cases == p.load_cases
    assert revised.safety_factor == p.safety_factor and p.thickness_mm == 6
    log.rounds[1].knobs["thickness_mm"] = 999
    with pytest.raises(ValueError, match="does not reproduce"):
        integration.recommended_problem(p, log)


def test_pdf_download_is_identical_to_bundled_report(monkeypatch, tmp_path):
    monkeypatch.setattr(integration, "OUTPUT", tmp_path)
    folder = str(data.CACHE_DIR / "rc_arm")
    assert integration.export_signature(folder)
    pdf, bundle = integration.export_downloads(folder)
    assert pdf.startswith(b"%PDF-")
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert archive.read("report.pdf") == pdf
        assert json.loads(archive.read("results.json")) == json.loads((Path(folder) / "results.json").read_text())
        assert not any(".env" in name for name in archive.namelist())


def test_provider_errors_do_not_include_request_details(monkeypatch):
    def fail(*args):
        raise RuntimeError("private request URL")
    monkeypatch.setitem(llm._PROVIDERS, llm.config.LLM_PROVIDER, fail)
    with pytest.raises(llm.LLMError) as error:
        llm.complete("system", "user")
    assert "private request URL" not in str(error.value)


def test_key_source_is_checkout_env_only(monkeypatch):
    paths = []
    monkeypatch.setattr(llm, "dotenv_values", lambda path: paths.append(path) or {})
    monkeypatch.setenv("GEMINI_API_KEY", "unused-test-value")
    with pytest.raises(llm.LLMError, match="not set in .env"):
        llm._key("GEMINI_API_KEY")
    assert paths == [integration.ROOT / ".env"]


def test_compare_starts_once_and_reviews_the_recommended_problem(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(llm, "complete_json", lambda system, user:
                        {"explanation": explain.template_explanation(json.loads(user))})
    started = []
    def start(problem):
        started.append(problem)
        job = integration.AgentJob(problem, path=tmp_path / "ui-agent.json")
        # A changed recommendation must reach Check instead of old widget values.
        log = agent.ExploreLog(part=problem.name, source="test", settings={}, llm={})
        log.rounds = [agent.Round(0, "starting problem", agent.knobs_of(problem), None,
                                 {"best": {"material": "pa6cf", "mass_g": 3.9}}, 1)]
        proposal = agent.Proposal("thickness", {"thickness_mm": problem.thickness_mm + 2}, "thicker")
        revised = agent.apply_proposal(problem, proposal)
        log.rounds.append(agent.Round(1, "thicker", agent.knobs_of(revised), proposal,
                                      {"best": {"material": "pa6cf", "mass_g": 4.9}}, 1))
        log.recommendation = {"round": 1, "text": "Review the changed design.", "source": "llm"}
        job.log = log
        job.path.write_text(log.to_json())
        job.done.set()
        return job
    monkeypatch.setattr(integration, "start_agent", start)
    at = AppTest.from_file(str(integration.ROOT / "app" / "streamlit_app.py"), default_timeout=120)
    at.query_params.update({"demo": "rc_arm", "step": "2"})
    at.run()
    assert not at.exception
    at.button(key="agent_start").click().run()
    assert not at.exception and len(started) == 1
    at.run()
    assert len(started) == 1
    at.button(key="agent_review").click().run()
    assert not at.exception and at.session_state["step"] == 1
    assert at.session_state["results"] is None and at.session_state["quick"] is False
    assert at.session_state["problem"].thickness_mm == started[0].thickness_mm + 2


def test_export_buttons_are_enabled(monkeypatch):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(integration.ROOT / "app" / "streamlit_app.py"), default_timeout=120)
    at.query_params.update({"demo": "rc_arm", "step": "3"})
    at.run()
    assert not at.exception and not at.error
    downloads = {element.label: element for element in at.get("download_button")}
    assert not downloads["PDF report"].disabled and not downloads["Run bundle (zip)"].disabled
