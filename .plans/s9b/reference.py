"""S9b reference: a fixed run whose results must not change beyond 1e-6.

Bracket, metal, cap given (default 20k): one cold run of 70 iterations (crosses the
beta 1 -> 2 step at 40), one warm run of 30 iterations from it, then the evaluation
of the final design with the real Ti64 values. Saves everything to an .npz.
Usage: python reference.py OUT.npz [cap]
"""
import json, sys, time
import numpy as np
from morphic import config, evaluate, topopt
from morphic.domain import build_domain
from morphic.materials import load_materials, load_processes
from morphic.problem import problem_from_dict

out = sys.argv[1]
cap = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
p = problem_from_dict(json.load(open("examples/aero_bracket.json")))
proc = load_processes()["metal"]
mat = load_materials()["ti64"]
dom = build_domain(p, "metal", proc.min_wall_mm, cap)
prob = dom.topopt_problem(config.CATALOG_REFERENCE_NU)
w = topopt.normalization_weights(prob, 0.6)
prob.case_weights = w
t = time.perf_counter()
r1 = topopt.run(prob, topopt.TopOptSettings(volfrac=0.6, rmin=dom.rmin_elements, mode="cold", max_iters=70))
r2 = topopt.run(prob, topopt.TopOptSettings(volfrac=0.45, rmin=dom.rmin_elements, mode="warm", x0=r1.x, max_iters=30))
dt = time.perf_counter() - t
mech = evaluate.analyze_design(dom, r2.xPhys, mat.E, mat.nu)
np.savez(out, weights=w, x1=r1.x, xPhys1=r1.xPhys, c1=r1.compliance, obj1=[h["objective"] for h in r1.history],
         x2=r2.x, xPhys2=r2.xPhys, c2=r2.compliance, obj2=[h["objective"] for h in r2.history],
         defl=mech.deflection_mm, s_rep=mech.stress_reported_MPa, s_raw=mech.stress_raw_MPa, area=[mech.area_mm2],
         seconds=[dt], iters=[r1.iterations + r2.iterations])
print(f"elements {dom.mesh.nel}, {r1.iterations + r2.iterations} it in {dt:.1f} s = "
      f"{dt / (r1.iterations + r2.iterations):.3f} s/it; c2 {r2.compliance}")
