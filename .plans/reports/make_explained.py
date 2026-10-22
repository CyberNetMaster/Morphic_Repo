"""Generate examples/explained/<stem>.json for the three demo parts through the explain pipeline
(live LLM with the template fallback), verified by the numeric grounding. Prints sources only, never keys.
Run again when the provider quota is back to replace template texts with LLM prose:
    python .plans/reports/make_explained.py
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app import data  # noqa: E402
from morphic import config, explain  # noqa: E402

out_dir = ROOT / "examples" / "explained"
out_dir.mkdir(exist_ok=True)
for stem in data.DEMOS.values():
    r = data.load_results(data.CACHE_DIR / stem)
    payload = explain.saved_results_json(r)
    t = time.time()
    e = explain.explain(payload, use_llm=True)
    bad = explain.check_grounding(e.text, payload)
    assert not bad, (stem, bad)
    saved = {
        "part": stem,
        "results_key": r["key"],
        "source": e.source,
        "provider": config.LLM_PROVIDER if e.source == "llm" else None,
        "model": config.LLM_MODELS[config.LLM_PROVIDER] if e.source == "llm" else None,
        "attempts": e.attempts,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "grounding": "passed: every number in the text matches the computed results at display precision",
        "text": e.text,
    }
    (out_dir / f"{stem}.json").write_text(json.dumps(saved, indent=2, ensure_ascii=False) + "\n",
                                          encoding="utf-8", newline="\n")
    print(stem, "->", e.source, "attempts", e.attempts, f"{time.time() - t:.1f}s", "|", e.text[:90].replace("\n", " "))
