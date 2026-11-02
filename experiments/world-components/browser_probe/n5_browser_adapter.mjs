// N5 browser adapter (commit 3): MiniRBT-H256 relation head in the browser.
//
//   tokenizer  hand-rolled BertTokenizer-equivalent (Chinese per-char,
//              lowercase, longest-match WordPiece for ASCII/digit runs,
//              [CLS]/[SEP]); verified id-identical to Python BertTokenizer
//              on the baked cases before any label is consumed
//   graph      n5-encoder-head.onnx (encoder + masked mean-pool + linear
//              head fused; exported by export_n5_onnx.py with a
//              Python-side 1e-4 parity gate)
//   decision   frozen rule: support if p_s >= t_s; else contradiction if
//              p_c >= t_c; else unknown (待核). Thresholds are fixed on
//              the dev split by eval_n5_head.py and passed in, never fitted
//              in the browser.
//
// The adapter is C's experiment module; page wiring stays with B.

export const N5_ADAPTER_ID = "n5-browser-adapter-r1";

export class N5Browser {
  static async create({ ortBundleUrl = "/ort/ort.bundle.min.mjs",
                        wasmPaths = "/ort/", modelUrl, vocabUrl,
                        maxLen = 96 } = {}) {
    const ort = await import(ortBundleUrl);
    ort.env.wasm.numThreads = 1;
    ort.env.wasm.wasmPaths = wasmPaths;
    const vocabText = await (await fetch(vocabUrl)).text();
    const vocab = new Map();
    vocabText.split("\n").forEach((line, index) =>
      vocab.set(line.replace(/\r$/, ""), index));
    const t0 = performance.now();
    const session = await ort.InferenceSession.create(modelUrl, {
      executionProviders: ["wasm"], graphOptimizationLevel: "all" });
    const loadMs = performance.now() - t0;
    return new N5Browser(ort, vocab, session, loadMs, maxLen);
  }

  constructor(ort, vocab, session, loadMs, maxLen) {
    this.ort = ort;
    this.vocab = vocab;
    this.session = session;
    this.loadMs = loadMs;
    this.maxLen = maxLen;
  }

  getId(token) {
    const id = this.vocab.get(token);
    return id === undefined ? this.vocab.get("[UNK]") : id;
  }

  /** BertTokenizer-equivalent ids WITHOUT padding: [CLS] … [SEP].
   *  Matches transformers.BertTokenizer(do_lower_case=True) on the probe
   *  cases; parity is asserted in the probe before inference is trusted. */
  encode(text) {
    const ids = [this.getId("[CLS]")];
    let asciiRun = [];
    const flushAscii = () => {
      if (!asciiRun.length) return;
      const word = asciiRun.join("");
      asciiRun = [];
      let start = 0;
      while (start < word.length) {
        let end = word.length;
        let id = null;
        while (end > start) {
          const piece = start === 0
            ? word.slice(start, end) : "##" + word.slice(start, end);
          if (this.vocab.has(piece)) {
            id = this.vocab.get(piece);
            break;
          }
          end -= 1;
        }
        if (id === null) {
          id = this.vocab.get("[UNK]");
          end = start + 1;
        }
        ids.push(id);
        start = end;
      }
    };
    for (const ch of text.toLowerCase()) {
      if (/\s/.test(ch)) {
        flushAscii();
        continue;
      }
      if (/[a-z0-9]/.test(ch)) {
        asciiRun.push(ch);
        continue;
      }
      flushAscii();
      ids.push(this.getId(ch));
    }
    flushAscii();
    ids.push(this.getId("[SEP]"));
    return ids.slice(0, this.maxLen);
  }

  /** Full component call: text -> ids -> graph -> softmax -> frozen-label
   *  rule. Returns the raw logits and probabilities so the archive can
   *  compare them against the Python reference, not just the label. */
  async classify(text, { tSupport, tContradict } = {}) {
    const t0 = performance.now();
    const ids = this.encode(text);
    const tIds = performance.now();
    const len = ids.length;
    const feed = {
      input_ids: new this.ort.Tensor("int64",
        BigInt64Array.from(ids.map(BigInt)), [1, len]),
      attention_mask: new this.ort.Tensor("int64",
        BigInt64Array.from({ length: len }, () => 1n), [1, len]),
    };
    const out = await this.session.run(feed);
    const tRun = performance.now();
    const logits = Array.from(out.logits.data).map(Number);
    const max = Math.max(...logits);
    const exps = logits.map((v) => Math.exp(v - max));
    const sum = exps.reduce((a, b) => a + b, 0);
    const probs = exps.map((v) => v / sum);
    const label = probs[0] >= tSupport ? "support"
      : probs[1] >= tContradict ? "contradiction" : "unknown";
    return {
      ids, logits, probs, label,
      timings: {
        tokenizeMs: +(tIds - t0).toFixed(2),
        runMs: +(tRun - tIds).toFixed(2),
        totalMs: +(performance.now() - t0).toFixed(2),
      },
    };
  }
}
