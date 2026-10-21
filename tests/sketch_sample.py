"""A sample hand sketch drawn in code, and the fixed answer a fake vision LLM gives for it.

The part, in mm: a bracket 120 x 40, 6 thick. Two Ø6 bolt holes at (10, 10) and (10, 30) hold it
to a wall on the left. A Ø6 hole at (110, 20) carries 250 N downward. A Ø16 keep-out circle sits at
(60, 20). Deflection limit 0.5 mm. The heights of the load hole and of the keep-out circle have no
dimension, so a reader must scale them from the drawing.

Write the image for a live test:  python -m tests.sketch_sample
"""

from __future__ import annotations

import io
import math
import random
from pathlib import Path

import matplotlib
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PNG = ROOT / "examples" / "sketches" / "bracket_sketch.png"
APPROVED_JSON = ROOT / "examples" / "sketches" / "bracket_sketch.json"

SIZE = (1800, 1150)
PX_PER_MM = 10.0
ORIGIN_PX = (300, 800)  # pixel position of the part's bottom-left corner
PAPER = (247, 245, 238)
RULE = (198, 214, 236)
MARGIN = (232, 172, 172)
PENCIL = (52, 54, 66)
# DejaVu Sans ships with matplotlib (a dependency) and has "Ø", so the image is the same everywhere.
FONT = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"

# What a vision LLM returns for the sample (the parser's draft schema), fixed for the tests.
FAKE_ANSWER = """{
  "name": "Bracket",
  "design_space": {"width_mm": 120, "height_mm": 40},
  "thickness_mm": 6,
  "zones": [{"id": "keep_out_1", "kind": "keep_out", "shape": "circle",
             "circle": {"cx": 60, "cy": 20, "r": 8}}],
  "pads": [
    {"id": "A", "cx": 10, "cy": 10, "hole_r_mm": 3, "ring_r_mm": null, "solid": false},
    {"id": "B", "cx": 10, "cy": 30, "hole_r_mm": 3, "ring_r_mm": null, "solid": false},
    {"id": "L", "cx": 110, "cy": 20, "hole_r_mm": 3, "ring_r_mm": null, "solid": false}
  ],
  "supports": [{"pad_id": "A", "type": "pin"}, {"pad_id": "B", "type": "pin"}],
  "load_cases": [{"id": "c1", "name": "Load", "reason": "",
                  "loads": [{"pad_id": "L", "fx_N": 0, "fy_N": -250, "fz_N_out_of_plane": 0}],
                  "max_deflection_mm": 0.5}],
  "deflection_span_ratio": null,
  "safety_factor": null,
  "printer": null,
  "materials": null,
  "original_text": {
    "design_space.width_mm": "120",
    "design_space.height_mm": "40",
    "thickness_mm": "t = 6 mm",
    "pads[0].hole_r_mm": "2x Ø6 bolted",
    "pads[1].hole_r_mm": "2x Ø6 bolted",
    "pads[2].hole_r_mm": "Ø6",
    "load_cases[0].loads[0].fy_N": "250 N",
    "load_cases[0].max_deflection_mm": "max deflection 0.5 mm"
  },
  "warnings": [
    "Pad L height scaled from the drawing: y = 20 mm.",
    "Keep-out circle height scaled from the drawing: y = 20 mm."
  ]
}"""


def _px(x: float, y: float) -> tuple[float, float]:
    return ORIGIN_PX[0] + x * PX_PER_MM, ORIGIN_PX[1] - y * PX_PER_MM


class _Pen:
    """Pencil strokes with a small, smooth wobble and overshoot, in part coordinates (mm, y up)."""

    def __init__(self, img: Image.Image, seed: int):
        self.img = img
        self.draw = ImageDraw.Draw(img)
        self.rng = random.Random(seed)

    def line(self, a, b, width: int = 4, overshoot: bool = True) -> None:
        (x0, y0), (x1, y1) = _px(*a), _px(*b)
        length = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        e0, e1 = (self.rng.uniform(2, 7), self.rng.uniform(2, 7)) if overshoot else (0.0, 0.0)
        a1, a2, ph = self.rng.uniform(-2.2, 2.2), self.rng.uniform(-1.2, 1.2), self.rng.uniform(0, 2 * math.pi)
        n = max(2, int(length / 12))
        pts = []
        for i in range(n + 1):
            t = i / n
            s = -e0 + t * (length + e0 + e1)
            off = a1 * math.sin(math.pi * t) + a2 * math.sin(2 * math.pi * t + ph)
            pts.append((x0 + ux * s - uy * off, y0 + uy * s + ux * off))
        self.draw.line(pts, fill=PENCIL, width=width, joint="curve")

    def circle(self, c, r_mm: float, width: int = 4) -> None:
        cx, cy = _px(*c)
        r = r_mm * PX_PER_MM
        start, ph = self.rng.uniform(0, 2 * math.pi), self.rng.uniform(0, 2 * math.pi)
        amp = self.rng.uniform(0.02, 0.05) * r
        sweep = 2 * math.pi + 0.35  # the pencil runs past its start point
        pts = []
        for i in range(97):
            t = sweep * i / 96
            rr = r + amp * math.sin(2 * t + ph)
            pts.append((cx + rr * math.cos(start + t), cy + rr * math.sin(start + t)))
        self.draw.line(pts, fill=PENCIL, width=width, joint="curve")

    def arrow(self, tail, tip, head_mm: float = 3.0, width: int = 4) -> None:
        self.line(tail, tip, width, overshoot=False)
        ang = math.atan2(tip[1] - tail[1], tip[0] - tail[0])
        for side in (1, -1):
            t = ang + math.pi - side * math.radians(24)
            self.line(tip, (tip[0] + head_mm * math.cos(t), tip[1] + head_mm * math.sin(t)), width, overshoot=False)

    def dim(self, a, b, label: str, at) -> None:
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        self.arrow(mid, a, 1.8, 3)
        self.arrow(mid, b, 1.8, 3)
        self.text(label, at)

    def text(self, s: str, at, size: int = 38) -> None:
        font = ImageFont.truetype(str(FONT), size)
        x0, y0, x1, y1 = self.draw.textbbox((0, 0), s, font=font)
        layer = Image.new("RGBA", (x1 - x0 + 20, y1 - y0 + 20), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((10 - x0, 10 - y0), s, font=font, fill=PENCIL + (255,))
        layer = layer.rotate(self.rng.uniform(-3, 3), resample=Image.BICUBIC, expand=True)
        x, y = _px(*at)
        self.img.paste(layer, (int(x - layer.width / 2), int(y - layer.height / 2)), layer)

    def hatch_circle(self, c, r_mm: float, step_mm: float = 1.7) -> None:
        r = 0.92 * r_mm
        k = int(r / step_mm)
        for i in range(-k, k + 1):
            d = i * step_mm
            h = math.sqrt(max(r * r - d * d, 0.0))
            # 45-degree lines: offset d along (1, -1), half chord h along (1, 1)
            ox, oy = c[0] + d / math.sqrt(2), c[1] - d / math.sqrt(2)
            hx = h / math.sqrt(2)
            self.line((ox - hx, oy - hx), (ox + hx, oy + hx), width=2, overshoot=False)


def draw_sample() -> Image.Image:
    """The sample sketch as an RGB image. Deterministic: same pixels on every call."""
    img = Image.new("RGB", SIZE, PAPER)
    paper = ImageDraw.Draw(img)
    for y in range(60, SIZE[1], 34):  # ruled notebook paper
        paper.line([(0, y), (SIZE[0], y)], fill=RULE, width=2)
    paper.line([(70, 0), (70, SIZE[1])], fill=MARGIN, width=2)
    pen = _Pen(img, seed=7)

    # outline and the wall on the left
    for a, b in (((0, 0), (120, 0)), ((120, 0), (120, 40)), ((120, 40), (0, 40)), ((0, 40), (0, 0))):
        pen.line(a, b, width=5)
    pen.line((-1.5, -6), (-1.5, 46), width=4)
    for y in range(-4, 47, 3):
        pen.line((-1.5, y), (-5, y - 3.5), width=2, overshoot=False)

    # holes with centre marks
    for c in ((10, 10), (10, 30), (110, 20)):
        pen.circle(c, 3.0)
        pen.line((c[0] - 4.5, c[1]), (c[0] + 4.5, c[1]), width=2, overshoot=False)
        pen.line((c[0], c[1] - 4.5), (c[0], c[1] + 4.5), width=2, overshoot=False)
    pen.line((10, 49), (11.6, 33.2), width=2, overshoot=False)  # leader to the bolt label
    pen.text("2x Ø6 bolted", (12, 52))
    pen.text("Ø6", (101, 25.5))

    # keep-out circle
    pen.circle((60, 20), 8.0)
    pen.hatch_circle((60, 20), 8.0)
    pen.text("keep out Ø16", (60, 7))

    # load
    pen.arrow((110, 62), (110, 23.6), head_mm=3.0, width=5)
    pen.text("250 N", (118, 56), size=42)

    # dimensions: hole heights inside the part, keep-out position on top, lengths below, height right
    pen.line((13.5, 10), (21.5, 10), width=2, overshoot=False)
    pen.line((13.5, 30), (21.5, 30), width=2, overshoot=False)
    pen.dim((20, 0), (20, 10), "10", (23.5, 5))
    pen.dim((20, 10), (20, 30), "20", (23.5, 20))
    pen.line((0, 41), (0, 48), width=2, overshoot=False)
    pen.line((60, 29), (60, 48), width=2, overshoot=False)
    pen.dim((0, 46), (60, 46), "60", (30, 49.5))
    pen.line((0, -1), (0, -21), width=2, overshoot=False)
    pen.line((10, 6.5), (10, -7), width=2, overshoot=False)
    pen.line((110, 16.5), (110, -21), width=2, overshoot=False)
    pen.line((120, -1), (120, -14), width=2, overshoot=False)
    pen.dim((0, -5), (10, -5), "10", (5, -8.5))
    pen.dim((0, -12), (120, -12), "120", (60, -15.5))
    pen.dim((0, -19), (110, -19), "110", (55, -22.5))
    pen.line((121, 0), (134, 0), width=2, overshoot=False)
    pen.line((121, 40), (134, 40), width=2, overshoot=False)
    pen.dim((132, 0), (132, 40), "40", (137, 20))

    # notes
    pen.text("BRACKET", (-12, 72), size=44)
    pen.text("t = 6 mm", (40, 70))
    pen.text("max deflection 0.5 mm", (52, 64))
    return img.rotate(0.8, resample=Image.BICUBIC, fillcolor=PAPER)  # held a little crooked


def sample_png() -> bytes:
    buf = io.BytesIO()
    draw_sample().save(buf, "PNG", optimize=True)
    return buf.getvalue()


if __name__ == "__main__":
    SAMPLE_PNG.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE_PNG.write_bytes(sample_png())
    print(f"wrote {SAMPLE_PNG.relative_to(ROOT)}")
