# Morphic — Build Spec

Status: complete plan, ready to build. Written 2026-10-20.
Event: OSI Hackathon (Open Scientific Intelligence), Oct 21–22, 2026, MIT hub. Solo entry.
Submission: public post with a demo video (max 4:00) and a 1-page write-up. Due **Thu Oct 22, 8:00 PM Eastern**.
Judging: impact on research, innovativeness, scalability, relevance to physical sciences / materials.

---

## 1. What Morphic is

Morphic is a design tool for load-bearing parts.

1. The user describes a part in plain English: where it is held, where loads act, size limits, and goals.
2. Morphic turns the text into a structured problem. The user checks it on a drawing and fixes anything wrong.
3. Morphic runs 2D topology optimization for six real, printable materials across three print processes.
4. For each material, it finds the **lightest shape that still meets the safety factor and deflection limits**.
5. It ranks the results, explains the best choice using only computed numbers, and exports an STL, SVG, DXF, a PDF report, and a reproducible run bundle.

### 1.1 The core claim, stated precisely

In the standard topology optimization setup (stiffest shape for a fixed amount of material), the shape does **not** depend on the material. Stiffness scales every result by the same factor. Morphic uses a different setup, so the material does matter:

- **Goal:** lowest mass.
- **Limits:** safety factor ≥ target (uses material strength) and deflection ≤ limit (uses material stiffness), in every load case.

A stiffer or stronger material meets the limits with less material. Less material gives a different shape: fewer, thinner members. Each process also has its own minimum wall, which sets the optimizer's filter size. So shapes differ by **material** (through the fill level) and by **process** (through the minimum wall).

Honest note for the write-up: within one process, two materials differ only by their fill level. The shape at a given fill level is the same. Say this plainly. It is also why the catalog method (section 6) is correct and fast.

### 1.2 Scope

In scope: static loads, room temperature, linear elastic, small deflections, 2D plane stress, extruded to a constant thickness.
Out of scope: fluids, heat, fatigue, impact toughness, buckling analysis, nonlinear materials, physical testing (no printer available; validation is theoretical).
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

```
morphic/
  README.md                 # what it is, install, run, validate, reproduce, limits, citations
  LICENSE                   # MIT
  pyproject.toml / uv.lock
  .env.example / .gitignore
  morphic/
    config.py               # all constants: caps, defaults, model name, tolerances
    problem.py              # Pydantic schema for the problem (section 4)
    parse.py                # LLM: text -> problem JSON, retry, fallback
    sanity.py               # checks on a parsed problem (section 4.4)
    data/
      materials.yaml        # 6 materials, each value with citation (section 5)
      processes.yaml        # FDM / SLS / metal: min wall, citation
    fe.py                   # Q4 plane-stress element, assembly, solve, stresses
    topopt.py               # SIMP, density filter, Heaviside projection, OC update, snapshots
    catalog.py              # fill-level sweep per process + refinement bisection
    evaluate.py             # clean-up, re-analysis, stress filter, SF, deflection, out-of-plane check
    baseline.py             # automatic strut baseline + full-block baseline
    rank.py                 # goals, printer filter, badges, Pareto data, funnel counts
    geometry.py             # contour, smoothing, pad repair, extrude, STL/SVG/DXF, re-check raster
    explain.py              # LLM explanation + number-grounding check + template fallback
    report.py               # 1-page PDF per run
    bundle.py               # run bundle zip + rerun
    cache.py                # results keyed by hash
    cli.py                  # `morphic validate | precompute | rerun | render`
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
    Pad: { id, cx, cy, hole_r_mm, ring_r_mm }   # hole is keep_out, ring is keep_in
  supports: [ { pad_id, type: "fixed" | "roller_x" | "roller_y" } ]
  load_cases: [ LoadCase ]  (1..4)
    LoadCase: { id, name, reason,
                loads: [ { pad_id, fx_N, fy_N, fz_N_out_of_plane } ],
                max_deflection_mm }             # limit for this case
  safety_factor
  goal: "lightest" | "cheapest" | "balanced"
  printer: "desktop_fdm" | "sls_service" | "metal_service" | "any"
  materials: [ material_id ]                    # subset, default all 6
  warnings: [ str ]                             # from parser and sanity checks
```

Loads and supports always act on a pad, spread over the pad's ring. They never act on a single node. A bare "point" in the text becomes a pad with a default ring radius.

### 4.3 Defaults (shown in yellow on the check screen)

| Field | Default |
|---|---|
| safety_factor | 2.0 |
| max_deflection_mm | span / 100, where span = the largest distance from any support pad to any load pad |
| thickness_mm | 6 mm |
| goal | lightest |
| printer | any |
| materials | all 6 |
| pad hole radius | 1.6 mm (M3 clearance) |
| pad ring width | max(2 mm, 2 × process min wall) |

### 4.4 Parsing flow

1. Send the text and the JSON schema to Claude (structured output / tool use).
2. Validate with Pydantic. If it fails, retry **once**, sending the validation error back.
3. If it fails again, or the API cannot be reached within 20 s: show a manual form (always available as a tab on the Check step) and offer the 3 saved demo problems.
4. The demo parts load from saved, checked JSON. The video never depends on the network.

### 4.5 Sanity checks (run after parsing and after every edit)

Each failed check gives a plain message on the check screen. Red stops the solve; yellow does not.

| Check | Level | Message idea |
|---|---|---|
| Every pad is fully inside the design space | red | "Pad P2 is outside the design area." |
| At least one support; supports stop all rigid motion (2 translations + rotation). Checked by the rank of the support constraints, and caught again if the stiffness matrix is singular. | red | "The part can still slide or spin. Add a support or change a roller to fixed." |
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

The values below are **starting values to check**. During the build, open each datasheet, copy the exact value, and record the document title, version or date, page, and URL in `materials.yaml`. Do not use a value without a citation. If a datasheet has no Z-direction value, use a cited literature ratio and say so.

| id | Material | Process | Source to cite | E (MPa) approx | Strength used (MPa) approx | Density (g/cm³) approx | Cost $/kg (to source) |
|---|---|---|---|---|---|---|---|
| pla | Prusament PLA | FDM | Prusament PLA technical data sheet | ~2,200 | ~57 (XY) | ~1.24 | maker store price |
| petg | Prusament PETG | FDM | Prusament PETG technical data sheet | ~1,500 | ~47 (XY) | ~1.27 | maker store price |
| pa6cf | Polymaker PA6-CF (Fiberon) | FDM | Polymaker TDS | ~7,000 (XY) | ~100 (XY) | ~1.17 | maker store price |
| pa12 | EOS PA 2200 (PA12) | SLS | EOS material data sheet | ~1,650 | ~48 | ~0.93 | powder or service price, cited |
| alsi10mg | EOS Aluminium AlSi10Mg | Metal (DMLS) | EOS material data sheet (state the heat treatment used) | ~70,000 | ~230 yield (heat treated) | ~2.67 | powder price, cited |
| ti64 | EOS Titanium Ti64 | Metal (DMLS) | EOS material data sheet (state the condition used) | ~110,000 | ~1,000 yield | ~4.41 | powder price, cited |

Per material, `materials.yaml` stores:

```
id, name, process, E_xy_MPa, nu, strength_xy_MPa, strength_z_MPa,
strength_kind ("yield" | "tensile" — use the lower of yield and tensile),
density_g_cm3, cost_usd_per_kg, cost_note,
z_knockdown: { value, source }       # used only when strength_z is missing
citations: { E, nu, strength_xy, strength_z, density, cost } -> {title, version/date, page, url}
```

Rules:
- **In-plane checks use XY strength** from printed test bars (the part is printed flat).
- **Out-of-plane checks use Z strength.** If the datasheet has no Z value, Z = XY × cited knockdown factor. The factor and its source appear in the results.
- Poisson's ratio: from the datasheet, or a cited typical value if the datasheet has none.
- Cost is **material cost per kg only**. Label it "material cost only, not print cost" everywhere it appears.
- Safety factor uses von Mises stress against the chosen strength for all materials. State in the limits that this is a simplification for plastics.

### 5.2 Processes

| id | Process | Min wall (to cite) | Printer filter group |
|---|---|---|---|
| fdm | Desktop FDM, 0.4 mm nozzle | ~1.2 mm (cite a slicer or maker design guide) | desktop_fdm |
| sls | SLS PA12 | ~0.8 mm (cite a service bureau design guide) | sls_service |
| metal | DMLS / LPBF | ~0.5 mm (cite a service bureau design guide) | metal_service |

---

## 6. Solver

### 6.1 Finite element model

- 2D plane stress, 4-node bilinear square elements (Q4), as in the 88-line code. The same element is used for optimization, re-checks, the baseline, and validation.
- Element size `h` per process: `h = max(min_wall / 2.5, size that fits the element cap)`.
  - Element cap: **40,000** for live runs, **150,000** for the precomputed demo parts.
  - Effective min wall = max(process min wall, 2.5 × h). It is **always shown** on every result, for example "metal: 1.1 mm enforced (process allows 0.5 mm)".
- Pads: hole elements are fixed at density 0 (passive void). Ring elements are fixed at density 1 (passive solid).
- Supports: all nodes on the inner edge of the pad ring are constrained (fixed: x and y; roller_x: y only, free in x; roller_y: x only, free in y).
- Loads: spread evenly over the nodes on the inner edge of the pad ring.
- Solve: one factorization per iteration, one back-solve per load case.

### 6.2 Topology optimization (per process, per fill level)

- SIMP, penalty p = 3, E_min = 1e-9 × E.
- Density filter with radius `r_min = effective_min_wall / 2` (in elements: at least 1.5).
- Heaviside projection with β continuation: 1 → 2 → 4 → 8 → 16, step up every 40 iterations or when the change < 0.01.
- Update: optimality criteria (OC), as in the 88-line code.
- Objective with several load cases: sum of compliances, each divided by its value at the first iteration (so each case counts equally).
- Constraint: volume fraction = fill level (over the non-passive elements).
- Stop: change < 0.01 at β = 16, or 300 iterations total.
- Material inside the catalog uses reference E = 1 and ν = 0.33. Results are scaled per material afterward (section 6.4).
- **Snapshots:** save the physical density field every 2 iterations as float16, compressed (`.npz`). Used for the growth animation and the cinematic renders.

### 6.3 Catalog per process

- Fill levels: 15%, 20%, …, 60% (10 levels).
- Run the 15% level first from a uniform start. Each next level starts from the previous result (warm start).
- If every material passes at 15%: add 12%, 10%, 8%. If they still pass, report "limits are loose; part size is set by the minimum wall".
- If the 60% level fails for a material: that material fails (section 8).

### 6.4 Scaling to each material (why the catalog is valid)

For one shape with force loads and the same ν:
- Deflection is proportional to 1 / E. Store `δ × E` for each load case.
- Stress does not depend on E. Store the max von Mises stress for each load case.

So, for material m at a catalog level: deflection = (δE) / E_m, and SF = strength_m / σ_max. Each material's passing range is found with no extra solves.

### 6.5 Refinement step (per material)

1. Find the lowest catalog level that passes (`v_hi`) and the level below it that fails (`v_lo`).
2. Bisect between them, 4 steps (final resolution about 0.3% fill). Each step is a short optimization warm-started from the `v_hi` design.
3. If results are not monotonic (noise), keep the smallest fill level that passed and add a note.
4. **Final re-check:** run the chosen shape again with the material's real E and ν. These numbers are the ones reported.

### 6.6 Evaluation of a chosen design (`evaluate.py`)

1. **Clean-up:** threshold the projected density at 0.5 into solid and void. Remove islands of solid not connected to any pad.
2. **Re-analysis** of the clean shape with the real E and ν, for each load case.
3. **Deflection:** the largest displacement magnitude over the load pad's nodes, per load case. Compared with that case's limit.
4. **Stress:** element von Mises at the element center.
   - **Reported value:** the max over solid elements, **leaving out a one-element band around each pad ring**.
   - **Raw peak:** the max over all solid elements, shown in small text next to it, with the note: "Raw peak includes stress spikes at load and support points, which are an artifact of the model. The filtered value is used for the safety factor."
5. **Safety factor** = strength / filtered max stress, worst case over all load cases.
6. **Mass** = solid area × thickness × density.
7. **Out-of-plane hand check** (only if a load case has `fz`): treat the part as a beam bending through its thickness, along the straight line from the load pad to the nearest support pad. At 20 sections along the line, take the solid width w crossing that section and use I = w·t³/12, M = F_z × distance to the load, σ = M·(t/2)/I. Report the worst SF (with Z strength) and pass or fail, labeled "approximate hand check".
8. **Smoothed re-check:** done after geometry export (section 9). Its numbers replace these if they differ.

### 6.7 Baselines (`baseline.py`)

- **Full block:** the whole design space minus keep-out zones and holes, same material. Mass only (no limits check needed).
- **Strut baseline (headline "weight saved"):** straight, constant-width solid struts from each load pad center to its nearest support pad(s), going around keep-out zones (shortest path on the grid if a straight line is blocked). Find the smallest width that meets the same SF and deflection limits, by bisection, with the same FE solver. Same material and thickness.
- Weight saved = 1 − mass_optimized / mass_baseline. Show both: "vs. simple strut design: X%" (headline) and "vs. solid block: Y%".
- If no strut width up to the design-space size passes, show "the simple design cannot meet the limits", and only the full-block number.

### 6.8 Compute estimates (to replace with measured numbers)

These are planning estimates. Task B9 measures the real values on this laptop and updates this table and the README.

| Run | Elements per catalog | Iterations per catalog (cold + 9 warm) | Est. time per catalog | Est. time per part (3 catalogs + refinement + checks) |
|---|---|---|---|---|
| Live | ≤ 40,000 | ~150 + 9 × ~50 | ~2–4 min | ~10–15 min |
| Quick mode (1 process, ≤ 10,000 elements) | ≤ 10,000 | same | < 1 min | < 1 min |
| Precomputed demo parts | ≤ 150,000 | same | ~10–20 min | ~1 hour; ~3 hours for all 3 parts |

---

## 7. Ranking and comparison (`rank.py`)

- **Printer filter:** materials whose process is not in the user's printer group are **greyed out with the reason** ("needs a metal printing service"). They are still computed and shown, but not ranked. "any" allows all.
- **Goal:**
  - lightest: lowest mass.
  - cheapest: lowest mass × $/kg (material cost only).
  - balanced: score = 0.5 × mass / min_mass + 0.5 × cost / min_cost over passing, allowed designs. Lowest wins.
- **Badges:** "Lightest", "Cheapest", "Best balance" on the matching cards. The top design for the chosen goal gets a highlight border.
- **Pareto chart:** mass (x) vs. material cost (y). One point per evaluated (material, fill level) pair. Passing points are colored by process. Failing points are hollow grey. Final picks are large markers. Pareto-optimal picks are joined by a line.
- **Funnel summary:** "N candidate designs evaluated → M met the limits → K printable with your printer → ranked". Shown above the cards.

---

## 8. Edge results

| Situation | What Morphic does |
|---|---|
| No material passes | Show each material's best SF and deflection against the target (at 60% fill, or the full block if that is better). Suggest specific fixes from simple scaling: thickness (deflection and stress scale about 1/t, so required t ≈ t × max(SF_target/SF, δ/δ_limit)), a larger design space, or a lower safety factor, each with the computed number, e.g. "increase thickness to 9 mm". Never change the problem on its own. |
| All pass at 8% | Report the loose-limits message (section 6.3). Show results at the lowest level. |
| A material passes only with a fill above its catalog's 60% | Treated as fail for that material, with its numbers. |
| Smoothed re-check fails a design that passed on the grid | Move to the next passing fill level, re-export, and add a note. |
| Out-of-plane hand check fails | The card shows a red "Out-of-plane: FAIL" line. The design is not ranked, but it is still shown. |
| Some materials filtered out by printer | Greyed with reason, not ranked. |
| All allowed materials fail, but a filtered one passes | Say so: "Only Ti64 (metal service) meets the limits." |
| FE solve singular | Caught as "part can move freely" (section 4.5). |
| Optimization not converged at 300 iterations | Use the result, mark "not fully converged" on the card. |

---

## 9. Geometry export (`geometry.py`)

1. Contour the filtered density at 0.5 with marching squares (scikit-image).
2. Smooth lightly. The max move of any point is under 0.5 element.
3. Repair pads: union the exact pad ring circles, subtract the exact hole circles and keep-out zones (shapely). Drop slivers smaller than the effective min wall.
4. Extrude to `thickness_mm` with trimesh. Check: `is_watertight`, and volume = area × thickness within 1%. Fail loudly if not.
5. Export: **STL** (mm), **SVG** (outline), **DXF** (ezdxf, outline with holes).
6. **Smoothed re-check:** rasterize the smoothed polygon back onto the analysis grid (area fraction per element, 4×4 supersampling). Run the FE again. Recompute stress, SF, deflection, and mass. **These are the numbers shown and exported**, so the numbers match the STL.

---

## 10. Explanation (`explain.py`)

- Input to the LLM: only the results JSON (all numbers, rounded as displayed) and the goal.
- Output: 3–4 short sentences on why the top design wins and what trade-off it makes.
- **Number check:** extract every number in the text. Each must match a value in the results JSON within display rounding. Units must match.
- If any number fails: retry once with the list of bad numbers. If it fails again: use a template explanation filled from the results.
- Plain English only. No claims beyond the computed data.

---

## 11. User interface (Streamlit)

Top bar: "Morphic" + step indicator. Tabs: **Design** (the 4 steps) and **Validation**.

### Step 1 — Describe
- Large text box.
- Three example buttons: "RC car arm", "Drone arm", "Aerospace bracket". Each fills in the text and loads the saved JSON.
- Printer selector and goal selector (they can also come from the text; the selectors win if changed).
- "Quick mode" toggle.
- Button: "Read my description".

### Step 2 — Check
- Drawing of the design space: pads (supports as blue triangles or rollers, loads as red arrows scaled by size, one color per load case), keep-in zones (solid fill), keep-out zones (hatched), dimensions.
- Editable table of all values. Defaults are highlighted yellow. The original text appears next to each value.
- Sanity messages (red / yellow) above the drawing.
- Manual form tab (always available).
- Shows the effective min wall per process and the estimated run time.
- Button: "Generate designs" (disabled while any red check is open).

### Step 3 — Compare
- Progress during a live run: current process, fill level, iteration, elapsed time, and a live preview of the growing shape.
- **Growth animation** of the top design (from snapshots) with the caption: "The update rule adds material where strain energy is high and removes it where it is low, the same idea as bone remodeling (Wolff's law)."
- Funnel summary and Pareto chart.
- **Card grid**, one card per material (up to 6), grouped by process. Each card shows:
  - optimized shape image and stress map (same color scale across cards, scale shown)
  - mass, weight saved (vs. strut, vs. block), fill level
  - SF (filtered) with the raw peak in small text and the one-line note
  - deflection per load case vs. limit
  - out-of-plane check (if any)
  - effective min wall enforced
  - material cost (labeled "material cost only")
  - badges; highlight on the winner; grey + reason if failed or filtered
  - citations link (expands the datasheet sources)
- Clicking a card opens an **interactive Plotly 3D view** of the extruded part, colored by stress, with orbit and zoom. Rendered only when opened.
- Explanation text (section 10).
- Fixed note on every result: "Static check only. Fatigue and impact toughness are not evaluated. Printed flat at 100% infill."

### Step 4 — Export
- Per design: STL, SVG, DXF downloads.
- PDF report (1 page per design: problem drawing, material and citations, shape, stress map, numbers, limits note).
- Run bundle zip (section 12).

### Validation tab
- Cantilever check table: FE vs. theory, % error, pass/fail at 3%.
- Mesh refinement plot (error vs. elements through the depth, log scale).
- MBB benchmark: our result image next to the published one, compliance vs. published value.
- Scaling-law check results.
- "Run all checks" button (runs `morphic validate`).

---

## 12. Reproducibility: run bundle (`bundle.py`)

Zip contents:
- `problem.json` (as solved, after user edits)
- `materials.yaml` + `processes.yaml` with a content hash
- `solver_settings.json` (all constants from `config.py`, element caps, filter, β schedule, tolerances)
- `code_version.txt` (git commit hash; "dirty" if there are uncommitted changes)
- `environment.txt` (Python, NumPy, SciPy, PyPardiso versions)
- `results.json` (every number shown in the UI)
- STL / SVG / DXF, `report.pdf`

`morphic rerun bundle.zip` solves again and prints a diff against `results.json`. Pass if every reported number matches within 0.5%.

Cache key = SHA-256 of (problem JSON + materials hash + solver settings + code version).

---

## 13. Validation suite (target: < 3% error)

All run as `pytest` tests and from the Validation tab.

1. **Cantilever beam** (L = 100 mm, h = 10 mm, t = 10 mm, solid, tip load spread over the end face, fixed face at x = 0).
   - Tip deflection vs. beam theory with shear correction: δ = PL³/(3EI) + PL/(κGA), κ = 5/6.
   - Bending stress at mid-span, top fiber, vs. σ = M·c/I with M = P·L/2. (Mid-span avoids the stress spike at the fixed end.)
   - Pass if both errors < 3% at the production element size used for the validation mesh.
   - If Q4 cannot reach 3% at that size, report the true error and the finer mesh that reaches it. Do not change the element only for the test.
2. **Mesh refinement:** 2, 4, 8, 16, 32 elements through the depth. Plot the error. It must shrink steadily.
3. **MBB benchmark:** run the 88-line paper's default MBB case with the same settings. Copy the published compliance value and figure from Andreassen et al. (2011) into the test during the build. Pass if compliance is within 1% and the layout matches visually.
4. **Scaling laws:** for a fixed shape, check that doubling E halves deflection and leaves stress unchanged (to 1e-6). This proves the catalog method in section 6.4.
5. **Other tests:** schema and sanity checks, watertight STL and volume, explanation grounding (a planted wrong number must be caught), and bundle rerun.

---

## 14. Demo parts (proposed values — user to approve before building)

All values are proposals. Sources marked "to cite" must be confirmed and cited in `examples/*.json` (`reason` field) and the README before use.

### 14.1 RC car lower suspension arm (1/10 scale buggy, rear)
- View: front view of the arm (vertical plane through the arm), so the main vertical load is in-plane.
- Design space: 90 mm × 20 mm. Thickness (fore-aft, extruded): 25 mm.
- Pads: inner hinge pin at (6, 10), fixed. Shock mount at (55, 16), fixed (models the bottomed-out shock). Outer hub pin at (84, 10), load pad.
- Load case 1 "Hard landing": fy = −80 N at the hub. Reason: about 0.5 kg per corner × 9.81 × ~15 g landing peak (impact factor to cite from RC or vehicle dynamics source). Deflection limit 1.0 mm.
- Load case 2 "Curb hit, sideways": fx = −40 N at the hub. Reason: lateral strike, ~3× the cornering force. Deflection limit 1.0 mm.
- Out-of-plane case 3 "Front impact": fz = 60 N at the hub (hand check only).
- SF 2.0. Printer: desktop FDM. Goal: lightest.

### 14.2 5-inch FPV drone arm
- View: side view along the arm, so thrust is in-plane.
- Design space: 120 mm × 15 mm. Thickness (width): 10 mm.
- Pads: two frame bolts at (5, 7.5) and (25, 7.5), both fixed (clamped between frame plates). Motor mount keep-in pad at (112, 7.5), ring r = 8 mm, load pad.
- Load case 1 "Full thrust": fy = +32 N. Reason: ~1.6 kgf max static thrust for a 2306 motor on 6S with a 5-inch prop (to cite from a motor thrust table) × 2 for dynamic loads.
- Load case 2 "Hard landing": fy = −50 N. Reason: arm hits the ground first (impact factor to cite).
- Out-of-plane case 3 "Side crash": fz = 30 N (hand check only).
- Deflection limit 0.5 mm in both cases. Reason: arm stiffness affects motor vibration seen by the flight controller.
- SF 2.0. Printer: desktop FDM. Goal: lightest.

### 14.3 Aerospace mounting bracket (inspired by the GE jet engine bracket challenge, simplified to 2D)
- Source: GE / GrabCAD Jet Engine Bracket Challenge (2013). Copy the exact envelope, bolt positions, and load values from the challenge page; the values below are from memory and must be checked.
- View: side view of the clevis bracket.
- Design space: about 178 mm × 65 mm (to confirm against the challenge drawing). Thickness: 25 mm.
- Pads: two base bolt pads (3/8-inch bolts, hole r ≈ 4.8 mm), fixed. One clevis pin pad at the top, load pad.
- Load cases (as in the challenge, each separate):
  - "Vertical": 8,000 lbf ≈ 35,600 N upward.
  - "Horizontal": 8,500 lbf ≈ 37,800 N.
  - "Angled 42°": 9,500 lbf ≈ 42,300 N at 42° from vertical.
  - The challenge's torsion load (5,000 lbf·in) is out-of-plane: noted, not checked in 2D.
- SF 1.5 (standard aerospace ultimate factor, FAR 25.303, to cite). Deflection limit: to set from the challenge if given, else span / 200.
- Printer: any. Goal: lightest.
- Expected story: plastics fail and are greyed out with numbers. Only metals pass. Ti64 vs. AlSi10Mg shows the material-dependent fill and shape. This also shows the "no material passes" and filter logic working.

---

## 15. Stretch goals (in priority order)

1. **Cinematic renders** (do after the core solver, benchmarks, and results screen work; before any other stretch goal, because it drives the video). `render/cinematic.py`:
   - Replays the winning design's recorded snapshots as an extruded 3D slab.
   - Low densities are translucent and become opaque as they converge. Stress coloring on the final frames. Soft lighting. Slow camera orbit.
   - One side-by-side sequence of the FDM, SLS, and metal designs growing.
   - **Every frame comes from real computed data.** No faked or interpolated shapes beyond showing the saved snapshots in order.
   - Output: 1080p MP4, 30 fps.
2. **3D SIMP for one part:** voxel grid about 60 × 30 × 10, drone arm only, PA6-CF only, marching cubes STL. No 3D material comparison. Shown as "the method extends to 3D".
3. **three.js live 3D rendering** in the app (instead of Plotly).

---

## 16. Build order (priority, not timed)

Each item is done when its acceptance check passes.

| # | Item | Done when |
|---|---|---|
| B1 | Repo skeleton, uv, config, README stub, MIT license, .gitignore, .env.example | `uv run pytest` runs |
| B2 | `fe.py` + cantilever and mesh tests | Section 13 checks 1, 2, 4 pass |
| B3 | `topopt.py` + MBB benchmark | Check 3 passes |
| B4 | Pads, passive zones, multiple load cases, snapshots | A test problem with 2 load cases converges |
| B5 | `materials.yaml` / `processes.yaml` with every citation filled | Loader rejects any value without a citation |
| B6 | `catalog.py`, refinement, `evaluate.py` | Results for a test problem across 3 processes |
| B7 | `baseline.py`, `rank.py`, edge results | Unit tests for each edge case in section 8 |
| B8 | `geometry.py` export + smoothed re-check | Watertight STL; re-check numbers shown |
| B9 | Timing benchmark | Section 6.8 table updated with measured times |
| B10 | `problem.py`, `parse.py`, `sanity.py`, manual form | 3 demo texts parse to the approved JSON |
| B11 | Streamlit 4-step flow + Validation tab | Full run from text to export in the app |
| B12 | `explain.py` with grounding check | Grounding test passes |
| B13 | `report.py`, `bundle.py`, `cache.py`, CLI | `morphic rerun` matches within 0.5% |
| B14 | Precompute the 3 demo parts at the 150k cap | Cached results load instantly |
| B15 | Cinematic renders (stretch 1) | MP4s for the video |
| B16 | 3D SIMP (stretch 2), three.js (stretch 3) | Only if time remains |
| B17 | README final: install, run, validate, reproduce, limits, all citations | — |

---

## 17. Submission plan

### 17.1 Video storyboard (max 4:00)

| Time | Shot | What is on screen | Judging criteria |
|---|---|---|---|
| 0:00–0:30 | Hook | A solid block part next to a bone-like Morphic part. Line: nature removes material that does not carry load (Wolff's law). Morphic does this for printed parts, with real materials. | Innovativeness |
| 0:30–1:15 | Describe + check | Type the RC arm (or drone arm) description. The check screen shows supports, loads, and yellow defaults. Fix one value live. | Innovativeness, scalability (plain English input) |
| 1:15–2:00 | Shape grows | Cinematic PyVista render of the winning design growing, translucent to solid, stress colors, orbit. Caption on the bone remodeling link. | Innovativeness |
| 2:00–2:30 | Material grid | Funnel, Pareto chart, cards. Show that FDM, SLS, and metal give different shapes, and that within a process the fill level changes with material. Side-by-side growth render. Badges and explanation. | Materials relevance |
| 2:30–3:05 | Validation | Validation tab: cantilever error under 3%, mesh plot, MBB benchmark matching the published result. | Research impact, rigor |
| 3:05–3:35 | Breadth | Quick cuts: RC arm, drone arm, aerospace bracket (plastics greyed out, metals pass). STL opens in PrusaSlicer; the slicer's estimated weight is compared with Morphic's mass. Run bundle and `morphic rerun`. | Scalability, research impact |
| 3:35–4:00 | Limits + next | Static, 2D, no fatigue, no physical test. Next: 3D, fatigue, physical tests, broader bio-inspired design. Open-source, reproducible. | Honesty, research impact |

### 17.2 Write-up outline (1 page)

1. **Problem** (2–3 sentences): lightweight printed parts need both shape and material choices; current tools treat them separately.
2. **Method:** plain-English parsing with a check screen; SIMP topology optimization; mass minimization under SF and deflection limits; per-process catalogs with min-wall filters; catalog scaling plus bisection; cited material data; smoothed re-check.
3. **Key result:** a figure of the material/process grid for one part, with mass and weight saved vs. the strut baseline.
4. **Validation:** cantilever error, mesh convergence, MBB match, scaling-law test. Numbers in one small table.
5. **Breadth:** three parts, three industries, one line each with the winning material and weight saved.
6. **Limits:** static only, 2D plane stress, no fatigue or impact, no physical test, simplified failure criterion for plastics.
7. **Impact and next steps:** reproducible run bundles, open source (MIT), 3D, fatigue, physical tests, broader bio-inspired design.
8. **Citations:** datasheets, Andreassen et al. 2011, Bendsøe & Sigmund 2003, Wolff / Huiskes et al. 2000, GE bracket challenge.

### 17.3 Judge Q&A prep

| Question | Short answer |
|---|---|
| Is the shape really material-dependent? | Yes, for a mass goal with stress and deflection limits. Stronger, stiffer materials need less fill, which changes the layout. Each process also has its own min wall. Within one process, the shape at a given fill is the same; we say so, and use it to make the method fast. |
| Why trust a 2D model? | It is checked against beam theory (< 3%) and a published benchmark. Out-of-plane loads get a hand check, and thin parts get a warning. 3D is the next step and a stretch demo. |
| Printed parts are weaker than datasheets. | We use printed-specimen values, print flat so in-plane stress runs along the layers, use Z values with a cited knockdown for out-of-plane loads, and show every value with its source. |
| Isn't the stress at corners unreliable? | Yes, so loads are spread over pads, the peak near pads is filtered, and the raw peak is shown next to it. Numbers come from the smoothed shape that is actually exported. |
| Is the weight saving inflated? | The headline compares with a simple strut design sized to the same limits by the same solver, not with a solid block. Both numbers are shown. |
| Could the LLM invent numbers? | It only explains. Every number it writes is checked against computed results; otherwise a template is used. Parsing is always checked by the user on a drawing. |
| What about fatigue and impact? | Out of scope and stated on every result. Demo loads use cited impact factors as static equivalents. |
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
3. **Verify every material value** against its datasheet and fill in all citations (B5).
4. **Approve the demo part values** in section 14, and confirm the GE bracket numbers from the challenge page.
5. Confirm the Claude API key and credits work; save the demo parse outputs as fallback JSON.
6. Install PrusaSlicer and confirm the STLs open and slice.
7. Run the timing benchmark (B9) and update section 6.8.
