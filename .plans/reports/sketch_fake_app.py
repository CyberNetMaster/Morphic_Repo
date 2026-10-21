"""Run the app with a fake vision LLM that returns the sample sketch's fixed answer, for local
browser checks of the Describe -> Check flow. No LLM request is made.

    python -m streamlit run .plans/reports/sketch_fake_app.py --server.port 8798 --server.address 127.0.0.1
"""

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from morphic import llm, sketch  # noqa: E402
from tests.sketch_sample import FAKE_ANSWER  # noqa: E402

sketch._default_llm = lambda *a, **k: llm.LLMResult(FAKE_ANSWER, "fake", "fake-vision")
runpy.run_path(str(ROOT / "app" / "streamlit_app.py"), run_name="__main__")
