"""Local Chrome acceptance check; uses an isolated browser profile, not user notes."""
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "evidence"
OUT.mkdir(exist_ok=True)
bookmarklet = (ROOT / "bookmarklet.txt").read_text().strip()


def invoke(page):
    page.evaluate("""url => {
      const a = document.createElement('a'); a.id = 'test-bookmarklet';
      a.href = url; a.textContent = 'Test bookmarklet';
      a.style = 'position:fixed;left:2px;top:2px;z-index:2147483647;background:white;color:black';
      document.body.appendChild(a);
    }""", bookmarklet)
    page.locator("#test-bookmarklet").click()
    page.locator("#test-bookmarklet").evaluate("e => e.remove()")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1050},
                                  permissions=["clipboard-read", "clipboard-write"])
    unexpected = []
    errors = []
    context.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname in
                  ("127.0.0.1", "localhost", None) else (unexpected.append(route.request.url), route.abort())[-1])
    page = context.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8766")
    assert page.get_by_role("link", name="Agentation (local)").get_attribute("href") == bookmarklet
    page.goto("http://127.0.0.1:8765/?step=0")
    page.locator(".st-key-sketch_upload").wait_for(timeout=120_000)
    invoke(page)
    start = page.get_by_role("button", name="Start feedback mode", exact=True)
    start.wait_for(timeout=30_000)
    page.screenshot(path=str(OUT / "01-mounted.png"), full_page=True)
    start.click()
    page.locator(".mx-title").first.click()
    note = page.get_by_placeholder("What should change?", exact=True)
    note.wait_for(timeout=15_000)
    note.fill("Describe step: make the heading a little smaller. Local bookmarklet acceptance test.")
    page.screenshot(path=str(OUT / "02-note-editor.png"), full_page=True)
    page.get_by_role("button", name="Add", exact=True).click()
    page.wait_for_timeout(1000)
    print("Annotation added; toolbar buttons:", page.locator('[data-agentation-toolbar] button').evaluate_all(
        "els => els.map(e => e.getAttribute('aria-label'))"), flush=True)
    page.get_by_role("button", name="Copy feedback", exact=True).click()
    page.wait_for_function("window.__morphicAgentation.lastOutput.includes('Local bookmarklet acceptance test')")
    output = page.evaluate("window.__morphicAgentation.lastOutput")
    clipboard = page.evaluate("navigator.clipboard.readText()")
    assert output.replace("\r\n", "\n") == clipboard.replace("\r\n", "\n"), "Copied feedback differs from callback output"
    assert "heading" in output.lower() or "mx-title" in output
    (OUT / "copied-feedback.txt").write_text(output, encoding="utf-8")
    page.screenshot(path=str(OUT / "03-saved-note.png"), full_page=True)
    page.get_by_role("button", name="Exit", exact=True).click()
    # Trigger a real Streamlit rerun and step transition with the external root mounted.
    page.get_by_role("button", name="Open RC car arm", exact=True).click()
    page.get_by_role("button", name="Generate designs", exact=True).wait_for(timeout=120_000)
    assert page.locator("#morphic-dev-agentation").count() == 1
    assert page.get_by_role("button", name="Start feedback mode", exact=True).is_visible()
    assert page.locator('[data-testid="stException"]').count() == 0
    page.screenshot(path=str(OUT / "04-after-streamlit-rerun.png"), full_page=True)
    invoke(page)
    assert page.locator("#morphic-dev-agentation").count() == 0
    invoke(page)
    page.get_by_role("button", name="Start feedback mode", exact=True).wait_for()
    assert page.locator("#morphic-dev-agentation").count() == 1
    assert not errors, errors
    assert not unexpected, unexpected
    result = {"passed": True, "annotation_add": True, "clipboard_copy": True,
              "streamlit_rerun_survives": True, "toggle_remove_remount": True,
              "page_errors": errors, "external_requests": unexpected,
              "app": "http://127.0.0.1:8765", "bundle": "http://127.0.0.1:8766/agentation.js"}
    (OUT / "acceptance.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    browser.close()
