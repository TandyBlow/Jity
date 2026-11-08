// c9 wllama check: can wllama 3.8.1 load a T5 *encoder-decoder*?
//
// The question is not "does wllama work" — it does for llama-family GGUF —
// but "is there a T5 encoder-decoder loader behind its loadModel()". No T5
// GGUF exists in this repo, and llama.cpp's GGUF path names architectures in
// a fixed registry. So the probe feeds loadModel() three minimal, well-formed
// GGUF v3 headers that differ only in general.architecture:
//
//   "t5"          the architecture name a T5 encoder-decoder GGUF would carry
//   "t5encoder"   the encoder-only arch that IS registered (positive control
//                 for arch dispatch: it must get past the arch check and fail
//                 later, on the missing tensors)
//   "notanarch"   negative control: must be rejected as unknown
//
// A T5 encoder-decoder can only be executed if "t5" resolves to a loader.
// Exit code is not a verdict about quality; it records what the loader said.
//
// Usage: node experiments/world-components/parallel/browser_t5/wllama_probe.mjs

import { mkdir, readFile, writeFile } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WT = path.resolve(HERE, "..", "..", "..", "..");
const FRONTEND = path.join(WT, "frontend");
const require2 = createRequire(path.join(FRONTEND, "package.json"));
const { chromium } = require2("@playwright/test");

const WLLAMA = path.join(FRONTEND, "node_modules", "@wllama", "wllama");
const RUN_DIR = path.join(HERE, "runs", process.argv[2] || "wllama1");
const PORT = Number(process.env.C9_WLLAMA_PORT || 3211);
const ARCHS = ["t5", "t5encoder", "notanarch"];

/** Minimal GGUF v3: header + one metadata string KV (general.architecture),
 *  zero tensors. Valid framing; llama.cpp rejects it later if the arch is
 *  unknown, which is exactly what this probe measures. */
function minimalGguf(arch) {
  const enc = new TextEncoder();
  const parts = [];
  const u32 = (n) => { const b = Buffer.alloc(4); b.writeUInt32LE(n); return b; };
  const u64 = (n) => { const b = Buffer.alloc(8); b.writeBigUInt64LE(BigInt(n)); return b; };
  const str = (s) => { const b = enc.encode(s); return Buffer.concat([u64(b.length), Buffer.from(b)]); };
  parts.push(Buffer.from("GGUF", "ascii"), u32(3), u64(0), u64(1));
  parts.push(str("general.architecture"), u32(8), str(arch)); // 8 = GGUF_TYPE_STRING
  return Buffer.concat(parts);
}

const MIME = { ".html": "text/html; charset=utf-8", ".mjs": "text/javascript",
  ".js": "text/javascript", ".wasm": "application/wasm",
  ".gguf": "application/octet-stream", ".json": "application/json" };

function serve(port) {
  const server = http.createServer(async (req, res) => {
    const p = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const m = /^\/gguf\/([a-z0-9]+)\.gguf$/.exec(p);
    try {
      let body;
      let type = null;
      if (p === "/" || p === "/index.html") {
        body = await readFile(path.join(HERE, "wllama_probe.html"));
        type = "text/html; charset=utf-8";
      }
      else if (p === "/wllama/index.js") body = await readFile(path.join(WLLAMA, "esm", "index.js"));
      else if (p === "/wllama/wllama.wasm") body = await readFile(path.join(WLLAMA, "esm", "wasm", "wllama.wasm"));
      else if (m) body = minimalGguf(m[1]);
      else { res.writeHead(404); res.end("no"); return; }
      res.writeHead(200, { "content-type": type ?? MIME[path.extname(p)] ?? "application/octet-stream",
                           "cache-control": "no-store",
                           "cross-origin-opener-policy": "same-origin",
                           "cross-origin-embedder-policy": "require-corp" });
      res.end(body);
    } catch (e) {
      res.writeHead(500); res.end(String(e));
    }
  });
  return new Promise((r) => server.listen(port, "127.0.0.1", () => r(server)));
}

await mkdir(RUN_DIR, { recursive: true });
for (const a of ARCHS) {
  await writeFile(path.join(RUN_DIR, `minimal-${a}.gguf`), minimalGguf(a));
}

const server = await serve(PORT);
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage();
page.on("console", (m) => console.log(`[console:${m.type()}]`, m.text()));
page.on("pageerror", (e) => console.log("[pageerror]", String(e).slice(0, 800)));
page.on("requestfailed", (r) => console.log("[reqfail]", r.url(), r.failure()?.errorText));
page.on("response", (r) => { if (!r.ok()) console.log("[http]", r.status(), r.url()); });
await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: "domcontentloaded" });
try {
  await page.waitForFunction("window.__C9_WLLAMA__ !== undefined", null, { timeout: 240000 });
} catch (e) {
  console.log("[timeout] page state:", await page.evaluate(
    "({ ready: typeof window.__C9_WLLAMA__, body: document.getElementById('out')?.textContent?.slice(0, 800) })"));
  await browser.close(); server.close(); process.exit(2);
}
const result = await page.evaluate("window.__C9_WLLAMA__");
const version = JSON.parse(await readFile(path.join(WLLAMA, "package.json"), "utf8")).version;
await browser.close();
server.close();

const archive = {
  purpose: "c9 wllama check: is a T5 encoder-decoder loadable at all through "
           + "wllama's GGUF API, and what does the loader say per arch name",
  environment: { wllama: version, browser: browser.version(),
                 wasm: "esm/wasm/wllama.wasm from the installed package",
                 note: "GGUFs are 3 hand-built minimal v3 headers that differ "
                       + "only in general.architecture; they are not models" },
  archs: ARCHS,
  result,
  conclusion: "see report; the encoder-only arch is a positive control for "
              + "dispatch, the t5 arch answers the encoder-decoder question",
};
const out = path.join(RUN_DIR, "wllama-result.json");
await writeFile(out, JSON.stringify(archive, null, 1) + "\n", "utf-8");
console.log("wrote", out);
console.log(JSON.stringify(result, null, 1));
