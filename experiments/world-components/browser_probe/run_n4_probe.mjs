// N4 browser minimal-feasibility probe driver (batch 1).
// Serves the C worktree's frontend/public (ORT vendored bundle + probe
// assets) on a localhost static server, drives n4_probe.html in headless
// Chromium (playwright), and archives the result. The probe proves the
// frozen r3-direction encoder-decoder graphs RUN in the browser and match
// the Python greedy reference ids — it is feasibility evidence, not the
// later adaptation batch's acceptance.
//
// Usage: node experiments/world-components/browser_probe/run_n4_probe.mjs
// Needs: frontend/node_modules (@playwright/test, onnxruntime-web via
// copy-ort-assets.mjs), experiments/world-components/assets/n4-onnx/
// r3-direction/*.onnx (export_n4_onnx.py), browser_probe/probe_inputs.json
// (bake_probe_inputs.py).

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

const PORT = 3199;
const ONNX_SRC = path.join(REPO, "experiments", "world-components",
                           "assets", "n4-onnx", "r3-direction");
const PROBE_INPUTS = path.join(HERE, "probe_inputs.json");
const SERVE_ROOT = path.join(FRONTEND, "public");
const ASSETS_DIR = path.join(SERVE_ROOT, "models", "n4-probe");
const ARCHIVE = path.join(REPO, "artifacts", "world-components",
                          "n4-browser-probe-r1.json");

async function stageAssets() {
  // vendored ORT bundle: reuse copy-ort-assets.mjs output, regenerating it
  // from node_modules if public/ort is missing (npm ci recreates it)
  const ortSrc = path.join(FRONTEND, "node_modules", "onnxruntime-web", "dist");
  const ortDst = path.join(SERVE_ROOT, "ort");
  const ortPkg = await readFile(path.join(FRONTEND, "node_modules",
      "onnxruntime-web", "package.json")).then(JSON.parse).catch(() => null);
  if (!ortPkg) throw new Error("onnxruntime-web not installed - run npm ci");
  try {
    await readFile(path.join(ortDst, "ort.bundle.min.mjs"));
  } catch {
    const { readdir } = await import("node:fs/promises");
    await mkdir(ortDst, { recursive: true });
    for (const entry of await readdir(ortSrc)) {
      if (entry === "ort.bundle.min.mjs" || entry.startsWith("ort-wasm-")) {
        await cp(path.join(ortSrc, entry), path.join(ortDst, entry));
      }
    }
  }
  await mkdir(ASSETS_DIR, { recursive: true });
  for (const f of ["encoder.onnx", "decoder_step.onnx"]) {
    await cp(path.join(ONNX_SRC, f), path.join(ASSETS_DIR, f));
  }
  await cp(PROBE_INPUTS, path.join(ASSETS_DIR, "probe_inputs.json"));
  await cp(path.join(HERE, "n4_probe.html"),
           path.join(ASSETS_DIR, "index.html"));
  return { ortWebVersion: ortPkg.version };
}

function serve(root, port) {
  const mime = { ".html": "text/html", ".mjs": "text/javascript",
                 ".js": "text/javascript", ".json": "application/json",
                 ".wasm": "application/wasm", ".onnx": "application/octet-stream" };
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://x");
    let p = path.join(root, decodeURIComponent(url.pathname));
    try {
      const body = await readFile(p);
      res.writeHead(200, { "content-type": mime[path.extname(p)] ?? "application/octet-stream" });
      res.end(body);
    } catch {
      res.writeHead(404); res.end("no");
    }
  });
  return new Promise((resolve) => server.listen(port, "127.0.0.1", () => resolve(server)));
}

const ortWebVersion = await stageAssets();
const server = await serve(SERVE_ROOT, PORT);
const browser = await chromium.launch({ channel: "msedge" });  // system Edge, as in the documented F3/F4 environment
const page = await browser.newPage();
const tNav = Date.now();
await page.goto(`http://127.0.0.1:${PORT}/models/n4-probe/index.html`,
                { waitUntil: "domcontentloaded" });
await page.waitForFunction("window.__N4_PROBE_RESULT__ !== undefined",
                           null, { timeout: 600000 });
const result = await page.evaluate("window.__N4_PROBE_RESULT__");
const wallMs = Date.now() - tNav;
await browser.close();
server.close();

const ortFiles = {};
for (const f of ["encoder.onnx", "decoder_step.onnx"]) {
  const st = await readFile(path.join(ASSETS_DIR, f));
  ortFiles[f] = st.length;
}
const archive = {
  purpose: `N4 browser minimal-feasibility probe (batch 1): frozen `
           + `r3-direction T5 encoder-decoder ONNX graphs on ORT-web `
           + `single-thread wasm in headless Chromium; token-id parity `
           + `against the ORT-python greedy reference per case`,
  environment: {
    onnxruntimeWeb: ortWebVersion,
    execution: "wasm, numThreads=1 (documented single-thread constraint)",
    browser: "playwright chromium (headless)",
    graphs: ortFiles,
    fp32: true,
    note: `int8 quantization and JS sentencepiece belong to the later `
          + `adaptation batch; localhost static server, so load times are `
          + `not network-representative`,
  },
  result,
  wallMs,
  pass: !result.fatal && result.allMatched === true,
};
await writeFile(ARCHIVE, JSON.stringify(archive, null, 1) + "\n",
                { encoding: "utf-8" });
console.log("probe pass:", archive.pass,
            "| load", result.sessionLoadMs, "ms |",
            (result.cases ?? []).map((c) => `${c.name}:${c.matched ? "ok" : "DIFF"}`).join(" "));
process.exit(archive.pass ? 0 : 1);
