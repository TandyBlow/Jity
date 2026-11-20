// c9 browser-side T5 encoder-decoder runtime (77M r3-direction, fp32 or int8
// ONNX).
//
// The generation loop is deliberately the same shape as the verified batch-3
// adapter (experiments/world-components/browser_probe/n4_browser_adapter.mjs,
// sha256 dc6ea7800734604d70cff5914e7facf46c237f0d2931db2a67e2ed280860182c):
// one token per decoder step, self-attention KV cache, cross-attention K/V
// recomputed inside the graph, greedy argmax, stop on </s>. What this copy
// adds is measurement, not behaviour: per-stage cold-start timing, per-step
// timings, an onStep hook, an abort that reports when it was observed, and an
// explicit release().
//
// The tokenizer is separated from the model:
//   createTokenizer()  sentencepiece-js + the real spiece.model bytes
//   T5Browser.create() ORT sessions only, or with a pre-built tokenizer
// Splitting them is what lets the model live in a worker (see t5_worker.mjs)
// while the small, cheap tokenizer stays on the main thread. It also means a
// worker-run probe measures the thing being reclaimed (the wasm heap), not a
// CJS bundle loaded through a shim.
//
// Tokenizer note: the sentencepiece-js bundle is CJS and asks for Node
// built-ins. The shim answers 'fs' (model bytes already fetched), and in a
// worker the emscripten path also touches 'url'/'module'/__filename, so those
// are stubbed too. Nothing is written to disk on either side.

export const ADAPTER_ID = "c9-browser-t5-adapter-r2";
export const LOOP_SOURCE_SHA256 =
  "dc6ea7800734604d70cff5914e7facf46c237f0d2931db2a67e2ed280860182c";

function instantiateSp(src, modelBytes) {
  const files = { "spiece.model": modelBytes };
  const stubFs = {
    readFileSync: (p) => {
      const key = String(p).split(/[\\/]/).pop();
      if (!(key in files)) throw new Error("fs stub: no preloaded file " + key);
      return new Uint8Array(files[key]); // emscripten FS.writeFile rejects ArrayBuffer
    },
  };
  const stubPath = {
    basename: (p) => String(p).split(/[\\/]/).pop(),
    dirname: (p) => String(p).split(/[\\/]/).slice(0, -1).join("/") || ".",
    join: (...xs) => xs.join("/").replace(/\/+/g, "/"),
    sep: "/",
  };
  const mods = { fs: stubFs, path: stubPath, url: { URL },
                 module: { createRequire: () => fakeRequire } };
  function fakeRequire(name) {
    const key = String(name).replace(/^node:/, "");
    if (key in mods) return mods[key];
    throw new Error("browser shim: require('" + name + "') unavailable");
  }
  const module_ = { exports: {} };
  // __filename/__dirname exist because emscripten's `typeof document ===
  // "undefined"` branch (a worker) builds its module URL from __filename
  const factory = new Function("module", "require", "exports",
                               "__filename", "__dirname",
                               src + "\nreturn module.exports;");
  factory(module_, fakeRequire, module_.exports, "/index.js", "/");
  return module_.exports;
}

/** Main-thread tokenizer. encode() appends </s>=1 like T5Tokenizer. */
export async function createTokenizer({ spBundleUrl, modelBytesUrl }) {
  const t0 = performance.now();
  const spSrc = await (await fetch(spBundleUrl)).arrayBuffer();
  const fetchBundleMs = performance.now() - t0;
  const t1 = performance.now();
  const bytes = await (await fetch(modelBytesUrl)).arrayBuffer();
  const fetchModelMs = performance.now() - t1;
  const t2 = performance.now();
  const smp = instantiateSp(new TextDecoder().decode(spSrc), bytes);
  const sp = new smp.SentencePieceProcessor();
  await sp.load("spiece.model");
  const loadMs = performance.now() - t2;
  if (typeof sp.encodeIds !== "function") {
    throw new Error("tokenizer: SentencePieceProcessor has no encodeIds " +
                    "(exports: " + Object.keys(smp).slice(0, 8).join(",") + ")");
  }
  return {
    sp,
    stages: { fetchBundleMs: +fetchBundleMs.toFixed(1),
              fetchModelMs: +fetchModelMs.toFixed(1),
              loadMs: +loadMs.toFixed(1) },
    encode(text) { const ids = Array.from(sp.encodeIds(text)); ids.push(1); return ids; },
    decode(ids) { return sp.decodeIds(ids); },
  };
}

export class T5Browser {
  /** tokenizer: result of createTokenizer(); omit to run ids-only (worker). */
  static async create({ ortBundleUrl = "/ort/ort.bundle.min.mjs",
                        wasmPaths = "/ort/",
                        graphDir, heads, dKv, threads = 1,
                        tokenizer = null } = {}) {
    const stages = {};
    let t = performance.now();
    const ort = await import(ortBundleUrl);
    stages.ortImportMs = +(performance.now() - t).toFixed(1);

    ort.env.wasm.numThreads = threads; // documented single-thread constraint
    ort.env.wasm.wasmPaths = wasmPaths;

    const so = { executionProviders: ["wasm"], graphOptimizationLevel: "all" };
    t = performance.now();
    const enc = await ort.InferenceSession.create(`${graphDir}/encoder.onnx`, so);
    stages.encoderCreateMs = +(performance.now() - t).toFixed(1);
    t = performance.now();
    const dec = await ort.InferenceSession.create(`${graphDir}/decoder_kv.onnx`, so);
    stages.decoderCreateMs = +(performance.now() - t).toFixed(1);

    const inst = new T5Browser(ort, tokenizer, enc, dec, heads, dKv, stages);
    inst.pastNames = dec.inputNames.slice(5);
    inst.stages.createTotalMs = +(stages.ortImportMs + stages.encoderCreateMs +
      stages.decoderCreateMs).toFixed(1);
    return inst;
  }

  constructor(ort, tokenizer, enc, dec, heads, dKv, stages) {
    this.ort = ort;
    this.tok = tokenizer;
    this.enc = enc;
    this.dec = dec;
    this.heads = heads;
    this.dKv = dKv;
    this.stages = stages;
    this.pastNames = [];
  }

  // guarded so a worker (no tokenizer) fails loudly instead of half-working
  encode(text) {
    if (!this.tok) throw new Error("no tokenizer attached");
    return this.tok.encode(text);
  }

  decode(ids) {
    if (!this.tok) throw new Error("no tokenizer attached");
    return this.tok.decode(ids);
  }

  /** Greedy generation from an id array. Returns raw ids + timings; no
   *  post-processing. signal: checked before every step; a cancelled call
   *  throws AbortError and hands back nothing usable. */
  async generateFromIds(ids, { maxTokens = 64, signal = null, onStep = null,
                               macrotaskYield = true } = {}) {
    if (ids.length > 128) {
      return { status: "unsupported", reason: "input-too-long",
               tokens: ids.length, modelCalled: false };
    }
    const tEnc0 = performance.now();
    const hidden = await this.enc.run({
      input_ids: new this.ort.Tensor("int64",
          BigInt64Array.from(ids.map(BigInt)), [1, ids.length]),
      attention_mask: new this.ort.Tensor("int64",
          BigInt64Array.from(ids.map(() => 1n)), [1, ids.length]),
    });
    const encStates = hidden.encoder_hidden_states;
    const encMs = performance.now() - tEnc0;

    const eos = 1, pad = 0;
    const stepMs = [];
    const t0Loop = performance.now();
    const stepEndOffsetsMs = [];
    let prefix = [pad];
    const out = [];
    const empty = new this.ort.Tensor("float32", new Float32Array(0),
                                      [1, this.heads, 0, this.dKv]);
    let past = Object.fromEntries(this.pastNames.map((n) => [n, empty]));
    let step = 0;
    let finishReason = "max_tokens";
    // Checked at every point where control can return to the caller or to a
    // callback: before the step, after the macrotask yield, and after onStep.
    // Without the third one, an onStep() that aborts synchronously still costs
    // one more decoder step.
    const throwIfAborted = (phase) => {
      if (!signal || !signal.aborted) return;
      const e = new DOMException("aborted before step " + step, "AbortError");
      // abortObservedAt is the instant the loop noticed the signal; the caller
      // records when it issued abort(), and the gap is the real latency.
      e.detail = { completedSteps: step, partialIds: null,
                   abortObservedAt: performance.now(),
                   abortPhase: phase,
                   stepEndOffsetsMs: stepEndOffsetsMs.slice() };
      throw e;
    };
    for (; step < maxTokens; step++) {
      throwIfAborted("before-step");
      // macrotask yield (off only for the "cost of yielding" measurement):
      // ORT-web single-thread runs inside a microtask cascade, so without it
      // the page cannot observe an abort, receive a cancel message, or repaint
      if (macrotaskYield) await new Promise((r) => setTimeout(r));
      throwIfAborted("after-yield");
      if (onStep) onStep(step);
      throwIfAborted("after-onStep");
      const feeds = {
        decoder_input_ids: new this.ort.Tensor("int64",
            BigInt64Array.from([BigInt(prefix[prefix.length - 1])]), [1, 1]),
        encoder_hidden_states: encStates,
        encoder_attention_mask: new this.ort.Tensor("int64",
            BigInt64Array.from(ids.map(() => 1n)), [1, ids.length]),
        cache_position: new this.ort.Tensor("int64", BigInt64Array.from([BigInt(step)]), [1]),
        self_mask: new this.ort.Tensor("int64",
            BigInt64Array.from(Array.from({ length: step + 1 }, () => 1n)), [1, step + 1]),
        ...past,
      };
      const t0 = performance.now();
      const res = await this.dec.run(feeds);
      stepMs.push(performance.now() - t0);
      const logits = res.logits;
      const [, seq, vocab] = logits.dims;
      const data = logits.data;
      let best = 0;
      for (let v = 1; v < vocab; v++) {
        if (data[(seq - 1) * vocab + v] > data[(seq - 1) * vocab + best]) best = v;
      }
      const flat = [];
      for (let i = 1; i < this.dec.outputNames.length; i++) {
        flat.push(res[this.dec.outputNames[i]]);
      }
      past = Object.fromEntries(this.pastNames.map((n, i) => [n, flat[i]]));
      stepEndOffsetsMs.push(+(performance.now() - t0Loop).toFixed(1));
      if (best === eos) {
        finishReason = "eos";
        break;
      }
      out.push(best);
      prefix.push(best);
    }
    // A run that stops because maxTokens ran out is NOT the same result as one
    // that produced </s>: the text is a prefix, not a finished sentence. Keep
    // status "ok" only for a real end and say so explicitly.
    return {
      status: finishReason === "eos" ? "ok" : "truncated",
      finishReason,
      maxTokens,
      ids: out,
      text: this.tok ? this.tok.decode(out) : null,
      inputTokens: ids.length,
      timings: { encoderMs: +encMs.toFixed(1),
                 stepEndOffsetsMs,
                 generationMs: +stepMs.reduce((a, b) => a + b, 0).toFixed(1),
                 meanStepMs: +(stepMs.reduce((a, b) => a + b, 0) /
                               Math.max(stepMs.length, 1)).toFixed(1),
                 steps: stepMs.length,
                 stepMs: stepMs.map((x) => +x.toFixed(1)) },
    };
  }

  generate(text, opts = {}) {
    return this.generateFromIds(this.encode(text), opts);
  }

  release() {
    try { this.enc.release(); } catch { /* already released */ }
    try { this.dec.release(); } catch { /* already released */ }
  }
}
