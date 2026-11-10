// c9 worker runtime: the same 77M T5 adapter, hosted inside a DedicatedWorker.
//
// Why a worker: the page-side probe showed ~973 MB attributable memory that
// did not come back after session.release(). A worker is a separate agent
// with its own wasm heap, so terminate() is the only mechanism that can hand
// that memory back to the browser. This module exists to measure whether it
// actually does, and whether a rebuilt worker reproduces the same tokens.
//
// Protocol (postMessage, one request id per call):
//   in:  {id, cmd:"init", graphDir, variant}
//        {id, cmd:"generate", ids, maxTokens}   // ids, not text
//        {id, cmd:"cancel"}        // aborts the in-flight generation
//        {id, cmd:"release"}       // session.release() inside the worker
//        {id, cmd:"mem"}           // cheap JS-heap read from inside
//   out: {id, type:"stages", stages}
//        {id, type:"result", result}
//        {id, type:"error", error}
//        {id, type:"cancelled", ...} | {id, type:"cancelAck"}
//        {id, type:"mem", mem}
//
// Generation is greedy and identical to the page adapter; the only addition
// is that "cancel" arrives as a message, so the abort is issued by the main
// thread and observed by this worker at the next step boundary. Both
// timestamps are reported so the latency is measurable, not inferred.

import { T5Browser } from "/app/t5_adapter.mjs";

// The tokenizer stays on the main thread (see t5_adapter.mjs): this worker
// holds only the ONNX sessions and their wasm heap, which is exactly the
// memory a terminate() is supposed to reclaim.

let adapter = null;
let config = null;
let controller = null;
let current = null;

const mem = () => (performance.memory
  ? { used: performance.memory.usedJSHeapSize,
      total: performance.memory.totalJSHeapSize }
  : null);

self.onmessage = async (ev) => {
  const msg = ev.data || {};
  const { id, cmd } = msg;
  try {
    if (cmd === "init") {
      const cfg = await (await fetch("/graphs/config.json")).json();
      config = cfg;
      const t0 = performance.now();
      adapter = await T5Browser.create({
        ortBundleUrl: "/ort/ort.bundle.min.mjs",
        wasmPaths: "/ort/",
        graphDir: msg.graphDir || "/graphs",
        heads: cfg.num_heads,
        dKv: cfg.d_kv,
        // no tokenizer: ids come in, ids go out
      });
      self.postMessage({ id, type: "stages", variant: msg.variant || "fp32",
        stages: { ...adapter.stages,
                  workerCreateMs: +(performance.now() - t0).toFixed(1) },
        mem: mem() });
      return;
    }
    if (cmd === "generate") {
      controller = new AbortController();
      current = { id, startedAt: performance.now(), steps: 0 };
      const result = await adapter.generateFromIds(msg.ids, {
        maxTokens: msg.maxTokens || 64,
        signal: controller.signal,
        onStep: (step) => { if (current) current.steps = step + 1; },
      });
      self.postMessage({ id, type: "result", result,
        workerWallMs: +(performance.now() - current.startedAt).toFixed(1),
        mem: mem() });
      current = null;
      controller = null;
      return;
    }
    if (cmd === "cancel") {
      const observed = performance.now();
      if (!controller) {
        self.postMessage({ id, type: "cancelAck", aborted: false,
                           receivedAt: observed,
                           reason: "no generation in flight" });
        return;
      }
      const stepsBefore = current ? current.steps : 0;
      controller.abort();
      self.postMessage({ id, type: "cancelAck", aborted: true,
        receivedAt: observed, stepsBefore });
      return;
    }
    if (cmd === "release") {
      adapter.release();
      self.postMessage({ id, type: "released", mem: mem() });
      return;
    }
    if (cmd === "mem") {
      self.postMessage({ id, type: "mem", mem: mem() });
      return;
    }
    self.postMessage({ id, type: "error", error: { message: "unknown cmd " + cmd } });
  } catch (e) {
    if (e && e.name === "AbortError") {
      self.postMessage({ id: msg.id, type: "cancelled",
        detail: e.detail || null,
        completedSteps: e.detail ? e.detail.completedSteps : null,
        stepEndOffsetsMs: e.detail ? e.detail.stepEndOffsetsMs : null,
        mem: mem() });
    } else {
      self.postMessage({ id: msg.id, type: "error",
        error: { name: e && e.name, message: String(e && e.message || e) } });
    }
  }
};
