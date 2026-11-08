// c9 browser-side T5 encoder-decoder runtime (77M r3-direction, fp32 ONNX).
//
// The generation loop is deliberately the same shape as the verified
// batch-3 adapter (experiments/world-components/browser_probe/
// n4_browser_adapter.mjs, sha256 dc6ea7800734604d70cff5914e7facf46c237f0d2931db2a67e2ed280860182c):
// one token per decoder step, self-attention KV cache, cross-attention K/V
// recomputed inside the graph, greedy argmax, stop on </s>. What this copy
// adds is measurement, not behaviour:
//   - per-stage cold-start timing (module import / tokenizer / each session)
//   - an onStep hook so a cancel can be issued deterministically at a step
//     boundary, and per-step timings are kept
//   - an explicit release() so memory can be sampled before and after
// If any of that changed numerics, the token-parity gate against
// ORT-python would fail — that is the check, not a promise.
//
// Tokenizer: sentencepiece-js fed the real spiece.model bytes through a
// stub-fs shim (the bundle has an unconditional require('fs')). T5 appends
// </s>=1 after the raw sentencepiece ids; sentencepiece-js does not.

export const ADAPTER_ID = "c9-browser-t5-adapter-r1";
export const LOOP_SOURCE_SHA256 =
  "dc6ea7800734604d70cff5914e7facf46c237f0d2931db2a67e2ed280860182c";

async function loadSentencePiece(bundleUrl, modelBytes) {
  const src = await (await fetch(bundleUrl)).text();
  const files = { "spiece.model": modelBytes };
  const stubFs = { readFileSync: (p) => {
    const key = String(p).split(/[\\/]/).pop();
    if (!(key in files)) throw new Error("fs stub: no preloaded file " + key);
    return new Uint8Array(files[key]); // emscripten FS.writeFile rejects ArrayBuffer
  } };
  const fakeRequire = (name) => {
    if (name === "fs") return stubFs;
    throw new Error("browser shim: require('" + name + "') unavailable");
  };
  const module_ = { exports: {} };
  const factory = new Function("module", "require", "exports",
                               src + "\nreturn module.exports;");
  factory(module_, fakeRequire, module_.exports);
  const smp = module_.exports;
  const sp = new smp.SentencePieceProcessor();
  await sp.load("spiece.model");
  return sp;
}

export class T5Browser {
  static async create({ ortBundleUrl = "/ort/ort.bundle.min.mjs",
                        wasmPaths = "/ort/",
                        spBundleUrl, modelBytesUrl,
                        graphDir, heads, dKv, threads = 1 } = {}) {
    const stages = {};
    let t = performance.now();
    const ort = await import(ortBundleUrl);
    stages.ortImportMs = +(performance.now() - t).toFixed(1);

    ort.env.wasm.numThreads = threads; // documented single-thread constraint
    ort.env.wasm.wasmPaths = wasmPaths;

    t = performance.now();
    const spSrc = await (await fetch(spBundleUrl)).arrayBuffer();
    const spBundleFetchMs = performance.now() - t;
    t = performance.now();
    const bytes = await (await fetch(modelBytesUrl)).arrayBuffer();
    stages.tokenizerFetchMs = +(spBundleFetchMs + (performance.now() - t)).toFixed(1);
    t = performance.now();
    const sp = await (async () => {
      // same shim path as loadSentencePiece, but the bundle is already here
      const src = new TextDecoder().decode(spSrc);
      const files = { "spiece.model": bytes };
      const stubFs = { readFileSync: (p) => {
        const key = String(p).split(/[\\/]/).pop();
        if (!(key in files)) throw new Error("fs stub: no preloaded file " + key);
        return new Uint8Array(files[key]);
      } };
      const fakeRequire = (name) => {
        if (name === "fs") return stubFs;
        throw new Error("browser shim: require('" + name + "') unavailable");
      };
      const module_ = { exports: {} };
      const factory = new Function("module", "require", "exports",
                                   src + "\nreturn module.exports;");
      factory(module_, fakeRequire, module_.exports);
      const sp = new module_.exports.SentencePieceProcessor();
      await sp.load("spiece.model");
      return sp;
    })();
    stages.spLoadMs = +(performance.now() - t).toFixed(1);

    const so = { executionProviders: ["wasm"], graphOptimizationLevel: "all" };
    t = performance.now();
    const enc = await ort.InferenceSession.create(`${graphDir}/encoder.onnx`, so);
    stages.encoderCreateMs = +(performance.now() - t).toFixed(1);
    t = performance.now();
    const dec = await ort.InferenceSession.create(`${graphDir}/decoder_kv.onnx`, so);
    stages.decoderCreateMs = +(performance.now() - t).toFixed(1);

    const inst = new T5Browser(ort, sp, enc, dec, heads, dKv, stages);
    inst.pastNames = dec.inputNames.slice(5);
    inst.stages.createTotalMs = +(stages.ortImportMs + stages.tokenizerFetchMs +
      stages.spLoadMs + stages.encoderCreateMs + stages.decoderCreateMs).toFixed(1);
    return inst;
  }

  constructor(ort, sp, enc, dec, heads, dKv, stages) {
    this.ort = ort;
    this.sp = sp;
    this.enc = enc;
    this.dec = dec;
    this.heads = heads;
    this.dKv = dKv;
    this.stages = stages;
    this.pastNames = [];
  }

  encode(text) {
    const ids = Array.from(this.sp.encodeIds(text));
    ids.push(1); // T5Tokenizer appends </s>
    return ids;
  }

  decode(ids) {
    return this.sp.decodeIds(ids);
  }

  /** Greedy generation. Returns raw ids + timings; no post-processing.
   *  signal: checked before every step; a cancelled call throws AbortError
   *  and hands back nothing usable (partial output is never returned). */
  async generate(text, { maxTokens = 64, signal = null, onStep = null,
                         macrotaskYield = true } = {}) {
    const ids = this.encode(text);
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
    let prefix = [pad];
    const out = [];
    const empty = new this.ort.Tensor("float32", new Float32Array(0),
                                      [1, this.heads, 0, this.dKv]);
    let past = Object.fromEntries(this.pastNames.map((n) => [n, empty]));
    let step = 0;
    for (; step < maxTokens; step++) {
      if (signal && signal.aborted) {
        const e = new DOMException("aborted before step " + step, "AbortError");
        e.detail = { completedSteps: step, partialIds: null };
        throw e;
      }
      // macrotask yield (switched off only for the "cost of yielding"
      // measurement): ORT-web single-thread runs synchronously inside a
      // microtask cascade, so without this the page cannot observe an abort
      // or repaint mid-generation
      if (macrotaskYield) await new Promise((r) => setTimeout(r));
      if (onStep) onStep(step);
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
      if (best === eos) break;
      out.push(best);
      prefix.push(best);
    }
    return {
      status: "ok",
      ids: out,
      text: this.decode(out),
      inputTokens: ids.length,
      timings: { encoderMs: +encMs.toFixed(1),
                 generationMs: +stepMs.reduce((a, b) => a + b, 0).toFixed(1),
                 meanStepMs: +(stepMs.reduce((a, b) => a + b, 0) /
                               Math.max(stepMs.length, 1)).toFixed(1),
                 steps: stepMs.length,
                 stepMs: stepMs.map((x) => +x.toFixed(1)) },
    };
  }

  release() {
    try { this.enc.release(); } catch { /* already released */ }
    try { this.dec.release(); } catch { /* already released */ }
  }
}
