"""Ranking and comparison (spec section 7) and the edge results (section 8).

Ranking is by mass among designs that pass every limit and are allowed by the
printer filter. Cost never ranks. Filtered or failed designs are shown greyed with
a reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import evaluate
from .baseline import BaselineResult
from .catalog import Design, RunResult

PRINTER_LABEL = {"desktop_fdm": "a desktop FDM printer", "sls_service": "an SLS printing service",
                 "metal_service": "a metal printing service"}
PROCESS_WORD = {"desktop_fdm": "FDM", "sls_service": "SLS", "metal_service": "metal"}


@dataclass
class Card:
    design: Design
    state: str  # ranked | failed | filtered
    rank: int | None
    reason: str
    badges: list[str]
    material_cost_usd: float | None
    weight_saved_vs_strut: float | None
    weight_saved_vs_block: float | None
    baseline: BaselineResult | None


@dataclass
class ParetoPoint:
    material_id: str
    process_id: str
    mass_g: float | None
    cost_usd: float | None
    state: str
    reason: str
    on_front: bool = False


@dataclass
class RankResult:
    cards: list[Card]
    pareto: list[ParetoPoint]
    funnel: dict
    winner: Design | None
    messages: list[str] = field(default_factory=list)
    caption_cost: str = "material cost only, not print cost"


def material_cost(design: Design) -> float | None:
    if design.checks is None or design.material.cost_per_kg is None:
        return None
    return design.checks.mass_g / 1000.0 * design.material.cost_per_kg


def fail_reason(design: Design) -> str:
    c = design.checks
    parts: list[str] = []
    if c is not None:
        oop = [h for h in c.out_of_plane if not h.passed]
        if oop:
            parts.append("Out-of-plane: FAIL (" + ", ".join(h.name for h in oop) + ")")
        brg = [h for h in c.bearing if not h.passed]
        if brg:
            parts.append("Bearing: FAIL (" + "; ".join(f"{h.name}: {h.suggestion}" if h.suggestion else h.name
                                                       for h in brg) + ")")
        others = [r for r in c.fail_reasons if not r.startswith(("out-of-plane", "interlayer", "bearing"))]
        parts += others
    if not parts:
        parts = design.reasons or [design.pick.reason or "fails the limits"]
    return "; ".join(parts)


def rank_designs(res: RunResult, baselines: dict[str, BaselineResult] | None = None) -> RankResult:
    baselines = baselines or {}
    problem = res.problem
    cards: list[Card] = []
    for d in res.designs:
        if not d.printer_allowed:
            state = "filtered"
            reason = f"needs {PRINTER_LABEL.get(d.process.printer_group, d.process.name)}"
        elif d.status == "pass":
            state, reason = "ranked", ""
        else:
            state, reason = "failed", fail_reason(d)
        b = baselines.get(d.material.id)
        mass = d.checks.mass_g if d.checks else None
        cards.append(Card(design=d, state=state, rank=None, reason=reason, badges=[],
                          material_cost_usd=material_cost(d),
                          weight_saved_vs_strut=(b.weight_saved_vs_strut(mass) if (b and mass is not None) else None),
                          weight_saved_vs_block=(b.weight_saved_vs_block(mass) if (b and mass is not None) else None),
                          baseline=b))

    ranked = sorted([c for c in cards if c.state == "ranked"], key=lambda c: c.design.checks.mass_g)
    for i, c in enumerate(ranked, start=1):
        c.rank = i
    if ranked:
        ranked[0].badges.append("Lightest")
        priced = [c for c in ranked if c.material_cost_usd is not None]
        if priced:
            min(priced, key=lambda c: c.material_cost_usd).badges.append("Cheapest material")
    cards.sort(key=lambda c: (c.state != "ranked", c.rank or 0, c.design.process.id, c.design.material.id))

    # Pareto: one point per material (its final pick)
    pareto: list[ParetoPoint] = []
    for c in cards:
        pareto.append(ParetoPoint(material_id=c.design.material.id, process_id=c.design.process.id,
                                  mass_g=c.design.checks.mass_g if c.design.checks else None,
                                  cost_usd=c.material_cost_usd, state=c.state, reason=c.reason))
    front = [p for p in pareto if p.state == "ranked" and p.mass_g is not None and p.cost_usd is not None]
    for p in front:
        dominated = any((q is not p) and q.mass_g <= p.mass_g and q.cost_usd <= p.cost_usd
                        and (q.mass_g < p.mass_g or q.cost_usd < p.cost_usd) for q in front)
        p.on_front = not dominated

    # Funnel
    candidates = sum(len(d.pick.levels) + len(d.pick.refinement) for d in res.designs)
    met = sum(1 for d in res.designs if d.status == "pass")
    printable = sum(1 for c in cards if c.state == "ranked")
    isolated = sum(1 for d in res.designs for s in d.pick.levels if s.label == "isolated stress failure")
    funnel = {"candidates": candidates, "met_limits": met, "printable": printable, "ranked": len(ranked),
              "isolated_stress_failures": isolated,
              "text": f"{candidates} candidate designs evaluated -> {met} met the limits -> "
                      f"{printable} printable with your printer -> ranked by mass"}

    messages = edge_messages(res, cards)
    return RankResult(cards=cards, pareto=pareto, funnel=funnel, winner=ranked[0].design if ranked else None,
                      messages=messages)


def edge_messages(res: RunResult, cards: list[Card]) -> list[str]:
    """Spec section 8 texts."""
    problem = res.problem
    msgs: list[str] = []
    passing_any = [c for c in cards if c.design.status == "pass"]
    ranked = [c for c in cards if c.state == "ranked"]
    if not passing_any:
        msgs.append("No material passes the limits.")
        for c in cards:
            d = c.design
            ch = d.checks
            if ch is None:
                continue
            t_new = evaluate.thickness_suggestion(problem.thickness_mm, ch.sf, ch.sf_target, ch.deflection_mm,
                                                  ch.deflection_limit_mm)
            worst = int(np.argmax(ch.deflection_mm / ch.deflection_limit_mm))
            fill_txt = f"{d.fill:.0%} fill" if d.fill is not None else "the full block"
            msgs.append(
                f"{d.material.id}: best SF {ch.sf:.2f} vs {ch.sf_target:g} and deflection "
                f"{ch.deflection_mm[worst]:.3f} mm vs {ch.deflection_limit_mm[worst]:g} mm at {fill_txt}. "
                f"Fixes from scaling: increase thickness to {t_new:.1f} mm (in-plane stress and deflection both "
                f"scale 1/t), or a larger design space, or a safety factor at or below {ch.sf:.2f}.")
    elif not ranked:
        names = [f"{c.design.material.id} ({PROCESS_WORD.get(c.design.process.printer_group, c.design.process.id)} service)"
                 for c in passing_any]
        msgs.append("Only " + ", ".join(names) + " meets the limits. Your printer selection filters it out.")
    if any(c.design.pick.status == "loose" for c in cards):
        msgs.append("Limits are loose; part size is set by the minimum wall. Results shown at the lowest fill level.")
    for c in cards:
        if c.design.rerun and not c.design.rerun.get("replaced", True):
            msgs.append(f"{c.design.material.id}: {c.design.rerun.get('note', '')}")
    return msgs
