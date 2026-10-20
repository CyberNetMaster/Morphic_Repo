import morphic
from morphic import config


def test_import_and_settings():
    assert morphic.__version__
    s = config.solver_settings()
    assert s["ELEMENT_CAP_LIVE"] == 40_000
    assert s["LLM_PROVIDER"] in ("gemini", "claude")
