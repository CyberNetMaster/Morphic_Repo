import { build } from "esbuild";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
process.chdir(fileURLToPath(new URL(".", import.meta.url)));

await build({
  entryPoints: ["src.jsx"],
  outfile: "dist/agentation.js",
  bundle: true,
  format: "iife",
  platform: "browser",
  target: ["chrome110", "firefox115", "safari16"],
  minify: true,
  define: { "process.env.NODE_ENV": '"production"' },
  legalComments: "linked",
  // Restrict only the standalone annotation package, never the host page's fetch.
  // Even a saved/custom webhook cannot send page content out of this local tool.
  plugins: [{ name: "local-feedback-only", setup(builder) {
    builder.onLoad({ filter: /agentation[\\/]dist[\\/]index\.mjs$/ }, async ({ path }) => ({
      contents: `const fetch = () => Promise.reject(new Error("Network sync is disabled in this local bookmarklet"));
const EventSource = class { constructor() { throw new Error("Network sync is disabled in this local bookmarklet"); } };
` + await readFile(path, "utf8"),
      loader: "js",
    }));
  }}],
});
const bookmarklet = (await readFile("bookmarklet.txt", "utf8")).trim();
const attr = bookmarklet.replaceAll("&", "&amp;").replaceAll('"', "&quot;");
await mkdir("dist", { recursive: true });
await writeFile("dist/index.html", `<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Local Agentation bookmarklet</title>
<style>body{font:17px system-ui;max-width:780px;margin:64px auto;padding:24px;background:#151515;color:#eee;line-height:1.6}a{color:#8ccaff}a.bookmark{display:inline-block;padding:14px 24px;border-radius:12px;background:#246dde;color:white;text-decoration:none}textarea{width:100%;height:150px;background:#222;color:#eee}code{color:#acd6ff}</style>
<h1>Agentation · local bookmarklet</h1>
<p>Drag this button to your browser's bookmarks bar:</p>
<p><a class="bookmark" href="${attr}">Agentation (local)</a></p>
<p>Open <a href="http://127.0.0.1:8765">Morphic</a>, then click the bookmark. Click the toolbar at the bottom right, select an element, write a note and choose Add. Copy the feedback and paste it into your coding-agent chat.</p>
<p>Click the bookmark again to remove the toolbar. Reloading also removes it; saved notes remain in this browser. Keep this local server running.</p>
<p>If dragging is unavailable, create a bookmark and paste this entire line into its URL field:</p>
<textarea readonly aria-label="Bookmarklet URL">${bookmarklet.replaceAll("&", "&amp;").replaceAll("<", "&lt;")}</textarea>
<p>No sync endpoint, webhooks or remote assets. Notes stay in the page origin's localStorage until you copy or delete them. This is a manual dev tool; nothing is installed in the app.</p>
<p>Desktop ordinary web pages only. Browser internal pages and restrictive CSP policies may block injection. Streamlit steps share the same pathname, so include the step name in each note.</p></html>`);
console.log("Built dist/agentation.js and local bookmark setup page.");
