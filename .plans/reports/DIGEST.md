Morphic consolidated digest - 2026-10-21

Scope and current master
This digest consolidates workspace reports, saved test evidence, integration runs and the latest status check.
Master before this documentation commit: ed06259. The working tree was clean.
A, B, C, D and E are merged. F and G are finished and committed locally, but remain unmerged.
The app is running on localhost port 8765; its health endpoint returned 200 during this digest check.
Latest full master suite: 156 passed, zero failures/errors/skips, including slow tests, after merging E.
No tests were rerun for this documentation-only change. Counts below reflect different branch baselines.
All Git work remains local: no pushes, remote changes, pull requests or uploads.
Configured LLM calls remain enabled; credentials are read only from .env and are never included in reports.

Workspace A - emdash/a-app-z7rfi - merged
Commit: 53219e8. Report: .plans/reports/app.md.
Built the Streamlit Describe, Check, Compare and Export steps, plus the Validation tab.
Added shared theme tokens, drawings, editable problem tables, cached demos, live-run progress and estimates.
Compare includes shape/stress maps, growth playback, material cards, Pareto plot, hand checks and a 3D view.
Branch tests: 81 passed, including nine app tests and headless coverage of every step.
Its original agent placeholder and disabled PDF/bundle buttons were subsequently connected by integration.
Remaining issues: overlapping Pareto labels and deprecated Streamlit use_container_width calls.
The branch did not validate a full live solve through the UI; later integration tested the agent and exports.

Workspace B - emdash/b-agent-j5t44 - merged
Commits: f2dc31e and 6a3eb57. Report: .plans/reports/agent.md.
Built the design exploration loop, structured logs, CLI, deterministic fallback and recommendation retry command.
Explores up to five changes to thickness, materials, process or design-space size after the baseline run.
Guards prohibit weakening loads, supports, safety factors or deflection limits; numeric prose is checked.
Tests: 15 agent tests passed; the branch reported its full fast suite passing without a total count.
Earlier branch runs obtained live Gemini proposals and grounded recommendations: quick winners 8.63 g and 8.84 g.
Those are different candidates from integration's later 11.77 g winner; no full-resolution validation is recorded for them.
Quick runs use a 10,000-element cap without refinement/cold reruns and may remain unconverged.
An optional improvement is to stop exploring taller sections once the lowest fill level already passes.
The branch's lack of HTTP retries was fixed later on master; it is not a current limitation.

Workspace C - emdash/c-explain-f2374 - merged
Commit: 07df99d. Report: .plans/reports/explain.md.
Built display-rounded result payloads, unit-aware numeric grounding, one correction attempt and template fallback.
Explanations cover mass ranking, printer eligibility and material-only cost, including missing-cost/no-winner cases.
Tests: 26 explanation tests; 98 passed in the full branch suite, including slow tests.
Limit: numeric grounding does not prove every natural-language claim, and it does not silently convert units.
The module defaults to offline use; the integrated app explicitly enables the configured LLM and retains fallback.

Workspace D - emdash/d-bundle-qz069 - merged
Commit: d437db8. Report: .plans/reports/bundle.md.
Built A4 PDF reports, allowlisted ZIP bundles, SHA-256 manifests, safe extraction, local cache and replay commands.
Strict replay rebuilds smoothed geometry and re-evaluates results; fresh replay repeats optimization from scratch.
Also added recorded-snapshot GIF rendering. Bundles contain data, not executable source or credentials.
Tests: 79 passed, including seven new integration tests. PDFs were rendered and visually inspected.
Production RC strict replay passed 450 comparisons with zero relative difference.
Fresh optimization replay passed all 12 fill/mass comparisons on a separate 1,200-element-cap smoke case.
Limit: production-size fresh optimization reproducibility was not tested; smoke acceptance must not imply it.
Bundle environment metadata describes bundle creation, not the original historical cache-generation environment.

Workspace E - emdash/e-design-fr4sx - merged
Commit: 308e9e1; merge: 3f9190b. Report: .plans/reports/design.md.
Made every screen and native Streamlit control dark, using shared theme tokens.
Describe now has three real cached-shape preview cards, computed headline values and a larger input area.
Check gained instrument readouts, load-case pills and pad/arrow glows; Validation plots use the same palette.
Tests: 156 passed on the branch; 156 passed again after merge, including slow tests, with zero failures/skips.
Remaining visual issues: pad labels can overlap support symbols; Validation tables retain thin cell borders.
Describe's redesign must be retained when integrating F's upload control.

Workspace F - emdash/f-sketch-0l68c - finished, not merged
Commits: fedb7c4 and f01eb92. Worktree is clean, with no uncommitted changes.
Report: .plans/reports/sketch.md in F's worktree, not yet present in master.
Built a theme-token upload control, image preparation, Gemini/Claude vision requests and sketch-to-draft parsing.
Reuses the text parser's schema, defaults and provenance; routes successful readings into the existing Check screen.
Includes a sample sketch, approved problem, fake-provider browser checks and 27 new tests.
Saved full-suite XML confirms 179 passed with zero failures/errors/skips. No live vision call was tested.
Its Claude Code transcript ends with a completion message at 15:27 EDT, not approval/error/usage-limit blockage.
Open: show sketch interpretation warnings on Check; use sketch-specific failure wording; validate live readings.
Sketch attempts allow 90 seconds, versus text's 45; all transport retries can extend the wait to 515 seconds.
HEIC is unsupported. Provider-specific image assumptions/detail settings and Claude text token limits need live validation.
Recommendation: merge the completed branch, preserving E's Describe layout and the existing retry/throttle behavior.

Workspace G - emdash/g-renders-us52v - finished, not merged
Commit: 35185c1. Worktree is clean, with no uncommitted changes.
Report: .plans/reports/renders.md in G's worktree, not yet present in master.
Built an off-screen PyVista renderer, H.264 writer, optional render dependencies and 11 rendering tests.
Reads saved density/utilization fields and cold-run snapshots; never invokes the solver or invents intermediate shapes.
Four finished local clips: RC arm, drone arm, aerospace bracket and RC arm FDM/SLS/metal side-by-side.
All four were read back as 1920 x 1080, 30 fps H.264; durations are about 17-19 seconds.
Tests reported: 21 targeted tests and 162 fast-suite tests passed. The full suite including slow tests was not run.
Its Claude Code transcript ends with a completion message at 15:34 EDT, not approval/error/usage-limit blockage.
Clips live in the worktree's ignored renders directory; Git merges will not copy those MP4s into master.
Limits: stair-stepped FE-grid walls; growth begins at saved iteration 1; only RC has all three process reruns.
Winners' growth runs differ from checked designs; a labelled picture dissolve ends on the checked design.
Recommendation: merge, ensure rendering dependencies are available, run the full suite, and copy videos locally.

Integration and validation history
Merged C, D, B, A in that order: c34f096, 0e1a2c8, 91755ab, 999bcaa.
Full suites after those merges passed: C 98; D 105; B 120; A 129, all without failures or skips.
Resolved shared CLI/README and ignore-file changes while retaining both branches' functionality.
Connected B's agent panel, C's grounded explanations and D's PDF/bundle downloads to A's app.
Review recommended design restores the chosen parameters and translated pads/zones on Check in full mode.
Moved exploration to isolated processes and stopped paused-animation polling/file watching to fix a stalled run.
Integration commits: 7f93ebd, 08d477b; evidence: 9f5b2ff. Final integrated suite: 139 passed, including slow tests.
Browser checks confirmed the downloaded PDF matches the bundle's PDF and every bundle checksum passes.
Added explicit 429/503 retries: four retries after 4, 8, 16 and 32 seconds; hidden SDK retries disabled.
Agent requests share a four-second minimum start interval across worker processes, including retries.
Extended the text parser's wait budget to allow those retries; other provider errors are not retried.
Retry commit: e9f8b57; evidence: 6c7b152. Full suite after these changes: 152 passed, including slow tests.
The later real drone run completed with 30 requests, minimum observed spacing 4.0 seconds, and fallback recommendations.
Gemini reported an exhausted 20-request daily free-tier quota plus occasional 503s; live recommendations remain unconfirmed for that run.
Earlier successful B runs do not establish that the later quota-blocked integration run succeeded with live prose.

Full-resolution drone result
Reconstructed the integration winner: PA6-CF, 120 x 22.5 x 10 mm, 11.77 g in quick mode.
Ran ten cold fill levels, refinement, an independent cold rerun, smoothing and geometry rechecks.
Configured cap: 80,000; actual mesh: 375 x 70 = 26,250 elements; cell size 0.32 mm; enforced wall 0.80 mm.
Retained geometry passes at 10.490688 g and 25.62% fill; in-plane safety factor 10.456 versus target 2.
Worst deflection: 0.456410 mm versus 0.5 mm. All bearing/out-of-plane hand checks pass; geometry is watertight.
Qualification: the retained refinement is not fully converged. The separate cold rerun converged but failed checks.
The pipeline therefore kept the passing refinement; this is not an unqualified convergence/reproducibility result.
Evidence: .plans/reports/drone-full-results.json and retry-and-full-solve-summary.json.
Geometry and arrays: .plans/live_runs/full-resolution/drone_best_pa6cf, ignored by Git.

Remaining integration work and evidence status
Phase 3 is incomplete: merge F, run/fix the full suite, then merge G and run/fix the full suite again.
Keep E's redesign, place F's upload control using theme tokens, and review the shared adapter/state handoff.
Copy G's ignored MP4s locally if they are needed beside master; retain their provenance footnotes.
Then launch the final app, exercise upload-to-Check and exports, and retake the final integrated screenshots.
Current screenshots 1-describe through 5-validation show master with E, without F/G; export checks passed again.
Older screenshots 6-drone-agent, 6-drone-agent-panel and 7-agent-review were not retaken after E.
Phase 3 evidence commit: ed06259. phase3-progress.json predates F/G completion; this digest supersedes that readiness status.
Recover provider quota before validating live vision and a fresh live recommendation; do not disable live calls.
Investigate/refine the unconverged drone candidate before claiming a converged final optimization.
Shared physics limits remain: static linear-elastic 2D plane stress, constant extrusion and approximate hand checks.
Fatigue, impact toughness, buckling and physical print testing are not validated; printed-material assumptions still apply.
No merges or runtime changes were performed while writing this digest.
