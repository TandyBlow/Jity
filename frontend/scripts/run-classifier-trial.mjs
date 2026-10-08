// Classifier trial v2: MiniRBT-H256 action-type classifier on browser CPU
// (ONNX Runtime Web 1.30.0, stable, driven directly), evaluated on the parse
// task's action_type field — the same 12 sentences as the LLM parse arms.
//
// v2 changes from v1, per review of classifier-trial-1791485810864:
// - TIMING SCOPE: v1 timed only session.run (tokenize ran before the timer,
//   argmax/softmax after). Every per-call wall now covers the whole
//   component: raw text -> tokenize -> feed -> run -> argmax -> label.
//   Session-create time is measured on a fresh page with no bootstrap
//   session excluded.
// - THREADS: v1 initialized the runtime with 1 thread and then flipped
//   numThreads to 4; ORT skips completed runtime init, so those numbers were
//   never proven 4-threaded (and the 8ms-vs-162ms gap may have been warm vs
//   cold). v2 verifies each thread config in an INDEPENDENT fresh page with
//   numThreads set before the first create. Finding (this environment,
//   headed and headless Edge): a >1-thread wasm session create hangs
//   forever — the threads=4 arm is reported as unavailable, and all timing
//   numbers are single-threaded. Re-test on target devices.
// - Runtime swap: @huggingface/transformers 4.3.1 web build was rejected
//   earlier (bare specifiers; hub-only file resolution; its pinned
//   1.31.0-dev ORT hangs the same way). This script imports the stable
//   ort.bundle.min.mjs vendored to /ort/ by scripts/copy-ort-assets.mjs.
//   Tokenizer is hand-rolled (BertTokenizerFast-equivalent: Chinese
//   per-char, lowercase, wordpiece fallback for ASCII runs), verified
//   in-run against the Python tokenizer's reference ids.
//
// Reference points from trial7 (same machine/cases, qwen3-0.6b):
//   parse/compact       action_type 8/12, whole call wall median 25.8s
//   parse/split-state   action_type 11/12, sub-call wall median ~15s
// Python-side fine-tune eval (train-action-classifier.py): 11/12
//
// Usage: node scripts/run-classifier-trial.mjs
// Output: artifacts/benchmark/classifier-trial-<ts>-action.json

import { mkdir, writeFile, stat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const frontendRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const baseUrl = process.env.BASE_URL ?? "http://localhost:3100";
const TARGET_MS = 4000;
const REPEATS = 10;
const CREATE_TIMEOUT_MS = 30000;

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
  const basePage = await browser.newPage();
  await basePage.goto(`${baseUrl}/benchmark`);
  await basePage.waitForLoadState("domcontentloaded");
  const isolated = await basePage.evaluate(() => window.crossOriginIsolated === true);
  const userAgent = await basePage.evaluate(() => navigator.userAgent);
  await basePage.close();
  log(`crossOriginIsolated: ${isolated}`);
  if (!isolated) {
    console.error("FATAL: not cross-origin isolated; wasm multithread unavailable.");
    await browser.close();
    process.exit(2);
  }

  // 每个臂一个独立页面：numThreads 在任何会话创建之前设定，创建互不污染。
  const armConfigs = [
    { name: "q8-t1", threads: 1, file: "onnx/model_quantized.onnx", timeoutMs: CREATE_TIMEOUT_MS },
    { name: "q8-t4", threads: 4, file: "onnx/model_quantized.onnx", timeoutMs: CREATE_TIMEOUT_MS },
    { name: "fp32-t1", threads: 1, file: "onnx/model.onnx", timeoutMs: CREATE_TIMEOUT_MS },
  ];
  const arms = [];
  for (const armConfig of armConfigs) {
    const page = await browser.newPage();
    await page.goto(`${baseUrl}/benchmark`);
    await page.waitForLoadState("domcontentloaded");
    const arm = await page.evaluate(
      async ({ modelDir, labels, cases, tokenizerCheck, threads, file, repeats, targetMs, timeoutMs }) => {
        const ort = await import("/ort/ort.bundle.min.mjs");
        ort.env.wasm.wasmPaths = "/ort/";
        ort.env.wasm.numThreads = threads;

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

        // 端到端单次组件调用：原文 → 分词 → feed → run → argmax → 类别。
        const makeFeed = (ids) => {
          const len = ids.length;
          return {
            input_ids: new ort.Tensor("int64", BigInt64Array.from(ids.map(BigInt)), [1, len]),
            attention_mask: new ort.Tensor("int64", BigInt64Array.from({ length: len }, () => 1n), [1, len]),
            token_type_ids: new ort.Tensor("int64", BigInt64Array.from({ length: len }, () => 0n), [1, len]),
          };
        };
        const classify = (session, text) => {
          const ids = tokenize(text);
          return session.run(makeFeed(ids)).then((output) => {
            const logits = Array.from(output.logits.data).map(Number);
            const maxIndex = logits.indexOf(Math.max(...logits));
            const exps = logits.map((value) => Math.exp(value - Math.max(...logits)));
            const sum = exps.reduce((a, b) => a + b, 0);
            return {
              label: id2label ? id2label[maxIndex] : labels[maxIndex],
              probs: exps.map((value) => value / sum),
            };
          });
        };

        const createStarted = performance.now();
        let session;
        try {
          session = await Promise.race([
            ort.InferenceSession.create(`${window.location.origin}${modelDir}/${file}`, {
              executionProviders: ["wasm"],
            }),
            new Promise((_, reject) => setTimeout(() => reject(new Error("CREATE-HANG")), timeoutMs)),
          ]);
        } catch (error) {
          if (error.message === "CREATE-HANG") {
            return { status: "create-hung", threads, file, timeoutMs, numThreadsReadback: ort.env.wasm.numThreads };
          }
          throw error;
        }
        const loadMs = Math.round(performance.now() - createStarted);

        // 冷调用（含会话预热/图优化），端到端。
        const coldStarted = performance.now();
        const cold = await classify(session, cases[0].action);
        const coldMs = Math.round(performance.now() - coldStarted);

        const caseResults = [];
        for (const testCase of cases) {
          const walls = [];
          let label = null;
          let probs = null;
          for (let run = 0; run < repeats + 1; run += 1) {
            const started = performance.now();
            const result = await classify(session, testCase.action);
            const wall = performance.now() - started;
            label = result.label;
            probs = result.probs;
            if (run > 0) walls.push(Math.round(wall * 1000) / 1000); // 首轮是该用例预热，不计入
          }
          const sorted = [...walls].sort((a, b) => a - b);
          const median = sorted[Math.floor(sorted.length / 2)];
          caseResults.push({
            batch: testCase.batch,
            action: testCase.action,
            expect: testCase.expect,
            label,
            probs: probs.map((value) => Math.round(value * 1000) / 1000),
            wallMs: Math.round(median * 1000) / 1000,
            minWallMs: sorted[0],
            maxWallMs: sorted[sorted.length - 1],
            walls,
            withinTarget: median <= targetMs,
            correct: label === testCase.expect,
          });
        }
        return {
          status: "ok",
          threads,
          file,
          numThreadsReadback: ort.env.wasm.numThreads,
          ortVersion: ort.env.version,
          loadMs,
          coldMs,
          coldLabel: cold.label,
          tokenizerCheckPass,
          cases: caseResults,
        };
      },
      {
        modelDir: MODEL_DIR,
        labels: LABELS,
        cases: CASES,
        tokenizerCheck: TOKENIZER_CHECK,
        threads: armConfig.threads,
        file: armConfig.file,
        repeats: REPEATS,
        targetMs: TARGET_MS,
        timeoutMs: armConfig.timeoutMs,
      },
    );
    page.close();
    arms.push({ name: armConfig.name, ...arm });
    log(`${armConfig.name}: ${arm.status === "ok" ? `load=${arm.loadMs}ms cold=${arm.coldMs}ms` : arm.status}`);
  }
  await browser.close();

  const scored = arms.map((arm) => {
    if (arm.status !== "ok") return arm;
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
    if (arm.status !== "ok") {
      log(`${arm.name}: ${arm.status}（${arm.threads} 线程会话创建在本环境挂起，已记录为发现）`);
      continue;
    }
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
          userAgent,
          crossOriginIsolated: isolated,
          ortVersion: arms.find((arm) => arm.ortVersion)?.ortVersion ?? null,
          timingScope: "end-to-end per call: tokenize -> feed -> session.run -> argmax/softmax",
          threadNote:
            "each arm runs in an independent fresh page with numThreads set before the first create; >1-thread wasm session create hangs in this environment (headed and headless), so all timings are single-threaded",
        },
        targetMs: TARGET_MS,
        repeatsPerCase: REPEATS,
        reference: {
          note: "same machine/cases, qwen3-0.6b chat arms from task-trial7",
          "parse/compact": { actionType: "8/12", wholeCallWallMedianMs: 25814 },
          "parse/split-state": { actionType: "11/12", subCallWallMedianMs: 15755 },
          pythonEval: { actionType: "11/12", old: "8/8", new: "3/4", corpusNote: "all 12 scored sentences excluded from training (see train-action-classifier.py)" },
        },
        arms: scored,
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
