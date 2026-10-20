"""S9b: profile N optimizer iterations on the S9 benchmark setup (bracket, metal, 40k cap)."""
import cProfile, json, pstats, sys, time
from morphic import config, topopt
from morphic.domain import build_domain
from morphic.materials import load_processes
from morphic.problem import problem_from_dict

iters = int(sys.argv[1]) if len(sys.argv) > 1 else 30
cap = int(sys.argv[2]) if len(sys.argv) > 2 else 40000
p = problem_from_dict(json.load(open("examples/aero_bracket.json")))
proc = load_processes()["metal"]
dom = build_domain(p, "metal", proc.min_wall_mm, cap)
prob = dom.topopt_problem(config.CATALOG_REFERENCE_NU)
prob.case_weights = topopt.normalization_weights(prob, 0.6)
s = topopt.TopOptSettings(volfrac=0.6, rmin=dom.rmin_elements, mode="cold", max_iters=iters)
print("elements", dom.mesh.nel, "rmin", round(dom.rmin_elements, 3))
pr = cProfile.Profile(); t = time.perf_counter(); pr.enable()
r = topopt.run(prob, s)
pr.disable(); dt = time.perf_counter() - t
print(f"{r.iterations} it in {dt:.1f} s = {dt / r.iterations:.3f} s/it")
pstats.Stats(pr).sort_stats("tottime").print_stats(14)
