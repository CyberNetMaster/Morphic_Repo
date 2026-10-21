"""Cinematic renders (S15): field ordering, colors, frame schedule, camera fit, and one tiny MP4."""

import json
import math

import numpy as np
import pytest

from render import cinematic as c

RC_ARM = c.CACHE_DIR / "rc_arm"


def test_cells_to_vtk_order():
    nelx, nely = 3, 2
    a = np.arange(nelx * nely)  # fe.Mesh order: index i * nely + j
    v = c.cells_to_vtk(a, nelx, nely)  # VTK: index i + j * nelx
    for i in range(nelx):
        for j in range(nely):
            assert v[i + j * nelx] == a[i * nely + j]


def test_nodes_to_vtk_order():
    nelx, nely = 2, 1
    a = np.arange((nelx + 1) * (nely + 1))
    v = c.nodes_to_vtk(a, nelx, nely)
    for i in range(nelx + 1):
        for j in range(nely + 1):
            assert v[i + j * (nelx + 1)] == a[i * (nely + 1) + j]


def test_fill_nan_nearest_takes_neighbours_then_zero():
    g = np.array([[np.nan, 1.0, np.nan, np.nan, np.nan, np.nan],
                  [0.5, np.nan, np.nan, np.nan, np.nan, np.nan]])
    out = c.fill_nan_nearest(g, passes=1)
    assert out[0, 0] == pytest.approx(0.75)  # mean of the finite neighbours 1.0 and 0.5
    assert out[1, 1] == pytest.approx(0.75)
    assert out[0, 5] == 0.0 and out[1, 5] == 0.0  # too far away: void
    assert not np.isnan(out).any()


def test_density_rgba_alpha_follows_density():
    d = np.array([0.0, 0.1, 0.5, 1.0])
    rgba = c.density_rgba(d)
    assert rgba.shape == (4, 4) and rgba.dtype == np.uint8
    assert rgba[0, 3] == 0 and rgba[3, 3] == 255
    assert np.all(np.diff(rgba[:, 3].astype(int)) > 0)
    assert rgba[1, 3] == round(0.1 ** c.ALPHA_GAMMA * 255)


def test_utilization_rgba_over_limit_is_red():
    rgba = c.utilization_rgba(np.array([0.0, 0.5, 1.0, 1.3]))
    assert np.all(rgba[:, 3] == 255)
    assert tuple(rgba[3, :3]) == c._rgb(c.theme.OVER_LIMIT)
    assert tuple(rgba[0, :3]) == c._rgb(c.theme.UTIL_SCALE[0][1])


def test_schedule_plays_every_snapshot_in_order_then_holds_the_design():
    n, fps = 50, 30
    s = c.make_schedule(n, frames_per_snapshot=2, hold_start_s=1.0, hold_end_s=2.0, dissolve_s=0.6, fps=fps)
    snap = [i for k, i in zip(s.kind, s.index) if k == "snapshot"]
    assert snap[0] == 0 and snap[-1] == n - 1
    assert sorted(set(snap)) == list(range(n))  # every saved snapshot appears
    assert all(b >= a for a, b in zip(snap, snap[1:]))  # in iteration order
    assert s.kind.count("dissolve") == round(0.6 * fps)
    assert s.kind.count("design") == 2 * fps
    assert snap.count(0) == fps  # the first snapshot holds for one second in total
    assert s.kind == sorted(s.kind, key=["snapshot", "dissolve", "design"].index)
    mixes = [m for k, m in zip(s.kind, s.mix) if k == "dissolve"]
    assert all(0 < m < 1 for m in mixes) and mixes == sorted(mixes)


def test_schedule_step_keeps_first_and_last():
    s = c.make_schedule(11, frames_per_snapshot=1, hold_start_s=0, hold_end_s=0, dissolve_s=0, step=4)
    assert s.index == [0, 4, 8, 10]


def test_orbit_is_slow_and_monotonic():
    az = c.orbit_azimuths(300, -20.0, 20.0)
    assert az[0] == pytest.approx(-20.0) and az[-1] == pytest.approx(20.0)
    assert np.all(np.diff(az) >= 0)
    assert np.max(np.diff(az)) < 0.5  # under half a degree per frame


def test_fit_distance_keeps_every_corner_in_frame():
    bounds = (0.0, 90.0, 0.0, 20.0, 0.0, 12.0)
    azimuths = np.linspace(-28, 28, 7)
    tilt, view_angle, aspect = 34.0, 30.0, 16 / 9
    d = c.fit_distance(bounds, azimuths, tilt, view_angle, aspect, fit_fraction=(1.0, 1.0), margin=1.0)
    corners = np.array([[x, y, z] for x in bounds[0:2] for y in bounds[2:4] for z in bounds[4:6]])
    center = corners.mean(axis=0)
    tan_v = math.tan(math.radians(view_angle) / 2)
    tan_h = tan_v * aspect
    for az in azimuths:
        pos, view_dir, right, up = c.camera_basis(center, d, az, tilt)
        rel = corners - pos
        depth = rel @ view_dir
        assert np.all(depth > 0)
        assert np.all(np.abs(rel @ right) <= depth * tan_h + 1e-9)
        assert np.all(np.abs(rel @ up) <= depth * tan_v + 1e-9)
    # and it is tight: a little closer and a corner falls outside
    pos, view_dir, right, up = c.camera_basis(center, d * 0.97, azimuths[0], tilt)
    rel = corners - pos
    depth = rel @ view_dir
    assert np.any(np.abs(rel @ right) > depth * tan_h) or np.any(np.abs(rel @ up) > depth * tan_v)


@pytest.mark.skipif(not (RC_ARM / "rerun_fdm.npz").exists(), reason="demo cache not present")
def test_load_sequence_reads_real_snapshots():
    seq = c.load_sequence(RC_ARM)  # the winner's process
    results = json.loads((RC_ARM / "results.json").read_text(encoding="utf-8"))
    assert seq.material == results["ranking"]["winner"]
    assert len(seq.snapshots) == len(seq.iterations) and np.all(np.diff(seq.iterations) > 0)
    assert all(s.dtype == np.uint8 and s.shape == (seq.nelx * seq.nely,) for s in seq.snapshots)
    assert seq.design.shape == (seq.nelx * seq.nely,)
    assert seq.utilization.shape == ((seq.nelx + 1) * (seq.nely + 1),)
    assert np.isnan(seq.utilization).any() and np.nanmax(seq.utilization) > 0
    assert seq.label == "FDM · PA6-CF"
    assert set(c.rerun_processes(RC_ARM)) == {"fdm", "sls", "metal"}


@pytest.mark.skipif(not (RC_ARM / "rerun_fdm.npz").exists(), reason="demo cache not present")
def test_tiny_mp4_frames_change_between_snapshots(tmp_path):
    pytest.importorskip("pyvista")
    pytest.importorskip("imageio_ffmpeg")
    seq = c.load_sequence(RC_ARM, "fdm")
    out = tmp_path / "tiny.mp4"
    info = c.render_growth(seq, out, size=(320, 180), fps=30, frames_per_snapshot=1,
                           hold_start_s=0.0, hold_end_s=0.1, dissolve_s=0.1, step=60)
    assert out.exists() and out.stat().st_size > 0
    assert info["frames"] == len(c.make_schedule(len(seq.snapshots), 1, 0.0, 0.1, 0.1, 30, 60))
    # the renderer must redraw each frame: the first snapshot and the design differ on screen
    r = c.SlabRenderer(seq, size=(320, 180))
    try:
        first = r.render_snapshot(0, 0.0)
        last = r.render_snapshot(len(seq.snapshots) - 1, 0.0)
        design = r.render_design(0.0)
    finally:
        r.close()
    assert first.shape == (180, 320, 3)
    assert np.abs(first.astype(int) - last).mean() > 1.0
    assert np.abs(last.astype(int) - design).mean() > 1.0
    assert info["design_equals_last_snapshot"] is False  # rc_arm FDM: the re-run did not replace the result
