# Local Agentation bookmarklet

Standalone dev tool. No Streamlit source changes, plugins, app dependencies or MCP setup.

## Use

1. Open http://127.0.0.1:8766 and drag **Agentation (local)** to your bookmarks bar.
2. Open http://127.0.0.1:8765 and click the bookmark.
3. Click the bottom-right toolbar launcher, click an element, type a note, and click **Add**.
4. Click **Copy feedback**, then paste it into the coding-agent conversation.
5. Click **Exit** to interact with the app again. Click the bookmark a second time to remove the toolbar.

The complete bookmark URL is in `bookmarklet.txt` and on the setup page. Add it to a bookmark's URL field, not the browser search field. Keep the static server running. Refreshing removes the toolbar; click the bookmark to mount it again. Saved notes remain in the page origin's localStorage unless cleared in Agentation.

## Restart / rebuild

From this directory:

```powershell
npm.cmd start
```

If rebuilding or restoring the dev dependencies:

```powershell
npm.cmd ci --ignore-scripts --no-audit --no-fund
npm.cmd run build
npm.cmd start
```

The initial server was launched hidden. To stop it, identify the listener with `Get-NetTCPConnection -LocalPort 8766 -State Listen`, verify its process is this Node server, and stop that process. Do not start another server on the same port.

## Scope and privacy

- Pins Agentation 3.1.2, React/React DOM 19.2.0 and esbuild 0.25.12 in a private npm project.
- The single minified bundle includes React, React DOM, Agentation and its styles: 637,378 bytes in this build. No CDN or runtime downloads.
- Production-mode React keeps the bundle small; use is dev-only because injection is manual and nothing imports it into the app.
- The server binds to 127.0.0.1:8766 and serves only the setup page, bundle and third-party license notices. No filesystem browsing or write API.
- No annotation endpoint is configured. The build additionally disables fetch/EventSource within Agentation's module, including user-configured or previously saved webhooks. The host app's network functions and live LLM adapter are untouched.
- Notes stay in browser localStorage. Copying to the clipboard is manual; no automatic agent connection or upload.
- Global Agentation keyboard shortcuts are disabled to avoid conflicts with Streamlit. Its toolbar and popup controls still work.
- node_modules, generated dist files, screenshots, test output and server logs are ignored by the dev folder's own .gitignore.

## Limits

Designed for ordinary desktop web pages. Restrictive Content Security Policy, browser internal pages and browser local-network permissions can prevent injection. The bookmark reports loading errors; this is not a CSP bypass.

The package isolates its toolbar styling in Shadow DOM. Same-origin page elements are selectable; cross-origin iframe contents remain inaccessible.

Streamlit steps share a pathname, so their notes share a storage bucket. Include the step name in each note and review notes on the screen where they were created. Canvas/chart internals may be represented by their enclosing element. Feedback is selector-based; Streamlit's Python source locations are not available to the toolbar.

## Verification (2026-10-21)

`verify.py` ran using installed Chrome and an isolated browser profile against the real app on port 8765. Passed: actual javascript-link injection, note creation, selector/text output, clipboard equality (allowing Windows line endings), survival of a Streamlit step transition, removal and remount. Zero browser page errors and zero external browser requests. The server's listener was verified as 127.0.0.1; a path outside its allowlist returned 404.

Local screenshots, copied sample feedback and JSON results are under `evidence/`. The app's Python suite was not rerun because no app code or dependencies changed.

Upstream installation/API reference: https://www.agentation.com/install
