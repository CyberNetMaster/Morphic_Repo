"""S14 acceptance: precomputed demo results load instantly (skipped until the cache exists)."""

import time

import pytest

from morphic.precompute import CACHE_DIR, load_cached

PARTS = ("rc_arm", "drone_arm", "aero_bracket")


@pytest.mark.parametrize("stem", PARTS)
def test_cached_part_loads_fast(stem):
    if not (CACHE_DIR / stem / "results.json").exists():
        pytest.skip("cache not built yet (run `morphic precompute`)")
    t = time.perf_counter()
    r = load_cached(stem)
    dt = time.perf_counter() - t
    assert dt < 1.0, dt
    assert r["designs"] and r["ranking"]["funnel"]
    assert r["solver_settings"]["cap_used"] == 80_000
    assert r["solver_settings"]["sweep_mode_used"] == "cold"
    assert not r["code_version"].endswith("-dirty")
