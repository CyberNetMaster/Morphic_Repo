"""Cinematic MP4 sequences from the recorded cold re-run snapshots (spec 15.1, step S15).

Every frame shows a saved density field. A growth sequence plays the cold re-run
snapshots of `rerun_<process>.npz` in iteration order as an extruded slab, then holds
on the checked design from `densities.npz` colored by its recovered nodal utilization
from `utilization.npz`. Nothing is interpolated between snapshots. When the cold re-run
did not replace the result (spec 6.7), the last snapshot and the design differ a little;
the cut between them is a short picture dissolve, which mixes two rendered pictures of
two saved fields and computes no new shape. `--cut` replaces it with a hard cut.

Output: 1920 x 1080, 30 fps, H.264 MP4 in renders/.

    uv sync --extra render
    uv run python -m render.cinematic --part drone_arm          # the winner growing
    uv run python -m render.cinematic --part rc_arm --side-by-side
    uv run python -m render.cinematic --all                     # three winners + side-by-side
    uv run python -m render.cinematic --part rc_arm --preview   # 960 x 540, every 6th snapshot

Reads examples/cache only; never runs the solver.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app import theme

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "examples" / "cache"
RENDERS_DIR = ROOT / "renders"
DEMO_PARTS = ("rc_arm", "drone_arm", "aero_bracket")

WIDTH, HEIGHT, FPS = 1920, 1080, 30
ALPHA_GAMMA = 0.5  # opacity = density ** gamma; a 13% fill block still reads as a block
VOID_EPS = 1.0 / 255.0  # cells below this (uint8 zero) are not drawn

MATERIAL_LABELS = {"pla": "PLA", "petg": "PETG", "pa6cf": "PA6-CF", "pa12": "PA12",
                   "alsi10mg": "AlSi10Mg", "ti64": "Ti-6Al-4V"}
INDEPENDENT_RUN_NOTE = ("Growth: an independent cold run at the same fill level. "
                        "Final frame: the checked design.")


# ----------------------------------------------------------------------------- data
@dataclass
class Sequence:
    """One cold re-run and the checked design it belongs to, straight from the cache files."""
    part: str
    title: str
    process: str
    material: str
    nelx: int
    nely: int
    h_mm: float
    thickness_mm: float
    iterations: np.ndarray  # int32 (n,), ascending
    snapshots: list  # uint8 (nelx * nely,), x-major (index i * nely + j), one per iteration
    design: np.ndarray  # float (nelx * nely,), the checked design density
    utilization: np.ndarray  # float ((nelx + 1) * (nely + 1),), max over load cases, NaN in void
    fill: float
    replaced: bool  # the cold re-run's final shape is the result (spec 6.7)
    note: str
    mass_g: float
    sf: float
    sf_target: float
    deflection_mm: float = 0.0
    deflection_limit_mm: float = 0.0
    width_mm: float = 0.0
    height_mm: float = 0.0

    @property
    def label(self) -> str:
        return f"{theme.PROCESS[self.process]['label']} · {MATERIAL_LABELS.get(self.material, self.material.upper())}"

    @property
    def utilization_peak(self) -> float:
        return float(np.nanmax(self.utilization)) if np.isfinite(self.utilization).any() else 0.0

    @property
    def design_matches_last_snapshot(self) -> bool:
        last = self.snapshots[-1].astype(float) / 255.0
        return bool(np.abs(last - self.design).max() <= 1.0 / 255.0)


def winner_process(results: dict) -> str:
    winner = results["ranking"]["winner"]
    for d in results["designs"]:
        if d["material"] == winner:
            return d["process"]
    raise ValueError(f"winner {winner!r} has no design")


def rerun_processes(cache_dir: Path) -> list[str]:
    """Processes with a saved cold re-run, in the spec's order FDM, SLS, metal."""
    return [p for p in ("fdm", "sls", "metal") if (cache_dir / f"rerun_{p}.npz").exists()]


def load_sequence(cache_dir: Path | str, process: str | None = None) -> Sequence:
    cache_dir = Path(cache_dir)
    results = json.loads((cache_dir / "results.json").read_text(encoding="utf-8"))
    if process is None:
        process = winner_process(results)
    path = cache_dir / f"rerun_{process}.npz"
    if not path.exists():
        raise FileNotFoundError(f"no cold re-run for {process} in {cache_dir}")
    with np.load(path, allow_pickle=False) as z:
        iterations = np.asarray(z["iterations"], dtype=np.int32)
        if iterations.size == 0 or np.any(np.diff(iterations) <= 0):
            raise ValueError(f"{path.name}: iterations must be ascending")
        snapshots = [np.asarray(z[f"it{int(i)}"], dtype=np.uint8) for i in iterations]
        material = str(z["material"])
    design_rec = next(d for d in results["designs"] if d["material"] == material and d["process"] == process)
    cat = results["catalogs"][process]
    nelx, nely = (int(v) for v in cat["mesh"])
    if any(s.shape != (nelx * nely,) for s in snapshots):
        raise ValueError(f"{path.name}: snapshot size does not match the {nelx} x {nely} mesh")
    with np.load(cache_dir / "densities.npz", allow_pickle=False) as z:
        design = np.asarray(z[f"design/{material}"], dtype=float)
    with np.load(cache_dir / "utilization.npz", allow_pickle=False) as z:
        util = np.asarray(z[material], dtype=float)
    if util.ndim == 2:  # one row per load case; the governing case colors each node
        with np.errstate(all="ignore"):
            util = np.where(np.all(np.isnan(util), axis=0), np.nan, np.nanmax(np.where(np.isnan(util), -np.inf, util), axis=0))
    if util.shape != ((nelx + 1) * (nely + 1),):
        raise ValueError("utilization does not match the node grid")
    problem = results["problem"]
    checks = design_rec.get("checks", {})
    rerun = design_rec.get("rerun", {})
    defl = checks.get("deflection_mm") or [0.0]
    limits = [lc.get("max_deflection_mm") or 0.0 for lc in problem.get("load_cases", [])]
    return Sequence(
        part=cache_dir.name, title=str(problem["name"]), process=process, material=material,
        nelx=nelx, nely=nely, h_mm=float(cat["h_mm"]), thickness_mm=float(problem["thickness_mm"]),
        iterations=iterations, snapshots=snapshots, design=design, utilization=util,
        fill=float(design_rec["fill"]), replaced=bool(rerun.get("replaced", False)), note=str(rerun.get("note", "")),
        mass_g=float(checks.get("mass_g", 0.0)), sf=float(checks.get("sf", 0.0)),
        sf_target=float(checks.get("sf_target", 0.0)),
        deflection_mm=float(max(defl)), deflection_limit_mm=float(max(limits) if limits else 0.0),
        width_mm=float(problem["design_space"]["width_mm"]), height_mm=float(problem["design_space"]["height_mm"]),
    )


# ----------------------------------------------------------------------------- field helpers
def cells_to_vtk(values: np.ndarray, nelx: int, nely: int) -> np.ndarray:
    """fe.Mesh element order (x-major, i * nely + j) -> VTK cell order (x fastest)."""
    return np.ascontiguousarray(np.asarray(values).reshape(nelx, nely).T.ravel())


def nodes_to_vtk(values: np.ndarray, nelx: int, nely: int) -> np.ndarray:
    """fe.Mesh node order (x-major) -> VTK point order for one node layer."""
    return np.ascontiguousarray(np.asarray(values).reshape(nelx + 1, nely + 1).T.ravel())


def fill_nan_nearest(grid: np.ndarray, passes: int = 4) -> np.ndarray:
    """Replace NaN nodes by the mean of finite 8-neighbours, repeated; leftovers become 0.

    The utilization file holds NaN in the void. A node on the shape's edge can still be NaN
    when the mask is tighter than the drawn cells, so it takes the nearest finite value.
    """
    g = np.array(grid, dtype=float)
    for _ in range(passes):
        nan = np.isnan(g)
        if not nan.any():
            break
        p = np.pad(g, 1, constant_values=np.nan)
        acc = np.zeros_like(g)
        cnt = np.zeros_like(g)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if di == 0 and dj == 0:
                    continue
                s = p[1 + di:1 + di + g.shape[0], 1 + dj:1 + dj + g.shape[1]]
                ok = np.isfinite(s)
                acc[ok] += s[ok]
                cnt[ok] += 1
        fillable = nan & (cnt > 0)
        g[fillable] = acc[fillable] / cnt[fillable]
    g[np.isnan(g)] = 0.0
    return g


def _rgb(c: str) -> tuple[int, int, int]:
    c = c.strip()
    if c.startswith("rgba"):
        r, g, b, _ = [float(v) for v in c[5:-1].split(",")]
        return int(r), int(g), int(b)
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _lut(scale: list, n: int = 256) -> np.ndarray:
    pos = np.array([p for p, _ in scale], dtype=float)
    cols = np.array([_rgb(c) for _, c in scale], dtype=float)
    t = np.linspace(0.0, 1.0, n)
    return np.stack([np.interp(t, pos, cols[:, k]) for k in range(3)], axis=1).astype(np.uint8)


DENSITY_LUT = _lut(theme.DENSITY_SCALE_CINEMATIC)
UTIL_LUT = _lut(theme.UTIL_SCALE)


def density_rgba(density: np.ndarray) -> np.ndarray:
    """Per-cell color and opacity of a density field: grey -> near-white, alpha = density ** gamma."""
    d = np.clip(np.asarray(density, dtype=float), 0.0, 1.0)
    rgba = np.empty((d.size, 4), dtype=np.uint8)
    rgba[:, :3] = DENSITY_LUT[(d * 255).astype(np.uint8)]
    rgba[:, 3] = np.rint(d ** ALPHA_GAMMA * 255).astype(np.uint8)
    return rgba


def utilization_rgba(util: np.ndarray) -> np.ndarray:
    """Per-node color of recovered utilization on the shared 0..1 scale; above 1 in the over-limit red."""
    u = np.asarray(util, dtype=float)
    rgba = np.empty((u.size, 4), dtype=np.uint8)
    rgba[:, :3] = UTIL_LUT[(np.clip(u, 0.0, 1.0) * 255).astype(np.uint8)]
    rgba[u > 1.0, :3] = _rgb(theme.OVER_LIMIT)
    rgba[:, 3] = 255
    return rgba


# ----------------------------------------------------------------------------- schedule
@dataclass
class Schedule:
    """Which saved field each output frame shows. Growth frames index the snapshots; the
    design frames show the checked design; dissolve frames mix the last snapshot picture with
    the design picture (picture blend only)."""
    kind: list = field(default_factory=list)  # "snapshot" | "dissolve" | "design"
    index: list = field(default_factory=list)  # snapshot index for "snapshot" frames
    mix: list = field(default_factory=list)  # 0..1 for "dissolve" frames, else 0 / 1

    def __len__(self) -> int:
        return len(self.kind)


def make_schedule(n_snapshots: int, frames_per_snapshot: int = 2, hold_start_s: float = 1.0,
                  hold_end_s: float = 4.0, dissolve_s: float = 0.6, fps: int = FPS,
                  step: int = 1) -> Schedule:
    s = Schedule()
    first_hold = max(0, int(round(hold_start_s * fps)) - frames_per_snapshot)
    for _ in range(first_hold):
        s.kind.append("snapshot"); s.index.append(0); s.mix.append(0.0)
    picked = list(range(0, n_snapshots, max(1, step)))
    if picked[-1] != n_snapshots - 1:
        picked.append(n_snapshots - 1)
    for i in picked:
        for _ in range(frames_per_snapshot):
            s.kind.append("snapshot"); s.index.append(i); s.mix.append(0.0)
    n_dis = int(round(dissolve_s * fps))
    for k in range(n_dis):
        t = (k + 1) / (n_dis + 1)
        s.kind.append("dissolve"); s.index.append(n_snapshots - 1); s.mix.append(0.5 - 0.5 * math.cos(math.pi * t))
    for _ in range(int(round(hold_end_s * fps))):
        s.kind.append("design"); s.index.append(n_snapshots - 1); s.mix.append(1.0)
    return s


def orbit_azimuths(n: int, start_deg: float = -28.0, end_deg: float = 28.0) -> np.ndarray:
    """A slow orbit: one gentle ease over the whole clip, no loops."""
    t = np.linspace(0.0, 1.0, max(n, 2))
    e = t * t * (3.0 - 2.0 * t)
    return start_deg + (end_deg - start_deg) * e


# ----------------------------------------------------------------------------- camera
def camera_basis(center: np.ndarray, distance: float, azimuth_deg: float, tilt_deg: float):
    """Camera above the slab's face (+z), tilted off the vertical and swung around z."""
    az, tilt = math.radians(azimuth_deg), math.radians(tilt_deg)
    u = np.array([math.sin(tilt) * math.sin(az), -math.sin(tilt) * math.cos(az), math.cos(tilt)])
    position = center + distance * u
    view_dir = -u
    up0 = np.array([0.0, 1.0, 0.0])
    right = np.cross(view_dir, up0)
    right /= np.linalg.norm(right)
    up = np.cross(right, view_dir)
    return position, view_dir, right, up


def fit_distance(bounds, azimuths, tilt_deg: float, view_angle_deg: float, aspect: float,
                 fit_fraction=(0.9, 0.72), margin: float = 1.04) -> float:
    """Smallest camera distance that keeps the whole slab inside the frame at every orbit angle.

    fit_fraction leaves room for the labels above and below the part."""
    x0, x1, y0, y1, z0, z1 = bounds
    corners = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)])
    center = corners.mean(axis=0)
    tan_v = math.tan(math.radians(view_angle_deg) / 2.0) * fit_fraction[1]
    tan_h = math.tan(math.radians(view_angle_deg) / 2.0) * aspect * fit_fraction[0]
    need = 0.0
    for az in np.asarray(azimuths, dtype=float):
        _, view_dir, right, up = camera_basis(center, 1.0, az, tilt_deg)
        rel = corners - center
        toward_camera = -(rel @ view_dir)  # how far in front of the center plane the corner sits
        need = max(need, float(np.max(np.abs(rel @ right) / tan_h + toward_camera)),
                   float(np.max(np.abs(rel @ up) / tan_v + toward_camera)))
    return need * margin


# ----------------------------------------------------------------------------- slab renderer
class SlabRenderer:
    """Off-screen PyVista scene for one extruded slab: deep near-black stage, three soft lights,
    depth peeling for the translucent cells, super-sampled anti-aliasing."""

    def __init__(self, seq: Sequence, size=(WIDTH, HEIGHT), tilt_deg: float = 34.0,
                 azimuths=(-28.0, 28.0), fit_fraction=(0.9, 0.72)):
        import pyvista as pv
        pv.OFF_SCREEN = True
        self.pv = pv
        self.seq = seq
        self.size = tuple(int(v) for v in size)
        self.tilt = tilt_deg
        nx, ny = seq.nelx, seq.nely
        grid = pv.ImageData(dimensions=(nx + 1, ny + 1, 2), spacing=(seq.h_mm, seq.h_mm, seq.thickness_mm),
                            origin=(0.0, 0.0, 0.0))
        self.base = grid.cast_to_unstructured_grid()
        self.n_nodes_layer = (nx + 1) * (ny + 1)
        self.center = np.array(self.base.center)
        self.distance = fit_distance(self.base.bounds, np.linspace(azimuths[0], azimuths[1], 7), tilt_deg, 30.0,
                                     self.size[0] / self.size[1], fit_fraction)
        self.plotter = pv.Plotter(off_screen=True, window_size=list(self.size), lighting="none")
        self.plotter.set_background(theme.DARK["bg"])
        self._lights()
        self.plotter.enable_depth_peeling(number_of_peels=12, occlusion_ratio=0.0)
        self.plotter.enable_anti_aliasing("ssaa")
        self.actor = None
        # the design frame: the clean checked shape (density >= 0.5, spec 6.8) with nodal utilization
        util_grid = fill_nan_nearest(seq.utilization.reshape(nx + 1, ny + 1))
        self.util_rgba = np.tile(utilization_rgba(nodes_to_vtk(util_grid, nx, ny)), (2, 1))
        self.design_vtk = cells_to_vtk(seq.design, nx, ny)

    def _lights(self):
        pv = self.pv
        c = self.center
        span = float(np.max(self.base.bounds[1::2]) - np.min(self.base.bounds[0::2])) or 1.0
        for pos, intensity in (((-0.3, -0.45, 1.7), 0.80),  # key: high, a little in front and left
                               ((1.3, 0.3, 0.9), 0.35),  # fill: right, lower, softens the walls
                               ((0.3, 1.2, 0.6), 0.30)):  # back light: catches the far walls
            light = pv.Light(position=tuple(c + span * np.array(pos)), focal_point=tuple(c),
                             color="white", intensity=intensity, light_type="scene light")
            light.positional = False
            self.plotter.add_light(light)

    def _mesh(self, cell_rgba: np.ndarray | None, keep: np.ndarray, point_rgba: np.ndarray | None = None):
        sub = self.base.extract_cells(np.flatnonzero(keep))
        if sub.n_cells == 0:
            return None
        if point_rgba is not None:
            sub.point_data["rgba"] = point_rgba[sub.point_data["vtkOriginalPointIds"]]
            scalars, prefer = "rgba", "point"
        else:
            sub.cell_data["rgba"] = cell_rgba[sub.cell_data["vtkOriginalCellIds"]]
            scalars, prefer = "rgba", "cell"
        return sub, scalars, prefer

    def _show(self, mesh_pack, azimuth_deg: float) -> np.ndarray:
        pl = self.plotter
        if self.actor is not None:
            pl.remove_actor(self.actor, render=False)
            self.actor = None
        if mesh_pack is not None:
            sub, scalars, prefer = mesh_pack
            self.actor = pl.add_mesh(sub, scalars=scalars, rgba=True, preference=prefer, ambient=0.20,
                                     diffuse=0.75, specular=0.15, specular_power=20.0, show_scalar_bar=False,
                                     render=False)
        position, view_dir, _, up = camera_basis(self.center, self.distance, azimuth_deg, self.tilt)
        pl.camera.position = tuple(position)
        pl.camera.focal_point = tuple(self.center)
        pl.camera.up = tuple(up)
        pl.camera.view_angle = 30.0
        pl.renderer.ResetCameraClippingRange()
        pl.render()  # off-screen screenshot() does not redraw by itself after the first frame
        img = pl.screenshot(return_img=True)
        return np.asarray(img)[..., :3]

    def render_snapshot(self, index: int, azimuth_deg: float) -> np.ndarray:
        """One saved snapshot: translucent where the density is low, opaque where it is solid."""
        d = cells_to_vtk(self.seq.snapshots[index].astype(float) / 255.0, self.seq.nelx, self.seq.nely)
        return self._show(self._mesh(density_rgba(d), d > VOID_EPS), azimuth_deg)

    def render_design(self, azimuth_deg: float) -> np.ndarray:
        """The checked design, solid cells only, colored by recovered nodal utilization."""
        keep = self.design_vtk >= 0.5
        return self._show(self._mesh(None, keep, point_rgba=self.util_rgba), azimuth_deg)

    def close(self):
        self.plotter.close()


# ----------------------------------------------------------------------------- overlays
_FONT_CACHE: dict = {}


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    key = (size, weight)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    names = {"regular": ["Inter-Regular.ttf", "segoeui.ttf", "arial.ttf"],
             "semibold": ["Inter-SemiBold.ttf", "seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"],
             "light": ["Inter-Light.ttf", "segoeuil.ttf", "segoeuisl.ttf", "segoeui.ttf", "arial.ttf"]}[weight]
    f = None
    for name in names:
        for folder in (Path("C:/Windows/Fonts"), Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
                       Path("/usr/share/fonts"), Path("/Library/Fonts")):
            p = folder / name
            if p.exists():
                try:
                    f = ImageFont.truetype(str(p), size)
                    break
                except OSError:
                    continue
        if f is not None:
            break
    if f is None:
        f = ImageFont.load_default(size)
    _FONT_CACHE[key] = f
    return f


def _tracked(draw: ImageDraw.ImageDraw, xy, text: str, fnt, fill, tracking: float = 0.08):
    """Uppercase eyebrow with letter spacing (PIL has no tracking of its own)."""
    x, y = xy
    size = getattr(fnt, "size", 12)
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + tracking * size
    return x


def _legend(draw: ImageDraw.ImageDraw, x: int, y: int, width: int = 260, height: int = 6):
    for k in range(width):
        c = tuple(int(v) for v in UTIL_LUT[int(k / max(width - 1, 1) * 255)])
        draw.line([(x + k, y), (x + k, y + height)], fill=c)
    draw.rounded_rectangle([x + width + 10, y, x + width + 10 + height, y + height], radius=1,
                           fill=_rgb(theme.OVER_LIMIT))


def overlay(frame: np.ndarray, seq: Sequence, iteration: int, final: bool, scale: float = 1.0,
            caption: str | None = None, show_title: bool = True, note: bool = True) -> np.ndarray:
    """Labels on a rendered frame: process eyebrow, part title, iteration readout, and on the
    final frames the utilization legend and the checked numbers. All text in the theme's tones.
    `scale` sizes text and margins (1.0 = a full 1080p frame)."""
    im = Image.fromarray(frame)
    draw = ImageDraw.Draw(im)
    h, w = frame.shape[:2]
    s = scale
    pad = int(56 * s)
    text, text2 = _rgb(theme.DARK["text"]), _rgb(theme.DARK["text_2"])
    accent = _rgb(theme.PROCESS[seq.process]["color"])
    small = font(int(18 * s), "regular")
    tiny = font(int(13 * s), "regular")
    # eyebrow + title, top left
    _tracked(draw, (pad, pad), seq.label.upper(), font(int(17 * s), "semibold"), accent)
    if show_title:
        draw.text((pad - int(2 * s), pad + int(28 * s)), seq.title, font=font(int(40 * s), "semibold"), fill=text)
    # iteration readout, bottom right (Segoe UI digits are tabular, so the number does not wobble)
    big = font(int(54 * s), "light")
    total = int(seq.iterations[-1])
    txt_big, txt_small = f"{iteration}", f" of {total}"
    wb, ws = draw.textlength(txt_big, font=big), draw.textlength(txt_small, font=small)
    x = w - pad - wb - ws
    yb = h - pad - int(70 * s)
    draw.text((x, yb), txt_big, font=big, fill=text)
    draw.text((x + wb, yb + int(32 * s)), txt_small, font=small, fill=text2)
    lab = ("final design" if final else "iteration").upper()
    lw = draw.textlength(lab, font=tiny) + 0.08 * 13 * s * len(lab)
    _tracked(draw, (w - pad - lw, h - pad - int(4 * s)), lab, tiny, text2)
    # bottom left: legend and checked numbers on the final frames, else the fill level
    if final:
        bar_w, bar_y = int(260 * s), h - pad - int(30 * s)
        _legend(draw, pad, bar_y, width=bar_w, height=int(6 * s))
        draw.text((pad, h - pad - int(16 * s)), "0", font=small, fill=text2)
        draw.text((pad + bar_w - draw.textlength("1", font=small), h - pad - int(16 * s)), "1", font=small, fill=text2)
        draw.text((pad + bar_w + int(30 * s), h - pad - int(16 * s)), "over limit", font=small, fill=text2)
        # a tick where the reported peak (outside the pad exclusion zones, = SF target / SF) sits on the
        # shared scale; the raw nodal peak inside the zones is named when it is higher (spec 6.8)
        raw = seq.utilization_peak
        reported = seq.sf_target / seq.sf if seq.sf > 0 and seq.sf_target > 0 else raw
        if reported > 0:
            px = pad + int(min(reported, 1.0) * (bar_w - 1))
            draw.rectangle([px - 1, bar_y - int(6 * s), px + 1, bar_y + int(11 * s)], fill=text)
            ptxt = f"peak {reported:.2f} outside the pad zones"
            if raw > reported * 1.05:
                ptxt += f"  ·  raw {raw:.2f}"
            tw = draw.textlength(ptxt, font=tiny)
            draw.text((max(pad, min(px - tw / 2, pad + bar_w + int(30 * s))), bar_y - int(26 * s)), ptxt, font=tiny, fill=text)
        _tracked(draw, (pad, h - pad - int(82 * s)), "UTILIZATION · σVM × SF TARGET / STRENGTH", tiny, text2)
        nums = []
        if seq.sf_target:
            nums.append(f"SF {seq.sf:.1f} vs {seq.sf_target:.1f} target")
        if seq.mass_g:
            nums.append(f"{seq.mass_g:.1f} g")
        if seq.deflection_limit_mm:
            nums.append(f"{seq.deflection_mm:.2f} of {seq.deflection_limit_mm:.1f} mm")
        if nums:
            draw.text((pad, h - pad - int(118 * s)), "  ·  ".join(nums), font=font(int(20 * s), "regular"), fill=text)
    else:
        draw.text((pad, h - pad - int(16 * s)),
                  f"fill level {seq.fill * 100:.1f}%  ·  {seq.width_mm:g} × {seq.height_mm:g} × {seq.thickness_mm:g} mm",
                  font=small, fill=text2)
    # quiet footnote in the middle bottom
    foot = caption
    if final and note and not seq.replaced and not foot:
        foot = INDEPENDENT_RUN_NOTE
    if foot:
        fw = draw.textlength(foot, font=small)
        draw.text(((w - fw) / 2, h - pad - int(16 * s)), foot, font=small, fill=text2)
    return np.asarray(im)


def header_strip(width: int, height: int, eyebrow: str, title: str, scale: float = 1.0) -> np.ndarray:
    im = Image.new("RGB", (width, height), _rgb(theme.DARK["bg"]))
    draw = ImageDraw.Draw(im)
    pad = int(56 * scale)
    _tracked(draw, (pad, int(16 * scale)), eyebrow.upper(), font(int(13 * scale), "semibold"), _rgb(theme.DARK["text_2"]))
    draw.text((pad - int(2 * scale), int(34 * scale)), title, font=font(int(26 * scale), "semibold"), fill=_rgb(theme.DARK["text"]))
    return np.asarray(im)


# ----------------------------------------------------------------------------- video
class Mp4Writer:
    """H.264 MP4 through imageio-ffmpeg's bundled ffmpeg; yuv420p so every player opens it."""

    def __init__(self, path: Path, size, fps: int = FPS, crf: int = 18):
        import imageio_ffmpeg
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.size = (int(size[0]), int(size[1]))
        self.gen = imageio_ffmpeg.write_frames(
            str(self.path), size=self.size, fps=fps, codec="libx264", quality=None, macro_block_size=1,
            pix_fmt_in="rgb24", pix_fmt_out="yuv420p",
            output_params=["-crf", str(crf), "-preset", "slow", "-movflags", "+faststart", "-tune", "film"])
        self.gen.send(None)
        self.frames = 0

    def write(self, frame: np.ndarray):
        if frame.shape[1] != self.size[0] or frame.shape[0] != self.size[1]:
            raise ValueError(f"frame {frame.shape[1]}x{frame.shape[0]} does not match {self.size}")
        self.gen.send(np.ascontiguousarray(frame[..., :3], dtype=np.uint8).tobytes())
        self.frames += 1

    def close(self):
        self.gen.close()


def _blend(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    return np.clip(a.astype(np.float32) * (1.0 - t) + b.astype(np.float32) * t, 0, 255).astype(np.uint8)


def _progress(label: str, i: int, n: int, t0: float, log=print):
    if i % 30 == 0 or i == n - 1:
        rate = (i + 1) / max(time.time() - t0, 1e-6)
        log(f"  {label}: frame {i + 1}/{n}  ({rate:.1f} fps render, {(n - i - 1) / max(rate, 1e-6):.0f} s left)")


# ----------------------------------------------------------------------------- sequences
def render_growth(seq: Sequence, out: Path, size=(WIDTH, HEIGHT), fps: int = FPS, frames_per_snapshot: int = 2,
                  hold_start_s: float = 1.0, hold_end_s: float = 4.0, dissolve_s: float = 0.6, step: int = 1,
                  caption: str | None = None, log=print) -> dict:
    """The winning design growing from the first saved snapshot to the checked design."""
    if seq.design_matches_last_snapshot:
        dissolve_s = 0.0  # same field: nothing to dissolve between
    sched = make_schedule(len(seq.snapshots), frames_per_snapshot, hold_start_s, hold_end_s, dissolve_s, fps, step)
    az = orbit_azimuths(len(sched))
    scale = size[1] / HEIGHT
    renderer = SlabRenderer(seq, size=size)
    writer = Mp4Writer(out, size, fps)
    t0 = time.time()
    try:
        last_pic = None
        for k, (kind, idx, mix) in enumerate(zip(sched.kind, sched.index, sched.mix)):
            it = int(seq.iterations[idx])
            if kind == "snapshot":
                pic = overlay(renderer.render_snapshot(idx, az[k]), seq, it, False, scale, caption)
            elif kind == "design":
                pic = overlay(renderer.render_design(az[k]), seq, it, True, scale, caption)
            else:
                a = overlay(renderer.render_snapshot(idx, az[k]), seq, it, False, scale, caption)
                b = overlay(renderer.render_design(az[k]), seq, it, True, scale, caption)
                pic = _blend(a, b, mix)
            writer.write(pic)
            last_pic = pic
            _progress(out.name, k, len(sched), t0, log)
    finally:
        writer.close()
        renderer.close()
    return {"output": str(out), "frames": len(sched), "seconds_video": len(sched) / fps,
            "snapshots": len(seq.snapshots), "iterations": [int(seq.iterations[0]), int(seq.iterations[-1])],
            "dissolve_frames": int(sum(1 for k in sched.kind if k == "dissolve")),
            "design_equals_last_snapshot": seq.design_matches_last_snapshot, "render_seconds": time.time() - t0,
            "size": list(size), "fps": fps, "last_frame": last_pic}


def render_side_by_side(seqs: list[Sequence], out: Path, size=(WIDTH, HEIGHT), fps: int = FPS,
                        frames_per_snapshot: int = 2, hold_start_s: float = 1.0, hold_end_s: float = 4.0,
                        dissolve_s: float = 0.6, step: int = 1, log=print) -> dict:
    """The process designs of one part growing in lockstep, one strip per process.

    Iteration k of every run is shown at the same time; a run that has finished holds its last
    snapshot until the longest run ends, then every strip shows its checked design."""
    if not seqs:
        raise ValueError("no sequences")
    scale = size[1] / HEIGHT
    header_h = int(round(72 * scale))
    strip_h = (size[1] - header_h) // len(seqs)
    header_h = size[1] - strip_h * len(seqs)  # absorb rounding so the stack is exactly the frame height
    n_max = max(len(s.snapshots) for s in seqs)
    sched = make_schedule(n_max, frames_per_snapshot, hold_start_s, hold_end_s,
                          0.0 if all(s.design_matches_last_snapshot for s in seqs) else dissolve_s, fps, step)
    az = orbit_azimuths(len(sched))
    # a flatter view in the strips: the wide parts then fill more of each strip's height
    renderers = [SlabRenderer(s, size=(size[0], strip_h), tilt_deg=26.0, fit_fraction=(0.95, 0.88)) for s in seqs]
    title = seqs[0].title
    labels = ", ".join(theme.PROCESS[s.process]["label"] for s in seqs)
    head = header_strip(size[0], header_h, f"{labels} · one part, {len(seqs)} processes", title, scale)
    tscale = scale * 0.7  # smaller labels and margins inside a strip
    writer = Mp4Writer(out, size, fps)
    t0 = time.time()
    try:
        last_pic = None
        for k, (kind, idx, mix) in enumerate(zip(sched.kind, sched.index, sched.mix)):
            strips = [head]
            for s, r in zip(seqs, renderers):
                i = min(idx, len(s.snapshots) - 1)
                it = int(s.iterations[i])
                if kind == "snapshot":
                    pic = overlay(r.render_snapshot(i, az[k]), s, it, False, tscale, show_title=False, note=False)
                elif kind == "design":
                    pic = overlay(r.render_design(az[k]), s, it, True, tscale, show_title=False, note=False)
                else:
                    a = overlay(r.render_snapshot(i, az[k]), s, it, False, tscale, show_title=False, note=False)
                    b = overlay(r.render_design(az[k]), s, it, True, tscale, show_title=False, note=False)
                    pic = _blend(a, b, mix)
                strips.append(pic)
            frame = np.concatenate(strips, axis=0)
            writer.write(frame)
            last_pic = frame
            _progress(out.name, k, len(sched), t0, log)
    finally:
        writer.close()
        for r in renderers:
            r.close()
    return {"output": str(out), "frames": len(sched), "seconds_video": len(sched) / fps,
            "processes": [s.process for s in seqs], "materials": [s.material for s in seqs],
            "snapshots": [len(s.snapshots) for s in seqs], "render_seconds": time.time() - t0,
            "size": list(size), "fps": fps, "last_frame": last_pic}


# ----------------------------------------------------------------------------- command line
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cinematic MP4 renders from the recorded cold re-run snapshots (S15).")
    ap.add_argument("--part", choices=DEMO_PARTS, help="demo part (cache folder under examples/cache)")
    ap.add_argument("--process", choices=("fdm", "sls", "metal"), help="which cold re-run; default: the winner's")
    ap.add_argument("--side-by-side", action="store_true", help="FDM, SLS and metal designs growing in lockstep")
    ap.add_argument("--all", action="store_true", help="the three winners plus the side-by-side sequence")
    ap.add_argument("--cache", default=str(CACHE_DIR), help="cache root (default examples/cache)")
    ap.add_argument("--out", default=str(RENDERS_DIR), help="output folder (default renders/)")
    ap.add_argument("--frames-per-snapshot", type=int, default=2)
    ap.add_argument("--hold-start", type=float, default=1.0, help="seconds on the first snapshot")
    ap.add_argument("--hold-end", type=float, default=4.0, help="seconds on the final design")
    ap.add_argument("--cut", action="store_true", help="hard cut to the final design instead of a picture dissolve")
    ap.add_argument("--caption", default=None, help="one quiet line at the bottom (e.g. the bone remodeling note)")
    ap.add_argument("--preview", action="store_true", help="960 x 540 and every 6th snapshot, for a quick look")
    ap.add_argument("--still", action="store_true", help="also save the last frame as PNG next to the MP4")
    args = ap.parse_args(argv)
    if not (args.part or args.all):
        ap.error("give --part or --all")
    size = (960, 540) if args.preview else (WIDTH, HEIGHT)
    step = 6 if args.preview else 1
    dissolve = 0.0 if args.cut else 0.6
    cache, out_dir = Path(args.cache), Path(args.out)
    jobs = []
    if args.all:
        jobs += [("growth", p, None) for p in DEMO_PARTS]
        jobs += [("side", "rc_arm", None)]
    elif args.side_by_side:
        jobs.append(("side", args.part, None))
    else:
        jobs.append(("growth", args.part, args.process))
    summary = []
    for kind, part, process in jobs:
        folder = cache / part
        suffix = "_preview" if args.preview else ""
        if kind == "growth":
            seq = load_sequence(folder, process)
            out = out_dir / f"{part}_{seq.process}_{seq.material}_growth{suffix}.mp4"
            print(f"{part}: {seq.label} · {len(seq.snapshots)} snapshots · {seq.nelx} x {seq.nely} cells")
            info = render_growth(seq, out, size, FPS, args.frames_per_snapshot, args.hold_start, args.hold_end,
                                 dissolve, step, args.caption)
        else:
            procs = rerun_processes(folder)
            seqs = [load_sequence(folder, p) for p in procs]
            out = out_dir / f"{part}_side_by_side{suffix}.mp4"
            print(f"{part}: side by side · {', '.join(s.label for s in seqs)}")
            info = render_side_by_side(seqs, out, size, FPS, args.frames_per_snapshot, args.hold_start, args.hold_end,
                                       dissolve, step)
        last = info.pop("last_frame")
        if args.still and last is not None:
            Image.fromarray(last).save(out.with_suffix(".png"))
        print(f"  wrote {out} ({info['frames']} frames, {info['seconds_video']:.1f} s, {info['render_seconds']:.0f} s to render)")
        summary.append(info)
    (out_dir / "last_render.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
