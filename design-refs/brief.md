# Morphic design brief

Inspiration: the reference images in design-refs. Take the design language only, never a layout, brand, logo or text. The feel is Apple-like: calm, precise, premium, tactile, with vivid color used deliberately.

## Principles
- Cards are the unit: every result, metric and control lives in a rounded card (16-28 px radius) with generous padding. No hard borders or visible gridlines; depth comes from soft shadows, frosted layers and gentle glows.
- One hero number per card: large, confident numerals with a small muted label. Safety factor, deflection and mass are shown as instrument-style readouts (gauges, dials, meters), not table cells.
- Two text tiers: primary text plus a soft grey secondary tone. Small uppercase tracked eyebrow labels for context (e.g. "FDM - PA6-CF").
- Dark stage by default: the Compare step, shape viewer and growth animation live on a deep near-black canvas so stress colors glow. Near-white is used for the Describe and Check steps and the Validation tab.
- Monochrome plus one accent: screens are black, white and grey with a single accent color for the one action or status that matters. Stress gradients and process tints are the only other color, confined to shapes and cards.
- Process identity: FDM, SLS and metal each get a consistent soft gradient tint on their cards.
- Pills for status: rounded chips for deltas and states ("-33% vs strut", "Passes", "Fails: bearing").
- Tactile controls: toggles, sliders and buttons feel physical and softly lit; never default widgets.
- Glass for overlays: frosted translucent panels for viewer controls and floating actions.
- Elegant charts: thin lines, minimal gridlines, highlighted points; the Pareto chart and funnel follow this style.
- Typography: one clean sans-serif (Inter or similar), clear hierarchy, tabular numerals for data.
- Motion: subtle and purposeful; cards fade and rise in, values count up once, nothing loops or bounces.
- One moment of charm per screen: a small tasteful detail (the growth animation, a glowing winner pill, an animated check mark), never clutter.

## Morphic-specific
- The shape is the hero: the optimized part sits large on the dark stage, the stress gradient its only strong color; everything around it stays quiet.
- Growth animation: a smooth scrubber with iteration count beneath the stage; the shape condensing from solid block to bone-like form is the signature moment.
- Material grid: equal cards, one per material, grouped by process tint. The winner gets a subtle spotlight (slightly larger, soft glow, "Lightest" pill). Failed or filtered materials are visibly quieter (greyed, smaller, one-line reason), never hidden.
- Check screen drawing: clean technical illustration, thin lines, pads as soft filled circles, loads as colored arrows (one accent per load case), defaults in a soft amber tint.
- Numbers with meaning: every key number carries its context inline ("5.5 vs 2.0 target", "0.3 mm of 1.0 mm").
- Validation tab: reads like a calm, credible lab report; passes in soft green, errors stated plainly.
- Honesty is part of the design: limits and notes are present and readable, styled as quiet footnotes, not alarms.

## Avoid
- Purple-to-blue gradient headers, neon glows on borders, emoji in headings, rainbow palettes.
- Dense tables as the main presentation.
- The default Streamlit look: unstyled widgets, default fonts, visible gridlines.
- Decorative icons, stock illustrations, fake "AI sparkle" effects.
- Walls of text; every screen reads at a glance, with detail one click away.

## Constraints
- All colors, radii, shadows and fonts are defined once in the central theme file.
- Readability first: numbers and limits legible at a glance; contrast holds on light and dark areas.
- Streamlit: reach this look with custom CSS and HTML components; where Streamlit cannot match it, choose clean and reliable over fragile.
