# Morphic: plain English, cited materials, checked and reproducible design

*OSI Hackathon, October 21 to 22, 2026. Solo entry. Open source (MIT). Code, demo parts, reports and run bundles are in the repository.*

**Problem.** A light printed part needs two choices at once: its shape and its material. The lightest shape depends on the limits, on the material's strength and stiffness, and on the print process and its minimum wall. In today's tools that coupling is hidden, and the material numbers rarely show a source.

**What Morphic does.** Plain English, cited materials, checked and reproducible design. You describe the part in plain English (where it is held, where the loads act, the size, the limits) and check the parsed problem on a drawing. Morphic then optimizes a shape for six real materials across FDM, SLS and metal printing, using only datasheet values shown with their sources, ranks the passing designs by mass, explains the winner in prose whose every number is verified against the results, and exports STL, SVG, DXF, a PDF report and a run bundle that reruns to the same answer.

**Method.** Our own SIMP topology optimizer, built on the published 88-line method. For each material it finds the lowest passing fill level among stiffness-optimized shapes: it minimizes compliance at a fixed fill level, then searches the fill levels for the lowest one whose shape meets the safety factor and the deflection limit in every load case. One catalog of shapes per process, each with its own minimum-wall filter, serves every material, because for a fixed shape deflection scales with 1/E and stress does not depend on E; a bisection refines the pick. The exported shape is smoothed and re-checked, so the card numbers are the STL's numbers. The update rule adds material where strain energy is high and removes it where it is low, the same principle as bone remodeling (Wolff's law; Huiskes et al. 2000).

**Key result.** RC car suspension arm, 90 × 20 × 12 mm, three load cases, safety factor 2, desktop FDM: Polymaker PA6-CF20 wins at 3.93 g and 10 % fill, 39 % lighter than a constant-width strut design sized by the same solver to the same limits (6.40 g) and 84 % lighter than the solid block. Of 84 candidate designs, 6 met the limits and 3 fit the printer. PLA passes at 4.17 g (cheapest material), PETG at 5.45 g; PA12, AlSi10Mg and Ti-6Al-4V pass but need a service and stay on screen, greyed, with that reason. Figure: the material and process grid, `.plans/reports/screens/3-compare.png`.

**Validation.** Every check uses the same element, assembly and solver as the designs; 201 automated tests pass.

| Check | Mesh | Result |
|---|---|---|
| Cantilever vs beam theory (with shear) | 200 × 20 elements, h = 0.5 mm | tip deflection 0.31 %, recovered surface stress 0.37 %, element-centre stress 0.12 % (limit 3 %) |
| Mesh refinement, tip deflection error | 2, 4, 8, 16, 32 elements through the depth | 11.2 % → 3.2 % → 1.0 % → 0.4 % → 0.2 % |
| MBB benchmark, paper mode | 60 × 20, density filter (Andreassen et al. 2011) | compliance 233.71 vs 233.71 published, within 0.002 %, 144 iterations |
| Plate with a hole vs K_t = 3.02 (Pilkey, Chart 4.1) | 8 / 16 / 32 elements per radius | element-centre error 15.7 / 10.2 / 5.6 %; recovered nodal 6.0 / 1.2 / 2.3 % |
| Scaling law, E doubled on a fixed shape | same cantilever model | deflection ratio 0.5000, stress ratio 1.0000, errors below 3e-13 |

**Breadth.** Hobby, RC car arm: PA6-CF, 3.93 g, 39 % lighter than the strut. UAV, 5-inch FPV drone arm: PA6-CF, 13.3 g at 46 % fill, 39 % lighter than the strut; PLA and PETG fail the 0.5 mm deflection limit. The design agent then proposed a taller section (120 × 22.5 mm), and the full-resolution solve passes at 10.49 g with safety factor 10.5 and 0.46 mm worst deflection. That shape passes every check, but its optimization stopped before convergence and the independent cold rerun did not pass, so it is reported as qualified, not as a converged result. Aerospace, GE jet engine bracket as a 2D slice: AlSi10Mg, 111 g at 13 % fill, 55 % lighter than the strut; Ti-6Al-4V passes at 174 g, every polymer fails on bearing and stress. The 25 mm slice carries the full challenge load, so its stresses are several times those in the real bracket and it is not comparable to the 3D challenge results.

**Limits.** Static loads only; 2D plane stress with an extruded thickness; no fatigue, impact or buckling; no physical test. Von Mises with one strength value is a simplification for plastics, and PA6-CF is anisotropic within a layer (the XY value runs along the bead; perimeters are assumed to follow the members). Corner stress is mesh-dependent: stresses are recovered to the nodes, and the remaining edge error at the live mesh (6.0 % at 8 elements per radius) is measured and stated on every card. Parts are assumed printed flat at 100 % infill.

**Relation to existing tools.** Fusion 360 generative design and nTopology also compare materials and processes. Morphic is open, every material value carries its source, every result is checked and explained with verified numbers, and a run bundle reproduces it; the catalog method adds a material at near-zero cost.

**Impact and next steps.** Run bundles with checksums reproduce a result (a strict replay of the RC arm matched 450 values with zero difference). MIT license. Next: 3D, fatigue, physical tests, broader bio-inspired design rules.

**Citations.** Datasheets: Prusament PLA and PETG TDS v1.1; Polymaker Fiberon PA6-CF20 TDS v1.1; EOS PA 2200, AlSi10Mg and Ti64 material data sheets; Protolabs (Hubs) minimum-wall guides. Andreassen et al. (2011), 88-line topology optimization code. Bendsøe and Sigmund (2003), Topology Optimization. Wolff (1892); Huiskes et al. (2000), Nature 405. Pilkey, Peterson's Stress Concentration Factors, Chart 4.1. GE / GrabCAD Jet Engine Bracket Challenge (2013). FAR 25.303 (factor of safety 1.5).
