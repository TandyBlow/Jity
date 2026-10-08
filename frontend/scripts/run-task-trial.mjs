// Task-level trial v3 (Qwen3 only):
// - parse task gains an explicit inspect-vs-item_use distinction;
// - name extraction gains an explicit title rule ("古德里安教授"→"古德里安");
// - BOTH tasks add a held-out NEW case batch that never informed prompt or
//   rule tuning, reported separately from the old set;
// - every case records input-processing and generation times separately
//   (llama.cpp timings from the completion response);
// - name extraction runs a short-output format comparison (json_schema vs
//   plain lines, no response_format).
// Arms: zero / compact (few-compact won the previous round; the plain few
// arm is dropped).
//
// Usage: node scripts/run-task-trial.mjs [threads]
// Output: artifacts/benchmark/task-trial4-<ts>-<spec>.json

import { mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const frontendRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const baseUrl = process.env.BASE_URL ?? "http://localhost:3100";
const threads = process.argv[2] ?? "4";
const TARGET_MS = 4000;

const MODEL = { tag: "qwen3-0.6b", url: "/models/Qwen3-0.6B-Q4_K_M.gguf" };

// ── 场景状态与实体表 ──────────────────────────────────────────────

const PARSE_STATE = `当前地点：卡塞尔学院图书馆。
已知地点：卡塞尔学院图书馆、二楼档案室。
持有物品：铜钥匙（owned）、旧笔记（owned）。
在场 NPC：诺诺、执行部学生。
体力 88/100，血统稳定 72/100。`;

const PARSE_SCHEMA = {
  type: "object",
  properties: {
    action_type: { enum: ["item_use", "npc_talk", "move", "inspect", "other"] },
    item_used: { type: ["string", "null"] },
    target: { type: ["string", "null"] },
  },
  required: ["action_type", "item_used", "target"],
};

const PARSE_INSTRUCTION = `把玩家行动解析为 JSON，只有三个字段：
- action_type：item_use（使用物品做事）/ npc_talk（与人物交谈）/ move（前往地点）/ inspect（查看物件）/ other。
- item_used：行动中使用的物品名（原文摘录），没有则为 null。注意区分"查看"与"使用"：
  "检查/查看某物"是 inspect，此时 item_used 为 null、target 为被查看的物件；
  只有行动"用某物品去达成别的目的"时才填 item_used（如"用铜钥匙打开大门"）。
- target：行动的作用对象（人物、地点或物件名，原文摘录），没有则为 null。
不要判断行动是否可行，那只由规则代码计算。只输出 JSON。`;

// 旧用例集：此前各轮已用于观察（保留以便与历史对照）。
const PARSE_CASES_OLD = [
  { action: "我用铜钥匙打开大门。", expect: { action_type: "item_use", item_used: "铜钥匙", target: "大门", feasible: true } },
  { action: "我和诺诺打听图书馆的传闻。", expect: { action_type: "npc_talk", item_used: null, target: "诺诺", feasible: true } },
  { action: "我去二楼档案室查资料。", expect: { action_type: "move", item_used: null, target: "二楼档案室", feasible: true } },
  { action: "我使用生锈的铁门钥匙打开大门。", expect: { action_type: "item_use", item_used: "铁门钥匙", target: "大门", feasible: false } },
  { action: "我和执行部学生搭话。", expect: { action_type: "npc_talk", item_used: null, target: "执行部学生", feasible: true } },
  { action: "我检查那扇书架后的暗门。", expect: { action_type: "inspect", item_used: null, target: "暗门", feasible: true } },
  { action: "我拔剑攻击诺诺。", expect: { action_type: "other", item_used: "剑", target: "诺诺", feasible: false } },
  { action: "我在原地休息一会儿。", expect: { action_type: "other", item_used: null, target: null, feasible: true } },
];

// 新用例集（held-out）：从未参与提示词、规则或判分调整。
const PARSE_CASES_NEW = [
  { action: "我仔细查看旧笔记里的字迹。", expect: { action_type: "inspect", item_used: null, target: "旧笔记", feasible: true } },
  { action: "我用旧笔记垫住门缝。", expect: { action_type: "item_use", item_used: "旧笔记", target: "门缝", feasible: true } },
  { action: "我去找执行部学生问话。", expect: { action_type: "npc_talk", item_used: null, target: "执行部学生", feasible: true } },
  { action: "我用路明非的校徽刷卡进楼。", expect: { action_type: "item_use", item_used: "校徽", target: "门禁", feasible: false } },
];

const ENTITY_ALIASES = {
  铜钥匙: ["铜钥匙"],
  旧笔记: ["旧笔记"],
  铁门钥匙: ["铁门钥匙", "生锈的铁门钥匙"],
  剑: ["剑", "长剑"],
  校徽: ["校徽", "路明非的校徽"],
  大门: ["大门", "图书馆大门"],
  门禁: ["门禁", "刷卡机"],
  暗门: ["暗门"],
  诺诺: ["诺诺"],
  执行部学生: ["执行部学生", "学生"],
  二楼档案室: ["二楼档案室", "档案室"],
  卡塞尔学院图书馆: ["卡塞尔学院图书馆", "图书馆"],
};

const OWNED = ["铜钥匙", "旧笔记"];
const PRESENT = ["诺诺", "执行部学生"];
const KNOWN_LOCATIONS = ["卡塞尔学院图书馆", "二楼档案室"];

function resolveEntity(raw) {
  if (raw == null) return null;
  const text = String(raw)
    .replace(/^我[把把]?/, "")
    .replace(/\s+/g, "")
    .trim()
    .replace(/[。，！？；、.!?;,]+$/, "");
  if (!text) return null;
  for (const [canonical, aliases] of Object.entries(ENTITY_ALIASES)) {
    if (aliases.includes(text)) return canonical;
  }
  return `UNKNOWN:${text}`;
}

function computeFeasible(extraction) {
  if (!extraction) return null;
  const item = resolveEntity(extraction.item_used);
  if (item !== null && !OWNED.includes(item)) return false;
  switch (extraction.action_type) {
    case "npc_talk": {
      const target = resolveEntity(extraction.target);
      return target !== null && PRESENT.includes(target);
    }
    case "move": {
      const target = resolveEntity(extraction.target);
      return target !== null && KNOWN_LOCATIONS.includes(target);
    }
    default:
      return true;
  }
}

const PARSE_FEWSHOT = [
  {
    user: "玩家行动：我检查铜钥匙的齿纹。",
    assistant: '{"action_type":"inspect","item_used":null,"target":"铜钥匙"}',
  },
  {
    user: "玩家行动：我沿着楼梯走到二楼档案室。",
    assistant: '{"action_type":"move","item_used":null,"target":"二楼档案室"}',
  },
];

const PARSE_SYSTEM_COMPACT = `你是文字冒险游戏的输入解析器。\n\n${PARSE_STATE}\n\n${PARSE_INSTRUCTION}`;

// ── 任务二：人名抽取（模型只抽人名；计数与 pass 由代码计算） ────────

const NAMES_SCHEMA = {
  type: "object",
  properties: { names: { type: "array", items: { type: "string" } } },
  required: ["names"],
};

const ROSTER = ["诺诺", "路明非", "古德里安", "绘梨衣"];
const NAMES_INSTRUCTION = `抽出文本中出现的所有人名，放入 names 数组。规则：
- 人名不含称谓与职务："古德里安教授"应输出"古德里安"；"执行部学生"这类职务指代不是人名。
- 不含地名和物品名。
只输出 JSON。`;

const NAMES_CASES_OLD = [
  { narration: "诺诺靠在书架旁，翻着那本旧笔记。路明非在门口安静地等着她。", expect: ["诺诺", "路明非"] },
  { narration: "月光像水一样洒在诺诺的肩上，她没有回头。", expect: ["诺诺"] },
  { narration: "诺诺说——这是个秘密。凯瑟琳在一旁快速记录。", expect: ["诺诺", "凯瑟琳"] },
  { narration: "古德里安教授推门进来，路明非起身行礼，绘梨衣跟在后面。", expect: ["古德里安", "路明非", "绘梨衣"] },
];

// 新用例集（held-out）：含称谓拆分、无人物的空输出。
const NAMES_CASES_NEW = [
  { narration: "绘梨衣在钟楼下等着路明非。", expect: ["绘梨衣", "路明非"] },
  { narration: "诺诺把报告交给古德里安教授。", expect: ["诺诺", "古德里安"] },
  { narration: "图书馆里只有凯瑟琳和诺诺两个人。", expect: ["凯瑟琳", "诺诺"] },
  { narration: "窗台上放着一杯凉掉的咖啡。", expect: [] },
];

const NAMES_FEWSHOT = [
  { user: "路明非把笔记本递给诺诺。", assistant: '{"names":["路明非","诺诺"]}' },
];

const NAMES_SYSTEM_COMPACT = `你是文字冒险游戏的文本检查器。\n\n${NAMES_INSTRUCTION}`;

function codeRuleCheck(narration, extractedNames) {
  const emDashCount = (narration.match(/—/g) ?? []).length;
  const simileCount = (narration.match(/像|仿佛|宛如|犹如|如同/g) ?? []).length;
  const unknownNames = extractedNames.filter((name) => !ROSTER.includes(name));
  return {
    em_dash_count: emDashCount,
    simile_count: simileCount,
    unknown_names: unknownNames,
    pass: emDashCount === 0 && simileCount === 0 && unknownNames.length === 0,
  };
}

const log = (...parts) => console.log(new Date().toISOString().slice(11, 19), ...parts);

async function main() {
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
  log(`crossOriginIsolated: ${isolated}`);
  if (!isolated) {
    console.error("FATAL: not cross-origin isolated; multi-thread unavailable.");
    await browser.close();
    process.exit(2);
  }

  const outDir = path.join(frontendRoot, "..", "artifacts", "benchmark");
  await mkdir(outDir, { recursive: true });

  log(`=== ${MODEL.tag}: loading ${MODEL.url} ===`);
  const loaded = await page.evaluate(
    async ({ modelUrl, threads: nThreads }) => {
      const { Wllama } = await import("/wllama/index.min.js");
      const instance = new Wllama(
        { default: "/wasm/wllama.wasm" },
        { logger: { ...console, debug: () => undefined } },
      );
      await instance.loadModelFromUrl(modelUrl, {
        useCache: false,
        n_ctx: 2048,
        n_batch: 512,
        n_ubatch: 128,
        n_gpu_layers: 0,
        warmup: false,
        n_threads: Number(nThreads),
      });
      window.__trialWllama = instance;
      return { multithread: instance.isMultithread(), numThreads: instance.getNumThreads() };
    },
    { modelUrl: `${baseUrl}${MODEL.url}`, threads },
  );
  log(`loaded: multithread=${loaded.multithread} threads=${loaded.numThreads}`);

  for (const trialArm of ["zero", "compact"]) {
    log(`--- arm: ${trialArm} ---`);
    const results = await page.evaluate(
    async (trial) => {
      const wllama = window.__trialWllama;
      const runCase = async (messages, schema, maxTokens, plain) => {
        const started = performance.now();
        try {
          const options = {
            messages,
            max_tokens: maxTokens,
            temperature: 0,
            seed: 4711,
            cache_prompt: false,
            chat_template_kwargs: { enable_thinking: false },
          };
          if (!plain) {
            options.response_format = {
              type: "json_schema",
              json_schema: { name: "trial", schema, strict: true },
            };
          }
          const response = await wllama.createChatCompletion(options);
          const text = (response.choices?.[0]?.message?.content ?? "")
            .replace(/<think>[\s\S]*?<\/think>/g, "")
            .trim();
          let parsed = null;
          if (plain) {
            parsed = {
              names: text
                .split("\n")
                .map((line) => line.replace(/^[-•\d.、\s]+/, "").replace(/^["']|["']$/g, "").trim())
                .filter(Boolean),
            };
          } else {
            try {
              parsed = JSON.parse(text);
            } catch {
              try {
                parsed = JSON.parse(text.replace(/^```(?:json)?|```$/g, "").trim());
              } catch {
                parsed = null;
              }
            }
          }
          return {
            wallMs: Math.round(performance.now() - started),
            // llama.cpp 分开计量：输入处理与生成各自的耗时与速率。
            promptTokens: response.usage?.prompt_tokens,
            completionTokens: response.usage?.completion_tokens,
            promptMs: response.timings?.prompt_ms != null ? Math.round(response.timings.prompt_ms) : null,
            predictedMs: response.timings?.predicted_ms != null ? Math.round(response.timings.predicted_ms) : null,
            promptPerSecond: response.timings?.prompt_per_second ?? null,
            predictedPerSecond: response.timings?.predicted_per_second ?? null,
            finishReason: response.choices?.[0]?.finish_reason ?? null,
            text,
            parsed,
            error: null,
          };
        } catch (error) {
          return {
            wallMs: Math.round(performance.now() - started),
            error: `${error instanceof Error ? error.name : ""} ${error instanceof Error ? error.message : error}`,
          };
        }
      };

      const buildMessages = (spec, userText) => {
        if (trial.arm === "zero") {
          return [
            { role: "system", content: spec.system },
            { role: "user", content: userText },
          ];
        }
        return [
          { role: "system", content: spec.compactSystem },
          ...spec.fewshot.flatMap((example) => [
            { role: "user", content: example.user },
            { role: "assistant", content: example.assistant },
          ]),
          { role: "user", content: userText },
        ];
      };

      const runBatch = async (cases, spec, userTextFor, schema, maxTokens, plain) => {
        const runs = [];
        for (const testCase of cases) {
          const run = {
            input: plain ? testCase.narration : testCase.action ?? testCase.narration,
            expect: testCase.expect,
            ...(await runCase(buildMessages(spec, userTextFor(testCase)), schema, maxTokens, plain)),
          };
          runs.push(run);
        }
        return runs;
      };

      const parseSpec = {
        system: "你是文字冒险游戏的输入解析器。",
        compactSystem: trial.parseSystemCompact,
        fewshot: trial.parseFewshot,
      };
      const parseUserText = (testCase) =>
        trial.arm === "compact"
          ? `玩家行动：${testCase.action}`
          : `${trial.parseState}\n\n玩家行动：${testCase.action}\n\n${trial.parseInstruction}`;

      const namesSpec = {
        system: "你是文字冒险游戏的文本检查器。",
        compactSystem: trial.namesSystemCompact,
        fewshot: trial.namesFewshot,
      };
      const namesUserText = (testCase) =>
        trial.arm === "compact" ? testCase.narration : `${testCase.narration}\n\n${trial.namesInstruction}`;

      return {
        parseOld: await runBatch(trial.parseCasesOld, parseSpec, parseUserText, trial.parseSchema, 120, false),
        parseNew: await runBatch(trial.parseCasesNew, parseSpec, parseUserText, trial.parseSchema, 120, false),
        namesOldJson: await runBatch(trial.namesCasesOld, namesSpec, namesUserText, trial.namesSchema, 80, false),
        namesNewJson: await runBatch(trial.namesCasesNew, namesSpec, namesUserText, trial.namesSchema, 80, false),
        // plain 每行一个名字、无 response_format——短输出格式对照臂。
        namesNewPlain:
          trial.arm === "compact"
            ? await runBatch(trial.namesCasesNew, namesSpec, namesUserText, trial.namesSchema, 60, true)
            : [],
      };
    },
    {
      parseCasesOld: PARSE_CASES_OLD,
      parseCasesNew: PARSE_CASES_NEW,
      parseState: PARSE_STATE,
      parseSchema: PARSE_SCHEMA,
      parseInstruction: PARSE_INSTRUCTION,
      parseFewshot: PARSE_FEWSHOT,
      parseSystemCompact: PARSE_SYSTEM_COMPACT,
      namesCasesOld: NAMES_CASES_OLD,
      namesCasesNew: NAMES_CASES_NEW,
      namesSchema: NAMES_SCHEMA,
      namesInstruction: NAMES_INSTRUCTION,
      namesFewshot: NAMES_FEWSHOT,
      namesSystemCompact: NAMES_SYSTEM_COMPACT,
      arm: trialArm,
    },
  );

  const normalize = (value) =>
    value == null ? null : String(value).replace(/\s+/g, "").trim() || null;
  const valueMatch = (expected, actual) => {
    const want = normalize(expected);
    const got = normalize(actual);
    if (want === null) return got === null;
    return got !== null && (got.includes(want) || want.includes(got));
  };

  const scoreParse = (runs) =>
    runs.map((run) => {
      let fieldResults = null;
      let correct = false;
      let codeFeasible = null;
      if (run.parsed) {
        fieldResults = {
          action_type: run.parsed.action_type === run.expect.action_type,
          item_used: resolveEntity(run.parsed.item_used) === resolveEntity(run.expect.item_used),
          target: resolveEntity(run.parsed.target) === resolveEntity(run.expect.target),
        };
        codeFeasible = computeFeasible(run.parsed);
        fieldResults.feasible = codeFeasible === run.expect.feasible;
        correct = Object.values(fieldResults).every(Boolean);
      }
      return { ...run, withinTarget: run.error ? undefined : run.wallMs <= TARGET_MS, correct, fieldResults, codeFeasible };
    });

  const scoreNames = (runs) =>
    runs.map((run) => {
      let namesMatch = false;
      let correct = false;
      if (run.parsed && Array.isArray(run.parsed.names)) {
        namesMatch =
          JSON.stringify([...run.parsed.names].sort()) ===
          JSON.stringify([...run.expect].sort());
        correct = namesMatch;
      }
      return { ...run, withinTarget: run.error ? undefined : run.wallMs <= TARGET_MS, namesMatch, correct };
    });

  const batches = {
    parseOld: scoreParse(results.parseOld),
    parseNew: scoreParse(results.parseNew),
    namesOldJson: scoreNames(results.namesOldJson),
    namesNewJson: scoreNames(results.namesNewJson),
    namesNewPlain: scoreNames(results.namesNewPlain),
  };
  const summarize = (runs) => ({
    withinTargetRate: `${runs.filter((run) => run.withinTarget).length}/${runs.length}`,
    correctRate: `${runs.filter((run) => run.correct).length}/${runs.length}`,
    minWallMs: Math.min(...runs.map((run) => run.wallMs)),
    maxWallMs: Math.max(...runs.map((run) => run.wallMs)),
    medianPromptMs: median(runs.map((run) => run.promptMs)),
    medianPredictedMs: median(runs.map((run) => run.predictedMs)),
  });
  const summary = Object.fromEntries(
    Object.entries(batches).map(([name, runs]) => [name, summarize(runs)]),
  );
  log(`summary: ${JSON.stringify(summary, null, 2)}`);

  const outPath = path.join(outDir, `task-trial4-${Date.now()}-${MODEL.tag}.json`);
  await writeFile(
    outPath,
    JSON.stringify(
      {
        hostCpu: cpu,
        threads: Number(threads),
        model: MODEL,
        runtime: loaded,
        targetMs: TARGET_MS,
        summary,
        batches,
        exportedAt: new Date().toISOString(),
      },
      null,
      2,
    ),
  );
  log(`saved: ${outPath}`);
  }

  await page.evaluate(async () => {
    await window.__trialWllama.exit();
    delete window.__trialWllama;
  });
  await browser.close();
}

function median(values) {
  const sorted = values.filter((value) => value != null).sort((a, b) => a - b);
  if (!sorted.length) return null;
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : Math.round((sorted[mid - 1] + sorted[mid]) / 2);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
