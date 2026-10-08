// Labeler trial v1: MiniRBT-H256 span labeler on browser CPU (ONNX Runtime
// Web 1.30.0 direct), marking ITEM/TGT character spans in player actions.
//
// PRE-REGISTERED ACCEPTANCE (written in train-span-labeler.py before any
// training): ACCEPTANCE batch (10 fresh sentences, slots/structures never
// trained, never evaluated during development) strict span match
// (start+end+type exact) >= 90% per field. The previous held-out batch is
// now DEV — it was evaluated repeatedly during debugging, so it no longer
// measures generalization. This trial runs once after the labeling-rule,
// decoder and tokenizer fixes; the gate judges the acceptance batch only.
//
// Timing scope (per classifier-trial v2 review): end-to-end per call —
// raw text -> tokenize -> feed -> run -> argmax -> span decode -> substrings.
// Threads: measured single-thread; >1-thread session create hangs in this
// environment (documented in run-classifier-trial.mjs, headed and headless).
//
// Usage: node scripts/run-labeler-trial.mjs
// Output: artifacts/benchmark/labeler-trial-<ts>-spans.json

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

const MODEL_DIR = "/models/minirbt-h256-span";
const TAGS = ["O", "B-ITEM", "I-ITEM", "B-TGT", "I-TGT"];

// (text, item, target)；期望值为原文子串（与 train-span-labeler.py 一致）。
// DEV：原 held-out 批，只用于定位错误。ACCEPTANCE v2：全新槽位（与训练
// 槽位不相交），含 item-only、提及不标、修饰语、单字中心语结构；v1 批
// 已评过一次退役。SCORED 的 item 期望按规则 6 v2 记中心语。
const DEV = [
  { text: "我用火把照亮地下藏书室。", item: "火把", target: "地下藏书室" },
  { text: "我用短刀割断绳索。", item: "短刀", target: "绳索" },
  { text: "我和图书馆管理员打听暗门。", item: null, target: "图书馆管理员" },
  { text: "我去地下藏书室。", item: null, target: "地下藏书室" },
  { text: "我检查雕像的底座。", item: null, target: "雕像" },
  { text: "我在原地休息。", item: null, target: null },
  { text: "我用指南针校准方向。", item: "指南针", target: null },
  { text: "我把铃铛挂在暗门上。", item: "铃铛", target: "暗门" },
  { text: "我向夏弥打听暗门的来历。", item: null, target: "夏弥" },
  { text: "我用蜡烛照亮壁画。", item: "蜡烛", target: "壁画" },
];
const ACCEPTANCE = [
  { text: "我把火钳握在手里。", item: "火钳", target: null },
  { text: "我想起了断桨。", item: null, target: null },
  { text: "我用铜哨示意马夫。", item: "铜哨", target: "马夫" },
  { text: "我检查门环。", item: null, target: "门环" },
  { text: "我在原地蹲了一会儿。", item: null, target: null },
  { text: "我用湿柴塞进灶膛。", item: "湿柴", target: "灶膛" },
  { text: "我用那把断剑撬开后院的门。", item: "断剑", target: "门" },
  { text: "我向马夫打听水井的位置。", item: null, target: "马夫" },
  { text: "断剑还在鞘里。", item: null, target: null },
  { text: "我用蒙尘的火钳拨开灰堆。", item: "火钳", target: "灰堆" },
];
const SCORED = [
  { text: "我用铜钥匙打开大门。", item: "铜钥匙", target: "大门" },
  { text: "我和诺诺打听图书馆的传闻。", item: null, target: "诺诺" },
  { text: "我去二楼档案室查资料。", item: null, target: "二楼档案室" },
  { text: "我使用生锈的铁门钥匙打开大门。", item: "铁门钥匙", target: "大门" },
  { text: "我和执行部学生搭话。", item: null, target: "执行部学生" },
  { text: "我检查那扇书架后的暗门。", item: null, target: "暗门" },
  { text: "我拔剑攻击诺诺。", item: "剑", target: "诺诺" },
  { text: "我在原地休息一会儿。", item: null, target: null },
  { text: "我仔细查看旧笔记里的字迹。", item: null, target: "旧笔记" },
  { text: "我用旧笔记垫住门缝。", item: "旧笔记", target: "门缝" },
  { text: "我去找执行部学生问话。", item: null, target: "执行部学生" },
  { text: "我用路明非的校徽刷开闸机。", item: "校徽", target: "闸机" },
];

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
    "onnx/model.onnx": await fileSize("models/minirbt-h256-span/onnx/model.onnx"),
    "onnx/model_quantized.onnx": await fileSize("models/minirbt-h256-span/onnx/model_quantized.onnx"),
  };

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
    { name: "q8-t1", threads: 1, file: "onnx/model_quantized.onnx" },
    { name: "fp32-t1", threads: 1, file: "onnx/model.onnx" },
  ];
  const arms = [];
  for (const armConfig of armConfigs) {
    const armPage = await browser.newPage();
    await armPage.goto(`${baseUrl}/benchmark`);
    await armPage.waitForLoadState("domcontentloaded");
    const arm = await armPage.evaluate(
      async ({ modelDir, tags, dev, acceptance, scored, threads, file, repeats, targetMs, timeoutMs }) => {
        const ort = await import("/ort/ort.bundle.min.mjs");
        ort.env.wasm.wasmPaths = "/ort/";
        ort.env.wasm.numThreads = threads;

        const vocabText = await fetch(`${window.location.origin}${modelDir}/vocab.txt`).then((r) => r.text());
        const vocab = new Map();
        vocabText.split("\n").forEach((line, index) => vocab.set(line.replace(/\r$/, ""), index));

        // 分词并保留每 token 的字符区间（与 Python 的 offset_mapping 对齐：
        // 特殊 token 为 [0,0)；中文逐字；ASCII 段最长 wordpiece，piece 自带
        // 前缀"##"的字符数即其区间宽度）。
        const tokenizeWithOffsets = (text, maxLen = 48) => {
          const ids = [vocab.get("[CLS]")];
          const offsets = [[0, 0]];
          let asciiRun = null; // 审查修正：此前初始化为数组、后面却按对象用，英文首段必坏
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

        // 与 train-span-labeler.py 的 tags_to_spans 同逻辑（组尾取组内最后
        // 片段的结束位置，而非下一个 token 的起点——句末特殊标记起点是 0）。
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

        const config = await fetch(`${window.location.origin}${modelDir}/config.json`).then((r) => r.json());
        const id2tag = config.id2label ?? null;

        const extract = (session, text) => {
          const { ids, offsets } = tokenizeWithOffsets(text);
          const feed = {
            input_ids: new ort.Tensor("int64", BigInt64Array.from(ids.map(BigInt)), [1, ids.length]),
            attention_mask: new ort.Tensor("int64", BigInt64Array.from({ length: ids.length }, () => 1n), [1, ids.length]),
            token_type_ids: new ort.Tensor("int64", BigInt64Array.from({ length: ids.length }, () => 0n), [1, ids.length]),
          };
          return session.run(feed).then((output) => {
            const logits = output.logits.data; // [seq, tags] Float32Array
            const seq = output.logits.dims[1];
            const tagCount = output.logits.dims[2];
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
              item: spans.ITEM !== null ? text.slice(spans.ITEM[0], spans.ITEM[1]) : null,
              target: spans.TGT !== null ? text.slice(spans.TGT[0], spans.TGT[1]) : null,
              itemSpan: spans.ITEM,
              targetSpan: spans.TGT,
            };
          });
        };
        const tagIndexLookup = (mapping, index) => {
          const tag = mapping[String(index)];
          return tags.indexOf(tag) >= 0 ? tags.indexOf(tag) : 0;
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
            return { status: "create-hung", threads, file, timeoutMs };
          }
          throw error;
        }
        const loadMs = Math.round(performance.now() - createStarted);

        const runCase = async (batch, entry) => {
          const walls = [];
          let result = null;
          for (let run = 0; run < repeats + 1; run += 1) {
            const started = performance.now();
            result = await extract(session, entry.text);
            const wall = performance.now() - started;
            if (run > 0) walls.push(Math.round(wall * 1000) / 1000);
          }
          const sorted = [...walls].sort((a, b) => a - b);
          const median = sorted[Math.floor(sorted.length / 2)];
          const fieldScore = (expected, span) => {
            if (expected === null && span === null) return { strict: true, loose: true };
            if (expected !== null && span !== null) {
              const strict = span[0] === entry.text.indexOf(expected) && span[1] === span[0] + expected.length;
              const loose = span[0] < entry.text.indexOf(expected) + expected.length && entry.text.indexOf(expected) < span[1];
              return { strict, loose };
            }
            return { strict: false, loose: false };
          };
          const itemScore = fieldScore(entry.item, result.itemSpan);
          const targetScore = fieldScore(entry.target, result.targetSpan);
          return {
            batch,
            text: entry.text,
            expectItem: entry.item,
            expectTarget: entry.target,
            predItem: result.item,
            predTarget: result.target,
            itemSpan: result.itemSpan,
            targetSpan: result.targetSpan,
            itemStrict: itemScore.strict,
            itemLoose: itemScore.loose,
            targetStrict: targetScore.strict,
            targetLoose: targetScore.loose,
            wallMs: Math.round(median * 1000) / 1000,
            withinTarget: median <= targetMs,
          };
        };

        const coldStarted = performance.now();
        await extract(session, scored[0].text);
        const coldMs = Math.round(performance.now() - coldStarted);

        const cases = [];
        for (const entry of dev) cases.push(await runCase("dev", entry));
        for (const entry of acceptance) cases.push(await runCase("acceptance", entry));
        for (const entry of scored) cases.push(await runCase("scored", entry));

        return {
          status: "ok",
          threads,
          file,
          loadMs,
          coldMs,
          cases,
        };
      },
      {
        modelDir: MODEL_DIR,
        tags: TAGS,
        dev: DEV,
        acceptance: ACCEPTANCE,
        scored: SCORED,
        threads: armConfig.threads,
        file: armConfig.file,
        repeats: REPEATS,
        targetMs: TARGET_MS,
        timeoutMs: CREATE_TIMEOUT_MS,
      },
    );
    await armPage.close();
    arms.push({ name: armConfig.name, ...arm });
    log(`${armConfig.name}: ${arm.status === "ok" ? `load=${arm.loadMs}ms cold=${arm.coldMs}ms` : arm.status}`);
  }
  await browser.close();

  const scoredArms = arms.filter((arm) => arm.status === "ok");
  for (const arm of scoredArms) {
    const summarize = (batch, field) => {
      const rows = arm.cases.filter((row) => row.batch === batch);
      return `${rows.filter((row) => row[`${field}Strict`]).length}/${rows.length}`;
    };
    log(
      `${arm.name}: acceptance ITEM ${summarize("acceptance", "item")} TGT ${summarize("acceptance", "target")} | ` +
        `dev ITEM ${summarize("dev", "item")} TGT ${summarize("dev", "target")} | ` +
        `medianWall=${arm.cases.map((row) => row.wallMs).sort((a, b) => a - b)[Math.floor(arm.cases.length / 2)]}ms`,
    );
  }

  // 预注册验收判定：ACCEPTANCE 批每字段 strict >= 90% 且端到端 <= 4s；
  // dev 批只作诊断，不进门控。
  const primary = scoredArms[0]?.cases ?? [];
  const acceptanceRows = primary.filter((row) => row.batch === "acceptance");
  const gate = {
    itemStrictRate: `${acceptanceRows.filter((row) => row.itemStrict).length}/${acceptanceRows.length}`,
    targetStrictRate: `${acceptanceRows.filter((row) => row.targetStrict).length}/${acceptanceRows.length}`,
    itemPass: acceptanceRows.filter((row) => row.itemStrict).length / acceptanceRows.length >= 0.9,
    targetPass: acceptanceRows.filter((row) => row.targetStrict).length / acceptanceRows.length >= 0.9,
    latencyAllWithinTarget: primary.every((row) => row.withinTarget),
    verdict: null,
  };
  gate.verdict = gate.itemPass && gate.targetPass && gate.latencyAllWithinTarget ? "accepted" : "rejected";
  log(`pre-registered gate: ITEM ${gate.itemStrictRate} TGT ${gate.targetStrictRate} -> ${gate.verdict}`);

  const outDir = path.join(frontendRoot, "..", "artifacts", "benchmark");
  await mkdir(outDir, { recursive: true });
  const outPath = path.join(outDir, `labeler-trial-${Date.now()}-spans.json`);
  await writeFile(
    outPath,
    JSON.stringify(
      {
        hostCpu: cpu,
        task: "span-labeling",
        model: { dir: MODEL_DIR, base: "hfl/minirbt-h256 (~10.4M params, token-classification head)", files: modelSizes },
        runtime: {
          userAgent,
          crossOriginIsolated: isolated,
          timingScope: "end-to-end per call: text -> tokenize -> feed -> run -> argmax -> span decode",
          threadNote: "single-thread only; >1-thread wasm session create hangs in this environment",
        },
        targetMs: TARGET_MS,
        repeatsPerCase: REPEATS,
        acceptance: {
          preRegistered:
            "acceptance batch strict span match >= 90% per field AND end-to-end <= 4s; dev batch (ex held-out) is diagnostics only",
          gate,
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
