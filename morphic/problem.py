"""Problem schema (spec section 4.2). Units: mm, N.

Provenance: instead of wrapping every scalar, `Problem.provenance` maps a field
path such as "thickness_mm" or "load_cases[0].max_deflection_mm" to
{"source": "user" | "default", "original_text": str}. Fields without an entry
are treated as source "user" with empty original text.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel, Field, field_validator, model_validator

from . import config

PRINTERS = ("desktop_fdm", "sls_service", "metal_service", "any")
MATERIAL_IDS = ("pla", "petg", "pa6cf", "pa12", "alsi10mg", "ti64")


class Circle(BaseModel):
    cx: float
    cy: float
    r: float = Field(gt=0)


class Rect(BaseModel):
    x: float
    y: float
    w: float = Field(gt=0)
    h: float = Field(gt=0)


class Zone(BaseModel):
    id: str
    kind: Literal["keep_in", "keep_out"]
    shape: Literal["circle", "rect"]
    circle: Circle | None = None
    rect: Rect | None = None

    @model_validator(mode="after")
    def _shape_present(self):
        if self.shape == "circle" and self.circle is None:
            raise ValueError(f"zone {self.id}: shape is circle but no circle given")
        if self.shape == "rect" and self.rect is None:
            raise ValueError(f"zone {self.id}: shape is rect but no rect given")
        return self

    def contains(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        if self.shape == "circle":
            c = self.circle
            return (x - c.cx) ** 2 + (y - c.cy) ** 2 <= c.r**2
        r = self.rect
        return (x >= r.x) & (x <= r.x + r.w) & (y >= r.y) & (y <= r.y + r.h)


class Pad(BaseModel):
    """Where supports and loads attach. The hole is keep-out, the ring is keep-in.
    hole_r_mm = 0 means a solid pad (a solid disc of radius ring_r_mm)."""

    id: str
    cx: float
    cy: float
    hole_r_mm: float = Field(ge=0)
    ring_r_mm: float = Field(gt=0)

    @model_validator(mode="after")
    def _ring_outside_hole(self):
        if self.ring_r_mm <= self.hole_r_mm:
            raise ValueError(f"pad {self.id}: ring_r_mm must be larger than hole_r_mm")
        return self

    @property
    def ring_width_mm(self) -> float:
        return self.ring_r_mm - self.hole_r_mm

    @property
    def is_solid(self) -> bool:
        return self.hole_r_mm == 0.0


class Support(BaseModel):
    pad_id: str
    type: Literal["pin", "slide_x", "slide_y"]

    @property
    def fix_x(self) -> bool:
        return self.type in ("pin", "slide_y")

    @property
    def fix_y(self) -> bool:
        return self.type in ("pin", "slide_x")


class Load(BaseModel):
    pad_id: str
    fx_N: float = 0.0
    fy_N: float = 0.0
    fz_N_out_of_plane: float = 0.0

    @property
    def in_plane_resultant(self) -> float:
        return float(np.hypot(self.fx_N, self.fy_N))


class LoadCase(BaseModel):
    id: str
    name: str
    reason: str = ""
    loads: list[Load] = Field(min_length=1)
    max_deflection_mm: float = Field(gt=0)

    @property
    def has_in_plane(self) -> bool:
        return any(ld.fx_N != 0.0 or ld.fy_N != 0.0 for ld in self.loads)

    @property
    def has_out_of_plane(self) -> bool:
        return any(ld.fz_N_out_of_plane != 0.0 for ld in self.loads)


class DesignSpace(BaseModel):
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)


class Provenance(BaseModel):
    source: Literal["user", "default"] = "user"
    original_text: str = ""


class Problem(BaseModel):
    name: str
    design_space: DesignSpace
    thickness_mm: float = Field(gt=0)
    zones: list[Zone] = Field(default_factory=list)
    pads: list[Pad] = Field(min_length=1)
    supports: list[Support] = Field(min_length=1)
    load_cases: list[LoadCase] = Field(min_length=1, max_length=4)
    safety_factor: float = Field(gt=0)
    printer: Literal["desktop_fdm", "sls_service", "metal_service", "any"] = config.DEFAULT_PRINTER
    materials: list[str] = Field(default_factory=lambda: list(MATERIAL_IDS))
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, Provenance] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)  # fixed card notes (e.g. the bracket slice note)
    references: list[str] = Field(default_factory=list)  # sources for the load values

    @field_validator("materials")
    @classmethod
    def _known_materials(cls, v):
        bad = [m for m in v if m not in MATERIAL_IDS]
        if bad:
            raise ValueError(f"unknown material ids: {bad}")
        if not v:
            raise ValueError("materials must not be empty")
        return v

    @model_validator(mode="after")
    def _ids_consistent(self):
        ids = [p.id for p in self.pads]
        if len(set(ids)) != len(ids):
            raise ValueError("pad ids must be unique")
        for s in self.supports:
            if s.pad_id not in ids:
                raise ValueError(f"support refers to unknown pad {s.pad_id!r}")
        for lc in self.load_cases:
            for ld in lc.loads:
                if ld.pad_id not in ids:
                    raise ValueError(f"load case {lc.id!r} refers to unknown pad {ld.pad_id!r}")
        lc_ids = [lc.id for lc in self.load_cases]
        if len(set(lc_ids)) != len(lc_ids):
            raise ValueError("load case ids must be unique")
        return self

    # -- helpers -------------------------------------------------------------
    def pad(self, pad_id: str) -> Pad:
        return next(p for p in self.pads if p.id == pad_id)

    @property
    def support_pad_ids(self) -> list[str]:
        return [s.pad_id for s in self.supports]

    @property
    def load_pad_ids(self) -> list[str]:
        out: list[str] = []
        for lc in self.load_cases:
            for ld in lc.loads:
                if ld.pad_id not in out:
                    out.append(ld.pad_id)
        return out

    @property
    def span_mm(self) -> float:
        """Largest distance from any support pad to any load pad."""
        best = 0.0
        for s in self.support_pad_ids:
            ps = self.pad(s)
            for l in self.load_pad_ids:
                pl = self.pad(l)
                best = max(best, float(np.hypot(ps.cx - pl.cx, ps.cy - pl.cy)))
        return best

    def source_of(self, path: str) -> Provenance:
        return self.provenance.get(path, Provenance())


def default_ring_r(hole_r_mm: float, min_wall_mm: float) -> float:
    """Pad ring width default: max(2 mm, 2 x process min wall)."""
    width = max(config.DEFAULT_RING_WIDTH_MIN_MM, config.DEFAULT_RING_WIDTH_WALLS * min_wall_mm)
    return hole_r_mm + width


def problem_from_dict(d: dict) -> Problem:
    return Problem.model_validate(d)


def problem_to_dict(p: Problem) -> dict:
    return p.model_dump(mode="json")
