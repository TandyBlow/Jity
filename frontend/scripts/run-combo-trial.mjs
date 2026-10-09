// Combo trial: action-type classifier -> category-conditioned span
// extraction (user-directed round, 2026-10-09).
//
// RULE (as specified): when the classifier says inspect / move / npc_talk,
// constrained decoding is FORBIDDEN from emitting an ITEM span (forced
// empty; TGT still enumerated under the same whole-sentence argmax).
// item_use / other keep the current constraints — 拔剑攻击 classifies as
// "other" and must still extract 剑.
//
// ARMS (data + weights frozen; the 53 dev sentences of the labeler manifest
// are reused unchanged, the manifest file itself is not touched):
// - goldRule: categories from the hand annotation
//   artifacts/benchmark/span-labeler-dev-categories.json (sha recorded)
//   -> does the rule help when the category is right.
// - predRule: categories from the frozen minirbt-h256-action classifier
//   (q8, single-thread) -> the actual chain; misclassification impact is
//   reported per case, separately from the rule effect.
// Reported variants per case: greedy (current accepted default,
// unconditioned), constrained (plain, identical to the labeler trial),
// goldRule, predRule.
//
// TIMING SCOPE: three chains timed per case, each with its own REPEATS+1
// loop and median — classifyMs (classifier only: text -> tokenize -> run ->
// argmax -> label), greedyChainMs (classify + greedy extract: the default
// pipeline where the classifier runs alongside), ruleChainMs (classify +
// rule-constrained extract keyed on the PREDICTED category). All three
// cover tokenize -> feed -> run -> decode end-to-end. The three medians are
// independent measurements of whole paths — not additively decomposable
// into stage costs.
//
// FREEZE: labeler manifest and classifier corpus untouched (both shas
// recorded); the sealed acceptance batch is NOT loaded (gate:
// not-evaluated); greedy stays the accepted decode mode.
//
// Usage: node scripts/run-combo-trial.mjs
// Output: artifacts/benchmark/combo-trial-<ts>.json

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const frontendRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const baseUrl = process.env.BASE_URL ?? "http://localhost:3100";
const TARGET_MS = 4000;
const REPEATS = 10;
const CREATE_TIMEOUT_MS = 30000;

const LABELER_DIR = "/models/minirbt-h256-span";
const CLASSIFIER_DIR = "/models/minirbt-h256-action";
const LABELER_ROOT = path.join(frontendRoot, "public", "models", "minirbt-h256-span");
const CLASSIFIER_ROOT = path.join(frontendRoot, "public", "models", "minirbt-h256-action");
const MANIFEST_PATH = path.join(frontendRoot, "..", "artifacts", "benchmark", "span-labeler-corpus.json");
const CATEGORIES_PATH = path.join(frontendRoot, "..", "artifacts", "benchmark", "span-labeler-dev-categories.json");
const CLASSIFIER_CORPUS_PATH = path.join(frontendRoot, "..", "artifacts", "benchmark", "classifier-action-corpus.json");
const TAGS = ["O", "B-ITEM", "I-ITEM", "B-TGT", "I-TGT"];
const LABELS = ["item_use", "npc_talk", "move", "inspect", "other"];
const CLASS_ORDER = [
  "ok", "span-false", "span-missing", "all-o", "truncated-o", "truncated-b",
  "wrong-field", "over-extended", "boundary-mismatch", "modifier-as-head", "displaced",
];

const sha256 = (buffer) => createHash("sha256").update(buffer).digest("hex");

const log = (...parts) => console.log(new Date().toISOString().slice(11, 19), ...parts);

async function main() {
  // ── 唯一数据源：labeler 语料 manifest（不改动）+ 独立的类别标注层。───
  const manifestBytes = await readFile(MANIFEST_PATH);
  const manifest = JSON.parse(manifestBytes.toString("utf-8"));
  const categoriesBytes = await readFile(CATEGORIES_PATH);
  const categoriesDoc = JSON.parse(categoriesBytes.toString("utf-8"));
  const classifierCorpusBytes = await readFile(CLASSIFIER_CORPUS_PATH);
  const classifierCorpus = JSON.parse(classifierCorpusBytes.toString("utf-8"));
  const suppressCategories = categoriesDoc.suppressCategories;
  const categoryByText = new Map(categoriesDoc.categories.map((c) => [c.text, c.category]));
  // 与分类器语料的重叠标记：train 内 = 预测被污染；classifier 计分 12 句
  // 被分类器排除在训练外（干净泛化）；其余 = 未见。
  const classifierTrainTexts = new Set([...classifierCorpus.train, ...classifierCorpus.val].map((r) => r.text));
  const classifierScoredTexts = new Set(classifierCorpus.test.map((r) => r.text));

  const batches = [
    { name: "devClassic", rows: manifest.devClassic, tokens: true },
    { name: "devGroups", rows: manifest.devGroups.flatMap((g) => g.sentences.map((s) => ({ ...s, group: g.group }))), tokens: true },
    { name: "scored", rows: manifest.scored, tokens: false },
  ];
  for (const batch of batches) {
    for (const row of batch.rows) {
      row.goldCategory = categoryByText.get(row.text);
      if (!row.goldCategory) {
        console.error(`FATAL: no category annotation for: ${row.text}`);
        process.exit(2);
      }
      row.dataOverlap = classifierTrainTexts.has(row.text) ? "classifier-train" : classifierScoredTexts.has(row.text) ? "classifier-scored" : null;
    }
  }
  const dataSha = sha256(manifestBytes);
  log(`data: labeler manifest sha256=${dataSha.slice(0, 16)}… categories sha256=${sha256(categoriesBytes).slice(0, 16)}… (suppress: ${suppressCategories.join("/")})`);
  log(`sealed acceptance: NOT evaluated (combo trial never loads it)`);

  const modelFiles = {};
  for (const [name, root] of [["labeler", LABELER_ROOT], ["classifier", CLASSIFIER_ROOT]]) {
    modelFiles[name] = {};
    for (const rel of ["onnx/model.onnx", "onnx/model_quantized.onnx", "vocab.txt", "config.json"]) {
      try {
        const buf = await readFile(path.join(root, rel));
        modelFiles[name][rel] = { size: buf.length, sha256: sha256(buf) };
      } catch {
        modelFiles[name][rel] = null;
      }
    }
  }

  const cpu = os.cpus()[0]?.model ?? "unknown";
  log(`host CPU: ${cpu}`);

  const browser = await (async () => {
    try {
      return await chromium.launch({ channel: "msedge", headless: true });
    } catch {
      return chromium.launch({ headless: true });
    }
  })();
  const page = await browser.newPage();
  await page.goto(`${baseUrl}/benchmark`);
  await page.waitForLoadState("domcontentloaded");
  const isolated = await page.evaluate(() => window.crossOriginIsolated === true);
  const userAgent = await page.evaluate(() => navigator.userAgent);
  log(`crossOriginIsolated: ${isolated}`);
  if (!isolated) {
    console.error("FATAL: not cross-origin isolated; wasm multithread unavailable.");
    await browser.close();
    process.exit(2);
  }

  const armConfigs = [
    { name: "q8-t1", file: "onnx/model_quantized.onnx" },
    { name: "fp32-t1", file: "onnx/model.onnx" },
  ];
  const arms = [];
  for (const armConfig of armConfigs) {
    const armPage = await browser.newPage();
    await armPage.goto(`${baseUrl}/benchmark`);
    await armPage.waitForLoadState("domcontentloaded");
    const arm = await armPage.evaluate(
      async ({ modelDirLabeler, modelDirClassifier, labelerFile, classifierFile, tags, classOrder, labels, suppressCategories, batches, repeats, targetMs, timeoutMs }) => {
        const ort = await import("/ort/ort.bundle.min.mjs");
        ort.env.wasm.wasmPaths = "/ort/";
        ort.env.wasm.numThreads = 1;

        // 两个模型同源 MiniRBT-H256 分词器，共用一份词表。
        const vocabText = await fetch(`${window.location.origin}${modelDirLabeler}/vocab.txt`).then((r) => r.text());
        const vocab = new Map();
        vocabText.split("\n").forEach((line, index) => vocab.set(line.replace(/\r$/, ""), index));

        const tokenizeWithOffsets = (text, maxLen = 48) => {
          const ids = [vocab.get("[CLS]")];
          const offsets = [[0, 0]];
          let asciiRun = null;
          const flushAscii = () => {
            if (!asciiRun) return;
            const { word, start: base } = asciiRun;
            asciiRun = null;
            let start = 0;
            while (start < word.length && ids.length < maxLen - 1) {
              let end = word.length;
              let id = null;
              while (end > start) {
                const piece = start === 0 ? word.slice(start, end) : "##" + word.slice(start, end);
                if (vocab.has(piece)) {
                  id = vocab.get(piece);
                  break;
                }
                end -= 1;
              }
              if (id === null) {
                id = vocab.get("[UNK]");
                end = start + 1;
              }
              ids.push(id);
              offsets.push([base + start, base + end]);
              start = end;
            }
          };
          const chars = [...text];
          for (let index = 0; index < chars.length; index += 1) {
            const raw = chars[index];
            const ch = raw.toLowerCase();
            if (/\s/.test(ch)) {
              flushAscii();
              continue;
            }
            if (/[a-z0-9]/.test(ch)) {
              if (!asciiRun) asciiRun = { word: "", start: index };
              asciiRun.word += ch;
              continue;
            }
            flushAscii();
            if (ids.length >= maxLen - 1) break;
            ids.push(vocab.has(ch) ? vocab.get(ch) : vocab.get("[UNK]"));
            offsets.push([index, index + 1]);
          }
          flushAscii();
          ids.push(vocab.get("[SEP]"));
          offsets.push([0, 0]);
          return { ids: ids.slice(0, maxLen), offsets: offsets.slice(0, maxLen) };
        };

        const decodeSpans = (offsets, tagIds) => {
          const spans = { ITEM: null, TGT: null };
          let current = null;
          const flush = () => {
            if (current !== null && spans[current.type] === null) {
              spans[current.type] = [current.start, current.end];
            }
            current = null;
          };
          tagIds.forEach((tagId, index) => {
            const [tokenStart, tokenEnd] = offsets[index];
            const tag = tokenEnd === 0 || tagId >= tags.length ? "O" : tags[tagId];
            if (tag.startsWith("I-") && current !== null && current.type === tag.slice(2)) {
              current.end = tokenEnd;
              return;
            }
            flush();
            if (tag !== "O") current = { type: tag.slice(2), start: tokenStart, end: tokenEnd };
          });
          flush();
          return { ITEM: spans.ITEM, TGT: spans.TGT };
        };

        // 整句约束解码（与 train-span-labeler.py / run-labeler-trial.mjs 同
        // 口径、同枚举顺序）。suppressItem=true 时 ITEM 强制为空：只枚举
        // TGT 选项，其余规则不变——类别规则的唯一作用点。
        const constrainedDecode = (offsets, probs, suppressItem = false) => {
          const idx = [];
          for (let i = 0; i < offsets.length; i += 1) {
            if (offsets[i][1] !== 0) idx.push(i);
          }
          const n = idx.length;
          const ids = new Array(offsets.length).fill(0);
          if (n === 0) return { itemSpan: null, targetSpan: null, ids };
          const lp = (t, c) => Math.log(Math.max(probs[t][c], 1e-12));
          const options = (field) => {
            const bTag = tags.indexOf(`B-${field}`);
            const iTag = tags.indexOf(`I-${field}`);
            const oTag = tags.indexOf("O");
            const opts = [{ gain: 0, a: null, b: null }];
            for (let x = 0; x < n; x += 1) {
              let gain = lp(idx[x], bTag) - lp(idx[x], oTag);
              for (let y = x; y < n; y += 1) {
                if (y > x) gain += lp(idx[y], iTag) - lp(idx[y], oTag);
                opts.push({ gain, a: x, b: y });
              }
            }
            return opts;
          };
          const itemOpts = suppressItem ? [{ gain: 0, a: null, b: null }] : options("ITEM");
          const tgtOpts = options("TGT");
          let best = null;
          for (const itemOpt of itemOpts) {
            for (const tgtOpt of tgtOpts) {
              if (itemOpt.a !== null && tgtOpt.a !== null && itemOpt.a <= tgtOpt.b && tgtOpt.a <= itemOpt.b) continue;
              const total = itemOpt.gain + tgtOpt.gain;
              if (best === null || total > best.total) best = { total, itemOpt, tgtOpt };
            }
          }
          const assignment = new Array(n).fill("O");
          for (const [opt, field] of [[best.itemOpt, "ITEM"], [best.tgtOpt, "TGT"]]) {
            if (opt.a === null) continue;
            assignment[opt.a] = `B-${field}`;
            for (let t = opt.a + 1; t <= opt.b; t += 1) assignment[t] = `I-${field}`;
          }
          for (let k = 0; k < n; k += 1) ids[idx[k]] = tags.indexOf(assignment[k]);
          return {
            itemSpan: best.itemOpt.a === null ? null : [offsets[idx[best.itemOpt.a]][0], offsets[idx[best.itemOpt.b]][1]],
            targetSpan: best.tgtOpt.a === null ? null : [offsets[idx[best.tgtOpt.a]][0], offsets[idx[best.tgtOpt.b]][1]],
            ids,
          };
        };

        const diagnoseField = (text, gold, pred, otherGold, tokenRows, field, other) => {
          const classes = [];
          if (gold === null) {
            if (pred === null) return ["ok"];
            classes.push("span-false");
            if (otherGold !== null && pred[0] < otherGold[1] && otherGold[0] < pred[1]) classes.push("wrong-field");
            return classes;
          }
          const goldTokens = tokenRows.filter((row) => row.start < gold[1] && gold[0] < row.end);
          const mine = [`B-${field}`, `I-${field}`];
          const theirs = [`B-${other}`, `I-${other}`];
          const preds = goldTokens.map((row) => row.pred);
          if (preds.every((p) => p === "O")) classes.push("all-o");
          else if (preds.some((p) => p === "O") && preds.some((p) => mine.includes(p))) classes.push("truncated-o");
          if (goldTokens.some((row) => row.gold === `I-${field}` && row.pred === `B-${field}`)) classes.push("truncated-b");
          if (preds.some((p) => theirs.includes(p))) classes.push("wrong-field");
          if (pred === null) {
            classes.push("span-missing");
            return [...classes].sort((a, b) => classOrder.indexOf(a) - classOrder.indexOf(b));
          }
          if (pred[0] === gold[0] && pred[1] === gold[1]) return ["ok"];
          if (pred[0] < gold[1] && gold[0] < pred[1]) {
            classes.push(gold[0] >= pred[0] && pred[1] >= gold[1] ? "over-extended" : "boundary-mismatch");
            return [...classes].sort((a, b) => classOrder.indexOf(a) - classOrder.indexOf(b));
          }
          if (otherGold !== null && pred[0] < otherGold[1] && otherGold[0] < pred[1]) classes.push("wrong-field");
          if (pred[1] <= gold[0] && (text.slice(pred[1], gold[0]).includes("的") || text.slice(pred[0], pred[1]).endsWith("的"))) {
            classes.push("modifier-as-head");
          } else {
            classes.push("displaced");
          }
          return [...classes].sort((a, b) => classOrder.indexOf(a) - classOrder.indexOf(b));
        };

        const labelerConfig = await fetch(`${window.location.origin}${modelDirLabeler}/config.json`).then((r) => r.json());
        const classifierConfig = await fetch(`${window.location.origin}${modelDirClassifier}/config.json`).then((r) => r.json());
        const id2tag = labelerConfig.id2label ?? null;
        const tagIndexLookup = (mapping, index) => {
          const tag = mapping[String(index)];
          return tags.indexOf(tag) >= 0 ? tags.indexOf(tag) : 0;
        };
        const id2labelC = classifierConfig.id2label ?? null;

        const feedFor = (ids) => ({
          input_ids: new ort.Tensor("int64", BigInt64Array.from(ids.map(BigInt)), [1, ids.length]),
          attention_mask: new ort.Tensor("int64", BigInt64Array.from({ length: ids.length }, () => 1n), [1, ids.length]),
          token_type_ids: new ort.Tensor("int64", BigInt64Array.from({ length: ids.length }, () => 0n), [1, ids.length]),
        });

        // 分类全路径（计时内）：分词(32 上限，与分类 trial 同) -> run ->
        // argmax -> softmax -> 标签。
        const classify = (sessionC, text) => {
          const { ids } = tokenizeWithOffsets(text, 32);
          return sessionC.run(feedFor(ids)).then((output) => {
            const logits = Array.from(output.logits.data).map(Number);
            let best = 0;
            logits.forEach((value, index) => {
              if (value > logits[best]) best = index;
            });
            const maxValue = Math.max(...logits);
            const exps = logits.map((value) => Math.exp(value - maxValue));
            const sum = exps.reduce((a, b) => a + b, 0);
            const probs = exps.map((e) => e / sum);
            const label = id2labelC ? (id2labelC[String(best)] ?? labels[best]) : labels[best];
            return { label, probs };
          });
        };

        // 抽取推理共用前缀：分词(48) -> feed -> run -> logits。
        const infer = (sessionL, text) => {
          const { ids, offsets } = tokenizeWithOffsets(text, 48);
          return sessionL.run(feedFor(ids)).then((output) => ({
            offsets,
            logits: output.logits.data,
            seq: output.logits.dims[1],
            tagCount: output.logits.dims[2],
          }));
        };

        const greedyFromLogits = (text, { offsets, logits, seq, tagCount }) => {
          const tagIds = [];
          for (let index = 0; index < seq; index += 1) {
            let best = 0;
            let bestValue = -Infinity;
            for (let tagIndex = 0; tagIndex < tagCount; tagIndex += 1) {
              const value = logits[index * tagCount + tagIndex];
              if (value > bestValue) {
                bestValue = value;
                best = tagIndex;
              }
            }
            tagIds.push(id2tag ? tagIndexLookup(id2tag, best) : best);
          }
          const spans = decodeSpans(offsets, tagIds);
          return {
            offsets,
            tagIds,
            itemSpan: spans.ITEM,
            targetSpan: spans.TGT,
            predItem: spans.ITEM !== null ? text.slice(spans.ITEM[0], spans.ITEM[1]) : null,
            predTarget: spans.TGT !== null ? text.slice(spans.TGT[0], spans.TGT[1]) : null,
          };
        };

        const constrainedFromLogits = (text, { offsets, logits, seq, tagCount }, suppressItem) => {
          const probs = [];
          for (let index = 0; index < seq; index += 1) {
            let sum = 0;
            for (let tagIndex = 0; tagIndex < tagCount; tagIndex += 1) {
              sum += Math.exp(logits[index * tagCount + tagIndex]);
            }
            const row = [];
            for (let tagIndex = 0; tagIndex < tagCount; tagIndex += 1) {
              row.push(Math.exp(logits[index * tagCount + tagIndex]) / sum);
            }
            probs.push(row);
          }
          const decoded = constrainedDecode(offsets, probs, suppressItem);
          return {
            offsets,
            probs,
            ids: decoded.ids,
            itemSpan: decoded.itemSpan,
            targetSpan: decoded.targetSpan,
            predItem: decoded.itemSpan !== null ? text.slice(decoded.itemSpan[0], decoded.itemSpan[1]) : null,
            predTarget: decoded.targetSpan !== null ? text.slice(decoded.targetSpan[0], decoded.targetSpan[1]) : null,
          };
        };

        const createSession = (dir, file) => Promise.race([
          ort.InferenceSession.create(`${window.location.origin}${dir}/${file}`, { executionProviders: ["wasm"] }),
          new Promise((_, reject) => setTimeout(() => reject(new Error("CREATE-HANG")), timeoutMs)),
        ]);

        const classifierStarted = performance.now();
        const sessionC = await createSession(modelDirClassifier, classifierFile);
        const classifierLoadMs = Math.round(performance.now() - classifierStarted);
        const labelerStarted = performance.now();
        let sessionL;
        try {
          sessionL = await createSession(modelDirLabeler, labelerFile);
        } catch (error) {
          if (error.message === "CREATE-HANG") {
            return { status: "create-hung", file: labelerFile, timeoutMs };
          }
          throw error;
        }
        const loadMs = Math.round(performance.now() - labelerStarted);

        const medianOf = (walls) => [...walls].sort((a, b) => a - b)[Math.floor(walls.length / 2)];
        const timePath = async (path) => {
          const walls = [];
          let last = null;
          for (let run = 0; run < repeats + 1; run += 1) {
            const started = performance.now();
            last = await path();
            const wall = performance.now() - started;
            if (run > 0) walls.push(Math.round(wall * 1000) / 1000);
          }
          return { median: medianOf(walls), last };
        };

        const runCase = async (batch, entry, withTokens) => {
          const text = entry.text;
          const goldCategory = entry.goldCategory;
          const suppressGold = suppressCategories.includes(goldCategory);
          // 三条链各自全程计时：classify / classify+贪心 / classify+规则约束。
          const tClassify = await timePath(() => classify(sessionC, text));
          const tGreedy = await timePath(() =>
            classify(sessionC, text).then(() => infer(sessionL, text)).then((r) => greedyFromLogits(text, r)));
          const tRule = await timePath(() =>
            classify(sessionC, text)
              .then((c) => infer(sessionL, text).then((r) => constrainedFromLogits(text, r, suppressCategories.includes(c.label)))));

          const pred = tClassify.last;
          const suppressPred = suppressCategories.includes(pred.label);
          const goldSpans = {
            ITEM: entry.item !== null ? [text.indexOf(entry.item), text.indexOf(entry.item) + entry.item.length] : null,
            TGT: entry.target !== null ? [text.indexOf(entry.target), text.indexOf(entry.target) + entry.target.length] : null,
          };
          const fieldScore = (expected, span) => {
            if (expected === null && span === null) return { strict: true, loose: true };
            if (expected !== null && span !== null) {
              const strict = span[0] === text.indexOf(expected) && span[1] === span[0] + expected.length;
              const loose = span[0] < text.indexOf(expected) + expected.length && text.indexOf(expected) < span[1];
              return { strict, loose };
            }
            return { strict: false, loose: false };
          };
          const goldTokenTag = (tokenStart, tokenEnd) => {
            const mid = (tokenStart + tokenEnd) >>> 1;
            for (const name of ["ITEM", "TGT"]) {
              const span = goldSpans[name];
              if (span !== null && span[0] <= mid && mid < span[1]) {
                return `${mid === span[0] ? "B" : "I"}-${name}`;
              }
            }
            return "O";
          };
          // 概率与 offsets 取自规则链落盘运行（同一文本同一 logits）。
          const buildTokenRows = (ids) => {
            const rows = [];
            for (let index = 1; index < tRule.last.offsets.length; index += 1) {
              const [tokenStart, tokenEnd] = tRule.last.offsets[index];
              if (tokenEnd === 0) continue; // [SEP]
              const goldTag = goldTokenTag(tokenStart, tokenEnd);
              rows.push({
                start: tokenStart,
                end: tokenEnd,
                ch: text.slice(tokenStart, tokenEnd),
                gold: goldTag,
                pred: tags[ids[index]] ?? "O",
                pPred: Math.round(tRule.last.probs[index][ids[index]] * 10000) / 10000,
                pGold: Math.round(tRule.last.probs[index][tags.indexOf(goldTag)] * 10000) / 10000,
              });
            }
            return rows;
          };

          // plain constrained 与 goldRule 不占计时：同 logits 的枚举变体。
          const plainC = constrainedDecode(tRule.last.offsets, tRule.last.probs, false);
          const goldC = constrainedDecode(tRule.last.offsets, tRule.last.probs, suppressGold);

          const goldTokenRows = buildTokenRows(tGreedy.last.tagIds);
          const sub = (itemSpan, targetSpan, idsForDiag) => {
            const itemScore = fieldScore(entry.item, itemSpan);
            const targetScore = fieldScore(entry.target, targetSpan);
            const tokenRows = idsForDiag === null ? goldTokenRows : buildTokenRows(idsForDiag);
            return {
              predItem: itemSpan !== null ? text.slice(itemSpan[0], itemSpan[1]) : null,
              predTarget: targetSpan !== null ? text.slice(targetSpan[0], targetSpan[1]) : null,
              itemSpan,
              targetSpan,
              itemStrict: itemScore.strict,
              itemLoose: itemScore.loose,
              targetStrict: targetScore.strict,
              targetLoose: targetScore.loose,
              diagnosis: {
                item: diagnoseField(text, goldSpans.ITEM, itemSpan, goldSpans.TGT, tokenRows, "ITEM", "TGT"),
                target: diagnoseField(text, goldSpans.TGT, targetSpan, goldSpans.ITEM, tokenRows, "TGT", "ITEM"),
              },
            };
          };
          const row = {
            batch,
            group: entry.group ?? null,
            text,
            expectItem: entry.item,
            expectTarget: entry.target,
            goldCategory,
            suppressGold,
            predictedCategory: pred.label,
            suppressPred,
            categoryCorrect: pred.label === goldCategory,
            pPredicted: Math.round(pred.probs[labels.indexOf(pred.label)] * 10000) / 10000,
            pGold: Math.round(pred.probs[labels.indexOf(goldCategory)] * 10000) / 10000,
            dataOverlap: entry.dataOverlap,
            decodes: {
              greedy: sub(tGreedy.last.itemSpan, tGreedy.last.targetSpan, null),
              constrained: sub(plainC.itemSpan, plainC.targetSpan, plainC.ids),
              goldRule: sub(goldC.itemSpan, goldC.targetSpan, goldC.ids),
              predRule: sub(tRule.last.itemSpan, tRule.last.targetSpan, tRule.last.ids),
            },
            walls: {
              classifyMs: tClassify.median,
              greedyChainMs: tGreedy.median,
              ruleChainMs: tRule.median,
            },
            withinTarget: {
              classifyMs: tClassify.median <= targetMs,
              greedyChainMs: tGreedy.median <= targetMs,
              ruleChainMs: tRule.median <= targetMs,
            },
          };
          if (withTokens) {
            row.tokens = goldTokenRows.map((t) => ({
              ...t,
              probs: tRule.last.probs[tRule.last.offsets.findIndex((o) => o[0] === t.start && o[1] === t.end)]
                .map((p) => Math.round(p * 10000) / 10000),
            }));
          }
          return row;
        };

        const coldStarted = performance.now();
        const coldText = batches.find((b) => b.name === "scored").rows[0].text;
        await classify(sessionC, coldText).then(() => infer(sessionL, coldText)).then((r) => greedyFromLogits(coldText, r));
        const coldMs = Math.round(performance.now() - coldStarted);

        const cases = [];
        for (const batch of batches) {
          for (const entry of batch.rows) {
            cases.push(await runCase(batch.name, entry, batch.tokens));
          }
        }

        return {
          status: "ok",
          file: labelerFile,
          classifierFile,
          classifierLoadMs,
          loadMs,
          coldMs,
          cases,
        };
      },
      {
        modelDirLabeler: LABELER_DIR,
        modelDirClassifier: CLASSIFIER_DIR,
        labelerFile: armConfig.file,
        classifierFile: "onnx/model_quantized.onnx",
        tags: TAGS,
        classOrder: CLASS_ORDER,
        labels: LABELS,
        suppressCategories,
        batches,
        repeats: REPEATS,
        targetMs: TARGET_MS,
        timeoutMs: CREATE_TIMEOUT_MS,
      },
    );
    await armPage.close();
    arms.push({ name: armConfig.name, ...arm });
    log(`${armConfig.name}: ${arm.status === "ok" ? `classifierLoad=${arm.classifierLoadMs}ms load=${arm.loadMs}ms cold=${arm.coldMs}ms` : arm.status}`);
  }
  await browser.close();

  const scoredArms = arms.filter((arm) => arm.status === "ok");
  const batchNames = batches.map((b) => b.name);
  const VARIANTS = ["greedy", "constrained", "goldRule", "predRule"];

  const bothRate = (arm, rows, variant) => `${rows.filter((row) => row.decodes[variant].itemStrict && row.decodes[variant].targetStrict).length}/${rows.length}`;
  const fieldRate = (arm, rows, variant, field) => `${rows.filter((row) => row.decodes[variant][`${field}Strict`]).length}/${rows.length}`;
  const medianOf = (values) => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];

  for (const arm of scoredArms) {
    for (const batch of batchNames) {
      const rows = arm.cases.filter((row) => row.batch === batch);
      const parts = VARIANTS.map((v) => `${v} ${bothRate(arm, rows, v)}`);
      log(`${arm.name} ${batch} both-fields: ${parts.join(" | ")}`);
    }
    const all = arm.cases;
    log(`${arm.name} merged(53) both-fields: ${VARIANTS.map((v) => `${v} ${bothRate(arm, all, v)}`).join(" | ")}`);
    const suppressed = all.filter((row) => row.suppressGold);
    log(`${arm.name} suppress-gold subset (${suppressed.length}): ${VARIANTS.map((v) => `${v} ${bothRate(arm, suppressed, v)}`).join(" | ")}`);
  }

  // ── 分类器精度与误分类（分类器两臂相同，取主臂即可）。────────────────
  const primary = scoredArms[0] ?? { cases: [] };
  const misclassified = primary.cases.filter((row) => !row.categoryCorrect).map((row) => ({
    batch: row.batch,
    group: row.group,
    text: row.text,
    goldCategory: row.goldCategory,
    predictedCategory: row.predictedCategory,
    pPredicted: row.pPredicted,
    pGold: row.pGold,
    dataOverlap: row.dataOverlap,
  }));
  const accByBatch = Object.fromEntries(batchNames.map((batch) => {
    const rows = primary.cases.filter((row) => row.batch === batch);
    return [batch, `${rows.filter((row) => row.categoryCorrect).length}/${rows.length}`];
  }));
  log(`classifier accuracy: ${primary.cases.filter((row) => row.categoryCorrect).length}/${primary.cases.length} (${JSON.stringify(accByBatch)}), misclassified ${misclassified.length}`);
  for (const m of misclassified) {
    log(`  misclassified: [${m.batch}] ${m.text} gold=${m.goldCategory} pred=${m.predictedCategory} (pPred=${m.pPredicted} pGold=${m.pGold})${m.dataOverlap ? ` overlap=${m.dataOverlap}` : ""}`);
  }

  // ── 逐例得失。goldFlips：goldRule vs plain constrained（隔离规则效应）；
  // chainFlips：predRule vs greedy（真实链 vs 当前默认）。────────────────
  const flipsBetween = (rows, from, to) => {
    const gains = [];
    const losses = [];
    for (const row of rows) {
      const was = row.decodes[from].itemStrict && row.decodes[from].targetStrict;
      const now = row.decodes[to].itemStrict && row.decodes[to].targetStrict;
      if (was === now) continue;
      (now ? gains : losses).push({
        batch: row.batch,
        group: row.group,
        text: row.text,
        expectItem: row.expectItem,
        expectTarget: row.expectTarget,
        [from]: { predItem: row.decodes[from].predItem, predTarget: row.decodes[from].predTarget },
        [to]: { predItem: row.decodes[to].predItem, predTarget: row.decodes[to].predTarget },
      });
    }
    return { gains, losses };
  };
  const ruleFlipsGold = {};
  const chainFlips = {};
  for (const arm of scoredArms) {
    ruleFlipsGold[arm.name] = {};
    chainFlips[arm.name] = {};
    for (const batch of batchNames) {
      const rows = arm.cases.filter((row) => row.batch === batch);
      ruleFlipsGold[arm.name][batch] = flipsBetween(rows, "constrained", "goldRule");
      chainFlips[arm.name][batch] = flipsBetween(rows, "greedy", "predRule");
      const rg = ruleFlipsGold[arm.name][batch];
      const cg = chainFlips[arm.name][batch];
      log(`${arm.name} ${batch} goldRule vs constrained: +${rg.gains.length}/-${rg.losses.length}; predRule vs greedy: +${cg.gains.length}/-${cg.losses.length}`);
      const fmt = (p) => `${p.predItem ?? "∅"}/${p.predTarget ?? "∅"}`;
      for (const [label, list] of [["gain", rg.gains], ["loss", rg.losses]]) {
        for (const item of list) log(`  rule-${label}: ${item.text} gold=${item.expectItem ?? "∅"}/${item.expectTarget ?? "∅"} constrained=${fmt(item.constrained)} -> goldRule=${fmt(item.goldRule)}`);
      }
      for (const [label, list] of [["gain", cg.gains], ["loss", cg.losses]]) {
        for (const item of list) log(`  chain-${label}: ${item.text} gold=${item.expectItem ?? "∅"}/${item.expectTarget ?? "∅"} greedy=${fmt(item.greedy)} -> predRule=${fmt(item.predRule)}`);
      }
    }
  }

  // ── 误分类影响（单列：predRule vs goldRule 的逐例差）。────────────────
  const misclassificationImpact = {};
  for (const arm of scoredArms) {
    misclassificationImpact[arm.name] = primary.cases
      .filter((row) => !row.categoryCorrect)
      .map((row) => ({
        batch: row.batch,
        text: row.text,
        goldCategory: row.goldCategory,
        predictedCategory: row.predictedCategory,
        goldRuleBoth: row.decodes.goldRule.itemStrict && row.decodes.goldRule.targetStrict,
        predRuleBoth: row.decodes.predRule.itemStrict && row.decodes.predRule.targetStrict,
        greedyBoth: row.decodes.greedy.itemStrict && row.decodes.greedy.targetStrict,
        predRule: { predItem: row.decodes.predRule.predItem, predTarget: row.decodes.predRule.predTarget },
        goldRule: { predItem: row.decodes.goldRule.predItem, predTarget: row.decodes.goldRule.predTarget },
        // 预测类别造成的净影响：goldRule 对 而 predRule 错 = 误分类损失。
        lostByMisclassification: (row.decodes.goldRule.itemStrict && row.decodes.goldRule.targetStrict) && !(row.decodes.predRule.itemStrict && row.decodes.predRule.targetStrict),
      }));
    const lost = misclassificationImpact[arm.name].filter((r) => r.lostByMisclassification).length;
    log(`${arm.name} misclassification impact: ${lost} case(s) where predRule wrong but goldRule right`);
  }

  // ── 计时（三条链独立，不做减法解读）。────────────────────────────────
  const timing = {};
  for (const arm of scoredArms) {
    const rows = arm.cases;
    timing[arm.name] = Object.fromEntries(["classifyMs", "greedyChainMs", "ruleChainMs"].map((key) => {
      const values = rows.map((row) => row.walls[key]);
      return [key, { median: medianOf(values), max: Math.max(...values), allWithinTarget: rows.every((row) => row.withinTarget[key]) }];
    }));
    const t = timing[arm.name];
    log(`${arm.name} timing: classify median=${t.classifyMs.median}ms, greedyChain median=${t.greedyChainMs.median}ms, ruleChain median=${t.ruleChainMs.median}ms (independent paths, each text->output; max ${Math.max(t.classifyMs.max, t.greedyChainMs.max, t.ruleChainMs.max)}ms)`);
  }

  const outDir = path.join(frontendRoot, "..", "artifacts", "benchmark");
  await mkdir(outDir, { recursive: true });
  const outPath = path.join(outDir, `combo-trial-${Date.now()}.json`);
  await writeFile(
    outPath,
    JSON.stringify(
      {
        hostCpu: cpu,
        task: "classifier->span-labeler combo",
        data: {
          labelerManifest: { file: path.relative(frontendRoot, MANIFEST_PATH), sha256: dataSha },
          categories: { file: path.relative(frontendRoot, CATEGORIES_PATH), sha256: sha256(categoriesBytes), suppressCategories },
          classifierCorpus: { file: path.relative(frontendRoot, CLASSIFIER_CORPUS_PATH), sha256: sha256(classifierCorpusBytes) },
        },
        model: {
          classifier: { dir: CLASSIFIER_DIR, arm: "q8 single-thread", files: modelFiles.classifier },
          labeler: { dir: LABELER_DIR, files: modelFiles.labeler },
        },
        runtime: {
          userAgent,
          crossOriginIsolated: isolated,
          timingScope: "three chains timed per case, each its own REPEATS+1 median, whole path text->output: classifyMs (classifier), greedyChainMs (classify+greedy extract), ruleChainMs (classify+rule-constrained extract on predicted category); medians of independent paths are not additively decomposable",
          threadNote: "single-thread only; >1-thread wasm session create hangs in this environment",
        },
        rule: {
          statement: "inspect/move/npc_talk -> constrained decoding forced ITEM empty (TGT still enumerated); item_use/other keep current constraints (拔剑攻击=other must still extract 剑)",
          appliedTo: "constrained decoding only; greedy stays unconditioned accepted default",
        },
        decodingMode: "greedy (unchanged)",
        targetMs: TARGET_MS,
        repeatsPerCase: REPEATS,
        variantComparison: Object.fromEntries(scoredArms.map((arm) => [arm.name, Object.fromEntries([...batchNames, "merged", "suppressGoldSubset"].map((batch) => {
          const rows = batch === "merged" ? arm.cases : batch === "suppressGoldSubset" ? arm.cases.filter((r) => r.suppressGold) : arm.cases.filter((row) => row.batch === batch);
          return [batch, Object.fromEntries(VARIANTS.map((v) => [v, {
            itemStrict: fieldRate(arm, rows, v, "item"),
            targetStrict: fieldRate(arm, rows, v, "target"),
            bothFields: bothRate(arm, rows, v),
          }]))];
        }))])),
        classifierAccuracy: {
          overall: `${primary.cases.filter((row) => row.categoryCorrect).length}/${primary.cases.length}`,
          byBatch: accByBatch,
          misclassified,
        },
        ruleFlipsGold,
        chainFlips,
        misclassificationImpact,
        timing,
        acceptance: {
          evaluated: false,
          sealedSentences: manifest.acceptance.reduce((n, g) => n + g.sentences.length, 0),
          gate: { evaluated: false, decodeMode: "greedy", note: "sealed acceptance batch NOT loaded (protocol unchanged); this combo round is an experiment on dev batches only", verdict: "not-evaluated" },
        },
        arms: scoredArms,
        exportedAt: new Date().toISOString(),
      },
      null,
      2,
    ),
  );
  log(`saved: ${outPath}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
