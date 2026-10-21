"""Capture the integrated app locally using installed Chrome; no external browser traffic."""
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / ".plans/reports"
SCREENS = REPORTS / "screens"
PORT = sys.argv[1] if len(sys.argv) > 1 else "8765"
BASE = f"http://127.0.0.1:{PORT}"
SHOTS = {
    "1-describe": "?step=0",
    "2-check": "?demo=rc_arm&step=1",
    "3-compare": "?demo=rc_arm&step=2",
    "4-export": "?demo=rc_arm&step=3",
    "5-validation": "?tab=validation",
}


def ready(page, name):
    page.wait_for_selector(".mx-title", timeout=180_000)
    if name == "1-describe":
        page.locator(".st-key-sketch_upload").wait_for(timeout=180_000)
    if name == "5-validation":
        page.locator(".st-key-card_hole").wait_for(timeout=180_000)
    if name == "4-export":
        page.get_by_role("button", name="Run bundle (zip)", exact=True).wait_for(timeout=180_000)
    if name == "3-compare":
        page.get_by_role("button", name="Explore design changes", exact=True).wait_for(timeout=360_000)
        page.get_by_role("button", name="Export →", exact=True).wait_for(timeout=360_000)
    page.locator('[data-testid="stSpinner"]').wait_for(state="hidden", timeout=360_000)
    page.locator('[data-testid="stStatusWidget"]').wait_for(state="hidden", timeout=360_000)
    assert page.locator('[data-testid="stException"]').count() == 0


def capture(page, name):
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.wait_for_timeout(1500)
    height = page.locator(".block-container").evaluate("e => Math.ceil(e.scrollHeight + 160)")
    page.set_viewport_size({"width": 1440, "height": min(height, 16000)})
    page.wait_for_timeout(1500)
    # Streamlit scrolls inside its main section. Re-measure after chart reflow so
    # the lower material cards and footer are included, not clipped by that section.
    for _ in range(4):
        bottom = page.locator(".block-container").evaluate("e => Math.ceil(e.getBoundingClientRect().bottom)")
        if bottom + 24 <= page.viewport_size["height"]:
            break
        page.set_viewport_size({"width": 1440, "height": min(bottom + 48, 16000)})
        page.wait_for_timeout(1500)
    assert bottom <= page.viewport_size["height"], "Content exceeds the screenshot viewport"
    path = SCREENS / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return {"file": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "viewport": page.viewport_size}


with sync_playwright() as playwright:
    SCREENS.mkdir(exist_ok=True)
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(
        (BASE + "/", f"http://localhost:{PORT}/", "data:", "blob:")) else route.abort())
    evidence = {"captured_utc": datetime.now(timezone.utc).isoformat(), "url": BASE, "screens": [],
                "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    for name, query in SHOTS.items():
        page = context.new_page()
        page.goto(BASE + "/" + query)
        ready(page, name)
        if name == "1-describe":
            for stem in ("rc_arm", "drone_arm", "aero_bracket"):
                assert page.locator(f".st-key-preview_{stem}").count() > 0
            evidence["describe_upload_controls"] = page.locator('input[type="file"]').count()
            assert evidence["describe_upload_controls"] == 1
        if name == "3-compare":
            evidence["explanation"] = page.locator(".st-key-card_explain").inner_text()
        if name == "4-export":
            downloads = {}
            for label, filename in (("PDF report", "phase3-report.pdf"), ("Run bundle (zip)", "phase3-run.zip")):
                button = page.get_by_role("button", name=label, exact=True)
                assert button.is_enabled()
                with page.expect_download() as download:
                    button.click()
                target = ROOT / ".plans/live_runs" / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                download.value.save_as(str(target))
                downloads[label] = target.read_bytes()
            with zipfile.ZipFile(io.BytesIO(downloads["Run bundle (zip)"])) as archive:
                assert archive.read("report.pdf") == downloads["PDF report"]
                manifest = json.loads(archive.read("manifest.json"))
                assert all(hashlib.sha256(archive.read(n)).hexdigest() == digest
                           for n, digest in manifest["files"].items())
            evidence["pdf_matches_bundle"] = True
            evidence["bundle_checksums_pass"] = True
        evidence["screens"].append(capture(page, name))
        print(f"Captured {name}", flush=True)
        page.close()
    (REPORTS / "phase3-browser-acceptance.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    browser.close()
