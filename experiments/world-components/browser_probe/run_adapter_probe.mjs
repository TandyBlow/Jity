// N4 adapter probe driver (batch 3): stages the adapter page (fp32 + int8
// graphs, sentencepiece-js bundle, adapter module, baked inputs), drives it
// in headless Edge, and archives the result with a Python-side judge pass
// over the browser texts. Batch-1's minimal probe (run_n4_probe.mjs) stays
// as-is; this is the full-pipeline verification.
//
// Usage: node experiments/world-components/browser_probe/run_adapter_probe.mjs

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

const PORT = 3201;
const N4 = path.join(REPO, "experiments", "world-components", "assets", "n4-onnx", "r3-direction");
const N4I8 = path.join(REPO, "experiments", "world-components", "assets", "n4-onnx", "r3-direction-int8");
const CK = path.join(REPO, "experiments", "world-components", "assets", "n4-finetune", "r3-direction");
const SERVE_ROOT = path.join(FRONTEND, "public");
const BASE = path.join(SERVE_ROOT, "models", "n4-probe");
const I8DIR = path.join(SERVE_ROOT, "models", "n4-probe-int8");
const ARCHIVE = path.join(REPO, "artifacts", "world-components", "n4-browser-adapter-r2.json");

async function stage() {
  const ortPkg = JSON.parse(await readFile(path.join(
      FRONTEND, "node_modules", "onnxruntime-web", "package.json"), "utf8"));
  await mkdir(path.join(BASE, "sp"), { recursive: true });
  await mkdir(I8DIR, { recursive: true });
  const spSrc = path.join(FRONTEND, "node_modules", "sentencepiece-js", "dist", "index.js");
  await cp(spSrc, path.join(BASE, "sp", "index.js"));
  await cp(path.join(CK, "spiece.model"), path.join(BASE, "spiece.model"));
  await cp(path.join(HERE, "probe_inputs.json"), path.join(BASE, "probe_inputs.json"));
  await cp(path.join(HERE, "n4_browser_adapter.mjs"), path.join(BASE, "n4_browser_adapter.mjs"));
  await cp(path.join(HERE, "n4_adapter_probe.html"), path.join(BASE, "index.html"));
  for (const f of ["encoder.onnx", "decoder_kv.onnx"]) {
    await cp(path.join(N4, f), path.join(BASE, f));
    await cp(path.join(N4I8, f), path.join(I8DIR, f));
  }
  return { ortWebVersion: ortPkg.version };
}

function serve(root, port) {
  const mime = { ".html": "text/html", ".mjs": "text/javascript",
                 ".js": "text/javascript", ".json": "application/json",
                 ".wasm": "application/wasm", ".onnx": "application/octet-stream",
                 ".model": "application/octet-stream" };
  return new Promise((resolve) => {
    const server = http.createServer(async (req, res) => {
      try {
        const p = path.join(root, decodeURIComponent(new URL(req.url, "http://x").pathname));
        const body = await readFile(p);
        res.writeHead(200, { "content-type": mime[path.extname(p)] ?? "application/octet-stream",
                             "cache-control": "no-store" });
        res.end(body);
      } catch {
        res.writeHead(404); res.end("no");
      }
    });
    server.listen(port, "127.0.0.1", () => resolve(server));
  });
}

const versions = await stage();
const server = await serve(SERVE_ROOT, PORT);
const browser = await chromium.launch({ channel: "msedge" });
const page = await browser.newPage();
await page.goto(`http://127.0.0.1:${PORT}/models/n4-probe/index.html?v=${Date.now()}`,
                { waitUntil: "domcontentloaded" });
await page.waitForFunction("window.__N4_ADAPTER_RESULT__ !== undefined",
                           null, { timeout: 600000 });
const result = await page.evaluate("window.__N4_ADAPTER_RESULT__");
if (result.fatal) {
  console.error("PAGE FATAL:", result.fatal);
  await browser.close();
  server.close();
  process.exit(1);
}
await browser.close();
server.close();

// Python-side judge over the browser texts (same recognizer core as N5)
const { execFileSync } = await import("node:child_process");
const py = process.env.PYTHON || "python";
const textsTmp = path.join(HERE, "browser_texts.tmp.json");
await writeFile(textsTmp, JSON.stringify(
    Object.fromEntries(result.cases.map((c) => [c.name, c.fp32.text]))), "utf-8");
let judge = null;
try {
  const out = execFileSync(py, ["-X", "utf8",
    path.join(HERE, "judge_browser_texts.py"),
    textsTmp,
    path.join(HERE, "probe_inputs.json")], { encoding: "utf8" });
  judge = JSON.parse(out.slice(out.indexOf("{")));
} catch (e) {
  judge = { error: String(e.message).slice(0, 200) };
}

const archive = {
  purpose: `N4 browser adapter verification (batch 3): full pipeline in the `
           + `browser - sentencepiece-js tokenization (id-parity vs Python `
           + `T5Tokenizer), KV-cache greedy generation on fp32 and int8 `
           + `graphs, AbortSignal semantics; parity target = ORT-python loop`,
  environment: {
    onnxruntimeWeb: versions.ortWebVersion,
    execution: "wasm, numThreads=1 (documented single-thread constraint)",
    browser: "headless Edge (system)",
    cancellation: `AbortSignal between steps; ORT run itself not `
                  + `interruptible (F3) - documented granularity`,
  },
  result,
  judge,
  pass: !result.fatal && result.allFp32Matched === true
        && result.allTokenizersMatched === true
        && result.abortTest.threw === true
        && result.boundary && result.boundary.exact128
        && result.boundary.exact128.modelCalled === true
        && result.boundary.exact129.refusedNoModelCall === true
        && result.boundary.exact129.status === "unsupported",
};
await writeFile(ARCHIVE, JSON.stringify(archive, null, 1) + "\n", "utf-8");
console.log("abortTest keys:", result.abortTest ? Object.keys(result.abortTest) : "none", JSON.stringify(result.abortTest));
console.log("pageVersion:", result.pageVersion);
console.log("adapter probe pass:", archive.pass,
            "| tok", result.allTokenizersMatched,
            "| fp32", result.allFp32Matched,
            "| abort", result.abortTest.threw);
process.exit(archive.pass ? 0 : 1);
