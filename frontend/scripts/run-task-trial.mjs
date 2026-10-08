// Task-level trial v2: short-input/short-output agent jobs with the
// responsibility split proposed in review —
//   model: extract action type / item used / target object, extract names
//   code:  possession & presence checks, dash/simile counts, pass flag
// Zero-shot vs few-shot arms share one held-out test set; few-shot examples
// never appear in it. Scored on wall time AND deterministic correctness.
//
// Usage: node scripts/run-task-trial.mjs [threads]
// Output: artifacts/benchmark/task-trial2-<ts>-<modeltag>-<arm>.json

import { mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const frontendRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const baseUrl = process.env.BASE_URL ?? "http://localhost:3100";
const threads = process.argv[2] ?? "4";
const TARGET_MS = 4000;

const MODELS = [
  { tag: "qwen3-0.6b", url: "/models/Qwen3-0.6B-Q4_K_M.gguf" },
  { tag: "qwen2.5-0.5b", url: "/models/qwen2.5-0.5b-instruct-q4_k_m.gguf" },
];

// ── 场景状态（与期望答案一致；地点/物品/NPC 全部显式列出） ──────────

const PARSE_STATE = `当前地点：卡塞尔学院图书馆。
已知地点：卡塞尔学院图书馆、二楼档案室。
持有物品：铜钥匙（owned）、旧笔记（owned）。
在场 NPC：诺诺、执行部学生。
体力 88/100，血统稳定 72/100。`;

// ── 任务一：行动解析（模型只做抽取；feasible 由代码按规则计算） ────

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
- item_used：行动中使用的物品名（原文摘录），没有则为 null。
- target：行动的作用对象（人物、地点或物件名，原文摘录），没有则为 null。
不要判断行动是否可行，那只由规则代码计算。只输出 JSON。`;

// expected: 模型抽取期望；feasible 由 computeFeasible 按规则得出。
const PARSE_CASES = [
  { action: "我用铜钥匙打开大门。", expect: { action_type: "item_use", item_used: "铜钥匙", target: "大门" } },
  { action: "我和诺诺打听图书馆的传闻。", expect: { action_type: "npc_talk", item_used: null, target: "诺诺" } },
  { action: "我去二楼档案室查资料。", expect: { action_type: "move", item_used: null, target: "二楼档案室" } },
  { action: "我使用生锈的铁门钥匙打开大门。", expect: { action_type: "item_use", item_used: "铁门钥匙", target: "大门" } },
  { action: "我和执行部学生搭话。", expect: { action_type: "npc_talk", item_used: null, target: "执行部学生" } },
  { action: "我检查那扇书架后的暗门。", expect: { action_type: "inspect", item_used: null, target: "暗门" } },
  { action: "我拔剑攻击诺诺。", expect: { action_type: "other", item_used: "剑", target: "诺诺" } },
  { action: "我在原地休息一会儿。", expect: { action_type: "other", item_used: null, target: null } },
];

// 沿用 Examiner 的适用规则：item_use 需物品持有；npc_talk 需 NPC 在场；
// move 需地点已知；inspect/other 不加前置。
function computeFeasible(extraction) {
  if (!extraction) return null;
  const owned = ["铜钥匙", "旧笔记"];
  const present = ["诺诺", "执行部学生"];
  const knownLocations = ["卡塞尔学院图书馆", "二楼档案室"];
  switch (extraction.action_type) {
    case "item_use":
      return owned.includes(extraction.item_used ?? "");
    case "npc_talk":
      return present.includes(extraction.target ?? "");
    case "move":
      return knownLocations.includes(extraction.target ?? "");
    default:
      return true;
  }
}

// few-shot 示例：held-out，不属于测试集。
const PARSE_FEWSHOT = [
  {
    user: `${PARSE_STATE}\n\n玩家行动：我检查铜钥匙的齿纹。\n\n${PARSE_INSTRUCTION}`,
    assistant: '{"action_type":"inspect","item_used":null,"target":"铜钥匙"}',
  },
  {
    user: `${PARSE_STATE}\n\n玩家行动：我沿着楼梯走到二楼档案室。\n\n${PARSE_INSTRUCTION}`,
    assistant: '{"action_type":"move","item_used":null,"target":"二楼档案室"}',
  },
];

// ── 任务二：人名抽取（模型只抽人名；违规计数与 pass 由代码计算） ────

const NAMES_SCHEMA = {
  type: "object",
  properties: { names: { type: "array", items: { type: "string" } } },
  required: ["names"],
};

const ROSTER = ["诺诺", "路明非", "古德里安", "绘梨衣"];
const NAMES_INSTRUCTION = `抽出文本中出现的所有人名，放入 names 数组。人名指具体人物的名字，不含称谓、地名和物品名。只输出 JSON。`;

const NAMES_CASES = [
  {
    narration: "诺诺靠在书架旁，翻着那本旧笔记。路明非在门口安静地等着她。",
    expect: ["诺诺", "路明非"],
  },
  {
    narration: "月光像水一样洒在诺诺的肩上，她没有回头。",
    expect: ["诺诺"],
  },
  {
    narration: "诺诺说——这是个秘密。凯瑟琳在一旁快速记录。",
    expect: ["诺诺", "凯瑟琳"],
  },
  {
    narration: "古德里安教授推门进来，路明非起身行礼，绘梨衣跟在后面。",
    expect: ["古德里安", "路明非", "绘梨衣"],
  },
];

const NAMES_FEWSHOT = [
  {
    user: "路明非把笔记本递给诺诺。\n\n抽出文本中出现的所有人名，放入 names 数组。只输出 JSON。",
    assistant: '{"names":["路明非","诺诺"]}',
  },
];

// ── 代码侧规则检查（用户职责划分：计数与 pass 归代码） ─────────────

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

  for (const model of MODELS) {
    for (const arm of ["zero", "few"]) {
      log(`=== ${model.tag} / ${arm}-shot: loading ${model.url} ===`);
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
        { modelUrl: `${baseUrl}${model.url}`, threads },
      );
      log(`loaded: multithread=${loaded.multithread} threads=${loaded.numThreads}`);

      const results = await page.evaluate(
        async (trial) => {
          const wllama = window.__trialWllama;
          const runCase = async (messages, schema, maxTokens) => {
            const started = performance.now();
            try {
              const response = await wllama.createChatCompletion({
                messages,
                max_tokens: maxTokens,
                temperature: 0,
                seed: 4711,
                cache_prompt: false,
                chat_template_kwargs: { enable_thinking: false },
                response_format: {
                  type: "json_schema",
                  json_schema: { name: "trial", schema, strict: true },
                },
              });
              const text = (response.choices?.[0]?.message?.content ?? "")
                .replace(/<think>[\s\S]*?<\/think>/g, "")
                .trim();
              let parsed = null;
              try {
                parsed = JSON.parse(text);
              } catch {
                try {
                  parsed = JSON.parse(text.replace(/^```(?:json)?|```$/g, "").trim());
                } catch {
                  parsed = null;
                }
              }
              return {
                wallMs: Math.round(performance.now() - started),
                promptTokens: response.usage?.prompt_tokens,
                completionTokens: response.usage?.completion_tokens,
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

          const buildMessages = (fewshot, systemText, userText) => [
            { role: "system", content: systemText },
            ...fewshot.flatMap((example) => [
              { role: "user", content: example.user },
              { role: "assistant", content: example.assistant },
            ]),
            { role: "user", content: userText },
          ];

          const parseRuns = [];
          for (const testCase of trial.parseCases) {
            const userText = `${trial.parseState}\n\n玩家行动：${testCase.action}\n\n${trial.parseInstruction}`;
            const run = {
              action: testCase.action,
              expect: testCase.expect,
              ...(await runCase(
                buildMessages(
                  trial.arm === "few" ? trial.parseFewshot : [],
                  "你是文字冒险游戏的输入解析器。",
                  userText,
                ),
                trial.parseSchema,
                120,
              )),
            };
            parseRuns.push(run);
          }

          const namesRuns = [];
          for (const testCase of trial.namesCases) {
            const userText = `${testCase.narration}\n\n${trial.namesInstruction}`;
            const run = {
              narration: testCase.narration,
              expect: testCase.expect,
              ...(await runCase(
                buildMessages(
                  trial.arm === "few" ? trial.namesFewshot : [],
                  "你是文字冒险游戏的文本检查器。",
                  userText,
                ),
                trial.namesSchema,
                80,
              )),
            };
            namesRuns.push(run);
          }
          return { parseRuns, namesRuns };
        },
        {
          parseCases: PARSE_CASES,
          parseState: PARSE_STATE,
          parseSchema: PARSE_SCHEMA,
          parseInstruction: PARSE_INSTRUCTION,
          parseFewshot: PARSE_FEWSHOT,
          namesCases: NAMES_CASES,
          namesSchema: NAMES_SCHEMA,
          namesInstruction: NAMES_INSTRUCTION,
          namesFewshot: NAMES_FEWSHOT,
          arm,
        },
      );

      // ── 判分 ──
      // 双向包含匹配，但两侧都必须非空——空串不再是自动通过。
      const normalize = (value) =>
        value == null ? null : String(value).replace(/\s+/g, "").trim() || null;
      const valueMatch = (expected, actual) => {
        const want = normalize(expected);
        const got = normalize(actual);
        if (want === null) return got === null;
        return got !== null && (got.includes(want) || want.includes(got));
      };

      const parseScored = results.parseRuns.map((run) => {
        let fieldResults = null;
        let correct = false;
        let codeFeasible = null;
        if (run.parsed) {
          fieldResults = {
            action_type: run.parsed.action_type === run.expect.action_type,
            item_used: valueMatch(run.expect.item_used, run.parsed.item_used),
            target: valueMatch(run.expect.target, run.parsed.target),
          };
          correct = Object.values(fieldResults).every(Boolean);
          codeFeasible = computeFeasible(run.parsed);
        }
        return {
          ...run,
          withinTarget: run.error ? undefined : run.wallMs <= TARGET_MS,
          correct,
          fieldResults,
          codeFeasible,
        };
      });

      const namesScored = results.namesRuns.map((run) => {
        let namesMatch = false;
        let ruleCheck = null;
        let correct = false;
        if (run.parsed && Array.isArray(run.parsed.names)) {
          namesMatch =
            JSON.stringify([...run.parsed.names].sort()) ===
            JSON.stringify([...run.expect].sort());
          ruleCheck = codeRuleCheck(run.narration, run.parsed.names);
          const expectedRuleCheck = codeRuleCheck(run.narration, run.expect);
          correct = namesMatch && JSON.stringify(ruleCheck) === JSON.stringify(expectedRuleCheck);
        }
        return {
          ...run,
          withinTarget: run.error ? undefined : run.wallMs <= TARGET_MS,
          namesMatch,
          ruleCheck,
          correct,
        };
      });

      const summarize = (runs) => ({
        withinTargetRate: `${runs.filter((run) => run.withinTarget).length}/${runs.length}`,
        correctRate: `${runs.filter((run) => run.correct).length}/${runs.length}`,
        maxWallMs: Math.max(...runs.map((run) => run.wallMs)),
      });
      const summary = { parse: summarize(parseScored), names: summarize(namesScored) };
      log(`${model.tag}/${arm}: ${JSON.stringify(summary)}`);

      const outPath = path.join(outDir, `task-trial2-${Date.now()}-${model.tag}-${arm}.json`);
      await writeFile(
        outPath,
        JSON.stringify(
          {
            hostCpu: cpu,
            threads: Number(threads),
            model,
            arm,
            runtime: loaded,
            targetMs: TARGET_MS,
            summary,
            parseRuns: parseScored,
            namesRuns: namesScored,
            exportedAt: new Date().toISOString(),
          },
          null,
          2,
        ),
      );
      log(`saved: ${outPath}`);

      await page.evaluate(async () => {
        await window.__trialWllama.exit();
        delete window.__trialWllama;
      });
    }
  }

  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
