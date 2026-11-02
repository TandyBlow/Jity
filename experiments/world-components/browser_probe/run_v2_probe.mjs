// N4 v2 browser probe driver (commit 3): stages the v2 grouped-interface
// ONNX graphs, the real spiece.model + sentencepiece-js bundle, the
// committed N4 adapter and the baked cases; drives headless Edge; archives
// token ids/timings and a Python-side judge over the browser texts.
//
// Usage: node experiments/world-components/browser_probe/run_v2_probe.mjs

import { cp, mkdir, readFile, writeFile } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..", "..");
const FRONTEND = path.join(REPO, "frontend");
const require2 = createRequire(path.join(FRONTEND, "package.json"));
const { chromium } = require2("@playwright/test");

const PORT = 3202;
const GRAPHS = path.join(REPO, "experiments", "world-components", "assets",
                         "n4-onnx", "v2-grouped");
const CKPT = path.join(REPO, "experiments", "world-components",
                       "n4_corpus_v2", "ckpt-v2");
const SERVE_ROOT = path.join(FRONTEND, "public");
const BASE = path.join(SERVE_ROOT, "models", "v2-probe");
const ARCHIVE = path.join(REPO, "artifacts", "world-components",
                          "n4-v2-browser-adapter.json");

async function stage() {
  await mkdir(path.join(BASE, "sp"), { recursive: true });
  const ortPkg = JSON.parse(await readFile(path.join(
      FRONTEND, "node_modules", "onnxruntime-web", "package.json"), "utf8"));
  const spSrc = path.join(FRONTEND, "node_modules", "sentencepiece-js",
                          "dist", "index.js");
  await cp(spSrc, path.join(BASE, "sp", "index.js"));
  await cp(path.join(CKPT, "spiece.model"), path.join(BASE, "spiece.model"));
  await cp(path.join(HERE, "v2_probe_cases.json"),
           path.join(BASE, "v2_probe_cases.json"));
  await cp(path.join(HERE, "n4_browser_adapter.mjs"),
           path.join(BASE, "n4_browser_adapter.mjs"));
  await cp(path.join(HERE, "v2_probe.html"), path.join(BASE, "index.html"));
  for (const f of ["encoder.onnx", "decoder_kv.onnx"]) {
    await cp(path.join(GRAPHS, f), path.join(BASE, f));
  }
  return { ortWebVersion: ortPkg.version };
}

function serve(root, port) {
  const mime = { ".html": "text/html", ".mjs": "text/javascript",
                 ".js": "text/javascript", ".json": "application/json",
                 ".wasm": "application/wasm",
                 ".onnx": "application/octet-stream",
                 ".model": "application/octet-stream" };
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
  `http://127.0.0.1:${PORT}/models/v2-probe/index.html?v=${Date.now()}`,
  { waitUntil: "domcontentloaded" });
await page.waitForFunction("window.__V2_PROBE_RESULT__ !== undefined",
                           null, { timeout: 600000 });
const result = await page.evaluate("window.__V2_PROBE_RESULT__");
await browser.close();
server.close();

if (result.fatal) {
  console.error("PAGE FATAL:", result.fatal);
  process.exit(1);
}

const textsTmp = path.join(HERE, "v2_browser_texts.tmp.json");
await writeFile(textsTmp, JSON.stringify(Object.fromEntries(
    result.cases.map((c) => [c.rowId,
                             { text: c.text, finishReason: c.finishReason }]))),
    "utf-8");
const py = process.env.PYTHON || "python";
let judge = null;
try {
  const out = execFileSync(py, ["-X", "utf8",
    path.join(HERE, "judge_v2_browser_texts.py"), textsTmp],
    { encoding: "utf8" });
  judge = JSON.parse(out.slice(out.indexOf("{")));
} catch (e) {
  judge = { error: String(e.message).slice(0, 300) };
}

const judged = judge && !judge.error
  ? Object.fromEntries(Object.entries(judge).map(([k, v]) => [k, v.verdict.pass]))
  : {};
const archive = {
  purpose: `N4 v2 browser adapter (commit 3): grouped interface + `
           + `appellation grants through the committed adapter - `
           + `sentencepiece-js id parity, KV-cache greedy tokens vs the `
           + `ORT-python loop, per-case wall time, and the frozen v2 gates `
           + `over the BROWSER texts`,
  environment: {
    onnxruntimeWeb: versions.ortWebVersion,
    execution: "wasm, numThreads=1 (documented single-thread constraint)",
    browser: "headless Edge (system)",
    timingScope: "offline/browser evidence is separate; never merged with "
                 + "the Python holdout timings",
  },
  hfExactNote: "the Python ONNX export archive records HF-vs-ORT drift "
                + "(~1e-5 logits flips near-tie tokens on some cases); the "
                + "browser target is the ORT-python loop, same engine family",
  result,
  judge,
  // The ADAPTATION gate is tokenizer ids + browser tokens == ORT-python
  // tokens + a judge run over every text. Model quality is reported
  // separately: a known model gap must not be mislabelled as an adapter
  // failure, and an adapter that runs must not hide a quality failure.
  pass: !result.fatal
    && result.allTokenizersMatched === true
    && result.allTokensMatchedVsOrtPy === true
    && Object.values(judged).length === result.cases.length,
  quality: {
    cases: result.cases.length,
    passed: Object.values(judged).filter(Boolean).length,
    failures: Object.entries(judged).filter(([, ok]) => !ok).map(([k]) => k),
  },
};
await writeFile(ARCHIVE, JSON.stringify(archive, null, 1) + "\n", "utf-8");
console.log("v2 browser adaptation pass:", archive.pass,
            "| tok", result.allTokenizersMatched,
            "| ids", result.allTokensMatchedVsOrtPy,
            "| quality", archive.quality.passed, "/", archive.quality.cases,
            "| failures", archive.quality.failures.join(", "));
for (const c of result.cases) {
  if (!judged[c.rowId]) console.log("  judge fail:", c.rowId);
}
process.exit(archive.pass ? 0 : 1);
