"""Capture labelled local fixtures for sketch interpretation and a saved agent run."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".plans/reports/screens"
BASE = "http://127.0.0.1:8797"
evidence = {"captured_utc": datetime.now(timezone.utc).isoformat(), "screens": [],
            "sketch": "Fixed test-provider interpretation; not a live vision result",
            "agent": "Replay of drone-agent-backoff.json; not a new agent run"}


def capture(page, name, locator=None):
    page.locator('[data-testid="stStatusWidget"]').wait_for(state="hidden", timeout=360_000)
    assert page.locator('[data-testid="stException"]').count() == 0
    if locator is None:
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.wait_for_timeout(1500)
        height = page.locator(".block-container").evaluate("e => Math.ceil(e.scrollHeight + 160)")
        page.set_viewport_size({"width": 1440, "height": min(height, 16000)})
        for _ in range(5):
            page.wait_for_timeout(1500)
            bottom = page.locator(".block-container").evaluate("e => Math.ceil(e.getBoundingClientRect().bottom)")
            if bottom + 24 <= page.viewport_size["height"]:
                break
            page.set_viewport_size({"width": 1440, "height": min(bottom + 48, 16000)})
        assert bottom <= page.viewport_size["height"]
    path = OUT / f"{name}.png"
    if locator is None:
        page.screenshot(path=str(path), full_page=True)
    else:
        locator.screenshot(path=str(path))
    evidence["screens"].append({"file": str(path.relative_to(ROOT)),
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    print(f"Captured {name}", flush=True)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(
        (BASE + "/", "data:", "blob:")) else route.abort())
    page = context.new_page()
    page.goto(BASE + "/?step=0&capture=sketch")
    upload = page.locator(".st-key-sketch_upload")
    upload.wait_for(timeout=180_000)
    capture(page, "sketch-1-describe")
    capture(page, "sketch-2-control", upload)
    upload.locator('input[type="file"]').set_input_files(str(ROOT / "examples/sketches/bracket_sketch.png"))
    page.locator('.st-key-sketch_btn button:not([disabled])').wait_for(timeout=30_000)
    page.wait_for_timeout(1500)
    capture(page, "sketch-3-chosen", upload)
    upload.locator('[data-testid="stFileUploaderDropzone"]').hover()
    page.wait_for_timeout(500)
    capture(page, "sketch-4-hover", upload)
    page.locator(".st-key-sketch_btn button").click()
    page.locator(".st-key-card_interpretation_warnings").wait_for(timeout=120_000)
    page.get_by_role("button", name="Generate designs", exact=True).wait_for(timeout=120_000)
    evidence["warnings"] = page.locator(".st-key-card_interpretation_warnings").inner_text()
    capture(page, "sketch-5-check")
    page.close()

    page = context.new_page()
    page.goto(BASE + "/?demo=drone_arm&step=2&capture=agent")
    review = page.get_by_role("button", name="Review recommended design", exact=True)
    review.wait_for(timeout=360_000)
    page.get_by_role("button", name="Export →", exact=True).wait_for(timeout=360_000)
    capture(page, "6-drone-agent")
    # Crop around the agent's containing card; the full view carries the replay label.
    panel = page.locator(".st-key-agent_panel")
    assert "Design agent" in panel.inner_text() or "DESIGN AGENT" in panel.inner_text()
    assert "Recommendation:" in panel.inner_text()
    capture(page, "6-drone-agent-panel", panel)
    review.click()
    page.get_by_role("button", name="Generate designs", exact=True).wait_for(timeout=120_000)
    assert page.get_by_text("Check the problem", exact=True).count() > 0
    capture(page, "7-agent-review")
    page.close()
    browser.close()

(ROOT / ".plans/reports/phase3-extra-screens.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
