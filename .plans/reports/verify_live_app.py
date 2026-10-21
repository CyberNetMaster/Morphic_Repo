"""Local browser acceptance: live drone exploration, exports and screenshots. No uploads."""
import hashlib
import io
import json
import sys
import time
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
SCREENS = OUT / "screens"
PORT = sys.argv[1] if len(sys.argv) > 1 else "8765"


def ready(page):
    page.wait_for_selector(".mx-title", timeout=180_000)
    page.locator('[data-testid="stSpinner"]').wait_for(state="hidden", timeout=180_000)
    assert page.locator('[data-testid="stException"]').count() == 0


def screenshot(page, name):
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.wait_for_timeout(1200)
    height = page.locator('.block-container').evaluate("e => Math.ceil(e.scrollHeight + 150)")
    page.set_viewport_size({"width": 1440, "height": min(height, 16000)})
    page.wait_for_timeout(1600)
    page.screenshot(path=str(SCREENS / f"{name}.png"), full_page=True)
    print(f"Screenshot saved: {name}", flush=True)


with sync_playwright() as p:
    SCREENS.mkdir(exist_ok=True)
    browser = p.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    # Browser traffic stays on localhost. Gemini is called by the existing Python adapter.
    context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(
        (f"http://127.0.0.1:{PORT}/", f"http://localhost:{PORT}/", "data:", "blob:")) else route.abort())
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{PORT}/?demo=drone_arm&step=2")
    ready(page)
    page.get_by_role("button", name="Explore design changes", exact=True).click()
    print("Live drone-arm exploration started through Compare.", flush=True)
    panel = page.locator('.st-key-agent_panel')
    deadline = time.monotonic() + 1800
    last = ""
    while page.get_by_role("button", name="Exploration log", exact=True).count() == 0:
        if time.monotonic() > deadline:
            raise TimeoutError("Agent did not finish within 30 minutes")
        assert not page.locator('[data-testid="stException"]').count()
        alerts = panel.locator('[data-testid="stAlert"]').all_text_contents()
        status = " ".join(alerts)
        if "Exploration failed" in status:
            raise RuntimeError("App reported an exploration failure")
        if status and status != last:
            print(status, flush=True)
            last = status
        page.wait_for_timeout(10000)
    with page.expect_download() as download:
        page.get_by_role("button", name="Exploration log", exact=True).click()
    log_path = OUT / "drone-agent-live.json"
    download.value.save_as(str(log_path))
    log = json.loads(log_path.read_text())
    assert log["llm"]["provider"] == "gemini"
    live_proposals = sum(row.get("proposal", {}).get("source") == "llm"
                         for row in log["rounds"] if row.get("proposal"))
    print(f"Live run complete: {len(log['rounds'])} rounds, {live_proposals} LLM proposals; "
          f"recommendation from {log['recommendation']['source']}.", flush=True)
    screenshot(page, "6-drone-agent")
    panel.screenshot(path=str(SCREENS / "6-drone-agent-panel.png"))
    # Verify the actual browser handoff to Check using the winning round's knobs.
    target = next(row for row in log["rounds"] if row["index"] == log["recommendation"]["round"])
    page.get_by_role("button", name="Review recommended design", exact=True).click()
    page.get_by_text("Check the problem", exact=True).wait_for()
    assert float(page.get_by_label("Thickness (mm)", exact=True).input_value()) == target["knobs"]["thickness_mm"]
    assert float(page.get_by_label("Height (mm)", exact=True).input_value()) == target["knobs"]["design_space"]["height_mm"]
    screenshot(page, "7-agent-review")
    evidence = {"live_proposals": live_proposals, "recommendation_source": log["recommendation"]["source"],
                "provider": log["llm"], "review_matches_recommendation": True, "screens": []}
    shots = {"1-describe": "?step=0", "2-check": "?demo=rc_arm&step=1",
             "3-compare": "?demo=rc_arm&step=2", "4-export": "?demo=rc_arm&step=3",
             "5-validation": "?tab=validation"}
    for name, query in shots.items():
        shot = context.new_page()
        shot.goto(f"http://127.0.0.1:{PORT}/{query}")
        ready(shot)
        if name == "3-compare":
            shot.get_by_role("button", name="Explore design changes", exact=True).wait_for()
            evidence["explanation"] = shot.locator('.st-key-card_explain').inner_text()
        if name == "4-export":
            downloads = {}
            for label, filename in (("PDF report", "integrated-report.pdf"), ("Run bundle (zip)", "integrated-run.zip")):
                button = shot.get_by_role("button", name=label, exact=True)
                assert button.is_enabled()
                with shot.expect_download() as received:
                    button.click()
                path = ROOT / ".plans" / "live_runs" / filename
                received.value.save_as(str(path))
                downloads[label] = path.read_bytes()
            with zipfile.ZipFile(io.BytesIO(downloads["Run bundle (zip)"])) as archive:
                assert archive.read("report.pdf") == downloads["PDF report"]
                manifest = json.loads(archive.read("manifest.json"))
                assert all(hashlib.sha256(archive.read(n)).hexdigest() == digest
                           for n, digest in manifest["files"].items())
            evidence["pdf_matches_bundle"] = True
            evidence["bundle_checksums_pass"] = True
        screenshot(shot, name)
        evidence["screens"].append(name)
        shot.close()
    (OUT / "browser-acceptance.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    browser.close()
