"""Classify quota failures without recording SDK messages, URLs, or credentials."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from morphic import config, llm

original = llm._PROVIDERS[config.LLM_PROVIDER]
attempts = []


def probe(*args):
    try:
        result = original(*args)
        attempts.append({"success": True})
        return result
    except Exception as exc:
        record = {"status": llm._status_code(exc), "quota_limits": []}
        body = getattr(exc, "details", {})
        body = body.get("error", body) if isinstance(body, dict) else {}
        for detail in body.get("details", []):
            for violation in detail.get("violations", []):
                identifier = str(violation.get("quotaId", "")).lower()
                metric = str(violation.get("quotaMetric", "")).lower()
                value = str(violation.get("quotaValue", ""))
                record["quota_limits"].append({
                    "per_day": "perday" in identifier or "per_day" in metric,
                    "per_minute": "perminute" in identifier or "per_minute" in metric,
                    "free_tier": "freetier" in identifier or "free_tier" in metric,
                    "limit": int(value) if value.isdigit() else None,
                })
            delay = str(detail.get("retryDelay", "")).removesuffix("s")
            try:
                record["retry_after_s"] = float(delay)
            except ValueError:
                pass
        attempts.append(record)
        raise


llm._PROVIDERS[config.LLM_PROVIDER] = probe
try:
    llm.complete("Return a JSON object.", 'Reply with {"ok":true}.',
                 before_attempt=llm.wait_for_agent_slot)
except llm.LLMError:
    pass
report = {"provider": config.LLM_PROVIDER, "model": config.LLM_MODELS[config.LLM_PROVIDER],
          "attempts": attempts}
(ROOT / ".plans/reports/gemini-quota-diagnostic.json").write_text(
    json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
