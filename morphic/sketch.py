"""Photo of a hand sketch -> checked Problem: the text parser's result, read from a drawing.

The user photographs a sketch (part outline, holes or bolt positions, load arrows, written
dimensions). A vision LLM reads it through `llm.complete(image=...)`, with Gemini or Claude.
The answer is the parser's draft JSON, so `parse.complete_draft` fills the same defaults with
the same provenance, and the result goes through the same schema, sanity checks and Check
screen as a typed description.

Flow (it mirrors parse.parse_text):
1. Normalize the photo: apply the camera's EXIF rotation, flatten transparency onto white,
   and shrink it to at most 2576 px on the long edge and 3.75 megapixels, the largest image
   Claude Opus reads at full detail (Gemini accepts the same). Re-encode as JPEG.
2. Send the image, an optional typed note and the draft schema. Invalid JSON or a failed
   validation is retried ONCE with the error sent back (with the image again).
3. Each HTTP attempt may take SKETCH_TIMEOUT_S; the adapter retries HTTP 429/503. Any other
   failure raises parse.ParseFailed, and the app opens the manual form as it does for text.

Written numbers are used as written. Positions with no written dimension are scaled from the
drawing and named in `warnings`. Hole sizes, forces and limits that are not written stay unset,
so a default (amber on the Check screen) or a red sanity check asks the user for them.

Run on one photo (a live call; the provider's key is read from .env):
    python -m morphic.sketch photo.jpg [--note TEXT] [--provider gemini|claude] [--expect problem.json]
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import functools
import hashlib
import io
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image as PILImage
from PIL import ImageOps, UnidentifiedImageError
from pydantic import ValidationError

from . import config, llm, parse
from .problem import Problem

ACCEPTED_TYPES = ("png", "jpg", "jpeg", "webp")
MAX_UPLOAD_MB = 20
MIN_SHORT_EDGE_PX = 300  # smaller photos cannot show handwritten numbers
MAX_EDGE_PX = 2576  # Claude Opus 5.x full-detail limit: 2576 px long edge, 3.75 MP
MAX_PIXELS = 3_750_000
MAX_IMAGE_BYTES = 4_500_000  # under the Claude API's 5 MB per-image limit
JPEG_QUALITIES = (90, 80, 70)
# Spec 4.4 gives a typed description 45 s per attempt. Reading a drawing takes longer.
SKETCH_TIMEOUT_S = 90.0

# The JSON rules shared with the text parser, from "Rules:" through "Schema (JSON Schema):".
_GENERAL_RULES = parse.SYSTEM_PROMPT.partition("Rules:\n")[2] or parse.SYSTEM_PROMPT

SYSTEM_PROMPT = """You read a photo of a hand sketch of a load-bearing part and turn it into JSON for a 2D \
structural design tool. Return ONLY one JSON object that matches the schema below. No prose, no code fences. \
If the photo does not show a sketch of a part, return {"not_a_sketch": "<one short sentence>"} instead.

Reading the sketch:
- The design space is the smallest rectangle around the drawn outline of the part. The origin is its \
bottom-left corner, x to the right, y UP. The photo's rows run downward, so a mark near the top of the part \
has a large y.
- If the outline is not a rectangle, add a keep_out rect zone for each empty region inside that rectangle \
(for an L shape, the missing corner). A hatched or shaded region inside the part, or one marked "keep out" \
or "no material", is a keep_out zone. A region marked "keep", "solid" or "must stay" is a keep_in zone.
- Written dimensions win over the drawing. A dimension runs between its arrowheads or extension lines. \
"Ø" or "dia" is a diameter, "R" is a radius, "M4" is a 4 mm bolt.
- A position or size with no written dimension is scaled from the drawing, using the written dimensions as \
the scale. Name every scaled value in `warnings`, for example "Pad L height scaled from the drawing: \
y = 20 mm". If no dimension is written at all, scale from an assumed 100 mm longest side and say so in \
`warnings`.
- Holes and bolt or pin positions are pads. Leave hole_r_mm null when no size is written for a hole.
- Supports: a bolt, screw or pin at a hole, a hatched wall or ground next to it, a triangle on hatching, or \
a word such as "fixed", "bolted" or "clamped" is a "pin". A support on small circles (rollers), or marked \
"slides" or "roller", is "slide_x" when it can move left-right and "slide_y" when it can move up-down. An \
edge held along its length without holes (a hatched wall, "welded", "clamped") gets two solid pin pads near \
the ends of that edge, inside the outline, and a warning.
- Loads: every arrow that pushes or pulls on the part is a load on the pad the arrow touches. If no hole is \
there, add a solid pad (solid=true). The arrowhead gives the direction: an arrow pointing down is a negative \
fy_N. The number written next to the arrow is the size; a mass such as "5 kg" is a weight in kgf. If an \
angle is written, resolve the force with it; if not, use the drawn direction and add a warning. If no size \
is written, set the force to 0 and add a warning: the tool will ask the user for it.
- Arrows labelled with different case names or numbers, or drawn in different colors, are separate load \
cases (at most 4). Otherwise all arrows are one load case.
- Notes written on the sketch (thickness such as "t = 6", safety factor, deflection limit, printer, \
material) are read like a typed description.
- If a typed note is given, it adds to the sketch. When the note and the sketch disagree, follow the note \
and add a warning.
- If a mark is unclear, use the most likely reading and add a warning that says what you assumed.

The general rules below are the ones for typed descriptions. Here "the text" means the words and numbers \
written on the sketch, plus the typed note. Scaling a position or size from the drawing counts as reading \
it, not inventing it. In original_text, quote each label exactly as written (for example "Ø6" or "250 N"). \
A value scaled from the drawing has no original_text entry.

General rules:
""" + _GENERAL_RULES


class SketchImageError(ValueError):
    """The upload cannot be used as a sketch photo. The message is plain English for the user."""


@dataclass
class SketchResult(parse.ParseResult):
    image: llm.Image | None = None  # exactly what was sent to the LLM
    upload_sha256: str = ""  # of the uploaded file, so a problem can be traced to its photo


def prepare_image(data: bytes) -> llm.Image:
    """Return the photo as an upright RGB JPEG within the size limits."""
    if not data:
        raise SketchImageError("The file is empty.")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise SketchImageError(f"The file is {len(data) / 1024 / 1024:.0f} MB. The limit is {MAX_UPLOAD_MB} MB.")
    try:
        with PILImage.open(io.BytesIO(data)) as src:
            img = ImageOps.exif_transpose(src)  # phone photos store their rotation in EXIF
            img.load()
        if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            img = PILImage.new("RGB", rgba.size, "white")
            img.paste(rgba, mask=rgba.getchannel("A"))
        else:
            img = img.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, PILImage.DecompressionBombError):
        raise SketchImageError("This file is not a PNG, JPEG or WebP image that can be opened.") from None
    w, h = img.size
    if min(w, h) < MIN_SHORT_EDGE_PX:
        raise SketchImageError(f"The photo is {w} x {h} px, too small to read. Use at least "
                               f"{MIN_SHORT_EDGE_PX} px on the short side.")
    scale = min(1.0, MAX_EDGE_PX / max(w, h), math.sqrt(MAX_PIXELS / (w * h)))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), PILImage.LANCZOS)
    for quality in JPEG_QUALITIES:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        if buf.tell() <= MAX_IMAGE_BYTES:
            break
    return llm.Image(data=buf.getvalue(), mime_type="image/jpeg")


def user_prompt(note: str = "", error: str | None = None, previous: str | None = None) -> str:
    msg = "The sketch photo is attached."
    msg += f"\n\nTyped note:\n\"\"\"\n{note.strip()}\n\"\"\"" if note.strip() else "\n\nThere is no typed note."
    if error:
        msg += (f"\n\nYour previous answer was not valid. Error:\n{error}\n\nPrevious answer:\n{previous}\n\n"
                "Return a corrected JSON object.")
    return msg


def _mark_sketch_labels(problem: Problem, note: str) -> None:
    """Prefix "sketch: " to quoted labels that are not in the typed note, so the Check screen
    says where each value came from."""
    typed = " ".join(note.lower().split())
    for pv in problem.provenance.values():
        quote = pv.original_text.strip()
        if pv.source == "user" and quote and " ".join(quote.lower().split()) not in typed:
            pv.original_text = f"sketch: {quote}"


def _default_llm(system: str, user: str, image: llm.Image, timeout_s: float, provider: str | None = None):
    return llm.complete(system, user, timeout_s, image=image, provider=provider)


_POOL = cf.ThreadPoolExecutor(max_workers=2, thread_name_prefix="morphic-sketch")


def read_sketch(data: bytes, note: str = "", *, llm_call: Callable | None = None, provider: str | None = None,
                timeout_s: float = SKETCH_TIMEOUT_S, retries: int = config.LLM_RETRIES,
                min_walls: list[float] | None = None,
                status: Callable[[str], None] | None = None) -> SketchResult:
    """Read a sketch photo. Raises SketchImageError for a file that cannot be used (before any
    LLM call) and parse.ParseFailed after the allowed attempts.

    ``llm_call(system, user, image, timeout_s)`` replaces the adapter in tests.
    """
    image = prepare_image(data)
    if llm_call is None:
        # Let the adapter finish its bounded transport retries before showing the fallback.
        call = functools.partial(_default_llm, provider=provider)
        wait_s = llm.request_timeout_budget(timeout_s) + 5
    else:
        call, wait_s = llm_call, timeout_s
    system = SYSTEM_PROMPT + parse.schema_text()
    attempts: list[dict] = []
    error = previous = None
    t0 = time.perf_counter()
    for attempt in range(1 + retries):
        if status:
            status("Reading your sketch... if this takes too long, a manual form will open.")
        ta = time.perf_counter()
        fut = _POOL.submit(call, system, user_prompt(note, error, previous), image, timeout_s)
        try:
            res = fut.result(timeout=wait_s)
        except cf.TimeoutError:
            attempts.append({"attempt": attempt + 1, "error": f"timeout after {wait_s:g} s",
                             "seconds": time.perf_counter() - ta})
            raise parse.ParseFailed(f"the LLM did not answer within {wait_s:g} s", attempts)
        except Exception as exc:  # the adapter has already handled transport retries
            attempts.append({"attempt": attempt + 1, "error": f"{type(exc).__name__}: {exc}",
                             "seconds": time.perf_counter() - ta})
            raise parse.ParseFailed(f"LLM call failed: {type(exc).__name__}: {exc}", attempts)
        raw = getattr(res, "text", res)
        rec = {"attempt": attempt + 1, "seconds": time.perf_counter() - ta, "raw": raw,
               "provider": getattr(res, "provider", ""), "model": getattr(res, "model", "")}
        try:
            obj = json.loads(parse._strip_json(raw))
            if isinstance(obj, dict) and "not_a_sketch" in obj and "pads" not in obj:
                attempts.append(rec)
                reason = str(obj["not_a_sketch"]).strip().rstrip(".")[:200]
                raise parse.ParseFailed(f"the photo does not look like a part sketch ({reason})", attempts)
            draft = parse.Draft.model_validate(obj)
            problem = parse.complete_draft(draft, min_walls)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            error, previous = str(exc)[:4000], raw[:8000]
            rec["error"] = error
            attempts.append(rec)
            continue
        _mark_sketch_labels(problem, note)
        attempts.append(rec)
        return SketchResult(problem=problem, draft=draft, raw=raw, attempts=attempts,
                            seconds=time.perf_counter() - t0, provider=rec["provider"], model=rec["model"],
                            image=image, upload_sha256=hashlib.sha256(data).hexdigest())
    raise parse.ParseFailed("the LLM answer did not validate after the allowed retry", attempts)


# ----------------------------------------------------------------------------- command line
def main(argv: list[str] | None = None) -> int:
    from . import sanity
    from .materials import load_materials, load_processes
    from .problem import problem_from_dict, problem_to_dict

    ap = argparse.ArgumentParser(prog="python -m morphic.sketch",
                                 description="Read a sketch photo into a checked problem (a live LLM call).")
    ap.add_argument("photo", type=Path)
    ap.add_argument("--note", default="", help="typed note sent with the photo")
    ap.add_argument("--provider", choices=sorted(llm._PROVIDERS),
                    help=f"default: config.LLM_PROVIDER ({config.LLM_PROVIDER})")
    ap.add_argument("--out", type=Path, help="write the problem JSON here instead of printing it")
    ap.add_argument("--expect", type=Path, help="approved problem JSON to compare the result with")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # LLM warnings may hold characters the console lacks
        sys.stdout.reconfigure(errors="replace")

    materials, processes = load_materials(), load_processes()
    try:
        r = read_sketch(args.photo.read_bytes(), args.note, provider=args.provider,
                        min_walls=[p.min_wall_mm for p in processes.values()], status=print)
    except (SketchImageError, parse.ParseFailed) as exc:
        print(f"Could not read the sketch: {exc}")
        return 1
    p = r.problem
    print(f"{r.provider} {r.model}: {len(r.attempts)} attempt(s) in {r.seconds:.1f} s")
    for w in p.warnings:
        print(f"warning: {w}")
    for m in sanity.check(p, processes, materials):
        print(m)
    text = json.dumps(problem_to_dict(p), indent=2, ensure_ascii=False) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"wrote {args.out}")
    else:
        print(text, end="")
    if args.expect:
        want = problem_from_dict(json.loads(args.expect.read_text(encoding="utf-8")))
        diffs = parse.compare_problems(p, want)
        print("Matches the approved problem." if not diffs else "\n".join(["Differences:"] + diffs))
        return 0 if not diffs else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
