"""Transport retry bounds, credential-safe failures, and actual agent request pacing."""
from types import SimpleNamespace
import subprocess
import sys

import pytest

from morphic import agent, config, llm, parse


class HTTPError(Exception):
    def __init__(self, code, attribute="code"):
        super().__init__("private request details must not appear in errors")
        setattr(self, attribute, code)


@pytest.fixture
def clock(monkeypatch, tmp_path):
    state = SimpleNamespace(now=100.0, sleeps=[])
    def sleep(seconds):
        state.sleeps.append(seconds)
        state.now += seconds
    monkeypatch.setattr(llm.time, "sleep", sleep)
    monkeypatch.setattr(llm.time, "monotonic", lambda: state.now)
    monkeypatch.setattr(llm, "_AGENT_GATE_PATH", tmp_path / "agent.lock")
    return state


@pytest.mark.parametrize("code,attribute", [(429, "code"), (503, "status_code")])
def test_four_retries_then_success(monkeypatch, clock, code, attribute):
    calls = []
    def provider(*args):
        calls.append(clock.now)
        if len(calls) < 5:
            raise HTTPError(code, attribute)
        return llm.LLMResult("{}", "test", "test")
    monkeypatch.setitem(llm._PROVIDERS, config.LLM_PROVIDER, provider)
    assert llm.complete("system", "user").text == "{}"
    assert calls == [100, 104, 112, 128, 160]
    assert clock.sleeps == [4, 8, 16, 32]


@pytest.mark.parametrize("code", [429, 503, 400, 401, 500])
def test_retry_exhaustion_is_bounded_and_sanitized(monkeypatch, clock, code):
    calls = []
    def provider(*args):
        calls.append(clock.now)
        raise HTTPError(code)
    monkeypatch.setitem(llm._PROVIDERS, config.LLM_PROVIDER, provider)
    with pytest.raises(llm.LLMError) as caught:
        llm.complete("system", "user")
    assert len(calls) == (5 if code in (429, 503) else 1)
    assert f"status {code}" in str(caught.value)
    assert "private" not in str(caught.value)


def test_agent_paces_calls_and_transport_retries(monkeypatch, clock):
    starts = []
    def provider(*args):
        starts.append(clock.now)
        if len(starts) == 2:
            raise HTTPError(503)
        return llm.LLMResult("{}", "test", "test")
    monkeypatch.setitem(llm._PROVIDERS, config.LLM_PROVIDER, provider)
    agent._default_llm("system", "user")
    agent._default_llm("system", "user")
    agent._default_llm("system", "user")
    assert starts == [100, 104, 108, 112]
    assert llm._AGENT_GATE_PATH.read_text().strip() == "112.0"


def test_agent_does_not_wait_after_long_solve(clock):
    llm.wait_for_agent_slot()
    clock.now += 20
    llm.wait_for_agent_slot()
    assert clock.sleeps == []


def test_gate_survives_a_monotonic_clock_reset(clock):
    llm._AGENT_GATE_PATH.write_bytes(b" 9999999999")
    llm.wait_for_agent_slot()
    assert clock.sleeps == [4]


def test_parser_waits_for_adapter_retry_budget(monkeypatch):
    waits = []
    class Future:
        def result(self, timeout):
            waits.append(timeout)
            raise llm.LLMError("exhausted")
    monkeypatch.setattr(parse._POOL, "submit", lambda *a: Future())
    with pytest.raises(parse.ParseFailed, match="exhausted"):
        parse.parse_text("part")
    assert waits == [290]  # five 45-second attempts + 60 backoff + 5 overhead


def test_sdk_retries_are_disabled(monkeypatch):
    from google import genai
    import anthropic
    options = {}
    def gemini(**kwargs):
        options["gemini"] = kwargs["http_options"]
        return SimpleNamespace(close=lambda: None,
                               models=SimpleNamespace(generate_content=lambda **k: SimpleNamespace(text="{}")))
    def claude(**kwargs):
        options["claude"] = kwargs["max_retries"]
        return SimpleNamespace(close=lambda: None,
                               messages=SimpleNamespace(create=lambda **k: SimpleNamespace(content=[])))
    monkeypatch.setattr(llm, "_key", lambda name: "unused-test-value")
    monkeypatch.setattr(genai, "Client", gemini)
    monkeypatch.setattr(anthropic, "Anthropic", claude)
    llm._complete_gemini("system", "user", 45)
    llm._complete_claude("system", "user", 45)
    assert options["gemini"].retry_options.attempts == 1
    assert options["claude"] == 0


def test_gate_is_shared_across_worker_processes(tmp_path):
    code = ("import sys,time; from pathlib import Path; from morphic import llm; "
            "llm._AGENT_GATE_PATH=Path(sys.argv[1]); "
            "llm.wait_for_agent_slot(); print(time.monotonic())")
    workers = [subprocess.Popen([sys.executable, "-c", code, str(tmp_path / "gate.lock")],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
               for _ in range(2)]
    try:
        starts = []
        for worker in workers:
            output, error = worker.communicate(timeout=20)
            assert worker.returncode == 0, error
            starts.append(float(output.strip()))
        assert abs(starts[1] - starts[0]) >= 3.95
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
                worker.wait()
