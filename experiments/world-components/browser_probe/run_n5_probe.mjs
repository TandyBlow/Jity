// N5 browser probe driver (commit 3): stages the trained MiniRBT relation
// head (ONNX), the committed adapter + page, the real vocab and the baked
// cases; drives headless Edge; archives ids/logits/labels/timings.
//
// Parity target: the export archive's HF logits and ORT-python logits.
// The label is the frozen dev-fixed threshold rule, applied identically
// on both sides — the browser never fits anything.
//
// Usage: node experiments/world-components/browser_probe/run_n5_probe.mjs

import { cp, mkdir, readFile, writeFile } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..", "..");
const FRONTEND = path.join(REPO, "frontend");
const require2 = createRequire(path.join(FRONTEND, "package.json"));
const { chromium } = require2("@playwright/test");

const PORT = 3203;
const ONNX = path.join(REPO, "experiments", "world-components", "n4_corpus_v2",
                      "onnx-n5", "n5-encoder-head.onnx");
const CKPT = path.join(REPO, "experiments", "world-components", "n4_corpus_v2",
                       "ckpt-n5");
const SERVE_ROOT = path.join(FRONTEND, "public");
const BASE = path.join(SERVE_ROOT, "models", "n5-probe");
const ARCHIVE = path.join(REPO, "artifacts", "world-components",
                          "n5-browser-probe.json");

async function stage() {
  await mkdir(BASE, { recursive: true });
  await cp(ONNX, path.join(BASE, "n5-encoder-head.onnx"));
  await cp(path.join(CKPT, "vocab.txt"), path.join(BASE, "vocab.txt"));
  await cp(path.join(HERE, "n5_browser_adapter.mjs"),
           path.join(BASE, "n5_browser_adapter.mjs"));
  await cp(path.join(HERE, "n5_probe.html"), path.join(BASE, "index.html"));
  await cp(path.join(HERE, "n5_probe_cases.json"),
           path.join(BASE, "probe_cases.json"));
  const ortPkg = JSON.parse(await readFile(path.join(
      FRONTEND, "node_modules", "onnxruntime-web", "package.json"), "utf8"));
  return { ortWebVersion: ortPkg.version };
}

function serve(root, port) {
  const mime = { ".html": "text/html", ".mjs": "text/javascript",
                 ".js": "text/javascript", ".json": "application/json",
                 ".wasm": "application/wasm",
                 ".onnx": "application/octet-stream" };
  return new Promise((resolve) => {
    const server = http.createServer(async (req, res) => {
      try {
        const p = path.join(root,
          decodeURIComponent(new URL(req.url, "http://x").pathname));
        const body = await readFile(p);
        res.writeHead(200, {
          "content-type": mime[path.extname(p)] ?? "application/octet-stream",
          "cache-control": "no-store" });
        res.end(body);
      } catch {
        res.writeHead(404);
        res.end("no");
      }
    });
    server.listen(port, "127.0.0.1", () => resolve(server));
  });
}

const versions = await stage();
const server = await serve(SERVE_ROOT, PORT);
const browser = await chromium.launch({ channel: "msedge" });
const page = await browser.newPage();
await page.goto(
  `http://127.0.0.1:${PORT}/models/n5-probe/index.html?v=${Date.now()}`,
  { waitUntil: "domcontentloaded" });
await page.waitForFunction("window.__N5_PROBE_RESULT__ !== undefined",
                           null, { timeout: 600000 });
const result = await page.evaluate("window.__N5_PROBE_RESULT__");
await browser.close();
server.close();

if (result.fatal) {
  console.error("PAGE FATAL:", result.fatal);
  process.exit(1);
}

const pass = result.allTokenizersMatched === true
  && result.allLogitsMatched === true
  && result.allLabelsMatched === true;
const archive = {
  purpose: `N5 browser probe (commit 3): MiniRBT-H256 relation head in `
           + `the browser - Bert tokenizer id parity, ONNX logits vs the `
           + `export's HF and ORT-python references (1e-4 gate), frozen `
           + `dev-fixed threshold labels, per-case wall time`,
  environment: {
    onnxruntimeWeb: versions.ortWebVersion,
    execution: "wasm, numThreads=1 (documented single-thread constraint)",
    browser: "headless Edge (system)",
  },
  result,
  pass,
};
await writeFile(ARCHIVE, JSON.stringify(archive, null, 1) + "\n", "utf-8");
const worst = Math.max(...result.cases.map((c) =>
  Math.max(c.maxAbsLogitDriftVsHf, c.maxAbsLogitDriftVsOrt)));
console.log("N5 browser probe pass:", pass,
            "| tok", result.allTokenizersMatched,
            "| logits", result.allLogitsMatched,
            "| labels", result.allLabelsMatched,
            "| worst drift", worst.toExponential(2));
process.exit(pass ? 0 : 1);
