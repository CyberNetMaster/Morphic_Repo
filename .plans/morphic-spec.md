# Morphic — Build Spec

Status: complete plan, ready to build. Written 2026-10-20. Revised 2026-10-20 after review (all review items A1–A7, B1–B10, C1–C9, D1–D7 applied; nodal stress recovery added after the second review).
Event: OSI Hackathon (Open Scientific Intelligence), Oct 21–22, 2026, MIT hub. Solo entry.
Submission: public post with a demo video (max 4:00) and a 1-page write-up. Due **Thu Oct 22, 8:00 PM Eastern**.
Judging: impact on research, innovativeness, scalability, relevance to physical sciences / materials.

---

## 1. What Morphic is

Morphic is a design tool for load-bearing parts.

1. The user describes a part in plain English: where it is held, where loads act, size limits, and limits on stress and bending.
2. Morphic turns the text into a structured problem. The user checks it on a drawing and fixes anything wrong.
3. Morphic runs 2D topology optimization for six real, printable materials across three print processes.
4. For each material, it finds the **lowest fill level, among stiffness-optimized shapes, that still meets the safety factor and deflection limits**.
5. It ranks the results by mass, explains the best choice using only computed numbers, and exports an STL, SVG, DXF, a PDF report, and a reproducible run bundle.

### 1.1 The core claim, stated precisely

In the standard topology optimization setup (stiffest shape for a fixed amount of material), the shape does **not** depend on the material. Stiffness scales every result by the same factor. Morphic uses a different setup, so the material does matter:

- **Goal:** lowest mass.
- **Limits:** safety factor ≥ target (uses material strength) and deflection ≤ limit (uses material stiffness), in every load case.

A stiffer or stronger material meets the limits with less material. Less material gives a different shape: fewer, thinner members. Each process also has its own minimum wall, which sets the optimizer's filter size. So shapes differ by **material** (through the fill level) and by **process** (through the minimum wall).

What the solver actually does: it minimizes compliance (maximizes stiffness) at a fixed fill level, then searches over fill levels for the lowest one that passes the limits. The result is "the stiffest shape at the lowest passing fill level," not a true minimum-mass design under a stress constraint. Say this plainly in the write-up and the Q&A. Stress constraints inside the optimizer are out of scope (section 17.3).

Honest note for the write-up: within one process, two materials differ only by their fill level. The shape at a given fill level is the same. Say this plainly. It is also why the catalog method (section 6) is correct and fast.

### 1.2 What is new, and what is not

Comparing materials and processes side by side is **not** new. Autodesk Fusion 360 generative design and nTopology both do it. Morphic does not claim to be first at that. What Morphic adds, and what the write-up leads with:

- Plain-English input, turned into a problem the user checks on a drawing before anything runs.
- Only cited datasheet values, shown with their sources. No invented materials.
- Process-aware minimum walls, enforced and displayed.
- An explanation whose every number is checked against the computed results.
- A run bundle that reruns to the same answer, so others can check and extend the work.
- Open source (MIT), and a catalog method that adds a material at near-zero cost.

The write-up says, in one sentence: "Commercial tools do material comparisons behind a paywall and without sources; Morphic is open, cited, and reproducible."

### 1.3 Scope

In scope: static loads, room temperature, linear elastic, small deflections, 2D plane stress, extruded to a constant thickness.
Out of scope: fluids, heat, fatigue, impact toughness, buckling analysis, nonlinear materials, physical testing (no printer available; validation is theoretical), stress constraints inside the optimizer.
Stated limits (shown in every result's "Limits" expander and in the write-up):
- Static check only. Fatigue and impact toughness are not evaluated.
- Printed flat at 100% infill. In-plane stresses run along the layers. If the part is printed standing up, in-plane stresses in the vertical direction would see the lower Z strength, and these numbers would not apply.
- Von Mises with one strength value is a simplification for plastics. PA6-CF is anisotropic within a layer: the XY datasheet value is along the bead direction, and strength across beads in the same layer is lower. The result assumes slicer perimeters follow the member direction.
- Stresses are recovered to the nodes (Gauss-point extrapolation, averaged over solid elements), so edge values are not under-read the way element-center values are. A small error remains at the production mesh; the hole check (section 13.4) measures it and the Validation tab shows it. Stress peaks at sharp inner corners still depend on mesh size. Stress is reported at the stated mesh size, from the smoothed shape that is exported.
- 2D plane stress. Out-of-plane loads get a hand check only.
- Pin bearing at every pad with a hole (load pads from the applied force, support pads from the FE reaction) is a hand check using the full strength (bearing allowables are often higher, so it errs on the safe side). Pin shear and edge tear-out are not checked.

Stretch: 3D SIMP for one part (section 15).
Long-term vision (write-up only): broader biologically inspired design.

---

## 2. Tech stack and setup

| Item | Choice |
|---|---|
| Language | Python 3.12 |
| Environment | `uv` (`pyproject.toml` + `uv.lock`) |
| UI | Streamlit |
| FE solve | NumPy + SciPy sparse, **PyPardiso** as the solver (works on Windows). Fall back to `scipy.sparse.linalg.spsolve` if PyPardiso fails to import, with a warning in the UI. |
| Optimizer | Own SIMP code, based on the published 88-line method (Andreassen et al., 2011) |
| LLM | Claude API, model `claude-opus-5-5` for parsing and explanations. Model name set in one config value. |
| Schema checking | Pydantic v2 |
| Geometry | scikit-image (marching squares), shapely (polygon ops), trimesh (extrude, watertight check), ezdxf (DXF), svgwrite or plain SVG text |
| Charts / 3D in app | Plotly (2D charts, Pareto, interactive 3D on demand) |
| Cinematic video renders | PyVista, offline script, MP4 output |
| PDF report | fpdf2 + matplotlib images |
| Slicer for video | PrusaSlicer |
| License | MIT |

Units inside the code are always SI-mm: **mm, N, MPa, g, s**. The LLM converts other units. The check screen shows the original text next to each converted value.

The API key is stored in `.env` (`ANTHROPIC_API_KEY`). `.env` is listed in `.gitignore`. `.env.example` is committed.

Publishing: build a clean, publish-ready repo with a README and MIT license. **Claude never pushes, adds remotes, or opens PRs.** The user publishes at the end, if they choose to.

---

## 3. Repo layout

The code lives at the **git root**, `C:\Users\night\projects\morphic`. This spec lives at `C:\Users\night\projects\morphic\.plans\morphic-spec.md`. The earlier `morphic-interview\` folder is not used for code.

Line endings: `.gitattributes` with `* text=auto eol=lf`, so the repo stores LF and git stops warning about CRLF.

```
morphic/                      (= git root, C:\Users\night\projects\morphic)
  README.md                 # what it is, install, run, validate, reproduce, limits, citations
  LICENSE                   # MIT
  pyproject.toml / uv.lock
  .env.example / .gitignore / .gitattributes
  .plans/morphic-spec.md    # this file
  morphic/
    config.py               # all constants: caps, defaults, model name, tolerances
    problem.py              # Pydantic schema for the problem (section 4)
    parse.py                # LLM: text -> problem JSON, retry, fallback
    sanity.py               # checks on a parsed problem (section 4.4)
    data/
      materials.yaml        # 6 materials, each value with citation (section 5)
      processes.yaml        # FDM / SLS / metal: min wall, citation
    fe.py                   # Q4 plane-stress element, assembly, solve, Gauss-point stresses, nodal stress recovery; node-level loads/supports for tests only
    topopt.py               # SIMP, density filter, Heaviside projection, OC update, snapshots, "paper mode" for the MBB test
    catalog.py              # fill-level sweep per process, level choice, refinement bisection, cold re-run
    evaluate.py             # clean-up, connectivity, re-analysis, stress filter, SF, deflection, out-of-plane checks
    baseline.py             # automatic strut baseline + full-block baseline
    rank.py                 # printer filter, mass ranking, badges, Pareto data, funnel counts
    geometry.py             # contour, smoothing, pad repair, extrude, STL/SVG/DXF, re-check raster
    explain.py              # LLM explanation + number-grounding check + template fallback
    report.py               # 1-page PDF per run
    bundle.py               # run bundle zip + rerun
    cache.py                # results keyed by hash
    cli.py                  # `morphic validate | bench | precompute | rerun | render`
  app/
    streamlit_app.py        # 4-step flow + Validation tab
  render/
    cinematic.py            # PyVista MP4 sequences from recorded snapshots
  examples/
    rc_arm.txt / .json
    drone_arm.txt / .json
    aero_bracket.txt / .json
    cache/                  # precomputed results for the 3 demo parts
  tests/
    test_cantilever.py
    test_mesh_convergence.py
    test_mbb_benchmark.py
    test_scaling_laws.py
    test_hole_stress.py
    test_schema_and_sanity.py
    test_geometry_export.py
    test_explain_grounding.py
    test_bundle_rerun.py
  stretch/
    topopt3d.py
```

---

## 4. Input: from plain English to a checked problem

### 4.1 Coordinate frame

- Origin at the bottom-left corner of the design rectangle. x to the right, y up. Units mm.
- The 2D plane is the plane the part is drawn in. The extrusion (thickness) direction is z.
- The part is assumed to be **printed lying flat** (z is the build direction), at **100% infill**. So in-plane stresses run along the print layers. This is stated on every result.

### 4.2 Problem JSON (Pydantic schema)

Every value carries `source: "user" | "default"` and `original_text` (the phrase it came from, or empty).

```
Problem
  name: str
  design_space: { width_mm, height_mm }
  thickness_mm                                  # extrusion depth
  zones: [ Zone ]
    Zone: { id, kind: "keep_in" | "keep_out",
            shape: "circle" | "rect",
            circle: { cx, cy, r } | rect: { x, y, w, h } }
  pads: [ Pad ]                                 # where supports and loads attach
    Pad: { id, cx, cy, hole_r_mm (>= 0; 0 = solid pad, no hole), ring_r_mm }
                                                # hole is keep_out, ring is keep_in
  supports: [ { pad_id, type: "pin" | "slide_x" | "slide_y" } ]
    pin:     x and y both held
    slide_x: free to move in x, y held (a vertical-only reaction)
    slide_y: free to move in y, x held (a horizontal-only reaction)
  load_cases: [ LoadCase ]  (1..4)
    LoadCase: { id, name, reason,
                loads: [ { pad_id, fx_N, fy_N, fz_N_out_of_plane } ],
                max_deflection_mm }             # limit for this case
  safety_factor
  printer: "desktop_fdm" | "sls_service" | "metal_service" | "any"
  materials: [ material_id ]                    # subset, default all 6
  warnings: [ str ]                             # from parser and sanity checks
```

Loads and supports always act on a pad, spread over the pad's ring. They never act on a single node. A bare "point" in the text becomes a pad with a default ring radius. (Node-level loads and supports exist in `fe.py` for the validation tests only.)

Ranking is always by mass (section 7). There is no `goal` field. Cost is shown as information and never ranks.

### 4.3 Defaults (shown in yellow on the check screen)

| Field | Default |
|---|---|
| safety_factor | 2.0 |
| max_deflection_mm | span / 100, where span = the largest distance from any support pad to any load pad |
| thickness_mm | 6 mm |
| printer | any |
| materials | all 6 |
| pad hole radius | 1.6 mm (M3 clearance); 0 if the text says a solid mount |
| pad ring width | max(2 mm, 2 × process min wall) |

### 4.4 Parsing flow

1. Send the text and the JSON schema to Claude (structured output / tool use).
2. Validate with Pydantic. If it fails, retry **once**, sending the validation error back.
3. Time limit 45 s per call. While waiting, show a spinner that says "Reading your description… if this takes too long, a manual form will open."
4. If it fails again, or the API cannot be reached within the time limit: show the manual form (always available as a tab on the Check step) and offer the 3 saved demo problems.
5. The demo parts load from saved, checked JSON. The video never depends on the network.

### 4.5 Sanity checks (run after parsing and after every edit)

Each failed check gives a plain message on the check screen. Red stops the solve; yellow does not.

| Check | Level | Message idea |
|---|---|---|
| Every pad is fully inside the design space | red | "Pad P2 is outside the design area." |
| At least one support; supports stop all rigid motion (2 translations + rotation). Checked by the rank of the support constraints, and caught again if the stiffness matrix is singular. | red | "The part can still slide or spin. Add a support or change a slide to a pin." |
| Every load case has at least one non-zero in-plane force, or is out-of-plane only | red | "Load case 'Landing' has no force." |
| A keep-out zone covers a pad or a support | red | names the zone and pad |
| Keep-in zones fill > 90% of the design space | red | nothing left to optimize |
| No path of free space from loads to supports (keep-out zones cut it off) | red | "Keep-out zones block every path from load to support." |
| Size < 5 mm or > 2000 mm; force > 1,000,000 N; thickness > shorter side of the design space | yellow | "Check units: did you mean …?" |
| Thickness < span / 20 | yellow | "Thin part: may buckle or twist sideways. The 2D model cannot check this." |
| Any `fz_N_out_of_plane` ≠ 0 | red banner, not blocking | "Out-of-plane load: not part of the optimization. Checked by hand formula only." |
| Process min wall needs smaller elements than the cap allows | yellow | shows the effective min wall that will be used |

---

## 5. Materials and processes

### 5.1 Library (6 materials, one cited datasheet each)

The values below were **starting values**; the cited values now live in `materials.yaml` (research log in `.plans/materials-research.md`). Substitutions accepted 2026-10-20, all flagged in the YAML: Poisson's ratios from cited literature (no maker sheet lists one); PLA and PETG Z strength from Ultimaker datasheet knockdown ratios (Prusa sheets have no Z-loaded value); AlSi10Mg modulus from the archived EOS 05.2014 sheet (current sheets list none); powder costs from third-party reseller prices. Do not use a value without a citation.

| id | Material | Process | Source to cite | E (MPa) approx | Strength used (MPa) approx | Density (g/cm³) approx | Cost $/kg (to source) |
|---|---|---|---|---|---|---|---|
| pla | Prusament PLA | FDM | Prusament PLA technical data sheet | ~2,200 | ~57 (XY) | ~1.24 | maker store price |
| petg | Prusament PETG | FDM | Prusament PETG technical data sheet | ~1,500 | ~47 (XY) | ~1.27 | maker store price |
| pa6cf | Polymaker PA6-CF (Fiberon) | FDM | Polymaker TDS (state the moisture condition the values were measured in) | ~7,000 (XY) | ~100 (XY) | ~1.17 | maker store price |
| pa12 | EOS PA 2200 (PA12) | SLS | EOS material data sheet | ~1,650 | ~48 | ~0.93 | powder or service price, cited |
| alsi10mg | EOS Aluminium AlSi10Mg | Metal (DMLS) | EOS material data sheet (state the heat treatment used) | ~70,000 | ~230 yield (heat treated) | ~2.67 | powder price, cited |
| ti64 | EOS Titanium Ti64 | Metal (DMLS) | EOS material data sheet (state the condition used) | ~110,000 | ~1,000 yield | ~4.41 | powder price, cited |

Per material, `materials.yaml` stores:

```
id, name, process, E_xy_MPa, nu, strength_xy_MPa, strength_z_MPa,
strength_kind ("yield" | "tensile" — use the lower of yield and tensile),
interlayer_shear_MPa (optional, only if a datasheet gives it),
density_g_cm3, cost_usd_per_kg, cost_note,
z_knockdown: { value, source }       # used only when strength_z is missing
citations: { E, nu, strength_xy, strength_z, interlayer_shear, density, cost } -> {title, version/date, page, url}
```

Rules:
- **In-plane checks use XY strength** from printed test bars (the part is printed flat).
- **The out-of-plane bending check also uses XY strength.** When a flat-printed slab bends about an in-plane axis, the tension on its faces runs along x, inside the layers, so XY strength applies.
- **The interlayer shear check uses Z strength / √3** as a conservative stand-in for interlayer shear strength, labeled as a stand-in. If a datasheet gives interlayer shear strength directly, use that and cite it. If the datasheet has no Z value, Z = XY × cited knockdown factor. The factor and its source appear in the results.
- Z strength stays in the library and is shown on the card, with the note that it would govern in-plane stresses if the part were printed standing up.
- Poisson's ratio: from the datasheet, or a cited typical value if the datasheet has none.
- Cost is **material cost per kg only**. Label it "material cost only, not print cost" everywhere it appears. It is shown as information and never used for ranking.
- Safety factor uses von Mises stress against the chosen strength for all materials. State in the limits that this is a simplification for plastics, and that PA6-CF is anisotropic within a layer (section 1.3).

### 5.2 Processes

| id | Process | Min wall (to cite) | Printer filter group |
|---|---|---|---|
| fdm | Desktop FDM, 0.4 mm nozzle | **0.8 mm** (Protolabs Network / Hubs knowledge base, "DFM tips for 3D printed parts with thin walls"; accepted 2026-10-20, no guide stating ~1.2 mm was found) | desktop_fdm |
| sls | SLS PA12 | **0.8 mm** (Hubs, "How to design parts for SLS 3D printing") | sls_service |
| metal | DMLS / LPBF | **0.4 mm** (Hubs, "How to design parts for metal 3D printing") | metal_service |

---

## 6. Solver

### 6.1 Finite element model

- 2D plane stress, 4-node bilinear square elements (Q4), as in the 88-line code. The same element is used for optimization, re-checks, the baseline, and validation.
- Element size `h` per process: `h = max(min_wall / 2.5, size that fits the element cap)`.
  - Element cap: **40,000** for live runs, **150,000** for the precomputed demo parts (or 80,000 if the timing benchmark, step S9, shows 150,000 cannot finish in time; section 6.10).
  - Effective min wall = max(process min wall, 2.5 × h). It is **always shown** on every result, for example "metal: 1.1 mm enforced (process allows 0.5 mm)".
- Pads: hole elements are fixed at density 0 (passive void). Ring elements are fixed at density 1 (passive solid). A pad with `hole_r_mm = 0` is a solid disc of passive solid.
- Supports: all nodes on the inner edge of the pad ring (or, for a solid pad, the nodes nearest the pad center within a radius of one element) are constrained. `pin`: x and y. `slide_x`: y only (free to move in x). `slide_y`: x only (free to move in y).
- Loads: spread evenly over the nodes on the inner edge of the pad ring (or the same central nodes for a solid pad).
- Solve: one factorization per iteration, one back-solve per load case.
- Stresses (evaluation only, never inside the optimizer loop): strain from the B matrices at the 2 × 2 Gauss points of the square element, plane-stress D matrix, then nodal recovery (section 6.8, step 5).
- Reactions (evaluation only): K·u − f at the constrained degrees of freedom, summed per support pad, for the bearing check (section 6.8, step 9).

### 6.2 Topology optimization (one run = one process, one fill level)

- SIMP, penalty p = 3, E_min = 1e-9 × E.
- Density filter with radius `r_min = effective_min_wall / 2` (in elements: at least 1.5).
- Heaviside projection with β continuation. Cold runs: 1 → 2 → 4 → 8 → 16, stepping up every 40 iterations or when the change < 0.01. **Warm-started runs start at β = 4** and continue 4 → 8 → 16 with the same rule.
- Update: optimality criteria (OC), as in the 88-line code, with the volume constraint on the projected (physical) densities.
- Objective with several load cases: sum of compliances, each divided by a fixed normalization value. **The normalization is computed once per process catalog**, at uniform density equal to the first sweep level (60%), and held fixed for every run in that catalog: the sweep, the refinement runs, and the cold re-runs. Each case then counts equally and the weights never drift between runs.
- Constraint: volume fraction = fill level (over the non-passive elements).
- Stop (two rules, either one ends the run; decided 2026-10-20 after S9): at β = 16, (a) max design-variable change < 0.01, or (b) the objective has changed less than 0.1% over 10 consecutive iterations. Limit 300 iterations total (cold) / 100 iterations (warm). A result is marked "not fully converged" only if neither rule is met at the iteration limit. Rule (b) exists because under the Heaviside projection a few boundary elements keep flipping after the objective has settled, so rule (a) alone almost never fires.
- Material inside the catalog uses reference E = 1 and ν = 0.33. Results are scaled per material afterward (section 6.4).
- **Snapshots:** save the physical density field as **uint8 (density × 255), zlib-compressed** (`.npz`). Near-binary fields compress about 10×. Catalog and refinement runs save every 2 iterations. The cold re-run for the animation (section 6.7) saves every iteration. Rough size: about 20–30 kB per snapshot at 150k elements, so tens of MB per demo part.
- **Paper mode** (tests only): density filter, no Heaviside projection, node-level point load and supports, and the exact mesh, volume fraction, penalty, filter radius, move limit, and stop rule of the published MBB run. Used by the MBB benchmark (section 13.3) and nowhere else.

### 6.3 Catalog per process

- Fill levels: 60%, 55%, …, 15% (10 levels), **swept downward**. Each level removes material from the one above, which changes the topology more than adding material would.
- **Live runs:** the 60% level runs cold from uniform density. Each lower level is warm-started from the level above (β from 4, section 6.2).
- **Precomputed demo parts:** every level runs cold from uniform density, so each shape is independent and the side-by-side grid shows real topology differences, not one topology thickened. If the timing benchmark (step S9) shows cold runs at the chosen cap cannot finish in time, fall back in this order: (1) 80k cap with cold runs, (2) the chosen cap with the warm downward sweep. Whichever is used is recorded in the run bundle.
- Early stop: if the 60% level fails every limit for every material, stop the sweep and go to the "no material passes" flow (section 8).
- If every material passes at 15%: continue down to 12%, 10%, 8%. If they still pass, report "limits are loose; part size is set by the minimum wall".
- If the 60% level fails for a material: that material fails (section 8).

### 6.4 Scaling to each material (why the catalog is valid)

For one shape with force loads and the same ν:
- Deflection is proportional to 1 / E. Store `δ × E` for each load case.
- Stress does not depend on E. Store the max von Mises stress for each load case.

So, for material m at a catalog level: deflection = (δE) / E_m, and SF = strength_m / σ_max. Each material's passing range is found with no extra solves.

### 6.5 Choosing the catalog level per material

For each material, every catalog level gets a pass/fail for deflection and for stress, from the scaled values in 6.4.

- Deflection should get better as fill rises. If it does not, mark the catalog "non-monotonic deflection", show it, and treat the odd level as failed.
- Stress need not get better as fill rises. A shape at higher fill can have a sharper inner corner than one at lower fill.

Rule: `v_pick` = the lowest level that passes both limits, such that the next level up also passes both. A level above `v_pick` that fails on stress only, with passing levels on both sides of it, is an **"isolated stress failure"**: it is shown greyed in the funnel with that label and does not move the pick. Two or more adjacent failing levels above `v_pick` are treated as real, and the pick moves above them. The refinement window is [the level just below `v_pick` (fails), `v_pick` (passes)], so both ends have a known, consistent status.

### 6.6 Refinement step (per material)

1. Bisect inside the refinement window, **3 steps** (final resolution about 0.6% fill). Each step is a short run (β from 4, at most 60 iterations) warm-started from the `v_pick` design.
2. **Memoize by (process, fill level).** The shape at a given fill level is the same for every material in a process, so materials that ask for the same bisection level share one run.
3. Quick mode skips refinement and reports the catalog level.
4. If results are not monotonic (noise), keep the smallest fill level that passed and add a note.
5. **Final re-check:** run the chosen shape again with the material's real E and ν. These numbers are the ones reported. If the re-check fails where the scaled estimate passed, step up to the next passing fill (refinement level first, then catalog level) and add a note.

### 6.7 Cold re-run for the animation

After the pick, for the top design of each process (up to 3 per part; in live mode, only the overall winner), re-run that exact fill level **cold from uniform density, with a snapshot every iteration**. These snapshots drive the growth animation in the app (section 11) and the cinematic renders (section 15), so the animation shows a real from-nothing growth and not a short warm-started touch-up.

If the cold re-run's final shape passes the limits, it replaces the sweep's shape as the result for that design, so animation and result match. If it fails (a different local minimum), the sweep's shape stays as the result, and the animation carries a one-line note: "animation shows an independent run at the same fill level."

### 6.8 Evaluation of a chosen design (`evaluate.py`)

1. **Clean-up:** threshold the projected density at 0.5 into solid and void. Remove islands of solid not connected to any pad.
2. **Connectivity:** check that every load pad is connected through solid to at least one support pad. If not, that fill level fails with the message "load pad not connected to a support."
3. **Re-analysis** of the clean shape with the real E and ν, for each load case.
4. **Deflection:** the largest displacement magnitude over the load pad's nodes, per load case. Compared with that case's limit.
5. **Stress: nodal recovery.** Element-center stress sits half an element inside a surface and under-reads edge peaks by roughly 10–15% at the production mesh, which would overstate the safety factor exactly where parts fail. So every reported stress is recovered to the nodes:
   - For each element counted as solid, compute the stress components (σx, σy, τxy) at the 2 × 2 Gauss points, using the **full material E** for every solid element. The strain comes from the FE solution; using full E errs on the high side for a partially filled boundary element.
   - Extrapolate the components from the 4 Gauss points to the 4 corner nodes with the standard Q4 extrapolation: the bilinear fit through the Gauss-point values, evaluated at ξ, η = ±1. The weights are 1 + √3/2, −1/2, 1 − √3/2, −1/2 (nearest Gauss point, the two adjacent ones, the opposite one).
   - At each node, average each component over the **solid elements only** that share the node. "Solid" means density ≥ 0.5 after clean-up, or area fraction ≥ 0.5 in the smoothed re-check; passive ring elements count as solid. Void elements never enter the average, so a boundary node is not pulled toward zero. A node touched by no solid element is masked.
   - Compute von Mises from the averaged components at each node. These nodal values feed the safety factor, the stress maps, the 3D view, and the cinematic coloring.
   - **Reported value:** the max nodal von Mises over solid nodes **outside an exclusion zone around each pad: the pad ring itself plus one ring width beyond it, measured in millimeters.** The zone is in mm, not elements, so it does not change with the element cap. (Pin bearing on the hole wall is not modeled in the FE: the load is spread evenly around the hole edge, so stress inside the ring is not physical. Bearing gets its own hand check, step 9.)
   - **Raw peak:** the max nodal von Mises over all solid nodes, including the exclusion zones, shown in small text next to it, with the note: "Raw peak includes stress spikes at load and support points, which are an artifact of the model. The filtered value is used for the safety factor."
   - **Mesh note (shown in the Limits expander):** stress is reported at the mesh size used, which is printed on the card. Nodal recovery removes most of the edge under-read; the error that remains at the production mesh is measured by the hole check (section 13.4) and shown on the Validation tab. Sharp inner corners have peaks that grow with mesh refinement; the smoothing step (section 9) removes most inner corners, and the final numbers come from the smoothed shape. Stair-stepped boundaries on the grid add local noise, which the smoothed re-check (area fractions) reduces.
6. **Safety factor** = strength / reported max stress (recovered nodal, outside the exclusion zones), worst case over all load cases.
7. **Mass** = solid area × thickness × density.
8. **Out-of-plane hand checks** (only if a load case has `fz`). Treat the part as a beam bending through its thickness, along the straight line from the load pad to the nearest support pad. At 20 sections along the line, take the solid width `w` crossing that section.
   - **Bending:** I = w·t³/12, M = F_z × distance to the load, σ = M·(t/2)/I. Compared with **XY strength** (the face stress runs along the layers). Report the worst SF.
   - **Interlayer shear:** τ = 1.5 · F_z / (w · t) at mid-thickness, which is a layer interface. Compared with **Z strength / √3** (or a cited interlayer shear strength if the datasheet has one). Report the worst SF.
   - Both are labeled "approximate hand check". The card shows pass or fail for each.
9. **Bearing hand check** (every pad with a hole, load pads and support pads, every load case). The pin presses on the hole wall. σ_bearing = F / (d × t), with d = 2 × `hole_r_mm` and t = `thickness_mm`.
   - **Load pads:** F is the in-plane resultant √(fx² + fy²) of the applied force on that pad. Out-of-plane `fz` does not count (it runs along the pin).
   - **Support pads:** F is the in-plane resultant of the FE reaction force on that pad: the reactions at the pad's constrained nodes, recovered as K·u − f on the constrained degrees of freedom and summed per pad. For `pin`, both components; for `slide_x`, only Ry exists; for `slide_y`, only Rx. A pad that is both a load pad and a support pad uses the reaction, which already includes the applied load. As a check, the reactions over all support pads must sum to minus the applied load in every load case (to 1e-6 relative); if not, the solve is flagged.
   - SF_bearing = strength / σ_bearing, worst case over load cases and pads, compared with the target safety factor. It uses the **full XY strength as an approximation; bearing allowables are often higher, so this errs on the safe side**, and the card says so. Solid pads (`hole_r_mm = 0`) show "n/a (solid mount)". Pin shear and edge tear-out are not checked, and the limits say so.
   - Load-pad bearing does not depend on the optimized shape, so a fail there applies to every design in that material at that hole size and thickness. Support-pad bearing can differ by design, because the reactions split between supports by stiffness, so it is evaluated per design from the re-analysis (and finally from the smoothed re-check, step 10). The suggested fix is scaled from the numbers: required d × t = current d × t × (SF_target / SF_bearing) for the failing pad, offered as a larger pin, a thicker part, or a bushing.
10. **Smoothed re-check:** done after geometry export (section 9). Its numbers replace these if they differ.

### 6.9 Baselines (`baseline.py`)

- **Full block:** the whole design space minus keep-out zones and holes, same material. Mass only (no limits check needed).
- **Strut baseline (headline "weight saved"):** straight, constant-width solid struts from each load pad center to its nearest support pad(s), going around keep-out zones (shortest path on the grid if a straight line is blocked). Find the smallest width that meets the same SF and deflection limits, by bisection, with the same FE solver. Same material and thickness. Said plainly on the card: "constant-width straight struts, sized by the same solver to the same limits."
- Weight saved = 1 − mass_optimized / mass_baseline. Show both: "vs. simple strut design: X%" (headline) and "vs. solid block: Y%".
- If no strut width up to the design-space size passes, show "the simple design cannot meet the limits", and only the full-block number.

### 6.10 Compute: measured on this laptop (S9, 2026-10-20)

Measured with `morphic bench` on the aerospace bracket, metal catalog (the largest demo mesh), 12 logical cores, PyPardiso in symmetric positive-definite mode. Raw logs and JSON are in `.plans/bench/`. The planning guesses were ~0.3 s at 40k, ~0.7 s at 80k, ~1.5 s at 150k; the measured cost is about 2.5x higher.

| Elements | Seconds per iteration | Cold level (60%, beta 1 -> 16) | Warm level (100 iterations) |
|---|---|---|---|
| 40,051 (40k cap) | 0.85 | 237 iterations, 3.4 min | 1.4 min |
| 80,199 (80k cap) | 1.62 | 230 iterations, 6.3 min | ~2.7 min (not run) |
| 149,994 (150k cap) | 3.9 | 250 iterations, 16 min | ~6.5 min (not run) |

The cost is close to linear in the element count (about 2.2e-5 s per element per iteration). Note that the cited FDM and SLS min wall of 0.8 mm sets the element size (h = 0.32 mm) for the two arms at every cap, so those catalogs have about 17.7k elements regardless of the cap; only the metal catalogs and the bracket reach the caps.

| Run | Elements per catalog | Iterations per catalog | Measured / estimated time per catalog | Time per part (3 catalogs) |
|---|---|---|---|---|
| Live, 10-level warm sweep, 40k cap | 40,051 | 237 cold + 9 x 100 warm = 1,137 | **16.4 min (measured)**; + refinement ~8 x 60 its (~7 min) + cold re-run (~3.5 min) | ~60 min |
| **Live, 7-level warm sweep, 40k cap (chosen default)** | 40,051 | 237 + 6 x 100 = 837 | ~12 min; ~22 min with refinement and the re-run | **~46 min** (arms: fdm/sls catalogs are 17.7k elements, so ~30 min) |
| Quick mode (1 process, <= 10k elements, no refinement, no re-run) | <= 10,000 | ~837 | ~3 min | ~3 min (one process) |
| Precomputed, cold per level, 150k cap | up to 149,994 | 10 x ~240 = 2,400 + refinement ~480 + re-run ~240 | bracket metal ~2.7 h, bracket fdm/sls (113k) ~2 h each, arm metal (70k) ~1 h, arm fdm/sls ~15 min | bracket ~7 h, each arm ~1.5 h: **~11.5 h for all 3 parts** |
| **Precomputed, cold per level, 80k cap (chosen)** | up to 80,199 | same | bracket (3 x 80k) ~65 min each; arms unchanged | bracket ~3.9 h, each arm ~1.5 h: **~7.5 h for all 3 parts** |

**Decisions recorded by S9:**
- Cached cap = **80,000** with cold runs per level (`config.ELEMENT_CAP_CACHED`, `ELEMENT_CAP_CACHED_SWEEP`). 150k would take about 11.5 h for the three parts, which does not leave a margin for a re-run before the video; 80k fits one overnight window. The two arms get the same meshes at either cap.
- Live mode drops to **7 levels** (`config.FILL_LEVELS_LIVE`), because the 10-level sweep measured 16.4 min per catalog (about 60 min per part).
- The per-iteration cost has optimization headroom (profiling at 4k elements showed the solver at about 40% of the iteration; the rest is sparse indexing, assembly and the OC bisection filter calls). This is step **S9b** (section 16): a live-mode speed-up with a 2x per-iteration target, verified against the benchmark, with results unchanged beyond 1e-6.

---

## 7. Ranking and comparison (`rank.py`)

- **Printer filter:** materials whose process is not in the user's printer group are **greyed out with the reason** ("needs a metal printing service"). They are still computed and shown, but not ranked. "any" allows all.
- **Ranking:** by mass, lowest first, among designs that pass every limit and are allowed by the printer filter. **Cost never ranks.**
- **Information shown, not ranked:** material cost per part = mass × $/kg, labeled "material cost only, not print cost."
- **Badges:** "Lightest" on the top of the ranking (it also gets the highlight border). "Cheapest material" on the passing, allowed design with the lowest material cost, labeled as information.
- **Pareto chart:** mass (x) vs. material cost per part (y). **One point per material: its final pick.** Passing and allowed designs are filled, colored by process. Failed or filtered designs are hollow grey, with a hover reason. A line joins the passing, allowed points that are not dominated. The caption says that cost is material only.
- **Funnel summary:** "N candidate designs evaluated → M met the limits → K printable with your printer → ranked by mass". Isolated stress failures (section 6.5) show as a labeled grey count.

---

## 8. Edge results

| Situation | What Morphic does |
|---|---|
| No material passes | Show each material's best SF and deflection against the target (at 60% fill, or the full block if that is better). Suggest specific fixes from scaling: for in-plane loads, deflection and stress both scale **exactly** 1/t for the same shape, so required t ≈ t × max(SF_target/SF, δ/δ_limit); out-of-plane bending stress scales 1/t² and interlayer shear 1/t. Also suggest a larger design space or a lower safety factor, each with the computed number, e.g. "increase thickness to 9 mm". Never change the problem on its own. |
| All pass at 8% | Report the loose-limits message (section 6.3). Show results at the lowest level. |
| A material passes only with a fill above its catalog's 60% | Treated as fail for that material, with its numbers. |
| Isolated stress failure at a level above the pick | Shown greyed in the funnel with the label; does not move the pick (section 6.5). |
| Load pad not connected to a support after clean-up | That fill level fails with the message; the pick moves up (section 6.8). |
| Smoothed re-check fails a design that passed on the grid | Move to the next passing fill level, re-export, and add a note. |
| Cold re-run shape fails where the sweep shape passed | Keep the sweep shape; animation shows the cold run with a note (section 6.7). |
| Out-of-plane hand check fails | The card shows a red "Out-of-plane: FAIL" line naming the check (bending or interlayer shear). The design is not ranked, but it is still shown. |
| Bearing hand check fails | The card shows a red "Bearing: FAIL" line naming the pad, with the suggested fix (larger pin, thicker part, or a bushing, with the computed number). The design is not ranked, but it is still shown. A load-pad bearing fail does not depend on the shape, so it appears on every design of that material at that hole size and thickness; a support-pad bearing fail can differ by design, because the reactions depend on the shape. |
| Some materials filtered out by printer | Greyed with reason, not ranked. |
| All allowed materials fail, but a filtered one passes | Say so: "Only Ti64 (metal service) meets the limits." |
| FE solve singular | Caught as "part can move freely" (section 4.5). |
| Optimization not converged at the iteration limit (neither stop rule met, section 6.2) | Use the result, mark "not fully converged" on the card. |

---

## 9. Geometry export (`geometry.py`)

1. Contour the filtered density at 0.5 with marching squares (scikit-image).
2. Smooth lightly. The max move of any point is under 0.5 element.
3. Repair pads: union the exact pad ring circles, subtract the exact hole circles and keep-out zones (shapely). Drop slivers smaller than the effective min wall.
4. Extrude to `thickness_mm` with trimesh. Check: `is_watertight`, and volume = area × thickness within 1%. Fail loudly if not.
5. Export: **STL** (mm), **SVG** (outline), **DXF** (ezdxf, outline with holes).
6. **Smoothed re-check:** rasterize the smoothed polygon back onto the analysis grid (area fraction per element, 4×4 supersampling). Run the FE again with **linear scaling, E_e = E × fraction** for boundary elements (no SIMP penalty; this is a geometry check, not an optimization). Recompute stress with nodal recovery (section 6.8, step 5), counting elements with fraction ≥ 0.5 as solid, then SF, deflection, and mass. **These are the numbers shown and exported**, so the numbers match the STL.

---

## 10. Explanation (`explain.py`)

- Input to the LLM: only the results JSON (all numbers, rounded as displayed).
- Output: 3–4 short sentences on why the top design wins and what trade-off it makes (mass vs. material cost vs. which printer is needed).
- **Number check:** extract every number in the text. Each must match a value in the results JSON within display rounding. Units must match.
- If any number fails: retry once with the list of bad numbers. If it fails again: use a template explanation filled from the results.
- Plain English only. No claims beyond the computed data.

---

## 11. User interface (Streamlit)

Top bar: "Morphic" + step indicator. Tabs: **Design** (the 4 steps) and **Validation**.

### Step 1 — Describe
- Large text box.
- Three example buttons: "RC car arm", "Drone arm", "Aerospace bracket". Each fills in the text and loads the saved JSON.
- Printer selector (it can also come from the text; the selector wins if changed).
- "Quick mode" toggle.
- Button: "Read my description".

### Step 2 — Check
- Drawing of the design space: pads (pins as filled triangles, slides as rollers with their free direction drawn, loads as red arrows scaled by size, one color per load case), keep-in zones (solid fill), keep-out zones (hatched), dimensions.
- Editable table of all values. Defaults are highlighted yellow. The original text appears next to each value.
- Sanity messages (red / yellow) above the drawing.
- Manual form tab (always available).
- Shows the effective min wall per process and the estimated run time (from the timing model measured in step S9).
- Button: "Generate designs" (disabled while any red check is open).

### Step 3 — Compare
- Progress during a live run: current process, fill level, iteration, elapsed time, and a live preview of the growing shape.
- **Growth animation** of the top design, built from the cold re-run snapshots (section 6.7), with the caption: "The update rule adds material where strain energy is high and removes it where it is low, the same idea as bone remodeling (Wolff's law)."
- Funnel summary and Pareto chart (section 7).
- **Card grid**, one card per material (up to 6), grouped by process. Each card shows:
  - optimized shape image and stress map. **Stress maps show recovered nodal utilization = σ_vm × SF_target / strength on a shared 0–1 scale**, drawn with smooth shading on the node grid, void nodes masked, with values above 1 in a distinct red. This keeps plastics and metals readable side by side.
  - mass, weight saved (vs. strut, vs. block), fill level
  - SF (filtered) with the raw peak in small text and the one-line note
  - deflection per load case vs. limit
  - out-of-plane checks (if any): bending and interlayer shear, each pass/fail; next to them, the bearing check per pad with a hole (load pads from the applied force, support pads from the FE reaction force; pass/fail, σ_bearing vs. strength, with the note that full strength is used as an approximation and bearing allowables are often higher)
  - effective min wall enforced, and the mesh size used
  - material cost per part (labeled "material cost only")
  - badges; highlight on the winner; grey + reason if failed or filtered
  - a "Sources" expander (datasheet citations, Z strength and knockdown used)
  - a "Limits" expander (the full list from section 1.3 plus the mesh note from 6.8)
- Clicking a card opens an **interactive Plotly 3D view** of the extruded part, colored by utilization, with orbit and zoom. Rendered only when opened.
- Explanation text (section 10).
- Fixed one-line note on every result: "Static check only. Fatigue and impact toughness are not evaluated. Printed flat at 100% infill. See Limits."

### Step 4 — Export
- Per design: STL, SVG, DXF downloads.
- PDF report (1 page per design: problem drawing, material and citations, shape, stress map, numbers, limits).
- Run bundle zip (section 12).

### Validation tab
- Cantilever check table: FE vs. theory, % error, pass/fail at 3%, with the validation mesh stated.
- Mesh refinement plot (error vs. elements through the depth, log scale).
- MBB benchmark: our result image next to the published one, compliance vs. published value.
- Hole stress check: FE edge stress vs. the finite-width stress-concentration formula, with and without nodal recovery, at 8, 16, and 32 elements per hole radius.
- Scaling-law check results.
- "Run all checks" button (runs `morphic validate`).

---

## 12. Reproducibility: run bundle (`bundle.py`)

Zip contents:
- `problem.json` (as solved, after user edits)
- `materials.yaml` + `processes.yaml` with a content hash
- `solver_settings.json` (all constants from `config.py`, element caps, filter, β schedule, tolerances, cold vs. warm sweep used)
- `code_version.txt` (git commit hash; "dirty" if there are uncommitted changes)
- `environment.txt` (Python, NumPy, SciPy, PyPardiso versions, thread count)
- `results.json` (every number shown in the UI)
- `densities.npz` (the final density field of every reported design)
- STL / SVG / DXF, `report.pdf`

`morphic rerun bundle.zip` does two things and prints a diff for each:
1. **Evaluation rerun (strict):** re-evaluates the stored density fields (section 6.8 and 9) and compares every reported number to `results.json`. Pass at 0.5%. This step is deterministic.
2. **Optimization rerun (loose):** re-runs the optimization from scratch. PyPardiso is multithreaded, so sums happen in a different order between runs, and the OC update can amplify tiny differences over hundreds of iterations into a slightly different design. Pass if the same fill level is chosen for each material and the mass is within 2%. The README says this plainly.

Cache key = SHA-256 of (problem JSON + materials hash + solver settings + code version).

---

## 13. Validation suite (target: < 3% error on the beam checks)

All run as `pytest` tests and from the Validation tab. The write-up names the mesh each error was measured at.

1. **Cantilever beam** (L = 100 mm, h = 10 mm, t = 10 mm, solid, tip load spread over the end face, fixed face at x = 0). **Validation mesh: 20 elements through the depth** (h_elem = 0.5 mm, 200 × 20 elements). This is still coarser than the production meshes (about 90 elements through 20 mm at the live cap).
   - Tip deflection vs. beam theory with shear correction: δ = PL³/(3EI) + PL/(κGA), κ = 5/6.
   - Bending stress at mid-span vs. σ = M·c/I with M = P·L/2: the **recovered nodal stress at the top surface node** (section 6.8, step 5) against the surface value. As a check on the element itself, also report the element-center value of the top row against σ = M·y/I at y = c − h_elem/2. (Mid-span avoids the stress spike at the fixed end.)
   - Pass if both errors < 3% at the validation mesh.
   - If Q4 cannot reach 3% at that mesh, report the true error and the finer mesh that reaches it. Do not change the element only for the test.
2. **Mesh refinement:** 2, 4, 8, 16, 32 elements through the depth. Plot the error. It must shrink steadily.
3. **MBB benchmark (paper mode):** run the 88-line paper's MBB case in paper mode (section 6.2): same mesh, volume fraction, penalty, density filter radius, move limit, point load, supports, and stop rule as the published run. Copy the exact call arguments, the published compliance value, and the published figure from Andreassen et al. (2011) into the test during the build. Pass if compliance is within 2% (the paper's value depends on its own iteration count) and the layout matches the figure visually.
4. **Hole stress check (plate with a central hole in tension), with and without nodal recovery.** Plate width W = 10 × hole diameter d (d = 10 mm, W = 100 mm, length 2W), uniform tension at the ends, quarter model with symmetry supports. The hole is represented **the way production represents it**: on the regular grid, as void elements with area fractions at the boundary (section 9.6), not as a body-fitted mesh. The hole center sits on a node and the radius is a whole number of elements, so the top of the hole (θ = 90°, where the stress is highest) lies exactly on a grid line and the edge node there is a true boundary node. Meshes: 8, 16, and 32 elements across the hole radius. The production meshes fall inside this range: a 1.6 mm pad hole has about 8 elements per radius at the live cap and about 14 at the demo cap.
   Target: the finite-width stress concentration factor from Pilkey, *Peterson's Stress Concentration Factors* (circular hole in a finite-width plate under tension; copy the exact formula and its range from the book during the build). At d/W = 0.1 it is within about 1% of the infinite-plate value of 3.0, and the check uses the finite-width value, not 3.0, so it is valid for a finite plate.
   The test reports, at each mesh:
   - **Without recovery:** the element-center von Mises in the edge element at θ = 90° vs. the true edge value K_t·σ_nom. This is the under-read.
   - **With recovery:** the **maximum recovered nodal von Mises over the hole boundary nodes** vs. the true edge value. This is the number production uses for the safety factor. On the grid the top of the hole is a flat ledge, so the peak flattens at θ = 90° and moves a few degrees along the ledge; the value at the θ = 90° node is also reported, with the angle where the maximum sits. (Decided 2026-10-20 after the build showed the 90° node alone reads 7.4% low at 16 elements per radius.)
   - **Element check:** the element-center value vs. the analytical hoop stress at that element's centroid radius (Kirsch field scaled by K_t,finite / 3). This separates the element's own error from the under-read.
   - **Stair-step noise:** the max recovered nodal stress on the hole boundary vs. the value at the θ = 90° node, which shows how much the grid representation moves the peak.
   Pass: the recovered (boundary-maximum) error is smaller than the element-center error at every mesh; the recovered error is < 5% at 16 elements per radius; the element check is < 5% at 8 elements per radius. The recovered error at 8 elements per radius (about 6%, measured during the build) is reported on the Validation tab and in the Limits note as "the remaining stress error at a smooth edge at the live mesh."
5. **Scaling laws:** for a fixed shape, check that doubling E halves deflection and leaves stress unchanged (to 1e-6). This proves the catalog method in section 6.4.
6. **Other tests:** schema and sanity checks, watertight STL and volume, connectivity check, reaction forces summing to the applied load, bearing (load and support pads) and out-of-plane hand checks against hand-computed values, explanation grounding (a planted wrong number must be caught), and bundle rerun (both modes).

---

## 14. Demo parts (approved 2026-10-20)

The values below are approved. Sources marked "to cite" must still be confirmed and cited in `examples/*.json` (`reason` field) and the README before use. Ranking is by mass for all three.

### 14.1 RC car lower suspension arm (1/10 scale buggy, rear)
- View: front view of the arm (vertical plane through the arm), so the main vertical load is in-plane.
- Design space: 90 mm × 20 mm. **Thickness (fore-aft, extruded): 12 mm.** (Thinner than the 20 mm height, so plane stress holds and the thickness sanity check does not fire.)
- Pads: inner hinge pin at (6, 10), **pin**. Shock mount at (55, 16), **slide_x** (vertical reaction only, free in x: a shock only pushes along its axis, which is close to vertical). Outer hub pin at (84, 10), load pad.
- Load case 1 "Hard landing": fy = −80 N at the hub. Reason: about 0.5 kg per corner × 9.81 × ~15 g landing peak (impact factor to cite from RC or vehicle dynamics source). Deflection limit 1.0 mm.
- Load case 2 "Curb hit, sideways": fx = −40 N at the hub. Reason: lateral strike, ~3× the cornering force. Deflection limit 1.0 mm.
- Out-of-plane case 3 "Front impact": fz = 60 N at the hub (hand checks only).
- SF 2.0. Printer: desktop FDM.

### 14.2 5-inch FPV drone arm
- View: side view along the arm, so thrust is in-plane.
- Design space: 120 mm × 15 mm. Thickness (width): 10 mm.
- Pads: two frame bolts at (5, 7.5) and (25, 7.5), both **pin** (clamped between frame plates). Motor mount keep-in pad at (112, 7.5), ring r = 8 mm, `hole_r_mm = 0` (solid), load pad.
- Load case 1 "Full thrust": fy = +32 N. Reason: ~1.6 kgf max static thrust for a 2306 motor on 6S with a 5-inch prop (to cite from a motor thrust table) × 2 for dynamic loads.
- Load case 2 "Hard landing": fy = −50 N. Reason: arm hits the ground first (impact factor to cite).
- Out-of-plane case 3 "Side crash": fz = 30 N (hand checks only).
- Deflection limit 0.5 mm in both cases. Reason: arm stiffness affects motor vibration seen by the flight controller.
- SF 2.0. Printer: desktop FDM.

### 14.3 Aerospace mounting bracket (inspired by the GE jet engine bracket challenge, simplified to 2D)
- Sources (cite both in `examples/aero_bracket.json`, `reason` field, and in the README):
  1. GE / GrabCAD Jet Engine Bracket Challenge page (2013): load cases, pin size, bolt spec, material, min wall, STEP file.
  2. Carter, W. T., et al. (2014), "The GE Aircraft Engine Bracket Challenge: An Experiment in Crowdsourcing for Mechanical Design Concepts": original mass and winner result.
- Verified from both sources: the four load cases, the 0.75 in clevis pin, the four 0.375-24 base bolts (interfaces 2–5), Ti-6Al-4V, min wall 0.050 in (1.27 mm).
- View: side view of the clevis bracket.
- Design space: about 178 mm × 65 mm (**to confirm from the challenge STEP file** during the build). Thickness: 25 mm.
- Pads: the original has four base bolts (interfaces 2–5, 0.375-24 UNF, hole r ≈ 4.8 mm). The 2D side view merges them into **two pad pairs**: each pad in the side view stands for the two bolts that lie behind each other along the viewing axis. Both merged base pads are **pin**. One clevis pin pad at the top (interface 1), load pad; hole diameter 0.75 in (19.05 mm), and the bearing check uses it.
- Load cases (as in the challenge, each separate):
  - "Vertical": 8,000 lbf ≈ 35,600 N upward.
  - "Horizontal": 8,500 lbf ≈ 37,800 N.
  - "Angled 42°": 9,500 lbf ≈ 42,300 N at 42° from vertical.
  - The challenge's torsion load (5,000 lbf·in) is out-of-plane: noted, not checked in 2D.
- Material of the original: Ti-6Al-4V, yield 131 ksi (about 903 MPa) at 75 °F. Minimum wall 0.050 in (1.27 mm). Use these as the reference values on the card; the metal entry in the library (section 5.1) must match or cite its own datasheet.
- SF 1.5 (standard aerospace ultimate factor, FAR 25.303, to cite). Deflection limit: to set from the challenge if given, else span / 200.
- Printer: any.
- **Slice simplification, stated on the card and in the write-up:** this is a 25 mm thick 2D slice that carries the full challenge load. The real bracket is wider at the base (width to confirm from the STEP file), so stresses here are several times those in the real part. The original Ti-6Al-4V bracket weighed about 1.8 kg; the challenge winner was about 80% lighter. Results are **not comparable to the 3D challenge results**, and no mass comparison with the original or the winner is made. The card carries one line: "2D slice of a known benchmark (original ≈ 1.8 kg Ti-6Al-4V, winner ≈ 80% lighter); not comparable to the 3D challenge results."
- Expected use: to show the printer filter, the fail-with-numbers logic, and the metal comparison. **Do not pre-assert which materials pass.** Run it and report what happens. (Quick estimate: PA6-CF at SF 1.5 needs about 21 mm of the 65 mm section in pure tension to carry 35 kN, so a plastic may pass some load cases; that is fine, and plastic failure here would be partly an artifact of the slice.)

---

## 15. Stretch goals (in priority order)

1. **Cinematic renders** (do after the core solver, benchmarks, and results screen work; before any other stretch goal, because it drives the video). `render/cinematic.py`:
   - Replays the winning design's cold re-run snapshots (section 6.7) as an extruded 3D slab.
   - Low densities are translucent and become opaque as they converge. Recovered nodal utilization coloring on the final frames. Soft lighting. Slow camera orbit.
   - One side-by-side sequence of the FDM, SLS, and metal designs growing, from the three cold re-runs.
   - **Every frame comes from real computed data.** No faked or interpolated shapes beyond showing the saved snapshots in order.
   - Output: 1080p MP4, 30 fps.
2. **3D SIMP for one part:** voxel grid about 60 × 30 × 10, drone arm only, PA6-CF only, marching cubes STL. No 3D material comparison. Shown as "the method extends to 3D".
3. **three.js live 3D rendering** in the app (instead of Plotly).

---

## 16. Build order (priority, not timed)

Steps are numbered S1–S17 so they do not collide with the review item numbers (A/B/C/D). Each step is done when its acceptance check passes.

| # | Item | Done when |
|---|---|---|
| S1 | Repo skeleton at the git root, uv, config, README stub, MIT license, `.gitignore`, `.gitattributes` (LF), `.env.example` | `uv run pytest` runs |
| S2 | `fe.py` (Gauss-point stresses, nodal stress recovery) + cantilever, mesh refinement, scaling-law, and hole stress (with/without recovery) tests | Section 13 checks 1, 2, 4, 5 pass |
| S3 | `topopt.py` + paper mode + MBB benchmark | Check 3 passes |
| S4 | Pads (incl. solid pads), passive zones, multiple load cases with fixed normalization, uint8 snapshots | A test problem with 2 load cases converges |
| S5 | `materials.yaml` / `processes.yaml` with every citation filled | Loader rejects any value without a citation |
| S6 | `catalog.py` (downward sweep, cold/warm modes, early stop), level choice rule, refinement with memoization, cold re-run, `evaluate.py` (connectivity, nodal stress recovery, mm exclusion zone, out-of-plane bending + interlayer shear, bearing check for load and support pads from reactions) | Results for a test problem across 3 processes |
| S7 | `baseline.py`, `rank.py` (mass ranking, badges, final-pick Pareto), edge results | Unit tests for each edge case in section 8 |
| S8 | `geometry.py` export + smoothed re-check (linear scaling) | Watertight STL; re-check numbers shown |
| **S9** | **Timing benchmark** (`morphic bench`): one full 10-level catalog run at the **40k cap** with the warm downward sweep, and one at the **150k cap** with cold runs per level, both on this laptop. Records seconds per iteration, iterations per level, and total time per catalog. Then **chooses the cached cap**: 150k if the three demo parts can be precomputed in the time available before the video; else measure at 80k and use it. Also decides whether live mode keeps 10 levels or drops to 7. Updates the table in section 6.10 and the README. **Must finish before S14.** | Section 6.10 table holds measured numbers; the cached cap is written in `config.py` |
| S9b | **Live-mode speed-up**: target 2x per iteration by optimizing sparse indexing, assembly and filter calls, verified against the benchmark (`morphic bench`, same part, process and cap as S9). Results must not change beyond 1e-6 (compliance, densities and evaluation numbers of a reference run before and after). | Benchmark shows the per-iteration time at 40k; section 6.10 updated; the 1e-6 comparison passes |
| S10 | `problem.py`, `parse.py` (45 s limit, spinner, retry, fallback), `sanity.py`, manual form | 3 demo texts parse to the approved JSON |
| S11 | Streamlit 4-step flow + Validation tab (nodal utilization stress maps, Sources and Limits expanders, hole check with/without recovery) | Full run from text to export in the app |
| S12 | `explain.py` with grounding check | Grounding test passes |
| S13 | `report.py`, `bundle.py` (two rerun modes), `cache.py`, CLI | `morphic rerun` passes both modes |
| S14 | Precompute the 3 demo parts at the cap chosen in S9 | Cached results load instantly |
| S15 | Cinematic renders (stretch 1) | MP4s for the video |
| S16 | 3D SIMP (stretch 2), three.js (stretch 3) | Only if time remains |
| S17 | README final: install, run, validate, reproduce (both rerun modes), limits, relation to existing tools, all citations | — |

---

## 17. Submission plan

### 17.1 Video storyboard (max 4:00)

| Time | Shot | What is on screen | Judging criteria |
|---|---|---|---|
| 0:00–0:30 | Hook | A solid block part next to a bone-like Morphic part. Line: nature removes material that does not carry load (Wolff's law). Morphic does this for printed parts, with real materials. | Innovativeness |
| 0:30–1:15 | Describe + check | Type the RC arm (or drone arm) description. The check screen shows supports, loads, and yellow defaults. Fix one value live. | Innovativeness, scalability (plain English input) |
| 1:15–2:00 | Shape grows | Cinematic PyVista render of the winning design growing from nothing (cold re-run), translucent to solid, utilization colors, orbit. Caption on the bone remodeling link. | Innovativeness |
| 2:00–2:30 | Material grid | Funnel, Pareto chart (one point per material), cards. Show that FDM, SLS, and metal give different shapes, and that within a process the fill level changes with material. Side-by-side growth render. Badges, sources expander, explanation. | Materials relevance |
| 2:30–3:05 | Validation | Validation tab: cantilever error under 3% at the stated mesh, mesh plot, MBB benchmark matching the published result, hole stress check showing the error with and without nodal recovery. | Research impact, rigor |
| 3:05–3:35 | Breadth | Quick cuts: RC arm, drone arm, aerospace bracket (greyed cards with reasons, metals compared, the slice note). STL opens in PrusaSlicer; the slicer's estimated weight is compared with Morphic's mass (same density set in the slicer). Run bundle and `morphic rerun`. | Scalability, research impact |
| 3:35–4:00 | Limits + next | Static, 2D, no fatigue, no physical test, commercial tools compare materials too but closed and unsourced. Next: 3D, fatigue, physical tests, broader bio-inspired design. Open-source, reproducible. | Honesty, research impact |

### 17.2 Write-up outline (1 page)

1. **Problem** (2–3 sentences): lightweight printed parts need both shape and material choices; the choice depends on the limits, the material, and the process, and that coupling is usually hidden or unsourced.
2. **What Morphic does** (lead paragraph): plain English → checked problem → cited material data → optimized shape per material and process → verified explanation → reproducible bundle. Open source.
3. **Method:** SIMP topology optimization; lowest passing fill level among stiffness-optimized shapes under SF and deflection limits (say exactly this); per-process catalogs with min-wall filters; catalog scaling plus bisection; smoothed re-check so the numbers match the STL. The physical intuition: the update rule adds material where strain energy is high and removes it where it is low, the same principle as bone remodeling (Huiskes et al. 2000).
4. **Key result:** a figure of the material/process grid for one part, with mass and weight saved vs. the strut baseline.
5. **Validation:** cantilever error, mesh convergence, MBB match, hole stress check (with and without nodal recovery), scaling-law test. Numbers in one small table, with the mesh stated.
6. **Breadth:** three parts, three industries, one line each with the winning material and weight saved. The bracket line carries the slice note.
7. **Limits:** static only, 2D plane stress, no fatigue or impact, no physical test, von Mises with one strength for plastics, PA6-CF in-layer anisotropy, mesh-dependent corner stress (nodal recovery used; the remaining edge error is measured and reported at a stated mesh), printed flat only.
8. **Relation to existing tools** (1–2 sentences): Fusion 360 generative design and nTopology also compare materials and processes. Morphic is open, cited, checked, and reproducible, and its catalog method adds a material at near-zero cost.
9. **Impact and next steps:** reproducible run bundles, open source (MIT), 3D, fatigue, physical tests, broader bio-inspired design.
10. **Citations:** datasheets, Andreassen et al. 2011, Bendsøe & Sigmund 2003, Wolff / Huiskes et al. 2000, Pilkey (Peterson's), GE bracket challenge, FAR 25.303.

### 17.3 Judge Q&A prep

| Question | Short answer |
|---|---|
| Is the shape really material-dependent? | Yes, for a mass goal with stress and deflection limits. Stronger, stiffer materials need less fill, which changes the layout. Each process also has its own min wall. Within one process, the shape at a given fill is the same; we say so, and use it to make the method fast. |
| Fusion 360 and nTopology already compare materials. What is new? | True, and we say so. Morphic is open source, uses only cited datasheet values shown with their sources, takes plain English with a checked problem, explains the result with numbers that are verified, and ships a bundle that reruns to the same answer. Adding a material costs almost nothing. The commercial tools are closed, credit-based, and do not show sources. |
| Why not put stress constraints in the optimizer? | Stress-constrained topology optimization is numerically hard (local stress, singularity at low density) and out of scope for this build. We minimize compliance at each fill level, search the fill level, and check stress after the fact on the smoothed, exported shape. We call the result "the lowest passing fill level among stiffness-optimized shapes," not a minimum-mass optimum. |
| Why trust a 2D model? | It is checked against beam theory (< 3% at the stated mesh), a published benchmark, and a stress-concentration formula. Out-of-plane loads get hand checks (bending and interlayer shear), and thin parts get a warning. 3D is the next step and a stretch demo. |
| Printed parts are weaker than datasheets. | We use printed-specimen values, print flat so in-plane stress runs along the layers, and show every value with its source. Z strength is in the library; it governs interlayer shear under out-of-plane loads, and we check that with a conservative stand-in. If the part were printed standing up, the numbers would not apply, and we say so. |
| PA6-CF is anisotropic. | Yes, even within a layer. The datasheet value is along the bead direction. We state the assumption that perimeters follow the member direction, and list it as a limit. |
| Isn't the stress at corners unreliable? | Yes, so loads are spread over pads, the ring and one ring width around each pad are excluded (a distance in mm, not in elements), the raw peak is shown next to it, and the mesh size is printed on the card. Stresses are recovered to the nodes by Gauss-point extrapolation and averaging, so edge values are not under-read the way element-center values are; the hole check shows the error with and without recovery at a known peak. Numbers come from the smoothed shape that is actually exported. |
| What about the bolt holes? | The FE spreads the pin load evenly around the hole, so hole-wall stress is not physical and is excluded. Each pad with a hole gets a bearing hand check, F / (d × t) against the full strength: load pads use the applied force, support pads use the FE reaction force. This is on the safe side because bearing allowables are often higher. Pin shear and tear-out are not checked, and we say so. |
| Is the weight saving inflated? | The headline compares with a constant-width strut design sized to the same limits by the same solver, not with a solid block. Both numbers are shown. |
| Why does titanium look cheap? | The card shows material cost only, labeled as such, and it never ranks. Ranking is by mass. Print cost for metal is far higher and is out of scope. |
| Could the LLM invent numbers? | It only explains. Every number it writes is checked against computed results; otherwise a template is used. Parsing is always checked by the user on a drawing. |
| What about fatigue and impact? | Out of scope and stated on every result. Demo loads use cited impact factors as static equivalents. |
| How does the bracket compare with the GE challenge results? | It does not. It is a 25 mm 2D slice carrying the full load, so stresses are several times higher than in the real part. We use it to show the filter and fail logic, not to compete with the challenge. |
| How does it scale? | More materials cost almost nothing (catalog scaling). More processes add one catalog each. Run bundles let others reproduce and extend results. |
| Is it really bio-inspired? | The update rule follows the same idea as bone remodeling: add material where strain energy is high, remove it where low (Huiskes et al. 2000). We claim a shared principle, not a copy of biology. |
| Has anything been printed? | No printer was available. We compare the slicer's predicted weight with ours, and list physical testing as next work. |

### 17.4 Thursday Oct 22 timeline

| Time (Eastern) | Milestone |
|---|---|
| by 3:00 PM | Video recorded and edited (≤ 4:00) |
| by 6:00 PM | Write-up final; public post done |
| 6:00–8:00 PM | Buffer |
| 8:00 PM | Deadline |

---

## 18. Open items

1. **Ask in the event Slack** whether the submission form needs a public code link. If yes, the user publishes the repo themselves.
2. **Check the hackathon rules** on code written before the event (deferred by the user until the plan is final).
3. **Verify every material value** against its datasheet and fill in all citations (S5). Record the moisture condition for PA6-CF and the heat treatment for the metals.
4. ~~**Approve the demo part values** in section 14 (now with the 12 mm RC arm, the `slide_x` shock mount, the solid motor pad, and the bracket slice note), and confirm the GE bracket numbers from the challenge page.~~ **Done 2026-10-20:** approved; GE bracket loads, pin, bolts, material, min wall, and masses verified from the challenge page and Carter et al. (2014). Envelope dimensions still to confirm from the STEP file during the build (section 14.3).
5. Confirm the Claude API key and credits work; save the demo parse outputs as fallback JSON.
6. Install PrusaSlicer and confirm the STLs open and slice; set the slicer's filament density to the datasheet value before comparing weights.
7. **Run the timing benchmark (S9) before choosing the cached cap.** If the three demo parts cannot be precomputed at 150k in the time available before the video, fall back to 80k (section 6.3 gives the full fallback order). The precompute (S14) depends on this and takes hours, so it must be the first long job once S9 has run.
8. Copy the exact MBB call arguments and published compliance (Andreassen et al. 2011) and the exact finite-width K_t formula (Pilkey) into the tests (S2, S3).
