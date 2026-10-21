"""Isolated screenshot fixtures. Production app keeps its live LLM adapter unchanged."""
import json
import runpy
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app import data, integration
from morphic import agent, llm, sketch
from morphic.problem import problem_from_dict
from tests.sketch_sample import FAKE_ANSWER

mode = st.query_params.get("capture")
if mode == "agent":
    st.caption("Screenshot fixture: replay of the saved drone exploration; no new agent run.")
    if not st.session_state.get("capture_seeded"):
        path = ROOT / ".plans/reports/drone-agent-backoff.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        job = integration.AgentJob(problem_from_dict(saved["starting_problem"]), path=path)
        job.log = agent.log_from_dict(saved)
        job.messages = ["Saved exploration replay for screenshot verification."]
        job.done.set()
        key = data.load_results(data.CACHE_DIR / "drone_arm")["key"]
        st.session_state.agent_jobs = {key: job}
        st.session_state.capture_seeded = True
elif mode == "sketch":
    st.caption("Screenshot fixture: sample sketch with a fixed test-provider interpretation.")
    sketch._default_llm = lambda *a, **k: llm.LLMResult(FAKE_ANSWER, "fake", "fake-vision")

runpy.run_path(str(ROOT / "app/streamlit_app.py"), run_name="__main__")
