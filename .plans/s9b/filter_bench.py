import time
import numpy as np, scipy.sparse as sp
from scipy import ndimage
from morphic import fe, topopt
mesh = fe.Mesh(331, 121, 0.538)
x = np.random.default_rng(1).uniform(0, 1, mesh.nel)
f = topopt.DensityFilter(mesh, 1.5)
ref = f.apply(x)
k = f.kernel; r = k.shape[0] // 2
# sparse H
rows, cols, vals = [], [], []
idx = np.arange(mesh.nel).reshape(mesh.nelx, mesh.nely)
for di in range(-r, r + 1):
    for dj in range(-r, r + 1):
        w = k[di + r, dj + r]
        if w <= 0: continue
        a = idx[max(0, -di):mesh.nelx - max(0, di), max(0, -dj):mesh.nely - max(0, dj)]
        b = idx[max(0, di):mesh.nelx + min(0, di) if di < 0 else mesh.nelx, max(0, dj):mesh.nely + min(0, dj) if dj < 0 else mesh.nely]
        b = idx[max(0, -di) + di:mesh.nelx - max(0, di) + di, max(0, -dj) + dj:mesh.nely - max(0, dj) + dj]
        rows.append(a.ravel()); cols.append(b.ravel()); vals.append(np.full(a.size, w))
H = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(mesh.nel, mesh.nel))
Hs = np.asarray(H.sum(axis=1)).ravel()
Hn = sp.diags(1 / Hs) @ H
Hn = Hn.tocsr()
def slices(xv):
    g = xv.reshape(mesh.nelx, mesh.nely)
    p = np.pad(g, r)
    out = np.zeros_like(g)
    for di in range(2 * r + 1):
        for dj in range(2 * r + 1):
            w = k[di, dj]
            if w > 0:
                out += w * p[di:di + mesh.nelx, dj:dj + mesh.nely]
    return out.ravel() / f.Hs
for name, fn in (("ndimage", f.apply), ("csr H x / Hs", lambda v: (H @ v) / Hs), ("csr normalized", lambda v: Hn @ v), ("slices", slices)):
    y = fn(x); t = time.perf_counter()
    for _ in range(300): fn(x)
    print(f"{name:16s} {(time.perf_counter() - t) / 300 * 1e3:.3f} ms  max diff {np.abs(y - ref).max():.1e}")
act = np.ones(mesh.nel, bool); act[:500] = False
af = act.astype(float)
for name, fn in (("x[mask].sum()", lambda: x[act].sum()), ("dot(x, maskf)", lambda: x @ af), ("sum - passive", lambda: x.sum() - x[:500].sum())):
    t = time.perf_counter()
    for _ in range(1000): fn()
    print(f"{name:16s} {(time.perf_counter() - t) / 1000 * 1e3:.3f} ms")
e = np.exp(-8.0)
t = time.perf_counter()
for _ in range(300): 1.0 - np.exp(-8.0 * x) + x * e
print(f"heaviside        {(time.perf_counter() - t) / 300 * 1e3:.3f} ms")
