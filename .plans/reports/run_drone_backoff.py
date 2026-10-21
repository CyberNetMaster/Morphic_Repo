"""Live Gemini acceptance run; log only request timing and safe adapter messages."""
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from morphic import agent, llm
from morphic.problem import problem_from_dict

reports = ROOT / ".plans/reports"
source = json.loads((reports / "drone-agent-live.json").read_text(encoding="utf-8"))
problem = problem_from_dict(source["starting_problem"])
events = []
real_gate = llm.wait_for_agent_slot
started = time.monotonic()


def gate():
    real_gate()
    events.append({"attempt": len(events) + 1, "elapsed_s": time.monotonic() - started})
    (reports / "drone-agent-request-times.json").write_text(json.dumps(events, indent=2), encoding="utf-8")


llm.wait_for_agent_slot = gate
logger = logging.getLogger("morphic.llm")
logger.setLevel(logging.INFO)
handler = logging.FileHandler(reports / "drone-agent-retries.txt", mode="w", encoding="utf-8")
handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
logger.addHandler(handler)
log = agent.explore(problem, source="Live retry acceptance run", status=lambda s: print(s, flush=True))
record = log.to_dict() | {"starting_problem": source["starting_problem"]}
(reports / "drone-agent-backoff.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps({"rounds": len(log.rounds), "seconds": log.seconds,
                  "proposal_sources": [r.proposal.source for r in log.rounds if r.proposal],
                  "recommendation": log.recommendation}, indent=2), flush=True)
