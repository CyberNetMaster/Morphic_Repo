"""Geometry export (spec section 9): contour, light smoothing, pad repair, extrude,
STL / SVG / DXF, and the smoothed re-check on the analysis grid.

The re-check numbers are the ones shown and exported, so they match the STL.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
import trimesh
from shapely.geometry import MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union
from skimage import measure

from . import config, evaluate
from .domain import Domain
from .materials import Material


class GeometryError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- contour
def contours_mm(domain: Domain, density: np.ndarray, level: float = config.SOLID_THRESHOLD) -> list[np.ndarray]:
    """Closed 0.5-level contours of the element density field, in mm (marching squares)."""
    mesh = domain.mesh
    g = mesh.element_grid(np.asarray(density, dtype=float))
    padded = np.zeros((mesh.nelx + 2, mesh.nely + 2))
    padded[1:-1, 1:-1] = g
    out = []
    for c in measure.find_contours(padded, level):
        if len(c) < 4:
            continue
        x = (c[:, 0] - 1 + 0.5) * mesh.h
        y = (c[:, 1] - 1 + 0.5) * mesh.h
        pts = np.stack([x, y], axis=1)
        if not np.allclose(pts[0], pts[-1]):
            pts = np.vstack([pts, pts[:1]])
        out.append(pts)
    return out


def smooth_contour(pts: np.ndarray, h: float, passes: int = 3,
                   max_move_elements: float = config.SMOOTH_MAX_MOVE_ELEMENTS) -> np.ndarray:
    """Light Laplacian smoothing of a closed polyline; no point moves more than max_move_elements * h."""
    p = pts[:-1].copy()  # drop the repeated closing point
    orig = p.copy()
    n = len(p)
    if n < 4:
        return pts
    for _ in range(passes):
        nb = 0.5 * (np.roll(p, 1, axis=0) + np.roll(p, -1, axis=0))
        p = 0.5 * p + 0.5 * nb
        d = p - orig
        dist = np.linalg.norm(d, axis=1)
        lim = max_move_elements * h
        over = dist > lim
        if over.any():
            p[over] = orig[over] + d[over] * (lim / dist[over])[:, None]
    return np.vstack([p, p[:1]])


def polygons_from_contours(contours: list[np.ndarray]) -> MultiPolygon:
    """Assemble closed contours into polygons with holes by nesting depth (even = shell, odd = hole)."""
    polys = [Polygon(c) for c in contours]
    polys = [p.buffer(0) if not p.is_valid else p for p in polys]
    polys = [p for p in polys if not p.is_empty and p.area > 0]
    order = sorted(range(len(polys)), key=lambda i: -polys[i].area)
    depth = {}
    parent = {}
    for i in order:
        d = 0
        par = None
        best_area = np.inf
        for j in order:
            if j == i:
                continue
            if polys[j].area > polys[i].area and polys[j].contains(polys[i].representative_point()):
                d += 1
                if polys[j].area < best_area:
                    best_area = polys[j].area
                    par = j
        depth[i] = d
        parent[i] = par
    shells = [i for i in order if depth[i] % 2 == 0]
    result = []
    for s in shells:
        holes = [list(polys[i].exterior.coords) for i in order if depth[i] % 2 == 1 and parent[i] == s]
        result.append(Polygon(list(polys[s].exterior.coords), holes))
    mp = unary_union(result)
    if isinstance(mp, Polygon):
        mp = MultiPolygon([mp])
    return mp


# ----------------------------------------------------------------------------- repair
def repair_pads(domain: Domain, shape, min_wall: float):
    """Union the exact pad rings and keep-in zones, subtract the exact holes and keep-out
    zones, and drop slivers smaller than the effective min wall."""
    p = domain.problem
    rings = [Point(pad.cx, pad.cy).buffer(pad.ring_r_mm, 64) for pad in p.pads]
    holes = [Point(pad.cx, pad.cy).buffer(pad.hole_r_mm, 64) for pad in p.pads if not pad.is_solid]
    keep_in, keep_out = [], []
    for z in p.zones:
        geom = (Point(z.circle.cx, z.circle.cy).buffer(z.circle.r, 64) if z.shape == "circle"
                else box(z.rect.x, z.rect.y, z.rect.x + z.rect.w, z.rect.y + z.rect.h))
        (keep_in if z.kind == "keep_in" else keep_out).append(geom)
    shape = unary_union([shape] + rings + keep_in)
    for g in holes + keep_out:
        shape = shape.difference(g)
    shape = shape.intersection(box(0, 0, domain.mesh.width, domain.mesh.height))
    # drop slivers: parts smaller than a min-wall square, and holes smaller than that
    parts = list(shape.geoms) if isinstance(shape, MultiPolygon) else [shape]
    kept = []
    a_min = min_wall * min_wall
    for part in parts:
        if part.is_empty or part.area < a_min:
            continue
        inner = [h for h in part.interiors if Polygon(h).area >= a_min]
        kept.append(Polygon(part.exterior.coords, [list(h.coords) for h in inner]))
    if not kept:
        raise GeometryError("no geometry left after pad repair")
    return MultiPolygon(kept)


# ----------------------------------------------------------------------------- extrude / export
@dataclass
class Geometry:
    shape: MultiPolygon
    thickness_mm: float
    mesh: trimesh.Trimesh
    area_mm2: float
    volume_mm3: float
    watertight: bool
    volume_error: float
    max_smoothing_move_mm: float


def extrude(shape: MultiPolygon, thickness: float) -> trimesh.Trimesh:
    parts = [trimesh.creation.extrude_polygon(poly, height=thickness) for poly in shape.geoms]
    m = trimesh.util.concatenate(parts) if len(parts) > 1 else parts[0]
    m.merge_vertices()
    return m


def build_geometry(domain: Domain, density: np.ndarray) -> Geometry:
    cs = contours_mm(domain, density)
    if not cs:
        raise GeometryError("no solid material to export")
    smoothed = []
    max_move = 0.0
    for c in cs:
        s = smooth_contour(c, domain.mesh.h)
        max_move = max(max_move, float(np.linalg.norm(s - c, axis=1).max()))
        smoothed.append(s)
    shape = polygons_from_contours(smoothed)
    shape = repair_pads(domain, shape, domain.effective_min_wall_mm)
    t = domain.problem.thickness_mm
    m = extrude(shape, t)
    expected = shape.area * t
    vol_err = abs(m.volume - expected) / expected
    if not m.is_watertight:
        raise GeometryError("extruded mesh is not watertight")
    if vol_err > config.VOLUME_CHECK_RTOL:
        raise GeometryError(f"mesh volume {m.volume:.1f} differs from area x thickness {expected:.1f} by {vol_err:.1%}")
    return Geometry(shape=shape, thickness_mm=t, mesh=m, area_mm2=float(shape.area), volume_mm3=float(m.volume),
                    watertight=bool(m.is_watertight), volume_error=float(vol_err), max_smoothing_move_mm=max_move)


def export_stl(geom: Geometry, path: Path | str) -> None:
    geom.mesh.export(str(path), file_type="stl")


def export_svg(geom: Geometry, path: Path | str, domain: Domain | None = None) -> None:
    W = domain.mesh.width if domain else geom.shape.bounds[2]
    H = domain.mesh.height if domain else geom.shape.bounds[3]
    paths = []
    for poly in geom.shape.geoms:
        rings = [poly.exterior] + list(poly.interiors)
        d = ""
        for r in rings:
            pts = list(r.coords)
            d += "M " + " L ".join(f"{x:.3f} {H - y:.3f}" for x, y in pts[:-1]) + " Z "
        paths.append(f'<path d="{d.strip()}" fill="#ddd" stroke="#000" stroke-width="0.2" fill-rule="evenodd"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">\n'
           + "\n".join(paths) + "\n</svg>\n")
    Path(path).write_text(svg, encoding="utf-8")


def export_dxf(geom: Geometry, path: Path | str) -> None:
    import ezdxf

    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    for poly in geom.shape.geoms:
        for r in [poly.exterior] + list(poly.interiors):
            msp.add_lwpolyline(list(r.coords)[:-1], close=True)
    doc.saveas(str(path))


def export_all(geom: Geometry, stem: Path | str, domain: Domain | None = None) -> dict[str, Path]:
    stem = Path(stem)
    out = {"stl": stem.with_suffix(".stl"), "svg": stem.with_suffix(".svg"), "dxf": stem.with_suffix(".dxf")}
    export_stl(geom, out["stl"])
    export_svg(geom, out["svg"], domain)
    export_dxf(geom, out["dxf"])
    return out


# ----------------------------------------------------------------------------- smoothed re-check
def rasterize_fraction(domain: Domain, shape: MultiPolygon, supersample: int = config.RECHECK_SUPERSAMPLE) -> np.ndarray:
    """Area fraction of each element inside the polygon (supersample x supersample points)."""
    mesh = domain.mesh
    s = supersample
    offs = (np.arange(s) + 0.5) / s * mesh.h
    x0 = mesh.xc - 0.5 * mesh.h
    y0 = mesh.yc - 0.5 * mesh.h
    frac = np.zeros(mesh.nel)
    prepared = shapely.prepared.prep(shape)
    for dx in offs:
        for dy in offs:
            frac += shapely.contains_xy(shape, x0 + dx, y0 + dy).astype(float)
    return frac / (s * s)


def smoothed_recheck(domain: Domain, geom: Geometry, material: Material, sf_target: float):
    """FE on the rasterized smoothed polygon with linear E scaling (spec 9.6). Returns (fraction, mech, checks)."""
    frac = rasterize_fraction(domain, geom.shape)
    mech, checks = evaluate.evaluate(domain, frac, material, sf_target, mode="fraction")
    return frac, mech, checks
