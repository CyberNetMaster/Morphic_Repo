"""Reconstruct the saved 11.77 g candidate and solve PA6-CF at production resolution."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.integration import recommended_problem
from morphic import agent, config, precompute
from morphic.problem import problem_from_dict

reports = ROOT / ".plans" / "reports"
source = json.loads((reports / "drone-agent-live.json").read_text(encoding="utf-8"))
log = agent.log_from_dict(source)
assert log.recommendation["best_design"]["mass_g"] == 11.77
assert log.recommendation["best_design"]["material"] == "pa6cf"
problem = recommended_problem(problem_from_dict(source["starting_problem"]), log)
problem.materials = ["pa6cf"]
assert (problem.design_space.width_mm, problem.design_space.height_mm, problem.thickness_mm) == (120, 22.5, 10)
part = reports / "drone_best_pa6cf.json"
part.write_text(problem.model_dump_json(indent=2), encoding="utf-8")
console = reports / "drone-full-solve.txt"
with console.open("w", encoding="utf-8") as stream:
    def say(message):
        print(message, flush=True)
        print(message, file=stream, flush=True)
    result = precompute.precompute_part(part, ROOT / ".plans" / "live_runs" / "full-resolution",
                                        cap=config.ELEMENT_CAP_CACHED, sweep_mode="cold",
                                        levels=config.FILL_LEVELS, log=say)
saved = json.loads((result / "results.json").read_text(encoding="utf-8"))
(reports / "drone-full-results.json").write_text(json.dumps(saved, indent=2), encoding="utf-8")
design = saved["designs"][0]
print(json.dumps({"status": design["status"], "fill": design["fill"], "checks": design["checks"],
                  "geometry": design["geometry"], "result_directory": str(result)}, indent=2), flush=True)
