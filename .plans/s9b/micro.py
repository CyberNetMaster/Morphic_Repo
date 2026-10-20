import json, time
import numpy as np, scipy.sparse as sp, pypardiso
from scipy import ndimage
from morphic import config, fe, topopt
from morphic.domain import build_domain
from morphic.materials import load_processes
from morphic.problem import problem_from_dict

p = problem_from_dict(json.load(open("examples/aero_bracket.json")))
dom = build_domain(p, "metal", load_processes()["metal"].min_wall_mm, 40000)
prob = dom.topopt_problem(0.33)
mesh = dom.mesh
x = np.random.default_rng(0).uniform(0.05, 1, mesh.nel)
K = prob.assembler.assemble(prob.modulus(x))
free = prob.free_dofs
A = sp.triu(K[free][:, free], format="csr")
F = np.asfortranarray(prob.loads[free])
ps = pypardiso.PyPardisoSolver(mtype=2)
def call(phase, b):
    ps.set_phase(phase); return ps._call_pardiso(A, b)
b0 = np.zeros((A.shape[0], 1))
for name, ph, b in (("analysis 11", 11, b0), ("numeric 22", 22, b0), ("solve 33", 33, F), ("numeric 22 again", 22, b0), ("combined 12", 12, b0)):
    t = time.perf_counter(); call(ph, b); print(f"{name:18s} {time.perf_counter() - t:.3f} s")
t = time.perf_counter()
for _ in range(5): K[free][:, free]
print(f"slice K_ff          {(time.perf_counter() - t) / 5:.3f} s")
t = time.perf_counter()
for _ in range(5): sp.triu(K[free][:, free], format='csr')
print(f"slice + triu        {(time.perf_counter() - t) / 5:.3f} s")
filt = topopt.DensityFilter(mesh, dom.rmin_elements)
t = time.perf_counter()
for _ in range(100): filt.apply(x)
print(f"filter apply        {(time.perf_counter() - t) / 100 * 1e3:.2f} ms  kernel {filt.kernel.shape}")
t = time.perf_counter()
for _ in range(100): topopt.heaviside(x, 8.0)
print(f"heaviside + deriv   {(time.perf_counter() - t) / 100 * 1e3:.2f} ms")
t = time.perf_counter()
e8 = np.exp(-8.0)
for _ in range(100): 1.0 - np.exp(-8.0 * x) + x * e8
print(f"heaviside only      {(time.perf_counter() - t) / 100 * 1e3:.2f} ms")
