"""Compare two reference .npz files; pass if every quantity matches within 1e-6."""
import sys
import numpy as np
a, b = np.load(sys.argv[1]), np.load(sys.argv[2])
worst = 0.0
for k in a.files:
    if k in ("seconds", "iters"):
        continue
    x, y = np.asarray(a[k], float), np.asarray(b[k], float)
    if x.shape != y.shape:
        print(f"{k:8s} SHAPE {x.shape} vs {y.shape}"); worst = np.inf; continue
    scale = max(np.abs(x).max(), 1e-300)
    d = np.abs(x - y).max() / scale if k.startswith(("x", "xPhys")) is False else np.abs(x - y).max()
    worst = max(worst, d)
    print(f"{k:8s} max diff {d:.2e}" + ("  (absolute, densities)" if k.startswith("x") else "  (relative)"))
print(f"time {a['seconds'][0]:.1f} s vs {b['seconds'][0]:.1f} s for {int(a['iters'][0])} iterations: "
      f"{a['seconds'][0] / b['seconds'][0]:.2f}x")
print("PASS" if worst <= 1e-6 else "FAIL", f"(worst {worst:.2e})")
