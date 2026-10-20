"""Materials and processes library loader (spec section 5).

Every numeric value must carry a citation (title + url) or the loader rejects it.
Values that are null must carry a flag saying why. Z strength falls back to
XY x cited knockdown; interlayer shear falls back to Z / sqrt(3) as a labeled stand-in.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

DATA_DIR = Path(__file__).parent / "data"
MATERIALS_PATH = DATA_DIR / "materials.yaml"
PROCESSES_PATH = DATA_DIR / "processes.yaml"

REQUIRED_NUMERIC = ("E_xy_MPa", "nu", "strength_xy_MPa", "density_g_cm3")
OPTIONAL_NUMERIC = ("strength_z_MPa", "interlayer_shear_MPa", "cost_usd_per_kg")
CITATION_KEY = {"E_xy_MPa": "E", "nu": "nu", "strength_xy_MPa": "strength_xy", "strength_z_MPa": "strength_z",
                "interlayer_shear_MPa": "interlayer_shear", "density_g_cm3": "density", "cost_usd_per_kg": "cost"}


class MaterialDataError(ValueError):
    pass


@dataclass
class Citation:
    title: str
    version_or_date: str = ""
    page: str = ""
    url: str = ""

    def short(self) -> str:
        bits = [self.title]
        if self.version_or_date:
            bits.append(str(self.version_or_date))
        if self.page:
            bits.append(f"p. {self.page}")
        return ", ".join(bits)


@dataclass
class Material:
    id: str
    name: str
    process: str
    E: float  # MPa, in-plane (XY)
    nu: float
    strength_xy: float  # MPa
    strength_kind: str  # "yield" | "tensile"
    density: float  # g/cm3
    strength_z: float | None = None
    interlayer_shear: float | None = None
    cost_per_kg: float | None = None
    cost_note: str = ""
    condition_note: str = ""
    z_knockdown_value: float | None = None
    z_knockdown_source: str = ""
    citations: dict[str, Citation] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    @property
    def strength(self) -> float:
        """The strength used for the safety factor (XY, the lower of yield and tensile)."""
        return self.strength_xy

    def strength_z_used(self) -> tuple[float, str]:
        if self.strength_z is not None:
            return self.strength_z, "datasheet Z value"
        if self.z_knockdown_value is None:
            raise MaterialDataError(f"{self.id}: no Z strength and no knockdown factor")
        return self.strength_xy * self.z_knockdown_value, (
            f"XY x {self.z_knockdown_value:g} knockdown ({self.z_knockdown_source})")

    def interlayer_shear_used(self) -> tuple[float, str]:
        if self.interlayer_shear is not None:
            return self.interlayer_shear, "datasheet interlayer shear"
        z, note = self.strength_z_used()
        return z / np.sqrt(3.0), f"Z strength / sqrt(3), a conservative stand-in ({note})"

    def cost_label(self) -> str:
        if self.cost_per_kg is None:
            return "material cost not sourced"
        return f"${self.cost_per_kg:.2f}/kg (material cost only, not print cost)"


@dataclass
class Process:
    id: str
    name: str
    min_wall_mm: float
    printer_group: str
    citation: Citation


def _citation(raw, where: str) -> Citation:
    if not isinstance(raw, dict) or not raw.get("title") or not raw.get("url"):
        raise MaterialDataError(f"{where}: citation needs a title and a url")
    return Citation(title=str(raw["title"]), version_or_date=str(raw.get("version_or_date", "") or ""),
                    page=str(raw.get("page", "") or ""), url=str(raw["url"]))


def _number(raw, where: str) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise MaterialDataError(f"{where}: not a number: {raw!r}")
    if not np.isfinite(v) or v <= 0:
        raise MaterialDataError(f"{where}: must be a positive number, got {v}")
    return v


def parse_material(d: dict) -> Material:
    mid = d.get("id", "?")
    cits_raw = d.get("citations") or {}
    cits: dict[str, Citation] = {}
    flags = list(d.get("flags") or [])
    values: dict[str, float | None] = {}
    for key in REQUIRED_NUMERIC + OPTIONAL_NUMERIC:
        raw = d.get(key)
        ckey = CITATION_KEY[key]
        if raw is None:
            if key in REQUIRED_NUMERIC:
                raise MaterialDataError(f"{mid}: required value {key} is missing")
            values[key] = None
            continue
        values[key] = _number(raw, f"{mid}.{key}")
        cits[ckey] = _citation(cits_raw.get(ckey), f"{mid}.{key}")  # rejects a value without a citation
    kind = d.get("strength_kind")
    if kind not in ("yield", "tensile"):
        raise MaterialDataError(f"{mid}: strength_kind must be yield or tensile")
    zk = d.get("z_knockdown") or {}
    zk_val = zk.get("value")
    zk_src = str(zk.get("source") or "")
    if values["strength_z_MPa"] is None:
        if zk_val is None or not zk_src:
            raise MaterialDataError(f"{mid}: no strength_z_MPa and no cited z_knockdown")
        zk_val = _number(zk_val, f"{mid}.z_knockdown.value")
        if zk_val > 1.0:
            raise MaterialDataError(f"{mid}: z_knockdown must be <= 1")
    elif zk_val is not None:
        zk_val = _number(zk_val, f"{mid}.z_knockdown.value")
    if d.get("process") not in ("fdm", "sls", "metal"):
        raise MaterialDataError(f"{mid}: process must be fdm, sls or metal")
    if values["cost_usd_per_kg"] is None and not any("cost" in f.lower() for f in flags):
        flags.append("cost not sourced")
    return Material(
        id=str(mid), name=str(d.get("name", mid)), process=d["process"],
        E=values["E_xy_MPa"], nu=values["nu"], strength_xy=values["strength_xy_MPa"], strength_kind=kind,
        density=values["density_g_cm3"], strength_z=values["strength_z_MPa"],
        interlayer_shear=values["interlayer_shear_MPa"], cost_per_kg=values["cost_usd_per_kg"],
        cost_note=str(d.get("cost_note") or ""), condition_note=str(d.get("condition_note") or ""),
        z_knockdown_value=zk_val, z_knockdown_source=zk_src, citations=cits, flags=flags,
    )


def load_materials(path: Path | str = MATERIALS_PATH) -> dict[str, Material]:
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    out: dict[str, Material] = {}
    for d in doc.get("materials") or []:
        m = parse_material(d)
        if m.id in out:
            raise MaterialDataError(f"duplicate material id {m.id}")
        out[m.id] = m
    if not out:
        raise MaterialDataError("no materials in library")
    return out


def load_processes(path: Path | str = PROCESSES_PATH) -> dict[str, Process]:
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    out: dict[str, Process] = {}
    for d in doc.get("processes") or []:
        pid = d.get("id", "?")
        p = Process(id=str(pid), name=str(d.get("name", pid)),
                    min_wall_mm=_number(d.get("min_wall_mm"), f"{pid}.min_wall_mm"),
                    printer_group=str(d.get("printer_group") or ""),
                    citation=_citation(d.get("citation"), f"{pid}.min_wall_mm"))
        if p.printer_group not in ("desktop_fdm", "sls_service", "metal_service"):
            raise MaterialDataError(f"{pid}: unknown printer_group {p.printer_group!r}")
        out[p.id] = p
    for req in ("fdm", "sls", "metal"):
        if req not in out:
            raise MaterialDataError(f"process {req} missing from library")
    return out


def library_hash(materials_path=MATERIALS_PATH, processes_path=PROCESSES_PATH) -> str:
    h = hashlib.sha256()
    for p in (materials_path, processes_path):
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:16]


def printer_allows(printer: str, process: Process) -> bool:
    return printer == "any" or printer == process.printer_group
