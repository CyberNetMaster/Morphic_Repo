"""All constants in one place: caps, defaults, model names, tolerances.

Units everywhere in the code: mm, N, MPa, g, s.
"""

from __future__ import annotations

# ---------------------------------------------------------------- LLM provider
# The LLM is a thin adapter (morphic/llm.py). Switch provider by changing
# LLM_PROVIDER to "claude" and the matching model name. Keys come from .env.
LLM_PROVIDER = "gemini"  # "gemini" | "claude"
LLM_MODELS = {
    "gemini": "gemini-2.5-pro",
    "claude": "claude-opus-5-5",
}
LLM_TIMEOUT_S = 45.0
LLM_RETRIES = 1

# ---------------------------------------------------------------- element caps
ELEMENT_CAP_LIVE = 40_000
ELEMENT_CAP_QUICK = 10_000
# Chosen by the timing benchmark (S9, 2026-10-20, .plans/bench/): measured 0.85 s/it at 40k,
# 1.62 s/it at 80k, 3.9 s/it at 150k elements on this laptop. Cold 10-level catalogs for the
# three demo parts take about 7.5 h at 80k and about 11.5 h at 150k, so the cached cap is 80k.
ELEMENT_CAP_CACHED = 80_000
ELEMENT_CAP_CACHED_SWEEP = "cold"  # cold run per level for the precomputed demo parts (spec 6.3)
MIN_WALL_TO_ELEMENT_RATIO = 2.5  # h = min_wall / 2.5; effective min wall = 2.5 * h

# ---------------------------------------------------------------- SIMP
SIMP_PENALTY = 3.0
E_MIN_RATIO = 1e-9
FILTER_RADIUS_MIN_ELEMENTS = 1.5
BETA_SCHEDULE_COLD = (1, 2, 4, 8, 16)
BETA_SCHEDULE_WARM = (4, 8, 16)
BETA_STEP_ITERS = 40
CHANGE_TOL = 0.01
# Second stop rule (decided 2026-10-20): at the last beta, stop when the objective has changed
# less than PLATEAU_RTOL over PLATEAU_WINDOW consecutive iterations.
PLATEAU_WINDOW = 10
PLATEAU_RTOL = 1e-3
MAX_ITERS_COLD = 300
MAX_ITERS_WARM = 100
MAX_ITERS_REFINE = 60
OC_MOVE = 0.2
CATALOG_REFERENCE_E = 1.0
CATALOG_REFERENCE_NU = 0.33
SNAPSHOT_EVERY_CATALOG = 2
SNAPSHOT_EVERY_COLD_RERUN = 1

# ---------------------------------------------------------------- catalog
FILL_LEVELS = (0.60, 0.55, 0.50, 0.45, 0.40, 0.35, 0.30, 0.25, 0.20, 0.15)
FILL_LEVELS_LIVE_SHORT = (0.60, 0.50, 0.40, 0.30, 0.25, 0.20, 0.15)
# S9: a 10-level warm sweep at 40k took 16.4 min per catalog (about 60 min per part with
# refinement and the cold re-run), so live mode uses the 7-level sweep (about 46 min per part).
FILL_LEVELS_LIVE = FILL_LEVELS_LIVE_SHORT
FILL_LEVELS_EXTRA_LOW = (0.12, 0.10, 0.08)
NORMALIZATION_FILL = 0.60
REFINE_BISECTION_STEPS = 3

# ---------------------------------------------------------------- evaluation
SOLID_THRESHOLD = 0.5
EXCLUSION_RING_WIDTHS = 1.0  # zone = ring + this many ring widths beyond it (in mm)
REACTION_SUM_RTOL = 1e-6
OUT_OF_PLANE_SECTIONS = 20
RECHECK_SUPERSAMPLE = 4

# ---------------------------------------------------------------- problem defaults
DEFAULT_SAFETY_FACTOR = 2.0
DEFAULT_THICKNESS_MM = 6.0
DEFAULT_DEFLECTION_SPAN_RATIO = 100.0
DEFAULT_PRINTER = "any"
DEFAULT_HOLE_R_MM = 1.6
DEFAULT_RING_WIDTH_MIN_MM = 2.0
DEFAULT_RING_WIDTH_WALLS = 2.0

# ---------------------------------------------------------------- sanity limits
SIZE_MIN_MM = 5.0
SIZE_MAX_MM = 2000.0
FORCE_MAX_N = 1_000_000.0
THIN_SPAN_RATIO = 20.0
KEEP_IN_MAX_FRACTION = 0.90

# ---------------------------------------------------------------- validation
VALIDATION_TOL_BEAM = 0.03
VALIDATION_TOL_MBB = 0.02
VALIDATION_TOL_SCALING = 1e-6

# ---------------------------------------------------------------- geometry
SMOOTH_MAX_MOVE_ELEMENTS = 0.5
VOLUME_CHECK_RTOL = 0.01

# ---------------------------------------------------------------- bundle
RERUN_STRICT_RTOL = 0.005
RERUN_LOOSE_MASS_RTOL = 0.02


def solver_settings() -> dict:
    """Every constant above as a plain dict, for the run bundle."""
    out = {}
    for k, v in globals().items():
        if k.isupper():
            out[k] = list(v) if isinstance(v, tuple) else v
    return out
