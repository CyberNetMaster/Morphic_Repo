import http from "node:http";
import { readFile } from "node:fs/promises";

const files = new Map([
  ["/", ["index.html", "text/html; charset=utf-8"]],
  ["/agentation.js", ["agentation.js", "text/javascript; charset=utf-8"]],
  ["/agentation.js.LEGAL.txt", ["agentation.js.LEGAL.txt", "text/plain; charset=utf-8"]],
]);
http.createServer(async (req, res) => {
  const headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Private-Network": "true",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Cross-Origin-Resource-Policy": "cross-origin",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  };
  if (!["127.0.0.1:8766", "localhost:8766"].includes(req.headers.host)) {
    res.writeHead(403); res.end(); return;
  }
  if (req.method === "OPTIONS") { res.writeHead(204, headers); res.end(); return; }
  if (!["GET", "HEAD"].includes(req.method)) { res.writeHead(405, headers); res.end(); return; }
  const file = files.get(new URL(req.url, "http://127.0.0.1:8766").pathname);
  if (!file) { res.writeHead(404, headers); res.end(); return; }
  try {
    const body = await readFile(new URL(`dist/${file[0]}`, import.meta.url));
    res.writeHead(200, { ...headers, "Content-Type": file[1] });
    res.end(req.method === "HEAD" ? undefined : body);
  } catch {
    res.writeHead(503, headers); res.end("Run npm run build first.");
  }
}).listen(8766, "127.0.0.1", () => console.log("Agentation bookmarklet: http://127.0.0.1:8766 (loopback only)"));
