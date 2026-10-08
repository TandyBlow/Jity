// Classifier trial v1: MiniRBT-H256 action-type classifier on browser CPU
// (ONNX Runtime Web), evaluated on the parse task's action_type field — the
// same 12 sentences as the LLM parse arms.
//
// Why: the user's direction — components don't have to be LLM calls; a
// task-trained small model predicts the class directly (no token-by-token
// JSON generation; structured output assembled by code). Reference points
// from trial7 (same machine, same cases, qwen3-0.6b):
//   parse/compact       action_type 8/12, whole call wall median 25.8s
//   parse/split-state   action_type 11/12, sub-call wall median ~15s
// Python-side fine-tune eval (train-action-classifier.py): 11/12
// (old 8/8, new 3/4 — the miss is 去找…问话, whose structure was
// deliberately excluded from training templates).
//
// Runtime note: @huggingface/transformers 4.3.1 (Transformers.js v4) web
// build was attempted first and abandoned — its file resolution only works
// for hub-style absolute URLs, and its bundled dev-JSEP ONNX Runtime picks
// the asyncify wasm and hangs forever in session.create on this setup.
// This script drives onnxruntime-web (what Transformers.js wraps anyway)
// directly: InferenceSession per dtype + a hand-rolled BertTokenizerFast-
// equivalent tokenizer (Chinese per-char, lowercase, wordpiece fallback for
// ASCII runs), verified in-run against the Python tokenizer's reference ids.
//
// Usage: node scripts/run-classifier-trial.mjs [threads]
// Output: artifacts/benchmark/classifier-trial-<ts>-action.json

import { mkdir, writeFile, stat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const frontendRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const baseUrl = process.env.BASE_URL ?? "http://localhost:3100";
const THREADS = Number(process.argv[2] ?? "4");
const TARGET_MS = 4000;
const REPEATS = 10;

const MODEL_DIR = "/models/minirbt-h256-action";
const LABELS = ["item_use", "npc_talk", "move", "inspect", "other"];

// 与 run-task-trial.mjs 的解析用例逐字一致（action_type 字段）。
const CASES = [
  { batch: "old", action: "我用铜钥匙打开大门。", expect: "item_use" },
  { batch: "old", action: "我和诺诺打听图书馆的传闻。", expect: "npc_talk" },
  { batch: "old", action: "我去二楼档案室查资料。", expect: "move" },
  { batch: "old", action: "我使用生锈的铁门钥匙打开大门。", expect: "item_use" },
  { batch: "old", action: "我和执行部学生搭话。", expect: "npc_talk" },
  { batch: "old", action: "我检查那扇书架后的暗门。", expect: "inspect" },
  { batch: "old", action: "我拔剑攻击诺诺。", expect: "other" },
  { batch: "old", action: "我在原地休息一会儿。", expect: "other" },
  { batch: "new", action: "我仔细查看旧笔记里的字迹。", expect: "inspect" },
  { batch: "new", action: "我用旧笔记垫住门缝。", expect: "item_use" },
  { batch: "new", action: "我去找执行部学生问话。", expect: "npc_talk" },
  { batch: "new", action: "我用路明非的校徽刷开闸机。", expect: "item_use" },
];

// Python BertTokenizerFast 参考输出（训练脚本环境），浏览器分词必须一致。
const TOKENIZER_CHECK = {
  text: "我用旧笔记垫住门缝。",
  ids: [101, 2769, 4500, 3191, 5011, 6381, 1807, 857, 7305, 5361, 511, 102],
};

const log = (...parts) => console.log(new Date().toISOString().slice(11, 19), ...parts);

async function fileSize(relativePath) {
  try {
    return (await stat(path.join(frontendRoot, "public", relativePath))).size;
  } catch {
    return null;
  }
}

async function main() {
  const cpu = os.cpus()[0]?.model ?? "unknown";
  log(`host CPU: ${cpu}`);
  const modelSizes = {
    "onnx/model.onnx": await fileSize("models/minirbt-h256-action/onnx/model.onnx"),
    "onnx/model_quantized.onnx": await fileSize("models/minirbt-h256-action/onnx/model_quantized.onnx"),
  };

  const browser = await (async () => {
    try {
      return await chromium.launch({ channel: "msedge", headless: true });
    } catch {
      return chromium.launch({ headless: true });
    }
  })();
  const page = await browser.newPage();
  page.on("console", (message) => log(`[page] ${message.text()}`));
  await page.goto(`${baseUrl}/benchmark`);
  await page.waitForLoadState("domcontentloaded");

  const isolated = await page.evaluate(() => window.crossOriginIsolated === true);
  log(`crossOriginIsolated: ${isolated}`);
  if (!isolated) {
    console.error("FATAL: not cross-origin isolated; wasm multithread unavailable.");
    await browser.close();
    process.exit(2);
  }

  const result = await page.evaluate(
    async ({ modelDir, labels, cases, tokenizerCheck, threads, repeats, targetMs }) => {
      const ort = await import("/transformers/ort/ort.bundle.min.mjs");
      ort.env.wasm.wasmPaths = "/transformers/ort/";
      // ORT 1.31.0-dev 的死锁规律（本环境实测）：首次会话创建若用默认线程
      // 数（>1）会永久挂起并毒化运行时。必须先显式 1 线程建一个会话释放，
      // 再按目标线程数创建。
      ort.env.wasm.numThreads = 1;
      const bootstrapUrl = `${window.location.origin}${modelDir}/onnx/model_quantized.onnx`;
      const bootstrap = await ort.InferenceSession.create(bootstrapUrl, { executionProviders: ["wasm"] });
      await bootstrap.release();
      ort.env.wasm.numThreads = threads;

      // 词表：vocab.txt 每行一个 token，行号即 id。
      const vocabText = await fetch(`${window.location.origin}${modelDir}/vocab.txt`).then((r) => r.text());
      const vocab = new Map();
      vocabText.split("\n").forEach((line, index) => vocab.set(line.replace(/\r$/, ""), index));

      // BertTokenizerFast 等价：小写、中文逐字、ASCII 连续段最长 wordpiece。
      const tokenize = (text, maxLen = 32) => {
        const ids = [vocab.get("[CLS]")];
        let asciiRun = [];
        const flushAscii = () => {
          if (!asciiRun.length) return;
          const word = asciiRun.join("");
          asciiRun = [];
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
          if (ids.length >= maxLen - 1) break;
          ids.push(vocab.has(ch) ? vocab.get(ch) : vocab.get("[UNK]"));
        }
        flushAscii();
        ids.push(vocab.get("[SEP]"));
        return ids.slice(0, maxLen);
      };

      const tokenizerCheckPass =
        JSON.stringify(tokenize(tokenizerCheck.text)) === JSON.stringify(tokenizerCheck.ids);

      const config = await fetch(`${window.location.origin}${modelDir}/config.json`).then((r) => r.json());
      const id2label = config.id2label ?? null;

      const arms = [];
      const variants = [
        { name: "q8", file: "onnx/model_quantized.onnx" },
        { name: "fp32", file: "onnx/model.onnx" },
      ];
      console.log(`[steps] vocab=${vocab.size} tokenizerCheck=${JSON.stringify(tokenize(tokenizerCheck.text)) === JSON.stringify(tokenizerCheck.ids)} variants=${variants.map((v) => v.name).join(",")}`);
      for (const variant of variants) {
        console.log(`[steps] ${variant.name}: session create start (${variant.file})`);
        const loadStarted = performance.now();
        const session = await ort.InferenceSession.create(
          `${window.location.origin}${modelDir}/${variant.file}`,
          { executionProviders: ["wasm"] },
        );
        console.log(`[steps] ${variant.name}: session created`);
        const loadMs = Math.round(performance.now() - loadStarted);

        const runOnce = (ids) => {
          const len = ids.length;
          const feed = {
            input_ids: new ort.Tensor("int64", BigInt64Array.from(ids.map(BigInt)), [1, len]),
            attention_mask: new ort.Tensor("int64", BigInt64Array.from({ length: len }, () => 1n), [1, len]),
            token_type_ids: new ort.Tensor("int64", BigInt64Array.from({ length: len }, () => 0n), [1, len]),
          };
          return session.run(feed);
        };

        // 首次推理：含 wasm 会话预热与图优化，单独记录。
        const coldStarted = performance.now();
        await runOnce(tokenize(cases[0].action));
        const coldMs = Math.round(performance.now() - coldStarted);

        const caseResults = [];
        for (const testCase of cases) {
          const ids = tokenize(testCase.action);
          const walls = [];
          let label = null;
          let probs = null;
          for (let run = 0; run < repeats + 1; run += 1) {
            const started = performance.now();
            const output = await runOnce(ids);
            const wall = performance.now() - started;
            const logits = Array.from(output.logits.data).map(Number);
            const maxIndex = logits.indexOf(Math.max(...logits));
            const exps = logits.map((value) => Math.exp(value - Math.max(...logits)));
            const sum = exps.reduce((a, b) => a + b, 0);
            probs = exps.map((value) => value / sum);
            label = id2label ? id2label[maxIndex] : labels[maxIndex];
            if (run > 0) walls.push(Math.round(wall * 1000) / 1000); // 首轮是该用例预热，不计入
          }
          const sorted = [...walls].sort((a, b) => a - b);
          caseResults.push({
            batch: testCase.batch,
            action: testCase.action,
            expect: testCase.expect,
            label,
            probs: probs.map((value) => Math.round(value * 1000) / 1000),
            wallMs: Math.round(sorted[Math.floor(sorted.length / 2)] * 1000) / 1000,
            minWallMs: sorted[0],
            maxWallMs: sorted[sorted.length - 1],
            walls,
            withinTarget: sorted[Math.floor(sorted.length / 2)] <= targetMs,
            correct: label === testCase.expect,
          });
        }
        arms.push({ name: variant.name, file: variant.file, loadMs, coldMs, cases: caseResults });
      }
      return {
        arms,
        tokenizerCheckPass,
        ortVersion: ort.env.version,
        numThreads: ort.env.wasm.numThreads,
      };
    },
    { modelDir: MODEL_DIR, labels: LABELS, cases: CASES, tokenizerCheck: TOKENIZER_CHECK, threads: THREADS, repeats: REPEATS, targetMs: TARGET_MS },
  );

  log(`tokenizer check vs python reference: ${result.tokenizerCheckPass ? "pass" : "FAIL"}`);
  const scored = result.arms.map((arm) => {
    const summarize = (runs) => ({
      correctRate: `${runs.filter((run) => run.correct).length}/${runs.length}`,
      withinTargetRate: `${runs.filter((run) => run.withinTarget).length}/${runs.length}`,
      medianWallMs: runs.map((run) => run.wallMs).sort((a, b) => a - b)[Math.floor(runs.length / 2)],
      maxWallMs: Math.max(...runs.map((run) => run.wallMs)),
    });
    return {
      ...arm,
      summary: {
        old: summarize(arm.cases.filter((run) => run.batch === "old")),
        new: summarize(arm.cases.filter((run) => run.batch === "new")),
        all: summarize(arm.cases),
      },
    };
  });

  for (const arm of scored) {
    log(
      `${arm.name}: load=${arm.loadMs}ms cold=${arm.coldMs}ms old=${arm.summary.old.correctRate} ` +
        `new=${arm.summary.new.correctRate} medianWall=${arm.summary.all.medianWallMs}ms ` +
        `maxWall=${arm.summary.all.maxWallMs}ms withinTarget=${arm.summary.all.withinTargetRate}`,
    );
  }

  const outDir = path.join(frontendRoot, "..", "artifacts", "benchmark");
  await mkdir(outDir, { recursive: true });
  const outPath = path.join(outDir, `classifier-trial-${Date.now()}-action.json`);
  await writeFile(
    outPath,
    JSON.stringify(
      {
        hostCpu: cpu,
        task: "action-classify",
        model: { dir: MODEL_DIR, base: "hfl/minirbt-h256 (~10.4M params, fine-tuned head)", files: modelSizes },
        runtime: {
          userAgent: await page.evaluate(() => navigator.userAgent),
          crossOriginIsolated: isolated,
          requestedThreads: THREADS,
          ortWasmNumThreads: result.numThreads,
          ortVersion: result.ortVersion,
          tokenizerCheckPass: result.tokenizerCheckPass,
        },
        targetMs: TARGET_MS,
        repeatsPerCase: REPEATS,
        reference: {
          note: "same machine/cases, qwen3-0.6b chat arms from task-trial7",
          "parse/compact": { actionType: "8/12", wholeCallWallMedianMs: 25814 },
          "parse/split-state": { actionType: "11/12", subCallWallMedianMs: 15755 },
          pythonEval: { actionType: "11/12", old: "8/8", new: "3/4" },
        },
        arms: scored,
        exportedAt: new Date().toISOString(),
      },
      null,
      2,
    ),
  );
  log(`saved: ${outPath}`);

  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
