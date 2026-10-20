"""Plain English -> checked Problem (spec section 4.4).

Flow:
1. Send the text and the draft JSON schema to the LLM (through `llm.py`).
2. Validate with Pydantic and fill defaults (section 4.3). If the JSON or the
   validation fails, retry ONCE, sending the error back.
3. Time limit 45 s per call. A timeout or an API error is not retried: the caller
   shows the manual form and offers the saved demo problems.

The LLM only fills a draft. Defaults are applied here, in code, so every default is
marked source "default" and shown in yellow on the check screen.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import time
from dataclasses import dataclass, field
from typing import Callable, Literal

import numpy as np
from pydantic import BaseModel, Field, ValidationError

from . import config
from .problem import MATERIAL_IDS, Problem, Provenance, problem_from_dict


# ----------------------------------------------------------------------------- draft schema
class DraftPad(BaseModel):
    id: str
    cx: float
    cy: float
    hole_r_mm: float | None = None  # null = not stated
    ring_r_mm: float | None = None  # null = not stated
    solid: bool = False  # true if the text says a solid mount (no hole)


class DraftLoad(BaseModel):
    pad_id: str
    fx_N: float = 0.0
    fy_N: float = 0.0
    fz_N_out_of_plane: float = 0.0


class DraftLoadCase(BaseModel):
    id: str
    name: str
    reason: str = ""
    loads: list[DraftLoad] = Field(min_length=1)
    max_deflection_mm: float | None = None


class DraftCircle(BaseModel):
    cx: float
    cy: float
    r: float


class DraftRect(BaseModel):
    x: float
    y: float
    w: float
    h: float


class DraftZone(BaseModel):
    id: str
    kind: Literal["keep_in", "keep_out"]
    shape: Literal["circle", "rect"]
    circle: DraftCircle | None = None
    rect: DraftRect | None = None


class DraftSupport(BaseModel):
    pad_id: str
    type: Literal["pin", "slide_x", "slide_y"]


class DraftDesignSpace(BaseModel):
    width_mm: float
    height_mm: float


class Draft(BaseModel):
    name: str
    design_space: DraftDesignSpace
    thickness_mm: float | None = None
    zones: list[DraftZone] = Field(default_factory=list)
    pads: list[DraftPad] = Field(min_length=1)
    supports: list[DraftSupport] = Field(min_length=1)
    load_cases: list[DraftLoadCase] = Field(min_length=1, max_length=4)
    deflection_span_ratio: float | None = None  # set when the text gives the limit as "span / N"
    safety_factor: float | None = None
    printer: Literal["desktop_fdm", "sls_service", "metal_service", "any"] | None = None
    materials: list[str] | None = None
    original_text: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


SYSTEM_PROMPT = """You turn a plain-English description of a load-bearing part into JSON for a 2D \
structural design tool. Return ONLY one JSON object that matches the schema below. No prose, no code fences.

Rules:
- Units inside the JSON are always mm and N. Convert every other unit (inch = 25.4 mm, lbf = 4.44822 N, \
kgf = 9.80665 N). Put the exact original phrase for each converted or stated value in `original_text`.
- Coordinate frame: origin at the bottom-left corner of the design rectangle, x to the right, y up. The 2D \
plane is the plane the part is drawn in; thickness is the extrusion depth (z).
- Every support and every load acts on a pad (a circle with a hole and a ring around it). A bare point \
becomes a pad. Give each pad a short id.
- hole_r_mm is the hole RADIUS (half the pin or bolt diameter). Leave hole_r_mm and ring_r_mm null when \
the text does not state them; the tool fills defaults. Set solid=true (and hole_r_mm 0) only when the \
text says the mount is solid / has no hole.
- Support types: "pin" holds x and y; "slide_x" is free to move in x and holds y (a vertical-only \
reaction); "slide_y" is free to move in y and holds x (a horizontal-only reaction).
- Loads: fx_N, fy_N are in-plane (sign by the axes: up is +y, right is +x). A load along the thickness \
direction (out of the drawing plane) goes in fz_N_out_of_plane. For a force at an angle, resolve it into \
fx_N and fy_N. Each separate loading situation is its own load case (at most 4).
- max_deflection_mm per load case only if the text gives a number. If the text gives the limit as \
"span / N", set deflection_span_ratio = N and leave max_deflection_mm null.
- Leave thickness_mm, safety_factor, printer, materials null when the text does not state them.
- printer: "desktop_fdm" for a home / desktop filament printer, "sls_service" for SLS nylon, \
"metal_service" for metal printing, "any" if the text allows any process.
- materials: a subset of ["pla","petg","pa6cf","pa12","alsi10mg","ti64"], or null for all.
- original_text keys are field paths, for example "thickness_mm", "safety_factor", \
"pads[0].hole_r_mm", "load_cases[1].loads[0].fy_N", "load_cases[0].max_deflection_mm".
- Do not invent values the text does not give. If something is unclear, add a short note to `warnings`.

Schema (JSON Schema):
"""


def schema_text() -> str:
    return json.dumps(Draft.model_json_schema(), separators=(",", ":"))


def user_prompt(text: str, error: str | None = None, previous: str | None = None) -> str:
    msg = f"Description:\n\"\"\"\n{text.strip()}\n\"\"\""
    if error:
        msg += (f"\n\nYour previous answer was not valid. Error:\n{error}\n\nPrevious answer:\n{previous}\n\n"
                "Return a corrected JSON object.")
    return msg


# ----------------------------------------------------------------------------- defaults
def default_ring_width(min_walls: list[float]) -> float:
    w = max(min_walls) if min_walls else 0.0
    return max(config.DEFAULT_RING_WIDTH_MIN_MM, config.DEFAULT_RING_WIDTH_WALLS * w)


def complete_draft(draft: Draft, min_walls: list[float] | None = None) -> Problem:
    """Fill defaults (spec 4.3), record provenance, and validate into a Problem."""
    ot = dict(draft.original_text)
    prov: dict[str, Provenance] = {}

    def mark(path: str, given: bool, default_text: str = "") -> None:
        prov[path] = Provenance(source="user" if given else "default",
                                original_text=ot.get(path, "") if given else default_text)

    ring_w = default_ring_width(min_walls or [])
    pads = []
    for i, p in enumerate(draft.pads):
        if p.solid:
            hole, hole_given = 0.0, True
        elif p.hole_r_mm is not None:
            hole, hole_given = float(p.hole_r_mm), True
        else:
            hole, hole_given = config.DEFAULT_HOLE_R_MM, False
        mark(f"pads[{i}].hole_r_mm", hole_given, "default: M3 clearance")
        if p.ring_r_mm is not None:
            ring, ring_given = float(p.ring_r_mm), True
        else:
            ring, ring_given = hole + ring_w, False
        if hole == 0.0 and not ring_given:
            ring = ring_w
        mark(f"pads[{i}].ring_r_mm", ring_given, f"default: ring width max(2 mm, 2 x min wall) = {ring_w:g} mm")
        pads.append({"id": p.id, "cx": p.cx, "cy": p.cy, "hole_r_mm": hole, "ring_r_mm": ring})

    thickness = draft.thickness_mm if draft.thickness_mm is not None else config.DEFAULT_THICKNESS_MM
    mark("thickness_mm", draft.thickness_mm is not None, "default: 6 mm")
    sf = draft.safety_factor if draft.safety_factor is not None else config.DEFAULT_SAFETY_FACTOR
    mark("safety_factor", draft.safety_factor is not None, "default: 2.0")
    printer = draft.printer or config.DEFAULT_PRINTER
    mark("printer", draft.printer is not None, "default: any")
    mats = [m for m in (draft.materials or []) if m in MATERIAL_IDS] or list(MATERIAL_IDS)
    mark("materials", bool(draft.materials), "default: all 6")

    d = {
        "name": draft.name,
        "design_space": draft.design_space.model_dump(),
        "thickness_mm": thickness,
        "zones": [z.model_dump(exclude_none=True) for z in draft.zones],
        "pads": pads,
        "supports": [s.model_dump() for s in draft.supports],
        "load_cases": [{"id": lc.id, "name": lc.name, "reason": lc.reason,
                        "loads": [ld.model_dump() for ld in lc.loads],
                        "max_deflection_mm": lc.max_deflection_mm or 1.0} for lc in draft.load_cases],
        "safety_factor": sf,
        "printer": printer,
        "materials": mats,
        "warnings": list(draft.warnings),
    }
    problem = problem_from_dict(d)  # raises ValidationError on bad ids etc.
    span = problem.span_mm
    for i, lc in enumerate(draft.load_cases):
        path = f"load_cases[{i}].max_deflection_mm"
        if lc.max_deflection_mm is not None:
            mark(path, True)
            continue
        if draft.deflection_span_ratio:
            val = span / draft.deflection_span_ratio
            prov[path] = Provenance(source="user", original_text=ot.get("deflection_span_ratio", "")
                                    or f"span / {draft.deflection_span_ratio:g}")
        else:
            val = span / config.DEFAULT_DEFLECTION_SPAN_RATIO
            prov[path] = Provenance(source="default", original_text=f"default: span / 100 = {val:.3g} mm")
        problem.load_cases[i].max_deflection_mm = float(val) if val > 0 else 1.0
    for path, txt in ot.items():  # load values and positions the text gave
        if path not in prov:
            prov[path] = Provenance(source="user", original_text=txt)
    problem.provenance = prov
    return problem


# ----------------------------------------------------------------------------- parse
class ParseFailed(RuntimeError):
    """Parsing failed: the caller shows the manual form and offers the demo problems."""

    def __init__(self, message: str, attempts: list[dict]):
        super().__init__(message)
        self.attempts = attempts


@dataclass
class ParseResult:
    problem: Problem
    draft: Draft
    raw: str
    attempts: list[dict] = field(default_factory=list)
    seconds: float = 0.0
    provider: str = ""
    model: str = ""


def _strip_json(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.lower().startswith("json"):
            t = t[4:]
    i, j = t.find("{"), t.rfind("}")
    return t[i:j + 1] if i >= 0 and j > i else t


def _default_llm(system: str, user: str, timeout_s: float):
    from . import llm

    return llm.complete(system, user, timeout_s)


_POOL = cf.ThreadPoolExecutor(max_workers=2, thread_name_prefix="morphic-llm")


def parse_text(text: str, llm_call: Callable | None = None, timeout_s: float = config.LLM_TIMEOUT_S,
               retries: int = config.LLM_RETRIES, min_walls: list[float] | None = None,
               status: Callable[[str], None] | None = None) -> ParseResult:
    """Parse a description. Raises ParseFailed after the allowed attempts."""
    llm_call = llm_call or _default_llm
    system = SYSTEM_PROMPT + schema_text()
    attempts: list[dict] = []
    error = previous = None
    t0 = time.perf_counter()
    for attempt in range(1 + retries):
        if status:
            status("Reading your description... if this takes too long, a manual form will open.")
        ta = time.perf_counter()
        fut = _POOL.submit(llm_call, system, user_prompt(text, error, previous), timeout_s)
        try:
            res = fut.result(timeout=timeout_s)
        except cf.TimeoutError:
            attempts.append({"attempt": attempt + 1, "error": f"timeout after {timeout_s:g} s",
                             "seconds": time.perf_counter() - ta})
            raise ParseFailed(f"the LLM did not answer within {timeout_s:g} s", attempts)
        except Exception as exc:  # API unreachable, auth, quota: not retried
            attempts.append({"attempt": attempt + 1, "error": f"{type(exc).__name__}: {exc}",
                             "seconds": time.perf_counter() - ta})
            raise ParseFailed(f"LLM call failed: {type(exc).__name__}: {exc}", attempts)
        raw = getattr(res, "text", res)
        rec = {"attempt": attempt + 1, "seconds": time.perf_counter() - ta, "raw": raw,
               "provider": getattr(res, "provider", ""), "model": getattr(res, "model", "")}
        try:
            draft = Draft.model_validate(json.loads(_strip_json(raw)))
            problem = complete_draft(draft, min_walls)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            error, previous = str(exc)[:4000], raw[:8000]
            rec["error"] = error
            attempts.append(rec)
            continue
        attempts.append(rec)
        return ParseResult(problem=problem, draft=draft, raw=raw, attempts=attempts,
                           seconds=time.perf_counter() - t0, provider=rec["provider"], model=rec["model"])
    raise ParseFailed("the LLM answer did not validate after the allowed retry", attempts)


# ----------------------------------------------------------------------------- comparison
def compare_problems(got: Problem, want: Problem, rtol: float = 0.005, atol: float = 0.05) -> list[str]:
    """Differences between a parsed problem and an approved one. Pads are matched by
    position, load cases by order. Returns plain-English lines; empty means a match."""
    diffs: list[str] = []

    def num(path, a, b):
        if not np.isclose(a, b, rtol=rtol, atol=atol):
            diffs.append(f"{path}: parsed {a:g}, approved {b:g}")

    num("design_space.width_mm", got.design_space.width_mm, want.design_space.width_mm)
    num("design_space.height_mm", got.design_space.height_mm, want.design_space.height_mm)
    num("thickness_mm", got.thickness_mm, want.thickness_mm)
    num("safety_factor", got.safety_factor, want.safety_factor)
    if got.printer != want.printer:
        diffs.append(f"printer: parsed {got.printer}, approved {want.printer}")
    if sorted(got.materials) != sorted(want.materials):
        diffs.append(f"materials: parsed {got.materials}, approved {want.materials}")
    if len(got.zones) != len(want.zones):
        diffs.append(f"zones: parsed {len(got.zones)}, approved {len(want.zones)}")
    if len(got.pads) != len(want.pads):
        diffs.append(f"pads: parsed {len(got.pads)}, approved {len(want.pads)}")
    idmap: dict[str, str] = {}
    for wp in want.pads:
        gp = min(got.pads, key=lambda p: np.hypot(p.cx - wp.cx, p.cy - wp.cy))
        idmap[gp.id] = wp.id
        for f in ("cx", "cy", "hole_r_mm", "ring_r_mm"):
            num(f"pad {wp.id}.{f}", getattr(gp, f), getattr(wp, f))
    gs = sorted((idmap.get(s.pad_id, s.pad_id), s.type) for s in got.supports)
    ws = sorted((s.pad_id, s.type) for s in want.supports)
    if gs != ws:
        diffs.append(f"supports: parsed {gs}, approved {ws}")
    if len(got.load_cases) != len(want.load_cases):
        diffs.append(f"load cases: parsed {len(got.load_cases)}, approved {len(want.load_cases)}")
    for i, (gl, wl) in enumerate(zip(got.load_cases, want.load_cases)):
        num(f"load case '{wl.name}' max_deflection_mm", gl.max_deflection_mm, wl.max_deflection_mm)
        gsum = {}
        for ld in gl.loads:
            k = idmap.get(ld.pad_id, ld.pad_id)
            gsum[k] = np.add(gsum.get(k, 0), [ld.fx_N, ld.fy_N, ld.fz_N_out_of_plane])
        wsum = {}
        for ld in wl.loads:
            wsum[ld.pad_id] = np.add(wsum.get(ld.pad_id, 0), [ld.fx_N, ld.fy_N, ld.fz_N_out_of_plane])
        for pid in sorted(set(gsum) | set(wsum)):
            a = np.asarray(gsum.get(pid, [0, 0, 0]), dtype=float)
            b = np.asarray(wsum.get(pid, [0, 0, 0]), dtype=float)
            scale = max(np.abs(b).max(), 1.0)
            if np.abs(a - b).max() > rtol * scale + atol:
                diffs.append(f"load case '{wl.name}' at pad {pid}: parsed (fx, fy, fz) = "
                             f"({a[0]:g}, {a[1]:g}, {a[2]:g}) N, approved ({b[0]:g}, {b[1]:g}, {b[2]:g}) N")
    return diffs
