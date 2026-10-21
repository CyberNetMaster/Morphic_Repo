"""Screenshot every app screen. Run: uv run --with playwright python .plans/reports/shoot.py [port]
Uses the installed Chrome (channel="chrome"), nothing is downloaded."""

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8765"
OUT = Path(__file__).parent / "screens"
SHOTS = {
    "1-describe": "?step=0",
    "2-check": "?demo=rc_arm&step=1",
    "3-compare": "?demo=rc_arm&step=2",
    "4-export": "?demo=rc_arm&step=3",
    "5-validation": "?tab=validation",
}

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    for name, q in SHOTS.items():
        page.goto(f"http://localhost:{PORT}/{q}", wait_until="networkidle")
        page.wait_for_selector(".mx-title", timeout=120_000)
        for _ in range(60):  # wait for spinners and the running indicator to go away
            busy = page.evaluate("""() => !!document.querySelector('[data-testid="stSpinner"]')
                || !!document.querySelector('[data-testid="stStatusWidget"]')""")
            if not busy:
                break
            time.sleep(1)
        time.sleep(4)  # plotly, images, fonts
        # Streamlit scrolls inside its main section, so size the viewport to the content
        h = page.evaluate("""() => {
            const els = [document.querySelector('[data-testid="stAppViewContainer"]'),
                         document.querySelector('[data-testid="stMain"]'), document.body, document.documentElement];
            return Math.max(...els.filter(Boolean).map(e => e.scrollHeight));
        }""")
        page.set_viewport_size({"width": 1440, "height": min(int(h) + 40, 9000)})
        time.sleep(5)  # charts re-layout after the resize
        path = OUT / f"{name}.png"
        # clip at the bottom of the content block (the measured height overshoots)
        bottom = page.evaluate("document.querySelector('.block-container').getBoundingClientRect().bottom")
        page.screenshot(path=str(path), full_page=True,
                        clip={"x": 0, "y": 0, "width": 1440, "height": int(bottom) + 40})
        print(name, "ok", int(bottom) + 40)
    browser.close()
