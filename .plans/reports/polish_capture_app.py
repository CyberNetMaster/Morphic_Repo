"""Screenshot server for the design polish pass: the app with every LLM call switched off.

The explanation falls back to its template, the sketch step uses the fixed test interpretation and the
agent panel replays the saved drone exploration (see phase3_capture_app.py). No request leaves this
machine. Run:
    python -m streamlit run .plans/reports/polish_capture_app.py --server.port 8797 --server.address 127.0.0.1
"""
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from morphic import llm  # noqa: E402


def _offline(*args, **kwargs):
    raise llm.LLMError("screenshot run: LLM calls are switched off")


llm.complete = _offline
llm.complete_json = _offline
runpy.run_path(str(ROOT / ".plans/reports/phase3_capture_app.py"), run_name="__main__")
