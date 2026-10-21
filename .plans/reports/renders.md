# Workspace G

S15 cinematic renders (spec 15.1, stretch goal 1). Done 2026-10-21 on this laptop, branch
`emdash/g-renders-us52v`, local commits only.

## What was built

| File | Purpose |
|---|---|
| `render/cinematic.py` | PyVista off-screen renderer and MP4 writer. Reads `examples/cache/<part>/` only. Never runs the solver. |
| `render/__init__.py` | Package marker. |
| `tests/test_cinematic.py` | 11 tests: field ordering, color maps, frame schedule, camera fit, real-cache loading, one tiny MP4. |
| `app/theme.py` | One added constant, `DENSITY_SCALE_CINEMATIC` (the slab's grey-to-white ramp). All other colors come from the existing theme. |
| `pyproject.toml`, `uv.lock` | Optional extra `render = ["pyvista>=0.44", "imageio-ffmpeg>=0.5"]`. Installed with `uv sync --extra render`. |
| `README.md` | New section "Cinematic renders (S15)". |
| `.gitignore` | `renders/*.mp4`, `renders/*.png`, `renders/last_render.json`. |

No engine module (`morphic/*`) was changed. The existing `morphic render` GIF command is untouched.

Commands:

```bash
uv sync --extra render
uv run python -m render.cinematic --all                          # all four clips below
uv run python -m render.cinematic --part drone_arm               # one winner
uv run python -m render.cinematic --part rc_arm --side-by-side   # FDM, SLS, metal in lockstep
uv run python -m render.cinematic --part rc_arm --preview        # 960 x 540, every 6th snapshot
```

Options: `--cut` (hard cut instead of the picture dissolve), `--caption "..."` (one quiet line at the
bottom, for the storyboard's bone remodeling note), `--frames-per-snapshot`, `--hold-start`, `--hold-end`,
`--still` (save the last frame as PNG).

## Finished clips (in `renders/`, ignored by git)

All four are H.264, yuv420p, 1920 x 1080, 30 fps (checked by reading each file back with ffmpeg).

| Clip | Snapshots | Frames | Length | Size | Render time |
|---|---|---|---|---|---|
| `rc_arm_fdm_pa6cf_growth.mp4` (winner: FDM PA6-CF) | 195 | 556 | 18.5 s | 4.0 MB | 77 s |
| `drone_arm_fdm_pa6cf_growth.mp4` (winner: FDM PA6-CF) | 179 | 524 | 17.5 s | 3.0 MB | 78 s |
| `aero_bracket_metal_alsi10mg_growth.mp4` (winner: metal AlSi10Mg) | 176 | 518 | 17.3 s | 2.2 MB | 86 s |
| `rc_arm_side_by_side.mp4` (FDM PA6-CF, SLS PA12, metal AlSi10Mg) | 195 / 189 / 189 | 556 | 18.5 s | 4.6 MB | 149 s |

Half-size JPEGs of each clip's last frame are in `.plans/reports/renders/`, with the render summary
`last_render.json`.

Timeline of a growth clip: 1.0 s on the first saved snapshot (the block), then 2 frames per snapshot
(about 12 s), a 0.6 s picture dissolve, then 4.0 s on the checked design with utilization colors. The
side-by-side clip plays iteration k of every run at the same time; a run that finished early holds its
last snapshot until the longest run (195 iterations) ends.

## Where every frame comes from

- Growth frames: `rerun_<process>.npz`, keys `it1 ... itN`, uint8 density x 255, one per iteration,
  flat element vector in `fe.Mesh` order (index `i * nely + j`). Mesh size from
  `results.json["catalogs"][process]["mesh"]`, cell size `h_mm` from the same record, thickness from
  the problem. The slab is `nelx x nely x 1` hexahedra; cells with density 0 are not drawn.
- Final frames: `densities.npz["design/<material>"]` thresholded at 0.5 (the clean shape of spec 6.8),
  colored by `utilization.npz[<material>]`, the recovered nodal utilization per load case; each node
  takes the highest of its load cases, NaN marks void. A NaN node next to a drawn cell takes the mean
  of its finite neighbours (same idea as the app's 3D view).
- Nothing is interpolated between snapshots. The orbit and the opacity are presentation only.

Cold re-run vs. checked design (spec 6.7): all three winners' re-runs ended in a slightly different
local minimum, so the catalog shape stayed the result (`replaced = 0`). Solid/void disagreement between
the last snapshot and the checked design: RC arm 3.0 % of cells, drone arm 5.9 %, bracket 1.6 %.
For the RC arm's SLS and metal re-runs the re-run replaced the result (`replaced = 1`, 0 % difference).
The clip therefore ends on the checked design, the one that was evaluated and exported, after a 0.6 s
dissolve between two rendered pictures (the last snapshot and the design). The dissolve mixes pixels of
two saved fields and computes no shape. The final frames carry the spec 6.7 footnote: "Growth: an
independent cold run at the same fill level. Final frame: the checked design." When the two fields are
identical the dissolve is skipped automatically. `--cut` removes it everywhere.

## Look

- Stage `#050506` (theme `DARK["bg"]`). Three directional lights: key from high front-left (0.80), fill
  from the right (0.35), back light (0.30). Depth peeling (12 peels) for the translucent cells,
  super-sampled anti-aliasing.
- Density color: `DENSITY_SCALE_CINEMATIC` (`#8E8E93` -> `#C7C7CC` -> `#E8E8ED`); opacity = density^0.5,
  so a 13 % fill block still reads as a block and converged cells are opaque.
- Utilization: theme `UTIL_SCALE` on the shared 0..1 scale, `OVER_LIMIT` red above 1, same as the app.
- Camera: above the slab, tilted 34 degrees off vertical (26 in the strips), one eased swing from
  -28 to +28 degrees over the whole clip. The distance is the smallest that keeps every slab corner in
  frame at every orbit angle, leaving room for the labels.
- Labels (PIL, Segoe UI): process eyebrow in the process color, part name, iteration readout
  ("139 of 179"), fill level and size. Final frames add the checked numbers ("SF 1.7 vs 1.5 target ·
  111.1 g · 0.15 of 0.3 mm"), the legend with a tick at the reported peak (= SF target / SF, outside
  the pad exclusion zones) and the raw nodal peak when it is higher (bracket: 0.87 reported, 1.95 raw
  inside the clevis pad zone, drawn red).

## Checks

- `uv run pytest tests/test_cinematic.py tests/test_smoke.py tests/test_app.py -q`: 21 passed.
- `uv run pytest -q -m "not slow"` (the whole fast suite, with the new tests): 162 passed, exit code 0.
- Each clip read back with ffmpeg: codec h264, pix_fmt yuv420p, 1920 x 1080, 30 fps, frame counts
  as in the table.
- Frames inspected by eye at several times for all four clips (block, mid-growth, dissolve, final).

## Notes and limits

- Walls are stair-stepped because the slab is the real FE grid (0.16 to 0.38 mm cells). The clips show
  the mesh the solver used, not the smoothed STL.
- The arms' final frames are mostly dark blue: their utilization is low (drone arm peak 0.19, limited by
  deflection at 0.49 of 0.5 mm; RC arm 0.32). The bracket, at SF 1.7 vs 1.5, is the colorful one. The
  shared 0..1 scale is kept on purpose so the three parts compare honestly.
- For the low-fill parts the design-space corners vanish at iteration 1: the OC move limit (0.2) is
  larger than the fill (0.08 to 0.13), so the first update sends unloaded cells straight to zero. Real data.
- Only the RC arm has all three cold re-runs (`rerun_fdm`, `rerun_sls`, `rerun_metal`), so it is the
  side-by-side part. The drone arm has FDM and metal, the bracket has metal only; `--side-by-side` on
  those renders the available strips.
- The first growth frame is iteration 1 (the first saved snapshot), not the uniform start, which is not
  stored.
- Off-screen PyVista needs an explicit `render()` before each screenshot on this machine; without it
  every frame repeated the first one. That is handled and covered by a test.
- Rendering uses the laptop's Intel Iris Xe GPU through VTK's Win32 OpenGL window; about 6 to 7 frames
  per second at 1080p with super-sampling.
