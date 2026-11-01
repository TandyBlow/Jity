// N4 browser adapter (batch 3): the frozen r3-direction T5 runs in the
// browser end-to-end through this module —
//   tokenizer   sentencepiece-js (the real spiece.model bytes, verified
//               id-identical to the Python T5Tokenizer on every probe and
//               corpus text; legacy=False parity)
//   graphs      encoder.onnx + decoder_kv.onnx (self-attention-only KV
//               cache; cross-attention K/V recomputed per step inside the
//               graph), fp32 reference or int8 dynamic
//   loop        greedy, max_new_tokens, per-step AbortSignal checks (the
//               ORT run itself is not interruptible — documented F3 — so
//               cancellation granularity is one step; an aborted result is
//               thrown away, never applied)
// Provenance: the adapter is C's verified experiment module; page
// integration stays with B (see component-contracts §8).
//
// The sentencepiece-js bundle is CJS with an unconditional require('fs'):
// the shim feeds it a stub fs whose readFileSync serves PRE-FETCHED bytes,
// so the unmodified load() path (emscripten FS.writeFile) works in the
// browser; the wasm is embedded in the bundle (data URIs).

export const N4_ADAPTER_ID = "n4-browser-adapter-r1";

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

export class N4Browser {
  /** dir: base URL for encoder.onnx/decoder_kv.onnx; int8 selects the
   *  r3-direction-int8 graphs; graphDirOverride for explicit URLs. */
  static async create({ ortBundleUrl = "/ort/ort.bundle.min.mjs",
                        wasmPaths = "/ort/",
                        spBundleUrl, modelBytesUrl,
                        graphDir, int8 = false } = {}) {
    const ort = await import(ortBundleUrl);
    ort.env.wasm.numThreads = 1; // documented single-thread constraint (F3)
    ort.env.wasm.wasmPaths = wasmPaths;
    const bytes = await (await fetch(modelBytesUrl)).arrayBuffer();
    const sp = await loadSentencePiece(spBundleUrl, bytes);
    const so = { executionProviders: ["wasm"], graphOptimizationLevel: "all" };
    const t0 = performance.now();
    // int8 is a separate graphDir served by the caller (r3-direction-int8)
    const enc = await ort.InferenceSession.create(`${graphDir}/encoder.onnx`, so);
    const dec = await ort.InferenceSession.create(`${graphDir}/decoder_kv.onnx`, so);
    const loadMs = performance.now() - t0;
    const inNames = dec.inputNames.slice(5);
    return new N4Browser(ort, sp, enc, dec, loadMs, inNames, int8);
  }

  constructor(ort, sp, enc, dec, loadMs, pastNames, int8) {
    this.ort = ort;
    this.sp = sp;
    this.enc = enc;
    this.dec = dec;
    this.loadMs = loadMs;
    this.pastNames = pastNames;
    this.int8 = int8;
    // frozen r3-direction config: 6 decoder heads, d_kv 64; the KV graph
    // inputs carry dynamic past dims, so the shapes are pinned here
    this.heads = 6;
    this.dk = 64;
  }

  encode(text) {
    // T5Tokenizer appends </s> (id 1) after the raw sentencepiece ids
    // (legacy=False parity); sentencepiece-js does not add it
    const ids = Array.from(this.sp.encodeIds(text));
    ids.push(1);
    return ids;
  }

  decode(ids) {
    return this.sp.decodeIds(ids);
  }

  /** Greedy generation. signal: AbortSignal checked between steps; an
   *  aborted call throws DOMException AbortError and returns nothing —
   *  the partial text is never applied (interface-table §2.1). */
  async generate(text, { maxTokens = 64, signal = null } = {}) {
    const ids = this.encode(text);
    const tEnc0 = performance.now();
    const hidden = await this.enc.run({
      input_ids: new this.ort.Tensor("int64",
          BigInt64Array.from(ids.map(BigInt)), [1, ids.length]),
      attention_mask: new this.ort.Tensor("int64",
          BigInt64Array.from(ids.map(() => 1n)), [1, ids.length]),
    });
    const encStates = hidden.encoder_hidden_states;
    const encMs = performance.now() - tEnc0;
    const eos = 1, pad = 0; // T5: </s>=1, <pad>=0 (frozen checkpoint vocab)
    const stepMs = [];
    let prefix = [pad];
    const out = [];
    let empty = new this.ort.Tensor("float32", new Float32Array(0), [1, this.heads, 0, this.dk]);
    let past = Object.fromEntries(this.pastNames.map((n) => [n, empty]));
    let step = 0;
    for (; step < maxTokens; step++) {
      if (signal && signal.aborted) {
        const e = new DOMException("aborted before step " + step, "AbortError");
        e.detail = { completedSteps: step };
        throw e;
      }
      // Yield a MACROTASK between steps. ORT-web single-thread runs execute
      // synchronously and their promises resolve within the microtask
      // cascade: without this yield the whole generation starves timers,
      // AbortSignal can never fire mid-generation, and the page freezes.
      await new Promise((r) => setTimeout(r));
      const feeds = {
        // the KV graph is a single-token-step contract (the Python loop
        // feeds [[token]] each step); the full prefix lives in the cache
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
      const [b, seq, vocab] = logits.dims;
      const data = logits.data;
      let best = 0;
      for (let v = 1; v < vocab; v++) {
        if (data[(seq - 1) * vocab + v] > data[(seq - 1) * vocab + best]) best = v;
      }
      const flat = [];
      // outputs: [logits, present_0_self_k, present_0_self_v, ...] — the
      // present tensors start at index 1 and mirror this.pastNames in order
      for (let i = 1; i < this.dec.outputNames.length; i++) {
        flat.push(res[this.dec.outputNames[i]]);
      }
      past = Object.fromEntries(this.pastNames.map((n, i) => [n, flat[i]]));
      if (best === eos) break;
      out.push(best);
      prefix.push(best);
    }
    return {
      ids: out,
      text: this.decode(out),
      timings: { encodeMs: null, encoderMs: +encMs.toFixed(1),
                 generationMs: +stepMs.reduce((a, b) => a + b, 0).toFixed(1),
                 meanStepMs: +(stepMs.reduce((a, b) => a + b, 0) / Math.max(stepMs.length, 1)).toFixed(1),
                 steps: stepMs.length },
      graphVariant: this.int8 ? "int8" : "fp32",
    };
  }
}
