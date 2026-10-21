"""Screenshot the Describe step with the sketch upload control, before and after a file is chosen.
Clicks "Read my sketch" only with the word "read", and only against sketch_fake_app.py (a fake LLM).

Run (app already running on the port):
    uv run --offline --no-project --with playwright python .plans/reports/sketch_shot.py [port] [read]
Uses the installed Chrome (channel="chrome"); nothing is downloaded.
"""

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8799"
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "screens"
SAMPLE = ROOT / "examples" / "sketches" / "bracket_sketch.png"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    page.goto(f"http://127.0.0.1:{PORT}/?step=0", wait_until="networkidle")
    page.wait_for_selector(".st-key-sketch_upload", timeout=120_000)
    time.sleep(3)
    page.screenshot(path=str(OUT / "sketch-1-describe.png"), full_page=True)
    page.locator(".st-key-sketch_upload").screenshot(path=str(OUT / "sketch-2-control.png"))
    page.locator('.st-key-sketch_upload input[type="file"]').set_input_files(str(SAMPLE))
    page.wait_for_selector('.st-key-sketch_btn button:not([disabled])', timeout=30_000)
    time.sleep(2)
    page.locator(".st-key-sketch_upload").screenshot(path=str(OUT / "sketch-3-chosen.png"))
    hover = page.locator('.st-key-sketch_upload [data-testid="stFileUploaderDropzone"]')
    hover.hover()
    time.sleep(0.5)
    page.locator(".st-key-sketch_upload").screenshot(path=str(OUT / "sketch-4-hover.png"))
    if "read" in sys.argv[2:]:
        page.locator(".st-key-sketch_btn button").click()
        page.wait_for_selector(".mx-title:has-text('Check the problem')", timeout=120_000)
        time.sleep(6)  # plotly drawing and data editors
        h = page.evaluate("""() => Math.max(...[document.querySelector('[data-testid="stMain"]'),
                                               document.body].filter(Boolean).map(e => e.scrollHeight))""")
        page.set_viewport_size({"width": 1440, "height": min(int(h) + 40, 6000)})
        time.sleep(4)
        page.screenshot(path=str(OUT / "sketch-5-check.png"), full_page=True)
    browser.close()
print("saved", *sorted(x.name for x in OUT.glob("sketch-*.png")))
