// c9 worker probe driver.
//
// Serves the same read-only route map as run_probe.mjs (plus a separate
// /graphs-int8 prefix so one run can pick either graph set) and drives
// worker_probe.html, which hosts the T5 adapter inside a DedicatedWorker so
// terminate() can be tried as a memory-release mechanism.
//
// Usage:
//   node .../run_worker_probe.mjs --stamp w1 [--graphs fp32|int8] [--mem]
//
// Writes runs/<stamp>/worker-result.json; exit 0 when the page completed and
// the rebuilt worker reproduced the first worker's tokens on case 0.

import { createWriteStream } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
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

const GRAPH_FP32 = path.join(REPO, ".local", "world-components-worktree",
  "experiments", "world-components", "assets", "n4-onnx", "r3-direction");
const GRAPH_INT8 = path.join(REPO, ".local", "world-components-worktree",
  "experiments", "world-components", "assets", "n4-onnx", "r3-direction-int8");
const CKPT_DIR = path.join(REPO, ".local", "world-components-worktree",
  "experiments", "world-components", "assets", "n4-finetune", "r3-direction");
const FIXTURE = path.join(WT, "experiments", "world-components", "browser_probe",
  "probe_inputs.json");
const ORT_DIST = path.join(FRONTEND, "node_modules", "onnxruntime-web", "dist");
const SP_DIST = path.join(FRONTEND, "node_modules", "sentencepiece-js", "dist");

const args = process.argv.slice(2);
const arg = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i === -1 ? fallback : args[i + 1];
};
const PORT = Number(arg("port", 3213));
const STAMP = arg("stamp", new Date().toISOString().replace(/[:.]/g, "-"));
const MEM = args.includes("--mem");
// --rss: sample the browser process tree's working set from the OS in parallel
// with the run. The page-side memory API is accurate but slow (~13-60 s per
// call), so it cannot say WHEN a release happened; RSS can (1 s resolution),
// with the caveat that "freed by the allocator" and "returned to the OS" are
// different things.
const RSS = args.includes("--rss");
// --no-rebuild: stop after terminating worker A, so the RSS series is not
// contaminated by worker B's re-initialisation. Used for the reclaim-time
// question; it cannot also test rebuild parity.
const NO_REBUILD = args.includes("--no-rebuild");
const GRAPHS = arg("graphs", "fp32");
const RUN_DIR = path.join(HERE, "runs", STAMP);

const MIME = { ".html": "text/html; charset=utf-8", ".mjs": "text/javascript",
  ".js": "text/javascript", ".json": "application/json",
  ".wasm": "application/wasm", ".onnx": "application/octet-stream",
  ".model": "application/octet-stream" };

const ROUTES = [
  [/^\/$/, () => path.join(HERE, "worker_probe.html")],
  [/^\/app\/([A-Za-z0-9_.-]+)$/, (m) => path.join(HERE, m[1])],
  [/^\/graphs\/encoder\.onnx$/, () => path.join(GRAPH_FP32, "encoder.onnx")],
  [/^\/graphs\/decoder_kv\.onnx$/, () => path.join(GRAPH_FP32, "decoder_kv.onnx")],
  [/^\/graphs-int8\/encoder\.onnx$/, () => path.join(GRAPH_INT8, "encoder.onnx")],
  [/^\/graphs-int8\/decoder_kv\.onnx$/, () => path.join(GRAPH_INT8, "decoder_kv.onnx")],
  [/^\/graphs(-int8)?\/spiece\.model$/, () => path.join(CKPT_DIR, "spiece.model")],
  [/^\/graphs(-int8)?\/config\.json$/, () => path.join(CKPT_DIR, "config.json")],
  [/^\/fixtures\/probe_inputs\.json$/, () => FIXTURE],
  [/^\/sp\/index\.js$/, () => path.join(SP_DIST, "index.js")],
  [/^\/ort\/([A-Za-z0-9_.-]+)$/, (m) => path.join(ORT_DIST, m[1])],
];

const transfers = [];
function resolveRoute(p) {
  for (const [re, fn] of ROUTES) {
    const m = re.exec(p);
    if (m) return fn(m);
  }
  return null;
}

function serve(port) {
  const server = http.createServer(async (req, res) => {
    const pathname = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const file = resolveRoute(pathname);
    if (!file) {
      res.writeHead(404); res.end("no route");
      transfers.push({ pathname, status: 404, bytes: 0 });
      return;
    }
    try {
      const body = await readFile(file);
      res.writeHead(200, {
        "content-type": MIME[path.extname(file)] ?? "application/octet-stream",
        "cache-control": "no-store",
        "cross-origin-opener-policy": "same-origin",
        "cross-origin-embedder-policy": "require-corp",
        "cross-origin-resource-policy": "same-origin",
      });
      res.end(body);
      transfers.push({ pathname, status: 200, bytes: body.length });
    } catch (e) {
      res.writeHead(500); res.end(String(e));
      transfers.push({ pathname, status: 500, bytes: 0, error: String(e) });
    }
  });
  return new Promise((r) => server.listen(port, "127.0.0.1", () => r(server)));
}

await mkdir(RUN_DIR, { recursive: true });
const consoleLog = createWriteStream(path.join(RUN_DIR, "console.log"));
const log = (...a) => {
  const line = a.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join(" ");
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
const browser = await chromium.launch({
  channel: "msedge", headless: true, args: ["--enable-precise-memory-info"],
});
const browserCdp = RSS ? await browser.newBrowserCDPSession() : null;
const { execFileSync } = await import("node:child_process");
const rssSamples = [];
function rssNow(ids) {
  if (!ids.length) return 0;
  try {
    const out = execFileSync("powershell", ["-NoProfile", "-Command",
      `Get-Process -Id ${ids.join(",")} -ErrorAction SilentlyContinue | ` +
      `ForEach-Object { "$($_.Id) $($_.WorkingSet64)" }`],
      { encoding: "utf8", timeout: 15000 });
    const rows = out.split(String.fromCharCode(10))
      .map((s) => s.trim()).filter(Boolean);
    return rows.reduce((a, line) => a + Number(
      line.split(" ").filter(Boolean).pop() || 0), 0);
  } catch {
    return 0;
  }
}
let rssTimer = null;
let rssBusy = false;
if (RSS) {
  rssTimer = setInterval(async () => {
    // skip overlapping samples: a PowerShell spawn that outlives the 1 s
    // tick stacks up and starves the browser of CPU (observed in w-fp32-mem3)
    if (rssBusy) return;
    rssBusy = true;
    try {
      const { processInfo } = await browserCdp.send("SystemInfo.getProcessInfo");
      const ids = processInfo.map((p) => p.id);
      const bytes = rssNow(ids);
      rssSamples.push({ t: Date.now(), processes: ids.length, bytes });
    } catch { /* browser gone */ } finally { rssBusy = false; }
  }, 1000);
}

const context = await browser.newContext();
const page = await context.newPage();
page.on("console", (m) => log(`[console:${m.type()}]`, m.text().slice(0, 400)));
page.on("pageerror", (e) => log("[pageerror]", String(e).slice(0, 600)));
page.on("worker", (w) => log("[worker started]", w.url()));

const query = new URLSearchParams({ graphs: GRAPHS });
if (MEM) query.set("mem", "1");
if (NO_REBUILD) query.set("norebuild", "1");
const tNav = Date.now();
await page.goto(`http://127.0.0.1:${PORT}/?${query}`, { waitUntil: "domcontentloaded" });
await page.waitForFunction("window.__C9_WORKER_RESULT__ !== undefined", null,
                           { timeout: 900000 });
const result = await page.evaluate("window.__C9_WORKER_RESULT__");
const wallMs = Date.now() - tNav;
if (rssTimer) clearInterval(rssTimer);
const browserVersion = browser.version();
await browser.close();
server.close();
consoleLog.end();

const archive = {
  purpose: "c9 worker probe: does terminating a DedicatedWorker that holds "
           + "the 77M T5 runtime return its memory, and does a rebuilt "
           + "worker reproduce the same tokens",
  stamp: STAMP,
  environment: {
    browser: { channel: "msedge", version: browserVersion, headless: true,
               args: ["--enable-precise-memory-info"] },
    playwright: pwPkg.version, onnxruntimeWeb: ortPkg.version,
    sentencepieceJs: spPkg.version, node: process.version,
    platform: `${process.platform} ${process.arch}`,
    graphs: GRAPHS,
    serving: "localhost static server, COOP/COEP same-origin, no throttling",
    deepMemoryPass: MEM,
  },
  result,
  wallMs,
  rss: RSS ? {
    note: "OS working set of the browser process tree, 1 s sampling; "
          + "aligned to result.terminate.terminateWallClockMs",
    samples: rssSamples,
    atTerminate: null,
    afterTerminate: null,
  } : null,
  transfer: { requests: transfers.length,
              bytes: transfers.reduce((a, t) => a + (t.bytes || 0), 0),
              perPath: transfers },
};
if (RSS && result.terminate?.terminateWallClockMs) {
  const MiB = (b) => +(b / 1048576).toFixed(1);
  const tT = result.terminate.terminateWallClockMs;
  // A sample of 0 bytes means the OS query failed (the PowerShell spawn can
  // time out while the browser is busy). Keep those out of the analysis but
  // report how many there were.
  const valid = rssSamples.filter((x) => x.bytes > 0);
  const invalid = rssSamples.length - valid.length;
  const before = valid.filter((x) => x.t <= tT).at(-1) || null;
  const after = valid.filter((x) => x.t > tT);
  const preWorker = valid[0] || null;
  archive.rss.atTerminate = before;
  archive.rss.preWorkerBaseline = preWorker;
  archive.rss.afterTerminate = after.map((x) => ({
    offsetMs: x.t - tT, mib: MiB(x.bytes),
  }));

  // Three separate questions, previously collapsed into one "firstDrop":
  //   1. first visible drop  - the big chunk is gone
  //   2. lowest point        - how far the tree ever gets
  //   3. level at end        - what it settles at over the sampled window
  // "Reached baseline" is deliberately NOT claimed: whole-tree RSS includes
  // the page, tokenizer, GPU/utility processes and allocator retention, so a
  // level below the pre-worker sample proves nothing about the model's heap.
  const firstDrop = before
    ? after.find((x) => x.bytes < before.bytes - 400 * 1048576) : null;
  const lowest = after.length
    ? after.reduce((a, x) => (x.bytes < a.bytes ? x : a)) : null;
  const tail = after.slice(-3);
  const settled = tail.length
    ? tail.reduce((a, x) => a + x.bytes, 0) / tail.length : null;
  archive.rss.summary = {
    preWorkerMiB: preWorker ? MiB(preWorker.bytes) : null,
    atTerminateMiB: before ? MiB(before.bytes) : null,
    firstVisibleDrop: firstDrop
      ? { offsetMs: firstDrop.t - tT, mib: MiB(firstDrop.bytes) } : null,
    lowestAfterTerminate: lowest
      ? { offsetMs: lowest.t - tT, mib: MiB(lowest.bytes) } : null,
    settledLastThree: settled == null ? null
      : { mib: +MiB(settled), offsetsMs: tail.map((x) => x.t - tT) },
    invalidSamples: invalid,
    samplingResolutionMs: 1000,
    claimLimit: "the drop happening is proven; the instant the model's heap is "
                + "fully released is not, because the series is whole-tree RSS "
                + "at 1 s resolution and the final level mixes in the page, "
                + "tokenizer, other browser processes and allocator retention",
  };
}
await writeFile(path.join(RUN_DIR, "worker-result.json"),
                JSON.stringify(archive, null, 1) + "\n", "utf-8");

const fails = [];
if (!result.ok) fails.push("page fatal: " + JSON.stringify(result.fatal));
const badRef = (result.cases || []).filter((c) => !c.tokenMatchVsBakedReference);
if (GRAPHS === "fp32" && badRef.length) {
  fails.push(`token mismatch on ${badRef.length} case(s)`);
}
if (!result.cancel?.outcome || result.cancel.outcome.type !== "cancelled") {
  fails.push("cancel did not produce a cancelled outcome");
}
if (!NO_REBUILD) {
  const sameAfterRebuild = (result.cases || []).find((c) => c.sameAsWorkerACase0 === true);
  if (!sameAfterRebuild) fails.push("rebuilt worker did not reproduce case-0 tokens");
}

log(`wall ${wallMs}ms | graphs ${GRAPHS}`);
log(`A stages ${JSON.stringify(result.workerA?.stages)}`);
log(`terminate: before ${result.terminate?.memBeforeTerminate} `
  + `after ${JSON.stringify(result.terminate?.samples?.map((s) => s.isolatedBytes))} `
  + `reclaimed ${result.terminate?.reclaimedBytes}`);
log(`cancel: ${JSON.stringify(result.cancel)}`);
log(fails.length ? `FAIL: ${fails.join("; ")}` : "worker probe completed");
process.exit(fails.length ? 1 : 0);
