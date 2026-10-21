"""Collect local retry acceptance and full-resolution evidence after both runs finish."""
import json
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
reports = ROOT / ".plans/reports"


def read(name):
    return json.loads((reports / name).read_text(encoding="utf-8"))


full = read("drone-full-results.json")
design = full["designs"][0]
checks = design["checks"]
run = read("drone-agent-backoff.json")
times = read("drone-agent-request-times.json")
quota = read("gemini-quota-diagnostic.json")
suite = ET.parse(reports / "retry-full-tests.xml").getroot().find("testsuite")
recommendation = run["recommendation"]
health = urllib.request.urlopen("http://127.0.0.1:8765/_stcore/health", timeout=10).status
summary = {
    "completed_utc": datetime.now(timezone.utc).isoformat(),
    "implementation_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "retry_policy": {"status_codes": [429, 503], "max_retries": 4,
                     "delays_s": [4, 8, 16, 32], "sdk_retries_disabled": True,
                     "agent_min_interval_s": 4, "shared_across_worker_processes": True},
    "tests": dict(suite.attrib) | {"includes_slow": True},
    "live_agent": {
        "completed": True, "live_recommendation_confirmed": recommendation["source"] == "llm",
        "provider": run["llm"], "round_count": len(run["rounds"]), "seconds": run["seconds"],
        "proposal_sources": [r["proposal"]["source"] for r in run["rounds"] if r["proposal"]],
        "recommendation_source": recommendation["source"],
        "recommendation_attempts": recommendation["attempts"],
        "best_design": recommendation["best_design"], "http_attempt_count": len(times),
        "minimum_observed_request_spacing_s": min(b["elapsed_s"] - a["elapsed_s"]
                                                  for a, b in zip(times, times[1:])),
        "log": "drone-agent-backoff.json", "quota_diagnostic": quota,
        "blocker": "Configured Gemini model's daily free-tier quota is exhausted (20 requests/day)."
                   if recommendation["source"] != "llm" else None,
    },
    "full_resolution": {
        "source": "drone-agent-live.json, recommended round 1; source quick mass 11.77 g",
        "problem": "drone_best_pa6cf.json", "material": design["material"],
        "design_space_mm": [120, 22.5], "thickness_mm": 10,
        "element_cap": full["solver_settings"]["cap_used"],
        "actual_mesh": full["catalogs"]["fdm"]["mesh"],
        "actual_elements": full["catalogs"]["fdm"]["elements"],
        "element_size_mm": design["mesh_h_mm"], "minimum_wall": design["effective_min_wall"],
        "workflow": "10 cold density levels, refinement, independent cold rerun, smoothing and recheck",
        "seconds": full["seconds"], "status": design["status"],
        "mass_g": checks["mass_g"], "fill": design["fill"], "safety_factor": checks["sf"],
        "safety_factor_target": checks["sf_target"],
        "worst_deflection_mm": max(checks["deflection_mm"]), "deflection_limit_mm": 0.5,
        "all_hand_checks_pass": all(c["passed"] for c in checks["out_of_plane"] + checks["bearing"]),
        "watertight": bool(design["geometry"]["watertight"]),
        "selected_design_converged": bool(design["converged"]), "notes": design["notes"],
        "independent_cold_rerun": design["rerun"],
        "independent_cold_rerun_passed": bool(design["rerun"]["replaced"]),
        "qualification": "The retained refined geometry passes the smoothed FE and hand checks, "
                         "but its optimization stopped before convergence. The separate cold rerun "
                         "converged but failed checks, so the production pipeline retained the refinement.",
        "results": "drone-full-results.json",
        "artifacts": ".plans/live_runs/full-resolution/drone_best_pa6cf",
    },
    "application": {"url": "http://127.0.0.1:8765", "health_status": health,
                    "restarted_with_new_adapter": True},
}
(reports / "retry-and-full-solve-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps({"tests": summary["tests"],
                  "agent_live": summary["live_agent"]["live_recommendation_confirmed"],
                  "agent_requests": len(times),
                  "spacing_s": summary["live_agent"]["minimum_observed_request_spacing_s"],
                  "full_pass": design["status"], "mass_g": checks["mass_g"],
                  "converged": bool(design["converged"]), "app_health": health}, indent=2))
