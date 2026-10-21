# Workspace F

Sketch to design. Date: 2026-10-21. Branch: `emdash/f-sketch-0l68c`.

Everything stayed on this computer. There was no push, no remote change, no pull request and no upload. No live API call was made. No key was read or printed: this worktree has no `.env`.

## What it does

1. On the Describe step, the user picks a photo of a hand sketch and clicks **Read my sketch**. Any text in the description box goes with the photo as a typed note.
2. `morphic/sketch.py` prepares the photo and sends it to a vision LLM through the adapter (`morphic/llm.py`). Gemini and Claude both work.
3. The LLM answers in the text parser's draft JSON. The parser's own code then fills the defaults and records where each value came from. The existing Pydantic schema validates the result. A bad answer gets one retry with the error, the same as for text.
4. The app opens the existing Check screen. The existing sanity checks run there. The user confirms the drawing or fixes values before anything runs.

A failure opens the manual form, the same as a failed text parse. A file that is not a usable image stays on the Describe step with a red message, and no LLM call is made.

## Files

| File | Change |
|---|---|
| `morphic/sketch.py` | New. Photo preparation, the prompt, `read_sketch()`, and a command line (`python -m morphic.sketch`). |
| `morphic/llm.py` | `complete()` takes an optional `image` and an optional `provider`. Text requests are unchanged. |
| `app/sketch_upload.py` | New. The upload control and its CSS. All values come from `app/theme.py` tokens. |
| `app/streamlit_app.py` | Two added lines: one import on its own line, and one call right after the text box. |
| `examples/sketches/bracket_sketch.png` | Sample sketch, drawn in code by `tests/sketch_sample.py`. |
| `examples/sketches/bracket_sketch.json` | The approved problem for the sample, used to compare a reading. |
| `tests/sketch_sample.py` | Draws the sample and holds the fixed fake-LLM answer. |
| `tests/test_sketch.py` | New. 27 tests. |
| `.plans/reports/sketch_shot.py`, `sketch_fake_app.py` | Browser screenshot script, and a wrapper that runs the app with the fake LLM. |

No engine module was changed. `problem.py`, `parse.py`, `sanity.py`, `config.py`, `form.py` and the solver modules are untouched. The sketch code imports the parser's `Draft`, `complete_draft`, `schema_text`, `ParseFailed` and `ParseResult`.

## How the sketch is read

The prompt has sketch rules first, then the text parser's own rules and schema, copied from `parse.SYSTEM_PROMPT` at import time. A later change to the parser's rules therefore also applies to sketches.

The sketch rules:

- The design space is the smallest rectangle around the drawn outline. The origin is its bottom-left corner, y up. The prompt warns that photo rows run downward.
- A non-rectangular outline gets keep-out rectangles for the empty parts of that rectangle. Hatched or "keep out" regions are keep-out zones. "Keep" or "solid" regions are keep-in zones.
- Written dimensions win over the drawing. Positions or sizes with no written dimension are scaled from the drawing, and each one is named in `warnings`. With no dimension at all, sizes are scaled from an assumed 100 mm longest side, with a warning.
- Hole sizes, forces, thickness and limits that are not written stay unset. A default then shows in amber on the Check screen, or a red check (for example "no force") asks for the value.
- Support symbols: a bolt, pin, hatched wall or "fixed" means a pin. Rollers or "slides" means `slide_x` or `slide_y`. An edge held along its length gets two solid pin pads and a warning.
- Arrows are loads on the pad they touch. The arrowhead gives the sign and the label gives the size. Different labels or colors mean different load cases.
- If the typed note and the sketch disagree, the note wins and a warning says so.
- If the photo is not a part sketch, the LLM returns `{"not_a_sketch": "..."}`. The read then stops at once, with no retry.

Provenance: each label the LLM quotes is stored with a `sketch: ` prefix (for example "sketch: t = 6 mm"), unless the quote comes from the typed note. The Check screen then shows `from the text: "sketch: t = 6 mm"`.

## Photo preparation

- The camera's EXIF rotation is applied. Transparency becomes white.
- The photo is shrunk to at most 2576 px on the long edge and 3.75 megapixels. This is the largest image Claude Opus 5.x reads at full detail (from the Claude API reference). Gemini accepts the same size. A smaller photo is not enlarged.
- It is saved as JPEG at quality 90. If the result is over 4.5 MB, quality drops to 80, then 70. The sample sketch becomes a 266 KB JPEG.
- These files are refused with a plain message: empty files, files that are not images, files over 20 MB, and photos under 300 px on the short side.
- The result keeps the SHA-256 of the uploaded file, so a problem can be traced back to its photo.

## Providers

- Gemini: the image goes as `types.Part.from_bytes(...)` before the text, with the same JSON response type as text requests.
- Claude: the image goes as a base64 `image` block before the text. Image requests get `max_tokens=16000`. Claude Opus 5.5 always thinks, and thinking counts toward `max_tokens`, so 4096 could cut off the answer.
- `llm.complete(..., provider="claude")` picks a provider for one call. The default is still `config.LLM_PROVIDER` (`gemini`).
- The adapter's retry rule is the same as for text: HTTP 429 and 503 are retried four times with 4, 8, 16 and 32 s waits, and the image is sent again each time.
- Time limit: 90 s per attempt for a sketch. The spec gives text 45 s, and reading a drawing takes longer. The worst case, with all transport retries, is 515 s before the manual form opens.

## Tests

`tests/test_sketch.py` has 27 tests. All use fakes, so none makes a network call.

- Sample: the drawing is the same on every run and matches the committed PNG.
- Photo preparation: size limits, RGB JPEG output, transparency to white, EXIF rotation, and the four refused cases.
- Adapter: the exact Gemini and Claude request shapes (fake SDK clients), the image before the text, text requests unchanged, the provider override, the image resent on a 503 retry, and an unknown provider refused.
- Reading the sample with a fake LLM that returns fixed JSON. The result matches `bracket_sketch.json` and no sanity check blocks the run. The tests also check the request (photo, sketch rules, parser rules, schema) and the provenance (labels marked `sketch:`, defaults marked default, two "scaled from the drawing" warnings).
- A typed note goes with the photo, and quotes from the note keep no `sketch:` prefix.
- One retry with the error and the same photo, then `ParseFailed`. A "not a sketch" answer stops with no retry. LLM error, timeout and a bad file are each tested. The bad file fails before any LLM call.
- The default call goes through the adapter, and the wait allows for the adapter's retries (515 s).
- Command line: a match gives exit code 0, and a difference gives exit code 2 with the list.
- Describe control (Streamlit AppTest with a real file upload): the read goes to the Check step with the printer selector applied and the note sent. A bad file stays on Describe with a red message. A failed read opens the manual form. The CSS uses only theme tokens.

Full suite on the committed code: **179 passed in 369.35 s** (152 before this work, plus 27). An earlier run, before a last prompt-wording change, also gave 179 passed, in 168.80 s. The final run was slower because other work ran on the laptop at the same time. Command:

```powershell
& C:/Users/night/projects/morphic/.venv/Scripts/python.exe -m pytest -p no:cacheprovider -q -o addopts="" --junitxml=.plans/reports/sketch-tests.xml
```

Record: `.plans/reports/sketch-tests.xml`.

Browser check: the app ran on 127.0.0.1 and was driven by the installed Chrome through Playwright from the local uv cache (`uv run --offline`). Nothing was downloaded. Screens are in `.plans/reports/screens/`:

- `sketch-1-describe.png`: the Describe step with the control under the text box.
- `sketch-2-control.png`, `sketch-3-chosen.png`, `sketch-4-hover.png`: the control empty, with a file chosen, and on hover.
- `sketch-5-check.png`: the Check screen after **Read my sketch**. For this run the app was started through `sketch_fake_app.py`, which swaps in the fake LLM.

The first screenshots showed two layout faults: the dropzone covered the note line, and the button label was cut off. Both are fixed: the note now has an inline bottom margin, as the demo-parts card does, and the button column is wider.

## For the live test tomorrow

Run these from a checkout that has your `.env`. The adapter reads only the `.env` next to the code, and this worktree has none.

```powershell
uv run python -m morphic.sketch examples/sketches/bracket_sketch.png --provider gemini --expect examples/sketches/bracket_sketch.json
uv run python -m morphic.sketch examples/sketches/bracket_sketch.png --provider claude --expect examples/sketches/bracket_sketch.json
uv run python -m morphic.sketch my_sketch.jpg --note "Desktop FDM printer" --out my_problem.json
```

Exit code 0 means the reading matches the approved problem. Exit code 2 prints each difference. A good reading of the sample should also print two warnings: the height of pad L and the height of the keep-out circle (both y = 20 mm) have no dimension on the sketch. The `--provider claude` run needs `ANTHROPIC_API_KEY` in `.env`.

In the app (`uv run streamlit run app/streamlit_app.py`), choose a photo under "Or a sketch" and click **Read my sketch**.

## Open points for you to decide

1. **Warnings are not shown on the Check screen.** This is true for text and sketches. For a sketch they matter more, because they name the values scaled from the drawing. I did not change the Check screen, because the task limited the UI change to the Describe control. A one-line list of `problem.warnings` at the top of the Check screen would show them. This could go into the Describe/Check redesign.
2. **Time limit for sketches is 90 s per attempt.** The spec has no sketch step. Text keeps 45 s.
3. **Claude text requests still use `max_tokens=4096`.** Opus 5.5 always thinks, and thinking counts toward that limit, so a long text parse on Claude could be cut off. I did not change the text path. If you switch text parsing to Claude, consider 16000.
4. **The failure banner says "Could not read the description"** also for a sketch. That text is on the Check screen, which I did not change.
5. **The 5 MB per-image Claude limit** is from my knowledge of the API docs. I did not check it today. The code keeps images under 4.5 MB.
6. **Gemini image detail**: `types.Part.from_bytes` accepts a `media_resolution` option. I kept the default. If Gemini misreads small handwritten numbers tomorrow, this is the setting to try.
7. **iPhone HEIC photos are not accepted.** Browsers usually convert them to JPEG on upload. If not, export the photo as JPEG.
8. **Merge note.** The state hand-off after a read (printer selector and session values) is copied from `read_description` into `app/sketch_upload.py` (a few lines). This keeps the change to `streamlit_app.py` at two lines. If the redesign changes that hand-off, change both. The only other shared file is `morphic/llm.py`.
