"""Manual form logic (spec 4.4 step 4, always available on the Check step).

The form is a plain dict of scalars and row tables, so the Streamlit app (S11) can
show it with data editors. `form_to_problem` validates it and returns plain-English
errors instead of raising, so the form can stay open while the user fixes values.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from pydantic import ValidationError

from . import config
from .problem import MATERIAL_IDS, Problem, Provenance, problem_from_dict, problem_to_dict

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
DEMOS = {"RC car arm": "rc_arm", "Drone arm": "drone_arm", "Aerospace bracket": "aero_bracket"}


def blank_form() -> dict:
    """An empty form with the spec 4.3 defaults filled in (marked default)."""
    return {
        "name": "",
        "width_mm": None,
        "height_mm": None,
        "thickness_mm": config.DEFAULT_THICKNESS_MM,
        "safety_factor": config.DEFAULT_SAFETY_FACTOR,
        "printer": config.DEFAULT_PRINTER,
        "materials": list(MATERIAL_IDS),
        "pads": [],  # rows: id, cx, cy, hole_r_mm, ring_r_mm
        "supports": [],  # rows: pad_id, type
        "zones": [],  # rows: id, kind, shape, cx, cy, r, x, y, w, h
        "load_cases": [],  # rows: id, name, reason, max_deflection_mm
        "loads": [],  # rows: case_id, pad_id, fx_N, fy_N, fz_N_out_of_plane
        "defaults": ["thickness_mm", "safety_factor", "printer", "materials"],
    }


def problem_to_form(problem: Problem) -> dict:
    f = blank_form()
    f.update(name=problem.name, width_mm=problem.design_space.width_mm, height_mm=problem.design_space.height_mm,
             thickness_mm=problem.thickness_mm, safety_factor=problem.safety_factor, printer=problem.printer,
             materials=list(problem.materials))
    f["pads"] = [p.model_dump() for p in problem.pads]
    f["supports"] = [s.model_dump() for s in problem.supports]
    f["zones"] = []
    for z in problem.zones:
        row = {"id": z.id, "kind": z.kind, "shape": z.shape}
        row.update(z.circle.model_dump() if z.circle else {})
        row.update(z.rect.model_dump() if z.rect else {})
        f["zones"].append(row)
    f["load_cases"] = [{"id": lc.id, "name": lc.name, "reason": lc.reason,
                        "max_deflection_mm": lc.max_deflection_mm} for lc in problem.load_cases]
    f["loads"] = [{"case_id": lc.id, **ld.model_dump()} for lc in problem.load_cases for ld in lc.loads]
    f["defaults"] = [k for k, v in problem.provenance.items() if v.source == "default"]
    f["_provenance"] = {k: v.model_dump() for k, v in problem.provenance.items()}
    f["_extra"] = {"warnings": problem.warnings, "notes": problem.notes, "references": problem.references}
    return f


def form_to_problem(form: dict) -> tuple[Problem | None, list[str]]:
    errors: list[str] = []
    for key in ("name", "width_mm", "height_mm"):
        if form.get(key) in (None, ""):
            errors.append(f"'{key}' is required.")
    zones = []
    for z in form.get("zones", []):
        row = {"id": z["id"], "kind": z["kind"], "shape": z["shape"]}
        if z["shape"] == "circle":
            row["circle"] = {"cx": z.get("cx"), "cy": z.get("cy"), "r": z.get("r")}
        else:
            row["rect"] = {"x": z.get("x"), "y": z.get("y"), "w": z.get("w"), "h": z.get("h")}
        zones.append(row)
    cases = []
    for lc in form.get("load_cases", []):
        loads = [{k: v for k, v in ld.items() if k != "case_id"} for ld in form.get("loads", [])
                 if ld.get("case_id") == lc["id"]]
        if not loads:
            errors.append(f"Load case '{lc.get('name', lc['id'])}' has no loads.")
        cases.append({**lc, "loads": loads})
    if errors:
        return None, errors
    d = {"name": form["name"], "design_space": {"width_mm": form["width_mm"], "height_mm": form["height_mm"]},
         "thickness_mm": form["thickness_mm"], "zones": zones, "pads": form.get("pads", []),
         "supports": form.get("supports", []), "load_cases": cases, "safety_factor": form["safety_factor"],
         "printer": form["printer"], "materials": form.get("materials") or list(MATERIAL_IDS)}
    extra = form.get("_extra") or {}
    d.update({k: v for k, v in extra.items() if v})
    try:
        p = problem_from_dict(d)
    except ValidationError as exc:
        for e in exc.errors():
            loc = ".".join(str(x) for x in e["loc"])
            errors.append(f"{loc}: {e['msg']}" if loc else e["msg"])
        return None, errors
    prov = {k: Provenance(**v) for k, v in (form.get("_provenance") or {}).items()}
    for k in form.get("defaults", []):
        prov.setdefault(k, Provenance(source="default"))
    p.provenance = prov
    return p, []


def load_demo(name: str) -> Problem:
    """Load one of the 3 saved, checked demo problems (works without the network)."""
    stem = DEMOS.get(name, name)
    with open(EXAMPLES / f"{stem}.json", encoding="utf-8") as f:
        return problem_from_dict(json.load(f))


def demo_text(name: str) -> str:
    stem = DEMOS.get(name, name)
    return (EXAMPLES / f"{stem}.txt").read_text(encoding="utf-8")
