// c9 browser T5 runtime probe driver.
//
// Serves a fixed route map (this directory + the pre-existing weights,
// tokenizer, fixtures and the installed ORT/tokenizer bundles, all read-only
// from where they already live), opens probe.html in headless Edge, and
// archives the raw page result plus server transfer accounting.
//
// Nothing is copied to frontend/public and no page under frontend/src is
// touched: c9 owns only experiments/world-components/parallel/browser_t5/.
//
// Usage:
//   node experiments/world-components/parallel/browser_t5/run_probe.mjs \
//        [--port 3210] [--stamp ISO] [--headed]
//
// Writes: runs/<stamp>/browser-result.json, runs/<stamp>/console.log,
//         runs/<stamp>/server.log
// Exit:   0 when the page reported ok and every case was produced; parity
//         against the offline reference is decided by compare.py, not here.

import { createWriteStream } from "node:fs";
import { mkdir, readFile, writeFile, stat } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WT = path.resolve(HERE, "..", "..", "..", "..");
const REPO = path.resolve(WT, "..", "..", "..");
const FRONTEND = path.join(WT, "frontend");
const require2 = createRequire(path.join(FRONTEND, "package.json"));
const { chromium } = require2("@playwright/test");

const GRAPH_DIR = path.join(REPO, ".local", "world-components-worktree", "experiments",
  "world-components", "assets", "n4-onnx", "r3-direction");
const GRAPH_DIR_INT8 = path.join(REPO, ".local", "world-components-worktree",
  "experiments", "world-components", "assets", "n4-onnx", "r3-direction-int8");
const CKPT_DIR = path.join(REPO, ".local", "world-components-worktree", "experiments",
  "world-components", "assets", "n4-finetune", "r3-direction");
const FIXTURE = path.join(WT, "experiments", "world-components", "browser_probe",
  "probe_inputs.json");
const ORT_DIST = path.join(FRONTEND, "node_modules", "onnxruntime-web", "dist");
const SP_DIST = path.join(FRONTEND, "node_modules", "sentencepiece-js", "dist");

const args = process.argv.slice(2);
const arg = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i === -1 ? fallback : args[i + 1];
};
const PORT = Number(arg("port", 3210));
const STAMP = arg("stamp", new Date().toISOString().replace(/[:.]/g, "-"));
const HEADED = args.includes("--headed");
const DEEP_MEM = args.includes("--mem");
const GRAPHS = arg("graphs", "fp32"); // fp32 | int8
if (!["fp32", "int8"].includes(GRAPHS)) {
  console.error("--graphs must be fp32 or int8");
  process.exit(2);
}
const GRAPH_SRC = GRAPHS === "int8" ? GRAPH_DIR_INT8 : GRAPH_DIR;
const RUN_DIR = path.join(HERE, "runs", STAMP);

const MIME = { ".html": "text/html; charset=utf-8", ".mjs": "text/javascript",
  ".js": "text/javascript", ".json": "application/json",
  ".wasm": "application/wasm", ".onnx": "application/octet-stream",
  ".model": "application/octet-stream" };

const ROUTES = [
  [/^\/$/, () => path.join(HERE, "probe.html")],
  [/^\/app\/([A-Za-z0-9_.-]+)$/, (m) => path.join(HERE, m[1])],
  [/^\/graphs\/encoder\.onnx$/, () => path.join(GRAPH_SRC, "encoder.onnx")],
  [/^\/graphs\/decoder_kv\.onnx$/, () => path.join(GRAPH_SRC, "decoder_kv.onnx")],
  [/^\/graphs\/spiece\.model$/, () => path.join(CKPT_DIR, "spiece.model")],
  [/^\/graphs\/config\.json$/, () => path.join(CKPT_DIR, "config.json")],
  [/^\/fixtures\/probe_inputs\.json$/, () => FIXTURE],
  [/^\/sp\/index\.js$/, () => path.join(SP_DIST, "index.js")],
  [/^\/ort\/([A-Za-z0-9_.-]+)$/, (m) => path.join(ORT_DIST, m[1])],
];

const transfers = [];

function resolveRoute(pathname) {
  for (const [re, fn] of ROUTES) {
    const m = re.exec(pathname);
    if (m) return fn(m);
  }
  return null;
}

function serve(port) {
  const server = http.createServer(async (req, res) => {
    const pathname = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const file = resolveRoute(pathname);
    const t0 = Date.now();
    if (!file) {
      res.writeHead(404); res.end("no route");
      transfers.push({ pathname, status: 404, ms: 0, bytes: 0 });
      return;
    }
    try {
      const body = await readFile(file);
      res.writeHead(200, {
        "content-type": MIME[path.extname(file)] ?? "application/octet-stream",
        "cache-control": "no-store",
        // cross-origin isolation enables performance.measureUserAgentSpecificMemory
        "cross-origin-opener-policy": "same-origin",
        "cross-origin-embedder-policy": "require-corp",
        "cross-origin-resource-policy": "same-origin",
      });
      res.end(body);
      transfers.push({ pathname, status: 200, ms: Date.now() - t0,
                       bytes: body.length });
    } catch (e) {
      res.writeHead(500); res.end("read failed: " + e.message);
      transfers.push({ pathname, status: 500, ms: Date.now() - t0, bytes: 0,
                       error: e.message });
    }
  });
  return new Promise((r) => server.listen(port, "127.0.0.1", () => r(server)));
}

await mkdir(RUN_DIR, { recursive: true });
const consoleLog = createWriteStream(path.join(RUN_DIR, "console.log"));
const log = (...a) => {
  const line = a.map((x) => typeof x === "string" ? x : JSON.stringify(x)).join(" ");
  console.log(line);
  consoleLog.write(line + "\n");
};

const ortPkg = JSON.parse(await readFile(
  path.join(FRONTEND, "node_modules", "onnxruntime-web", "package.json"), "utf8"));
const spPkg = JSON.parse(await readFile(
  path.join(FRONTEND, "node_modules", "sentencepiece-js", "package.json"), "utf8"));
const pwPkg = JSON.parse(await readFile(
  path.join(FRONTEND, "node_modules", "@playwright", "test", "package.json"), "utf8"));

const server = await serve(PORT);
const launchOpts = {
  channel: "msedge", // system Edge, same family as the documented F3/F21 setup
  headless: !HEADED,
  args: ["--enable-precise-memory-info"],
};
const browser = await chromium.launch(launchOpts);
const context = await browser.newContext();
const page = await context.newPage();
page.on("console", (msg) => log(`[console:${msg.type()}]`, msg.text()));
page.on("pageerror", (err) => log("[pageerror]", err.message));
page.on("requestfailed", (req) =>
  log("[requestfailed]", req.url(), req.failure() && req.failure().errorText));

const tNav = Date.now();
const query = new URLSearchParams({ variant: GRAPHS });
if (DEEP_MEM) query.set("mem", "1");
await page.goto(`http://127.0.0.1:${PORT}/?${query}`,
                { waitUntil: "domcontentloaded" });
await page.waitForFunction("window.__C9_RESULT__ !== undefined", null,
                           { timeout: 900000 });
const result = await page.evaluate("window.__C9_RESULT__");
const wallMs = Date.now() - tNav;

let heapUsage = null;
let pageMetrics = null;
try {
  const cdp = await context.newCDPSession(page);
  heapUsage = await cdp.send("Runtime.getHeapUsage");
  const m = await cdp.send("Performance.getMetrics");
  pageMetrics = Object.fromEntries(m.metrics.map((x) => [x.name, x.value]));
} catch (e) {
  log("[cdp] metrics unavailable:", String(e.message || e));
}

const browserVersion = browser.version();
await browser.close();
server.close();
consoleLog.end();

const archive = {
  purpose: "c9 browser T5 runtime probe: load / cold / warm / cancel / "
           + "memory / parity-input capture for the 77M r3-direction "
           + "encoder-decoder in real Edge",
  stamp: STAMP,
  environment: {
    browser: { channel: launchOpts.channel, version: browserVersion,
               headless: launchOpts.headless, args: launchOpts.args },
    playwright: pwPkg.version,
    onnxruntimeWeb: ortPkg.version,
    sentencepieceJs: spPkg.version,
    node: process.version,
    platform: `${process.platform} ${process.arch}`,
    executionProvider: "wasm, numThreads=1",
    serving: "localhost static server, COOP/COEP same-origin, no throttling",
    deepMemoryPass: DEEP_MEM,
    graphs: GRAPHS,
    graphDir: path.relative(REPO, GRAPH_SRC),
    routes: ROUTES.map(([re]) => String(re)),
  },
  result,
  wallMs,
  transfer: {
    requests: transfers.length,
    bytes: transfers.reduce((a, t) => a + (t.bytes || 0), 0),
    perPath: transfers,
  },
  cdp: { heapUsage, pageMetrics },
};
await writeFile(path.join(RUN_DIR, "browser-result.json"),
                JSON.stringify(archive, null, 1) + "\n", "utf-8");

const fails = [];
if (!result.ok) fails.push("page fatal");
const badTok = (result.tokenizer || []).filter((t) => !t.matchesBakedIds);
if (badTok.length) fails.push(`tokenizer mismatch on ${badTok.length} case(s)`);
const badRef = (result.cases || []).filter((c) => !c.tokenMatchVsBakedReference);
// The stored referenceIds are fp32. int8 is expected to diverge on some cases
// (documented quantisation contract), so it reports the count instead of
// failing the process; same-graph parity is judged by compare.py.
if (badRef.length && GRAPHS === "fp32") {
  fails.push(`stored-reference mismatch on ${badRef.length} case(s)`);
}
if (badRef.length && GRAPHS === "int8") {
  log(`int8 differs from the stored fp32 ids on ${badRef.length}/${result.cases.length} case(s) - expected`);
}
const truncated = (result.cases || []).filter((c) => c.finishReason && c.finishReason !== "eos");
if (truncated.length) fails.push(`generation hit maxTokens on ${truncated.length} case(s)`);
if (!result.cancel?.timerAbort?.threw) fails.push("timer abort did not throw");
if (!result.cancel?.stepAbort?.threw) fails.push("step abort did not throw");

log(`wall ${wallMs}ms | transfers ${transfers.length} `
  + `(${(archive.transfer.bytes / 1048576).toFixed(1)} MiB) `
  + `| stages ${JSON.stringify(result.stages)}`);
log(`cases ${(result.cases || []).map((c) => `${c.name}:${c.timings.steps}st/${c.timings.meanStepMs}ms`).join(" ")}`);
log(fails.length ? `FAIL: ${fails.join("; ")}` : "probe completed, output captured");
process.exit(fails.length ? 1 : 0);
