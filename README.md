# Morphic

Morphic is a local design and comparison tool for load-bearing printed parts. It runs
2D topology optimization, compares six materials across FDM, SLS and metal printing,
and ranks passing designs by mass. The Streamlit app lets you check the problem on a
drawing, inspect results and sources, and export STL, SVG, DXF, a PDF report and a run
bundle. It is a research prototype with numerical checks, not a validated physical product.

The solver minimizes compliance (maximizes stiffness) at each fill level, then searches
for the lowest passing fill level among those stiffness-optimized shapes. Stress and
deflection are checked after optimization; this is **not** a direct stress-constrained
minimum-mass optimizer or a guarantee of a global optimum.

Within a process catalog, materials share the shape at a given fill level. Material
stiffness and strength change which level passes; process minimum walls change the
catalog. The catalog uses a reference modulus and Poisson's ratio, scales its results,
then rechecks selections with each material's actual properties. Smoothed export geometry
is checked again. Cost is material-only information and never determines the ranking.
Problem dimensions are in mm, forces in N, stiffness/stress in MPa, and mass in g.

## Install

Run commands from the repository root. The project requires Python 3.12; `uv` manages
the environment and locked dependencies. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
first, then:

```powershell
uv sync --locked
```

The recorded integration checks ran on Windows with PyPardiso. The FE implementation
has a SciPy sparse-solver fallback when PyPardiso cannot be imported; comparable runtime
and installation on other platforms have not been established by these reports.

**No API key is required to use the app.** Demo parts, the manual problem form, local
solves, validation, template explanations, geometry exports, PDFs and bundles work
without a key. After dependencies are installed, these operations do not require an LLM
or a network connection. Natural-language and sketch interpretation do require a provider;
if interpretation fails or no key is present, the app opens the manual form.

For optional LLM features, copy `.env.example` to `.env` only if `.env` does not already
exist, then fill in the selected provider's key there. `morphic/config.py` selects
`LLM_PROVIDER` (`gemini` or `claude`) and the model. The adapter reads `GEMINI_API_KEY`
or `ANTHROPIC_API_KEY` from this checkout's `.env`. Keep that file private; it is ignored
by Git and excluded from bundles. Provider calls send the relevant description, sketch
or result payload to that provider; the numerical solver itself stays local.

## Run the app

```powershell
uv run streamlit run app/streamlit_app.py --server.address 127.0.0.1 --server.port 8765 --browser.gatherUsageStats false
```

Open http://127.0.0.1:8765. The workflow is Describe → Check → Compare → Export, with
a separate Validation tab.

- **Without a key:** open one of the three demo cards, or go directly to
  http://127.0.0.1:8765/?step=1 for the blank manual form. Enter the part, pads, supports
  and load cases; resolve blocking checks before generating designs. Compare uses a
  template explanation when the provider is unavailable.
- **With a key:** describe the part in text or upload a PNG, JPG or WEBP sketch. Check
  the interpretation, assumptions and warnings before solving. Sketch parsing has
  automated fixture coverage; a successful live vision interpretation has not yet been
  recorded in the integration reports. HEIC is unsupported.
- **Compare:** inspect shapes, recovered stress, hand checks, material data and limits.
  The optional design agent explores up to five changes, then lets you review its
  recommendation on Check in full mode. Agent trials use quick mode and do not replace
  the current result's exports.
- **Export:** download geometry, results JSON, a PDF or a ZIP bundle. The app's downloaded
  PDF is the same PDF stored inside its bundle.

The three supplied demos are `examples/rc_arm.json`, `examples/drone_arm.json` and
`examples/aero_bracket.json`; saved results are under `examples/cache/`. Unchanged demos
use their saved results. Custom solves can take minutes or longer, depending on mesh,
processes and settings. If demo caches are absent, rebuild them locally (potentially hours):

```powershell
uv run morphic precompute
```

The agent also has a CLI. This example uses only its deterministic fallback proposals
and template recommendation:

```powershell
uv run morphic explore examples/drone_arm.json --no-llm
```

Omit `--no-llm` to use the configured provider. Quick trials use a 10,000-element cap,
warm fill-level sweeps, no refinement and no cold rerun; they need a full solve before
treating the recommendation as a final result. Provider HTTP 429/503 errors are retried
`LLM_HTTP_RETRIES` times (`morphic/config.py`; default 0 for demo use, so a failed call falls
back within seconds; set 4 for 4, 8, 16 and 32 second delays on long agent runs). Design-agent
requests, including retries, start at least four seconds apart across local workers. Template explanations and
deterministic proposals remain fallbacks; numeric grounding does not verify every prose claim.

## Validate

Run the numerical reference checks from the CLI or the app's Validation tab:

```powershell
uv run morphic validate
```

This command prints JSON measurements. It is not a replacement for pytest assertions:
its current exit status indicates execution success, not an aggregate tolerance check.
For the complete automated suite, including slow tests and optional rendering tests:

```powershell
uv sync --locked --extra render
uv run --extra render pytest
```

Without the `render` extra, `uv run pytest` still runs the core suite but can skip tests
requiring PyVista/FFmpeg. Do not use `-m "not slow"` for full validation.

The latest saved full integration run has **194 passed, zero failures, errors or skips**,
including slow tests (`.plans/reports/phase3-merge-g-tests.xml`, 2026-10-21). It covers the
physics checks below, schema/sanity checks, connectivity, force balance, hand checks,
geometry/export checks, LLM grounding/retries, app flows, both bundle modes and rendering.
Live provider success is not established by tests using fake providers.

| Numerical check | Mesh / acceptance |
| --- | --- |
| Cantilever against beam theory with shear correction | 200 × 20 elements, 0.5 mm cells; tip deflection and recovered mid-span surface stress errors below 3% |
| Beam mesh refinement | 2, 4, 8, 16, 32 elements through the depth; errors must decrease |
| MBB paper benchmark | `top88(60,20,0.5,3,2.4,2)`; compliance within 2% of the published 233.71, plus layout-feature assertions [1] |
| Plate with a circular hole | 8, 16, 32 elements per radius; recovered boundary-maximum error below element-center error at each mesh, below 5% at 16/radius; element-centroid check below 5% at 8/radius [3] |
| Modulus scaling | Doubling E halves deflection and leaves stress unchanged for a fixed shape and Poisson's ratio, within 1e-6 |

The hole benchmark retains about 6% recovered edge-stress error at 8 elements per radius.
It uses grid/area-fraction boundaries, not a body-fitted mesh. These are numerical
reference tests, not physical print tests or a bound on error for every possible part.

## Create and reproduce a run bundle

These commands use saved checked results and require no API key:

```powershell
uv run morphic report examples/cache/rc_arm --out output/rc_arm.pdf
uv run morphic bundle examples/cache/rc_arm --out output/rc_arm.zip

# Re-evaluate the stored design; strict final-result comparisons:
uv run morphic rerun output/rc_arm.zip --mode evaluation --out output/evaluation-diff.json

# Repeat optimization from scratch; may take hours at production resolution:
uv run morphic rerun output/rc_arm.zip --mode optimization --out output/optimization-diff.json

# Both modes, also the default when --mode is omitted:
uv run morphic rerun output/rc_arm.zip --mode both --out output/both-diff.json
```

**Evaluation** rebuilds the smoothed geometry from saved final densities and recomputes
FE results, hand checks, baselines, material cost and ranking. Numeric comparisons use
a 0.5% relative tolerance. Historical timings, iteration counts and pre-smoothing checks
are not final measurements and are not required to repeat.

**Optimization** starts fresh catalogs and refinement with the saved settings and material
library. Each material must select the same fill level and have mass within 2%. Parallel
floating-point sums and iterative updates can produce different local solutions;
bitwise-identical shapes are not promised.

`--failures-only` reduces console output; the JSON diff remains complete. Exit codes
are 0 for pass, 1 for comparison failure and 2 for invalid input/execution failure.

The ZIP contains the solved problem, material/process YAML, settings, source revision,
environment description, results, density arrays, available snapshots, geometry, PDF and
a SHA-256 manifest. Checksums detect file changes; the bundle does not contain solver code.
Use the recorded source revision and compare the recorded environment when reproducing
elsewhere. Revision differences are reported. For the historical demo caches, the original
solve environment was not recorded: `environment.txt` describes bundle creation, and the
original solve commit is retained separately from the exporter commit.

Recorded evidence is narrower than a general reproducibility guarantee: production RC-arm
evaluation passed 450 comparisons with zero relative difference; fresh optimization passed
12 fill/mass comparisons on a separate 1,200-element-cap smoke case. A production-size
fresh optimization replay has not been verified (`.plans/reports/bundle.md`). To repeat
the smaller integration exercise:

```powershell
uv run morphic precompute examples/rc_arm.json --cap 1200 --out output/smoke-cache
uv run morphic bundle output/smoke-cache/rc_arm --out output/smoke.zip
uv run morphic rerun output/smoke.zip --mode both --out output/smoke-diff.json
```

## Render saved results

The optional renderer reads existing fields and snapshots; it does not run optimization:

```powershell
uv sync --locked --extra render
uv run --extra render python -m render.cinematic --all
uv run --extra render python -m render.cinematic --part drone_arm --preview
```

Full clips are 1920 × 1080 at 30 fps; outputs go to the ignored `renders/` folder. The
four saved clips cover the three demo winners and an RC-arm process comparison. Growth
starts at the first stored snapshot. When the cold rerun differs from the retained checked
design, a labelled picture dissolve leads to the checked design (`--cut` uses a hard cut).
The dissolve is a presentation transition, not an intermediate solver state. Grid walls
remain stair-stepped, and only the RC demo has all three process reruns for a comparison clip.

## Limits and unresolved evidence

- **Physics:** static, room-temperature, linear-elastic, small-deflection 2D plane stress,
  extruded to constant thickness. No fatigue, dynamic impact/toughness, buckling, thermal,
  fluid, nonlinear or physical-test validation. A load case named “crash” or “landing”
  remains a prescribed static force.
- **Printing/material model:** assumes printing flat at 100% infill. Standing the part up
  changes the applicable strength. Von Mises with one strength is a simplification for
  plastics. PA6-CF has in-layer anisotropy; the model assumes perimeters follow the members.
  Its library values are for dry material; wet values are substantially lower. AlSi10Mg
  uses as-manufactured strength and an older as-built modulus source; Ti64 uses the stated
  heat-treated condition. The library records these choices, not certified allowables.
- **Missing properties:** PLA/PETG Z strength uses labelled ratios from a different maker's
  datasheets. Missing interlayer shear uses Z strength divided by sqrt(3), a labelled
  stand-in. Some Poisson's ratios and powder costs are third-party values; prices are
  recorded observations, not current quotes or complete printing costs.
- **Stress/hand checks:** nodal recovery reduces edge under-read, but sharp-corner peaks
  and grid boundaries remain mesh-dependent. Out-of-plane loads receive approximate hand
  checks only. Hole-pad bearing uses the material strength as an approximation; pin shear
  and edge tear-out are not checked. Minimum-wall filtering and exported geometry do not
  establish complete manufacturability or service safety.
- **Optimization:** passing limits and numerical convergence are separate. The saved agent
  drone winner was 11.77 g in quick mode. Its later full solve retained a 10.490688 g
  PA6-CF design with SF 10.456 and deflection 0.456410 mm (targets 2 and 0.5 mm), but that
  retained refinement was not fully converged. A separate cold rerun converged and failed
  checks. This is a qualified passing result, not proof of a converged optimum
  (`.plans/reports/drone-full-results.json`).
- **Demo assumptions:** RC impact factors and the drone motor thrust table/impact factors
  still lack citations in their input files. Treat them as example assumptions, not measured
  loads. The aerospace envelope and pad locations still need confirmation from the challenge
  STEP file. Its 25 mm slice carries the challenge forces, merges four base bolts into two
  pads, and omits the torsion case. Its results are not comparable to the original 3D challenge.
  The chosen 0.32 mm deflection limit is a default; the SF 1.5 choice is not certification [5–7].
- **LLM/UI evidence:** numeric grounding can reject unsupported numbers, not every misleading
  statement. Earlier agent runs obtained live recommendations, but the later retry acceptance
  run exhausted provider quota and completed with fallbacks. Live vision remains unvalidated.
  Pad, support and Pareto label overlaps and the Streamlit width deprecations were fixed on
  2026-10-22. Typing a demo text verbatim loads its saved, checked parse from
  `examples/parsed/` with no LLM call (spec 4.4 step 5).

## Relation to existing tools

Material and process exploration is established work. Autodesk Fusion supports multiple
[materials](https://help.autodesk.com/cloudhelp/ENU/Fusion-GenerativeDesign/files/GD-SELECT-MATERIAL.htm)
and [manufacturing methods](https://help.autodesk.com/cloudhelp/ENU/Fusion-GenerativeDesign/files/GD-MFG-METHODS.htm)
in generative studies. nTop provides [material models](https://support.ntop.com/hc/en-us/articles/360063644233-How-to-create-a-material)
and [topology optimization with manufacturing constraints](https://www.ntop.com/software/capabilities/topology-optimization/).
Morphic makes no priority or performance-superiority claim against those tools.

Its focus is an inspectable local workflow: a small sourced material library, editable
problem inputs, per-process catalogs, checked explanation numbers and bundles with explicit
replay tolerances. Reusing catalog fields reduces repeated optimization work when evaluating
another material; material-specific checks and refinement still have a cost. The underlying
SIMP method builds on published topology-optimization work [1,2]. The analogy to bone
remodelling is mechanical adaptation to loading [4], not a biological simulation.

## References

### Method, validation and demo provenance

1. Andreassen, E., Clausen, A., Schevenels, M., Lazarov, B. S., and Sigmund, O. (2011).
   *Efficient topology optimization in MATLAB using 88 lines of code.* Structural and
   Multidisciplinary Optimization 43, 1–16. [DOI: 10.1007/s00158-010-0594-7](https://doi.org/10.1007/s00158-010-0594-7).
   MBB reference: section 3.4, Fig. 3 bottom-left; call and compliance are recorded in the test.
2. Bendsøe, M. P., and Sigmund, O. (2003). *Topology Optimization: Theory, Methods, and
   Applications.* Springer. [Author-institution record](https://orbit.dtu.dk/en/publications/topology-optimization-theory-methods-and-applications/).
3. Pilkey, W. D. (1997). *Peterson's Stress Concentration Factors*, 2nd ed., Wiley,
   Chart 4.1 (finite-width plate with circular hole; Howland solution fit).
   [DOI: 10.1002/9780470172674](https://doi.org/10.1002/9780470172674).
   The implementation uses `Ktn = 3 - 3.140r + 3.667r² - 1.527r³`, `r = d/W <= 0.5`,
   then `Ktg = Ktn/(1-r)` for gross-section stress; at `r = 0.1`, `Ktg = 3.02349`.
4. Huiskes, R., Ruimerman, R., van Lenthe, G. H., and Janssen, J. D. (2000).
   *Effects of mechanical forces on maintenance and adaptation of form in trabecular bone.*
   Nature 405, 704–706. [DOI: 10.1038/35015116](https://doi.org/10.1038/35015116).
5. GE / GrabCAD (2013), [Jet Engine Bracket Challenge](https://grabcad.com/challenges/ge-jet-engine-bracket-challenge).
   Source for the bracket challenge, loads and interfaces; Morphic uses a simplified slice.
6. Carter, W. T., et al. (2014). *The GE Aircraft Engine Bracket Challenge: An Experiment
   in Crowdsourcing for Mechanical Design Concepts.* Solid Freeform Fabrication Symposium.
   [Proceedings paper](https://utw10945.utweb.utexas.edu/sites/default/files/2014-110-Carter.pdf).
7. [14 CFR §25.303, Factor of safety](https://www.ecfr.gov/current/title-14/section-25.303).
   Regulatory context for the example's 1.5 factor; it distinguishes limit from ultimate loads.
   Morphic does not implement the full aircraft certification requirements.

### Material and process sources

The following index covers the library's property, cost, knockdown and process references.
Values and source observations are those recorded on 2026-10-20, not newly verified prices.
For the exact field-to-source mapping, page/table, print condition, uncertainty and missing-value
flags, see [materials.yaml](morphic/data/materials.yaml) and [processes.yaml](morphic/data/processes.yaml).
Null entries are missing data, not sourced measurements. Supporting research notes are in
`.plans/materials-research.md`.

#### Prusament PLA

- modulus, XY strength, density: [Technical datasheet Prusament PLA by Prusa Polymers](<https://storage.googleapis.com/prusa3d-content-prod-14e8-wordpress-prusament-prod/2024/05/7ca620c4-prusament-pla-plablend.zip>), Version 1.1, last update 27-07-2022.
- Poisson's ratio: [Gawel, Kuciel, Liber-Knec, Mierzwinski: Examination of Low-Cyclic Fatigue Tests and Poisson's Ratio Depending on the Different Infill Density of Polylactide (PLA) Produced by the FDM Method, Polymers 15(7):1651](<https://pmc.ncbi.nlm.nih.gov/articles/PMC10096656/>), 2023.
- material price: [Prusament PLA material page](<https://prusament.com/materials/pla/>), seen 2026-10-20.
- Z-strength fallback: Ultimaker PLA TDS v2.00 (2022-04-20), p.2: tensile stress at break XY (flat) 45.5 +/- 1.1 MPa vs Z (upright) 33.1 +/- 2.8 MPa, ASTM D3039. Ratio 33.1/45.5 = 0.73. Different PLA brand [Referenced datasheet](<https://um-support-files.ultimaker.com/materials/2.85mm/tds/PLA/Ultimaker-PLA-TDS-v5.00.pdf>).

#### Prusament PETG

- modulus, XY strength, density: [Technical datasheet Prusament PETG by Prusa Polymers](<https://storage.googleapis.com/prusa3d-content-prod-14e8-wordpress-prusament-prod/2023/10/9f8d2165-tds_prusament-petg_n_en.pdf>), Version 1.1, last update 16-02-2022.
- Poisson's ratio: [Guessasma, Belhabib, Nouri: Printability and Tensile Performance of 3D Printed PETG Using FDM, Polymers 11(7):1220](<https://pmc.ncbi.nlm.nih.gov/articles/PMC6680790/>), 2019.
- material price: [Prusament PETG material page](<https://prusament.com/materials/prusament-petg/>), seen 2026-10-20.
- Z-strength fallback: Ultimaker PETG TDS v1.00 (2022-04-29), p.2: tensile stress at break XY (flat) 38.5 +/- 1.4 MPa vs Z (upright) 19.0 +/- 6.4 MPa, ASTM D3039. Ratio 19.0/38.5 = 0.49. Different PETG brand [Referenced datasheet](<https://um-support-files.ultimaker.com/materials/2.85mm/tds/PETG/Ultimaker-PETG-TDS-v1.00.pdf>).

#### Polymaker Fiberon PA6-CF20

- modulus, XY strength, Z strength, density: [Polymaker Fiberon PA6-CF20 Technical Data Sheet](<https://fiberon.polymaker.com/wp-content/uploads/TDS_FIBERON-PA6-CF20_V1.1_EN.pdf>), V1.1.
- Poisson's ratio: [Fisher, Almeida Jr, Falzon, Kazanci: Tension and Compression Properties of 3D-Printed Composites: Print Orientation and Strain Rate Effects, Polymers 15(7):1708](<https://pmc.ncbi.nlm.nih.gov/articles/PMC10096896/>), 2023.
- material price: [Polymaker shop, Fiberon PA6-CF20 product data (Shopify JSON)](<https://shop.polymaker.com/products/fiberon-pa6-cf20.json>), seen 2026-10-20.

#### EOS PA 2200 (PA12, SLS)

- modulus, XY strength, Z strength, density: [EOS PA 2200 Material Data Sheet (web)](<https://www.eos.info/polymer-solutions/polymer-materials/data-sheets/mds-pa-2200>), page shows 'Status as of 20.10.2026 Last changed on 20.10.2026' (appears to be a dynamic date).
- Poisson's ratio: [Faes, Wang, Lava, Moens: Variability in the mechanical properties of laser sintered PA-12 components, Solid Freeform Fabrication Symposium proceedings](<https://utw10945.utweb.utexas.edu/sites/default/files/2015/2015-69-Faes.pdf>), 2015.
- material price: [Additive Plus: PA12 Nylon Powder SLS Material (KSPA12)](<https://additiveplus.com/product/kspa12-nylon-powder/>), seen 2026-10-20.

#### EOS Aluminium AlSi10Mg (DMLS / LPBF)

- modulus: [EOS Aluminium AlSi10Mg Material data sheet (older edition, EOSINT M 280 / EOS M 290 400W)](<https://web.archive.org/web/20181227164805id_/https://gpiprototype.com/pdf/EOS_Aluminium_AlSi10Mg_en.pdf>), AD, WEIL / 05.2014.
- Poisson's ratio: [nTop documentation, sample material 'AlSi10Mg' (values attributed to matweb.com)](<https://docs.ntop.com/Product-Documentation/ntop/block-documentation/blocks/design-analysis/sample-materials/al-si-10mg.md>), seen 2026-10-20.
- XY strength, Z strength, density: [EOS Aluminium AlSi10Mg Material Data Sheet (PDF, archived copy of the EOS file)](<https://web.archive.org/web/20250709102926id_/https://www.eos.info/var/assets/05-datasheet-images/Assets_MDS_Metal/EOS_Aluminium_AlSi10Mg/Material_Datasheet_EOS_Aluminium_AlSi10Mg_EN.pdf?v=6>), archive snapshot 2025-07-09 of the EOS PDF (?v=6); live EOS web MDS shows 'Last changed on 13.10.2026'.
- material price: [Additive Plus product search 'AlSi10Mg'](<https://additiveplus.com/?s=AlSi10Mg&post_type=product>), seen 2026-10-20.

#### EOS Titanium Ti64 (Ti-6Al-4V, DMLS)

- modulus, XY strength, Z strength, density: [EOS Titanium Ti64 Material data sheet, 'EOS Titanium Ti64 400W' edition (bundled in the EOS Ti64 MDS PDF)](<https://www.eos.info/05-datasheet-images/Assets_MDS_Metal/EOS_Titanium_Ti64/Material_DataSheet_EOS_Titanium_Ti64_EOSM290_EOSM300-4_EOSM400_EOSM400-4_en.pdf>), 07.2022.
- Poisson's ratio: [nTop documentation, sample material 'Ti-6Al-4V' (values attributed to matweb.com)](<https://docs.ntop.com/Product-Documentation/ntop/block-documentation/blocks/design-analysis/sample-materials/ti-6al-4v.md>), seen 2026-10-20.
- material price: [Additive Plus: CNPC Ti-6Al-4V Grade 5 Powder 15-53 um LPBF, 10 kg](<https://additiveplus.com/product/cnpc-ti-6al-4v-grade-5-powder-for-metal-3d-printing-15-53-%c2%b5m-lpbf-10-kg-22-lbs/>), seen 2026-10-20.

#### Process wall guides and source cross-checks

- Desktop FDM, 0.4 mm nozzle, 0.8 mm library minimum: [Protolabs Network (Hubs) knowledge base: DFM tips for 3D printed parts with thin walls](<https://www.hubs.com/knowledge-base/dfm-tips-for-3d-printed-parts-with-thin-walls/>), observed 2026-10-20. These are guide values; mesh resolution can require a larger effective wall.
- SLS PA12, 0.8 mm library minimum: [Protolabs Network (Hubs) knowledge base: How to design parts for SLS 3D printing](<https://www.hubs.com/knowledge-base/how-design-parts-sls-3d-printing/>), observed 2026-10-20. These are guide values; mesh resolution can require a larger effective wall.
- DMLS / LPBF metal, 0.4 mm library minimum: [Protolabs Network (Hubs) knowledge base: How to design parts for metal 3D printing](<https://www.hubs.com/knowledge-base/how-design-parts-metal-3d-printing/>), observed 2026-10-20. These are guide values; mesh resolution can require a larger effective wall.

- Cross-checks: [Prusa, Layers and perimeters](https://help.prusa3d.com/en/article/layers-and-perimeters_1748) (no universal fixed minimum); [Protolabs design toolkit](https://protolabs.com/resources/design-for-3d-printing-toolkit) (process/material-specific limits).
- Additional library source copies/checks: [Prusament PLA mirror](https://www.matterhackers.com/r/xFvGl8); [EOS AlSi10Mg M290 / 30 micrometre process sheet](https://www.eos.info/metal-solutions/data-sheets/aluminium/pds-eos-aluminium-alsi10mg-eos-m-290-30um); [AlSi10Mg powder product page](https://additiveplus.com/product/aluminum-powder-alsi10mg-lpbf-compatible-10-kg-22-lbs/).

## License

Morphic code is MIT licensed; see [LICENSE](LICENSE). Referenced publications, datasheets,
dependencies and optional development tools retain their own licenses.
