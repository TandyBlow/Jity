// Task-level trial: short-input/short-output real agent jobs (player-action
// parsing, narration checking) against candidate models, judged on wall time
// AND deterministic correctness.
//
// Usage: node scripts/run-task-trial.mjs [threads]
// Models are fixed below; each model is loaded, all cases run, then unloaded.
// Output: artifacts/benchmark/task-trial-<ts>-<modeltag>.json

import { mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const frontendRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const baseUrl = process.env.BASE_URL ?? "http://localhost:3100";
const threads = process.argv[2] ?? "4";

const MODELS = [
  { tag: "qwen3-0.6b", url: "/models/Qwen3-0.6B-Q4_K_M.gguf" },
  { tag: "qwen2.5-0.5b", url: "/models/qwen2.5-0.5b-instruct-q4_k_m.gguf" },
];

const TARGET_MS = 4000;

// ── 任务一：输入解析 ──────────────────────────────────────────────
// Fixed story state baked into every prompt; expectations are deterministic.

const PARSE_STATE = `当前地点：卡塞尔学院图书馆。
持有物品：铜钥匙（owned）、旧笔记（owned）。
在场 NPC：诺诺、执行部学生。
体力 88/100，血统稳定 72/100。`;

const PARSE_SCHEMA = {
  type: "object",
  properties: {
    action_type: { enum: ["item_use", "npc_talk", "move", "inspect", "other"] },
    target: { type: "string" },
    feasible: { type: "boolean" },
    reason: { type: "string" },
  },
  required: ["action_type", "target", "feasible", "reason"],
};

const PARSE_CASES = [
  { action: "我用铜钥匙打开大门。", expect: { action_type: "item_use", target: "铜钥匙", feasible: true } },
  { action: "我和诺诺打听图书馆的传闻。", expect: { action_type: "npc_talk", target: "诺诺", feasible: true } },
  { action: "我去二楼档案室查资料。", expect: { action_type: "move", target: "二楼档案室", feasible: true } },
  { action: "我使用生锈的铁门钥匙打开大门。", expect: { action_type: "item_use", target: "铁门钥匙", feasible: false } },
  { action: "我和执行部学生搭话。", expect: { action_type: "npc_talk", target: "执行部学生", feasible: true } },
  { action: "我绕着书架检查有没有暗门。", expect: { action_type: "inspect", target: null, feasible: true } },
  { action: "我拔剑攻击诺诺。", expect: { action_type: "other", target: null, feasible: false } },
  { action: "我在原地休息一会儿。", expect: { action_type: "other", target: null, feasible: true } },
];

// ── 任务二：文本检查 ──────────────────────────────────────────────

const CHECK_RULES = `检查规则：
1. 禁止破折号（—）。
2. 禁止比喻句式（像、仿佛、宛如、犹如、如同）。
3. 出现的人名必须在名单内：诺诺、路明非、古德里安、绘梨衣。
已知名单之外的任何名字都算违规。`;

const CHECK_SCHEMA = {
  type: "object",
  properties: {
    em_dash_count: { type: "integer" },
    simile_count: { type: "integer" },
    unknown_names: { type: "array", items: { type: "string" } },
    pass: { type: "boolean" },
  },
  required: ["em_dash_count", "simile_count", "unknown_names", "pass"],
};

const CHECK_CASES = [
  {
    narration: "诺诺靠在书架旁，翻着那本旧笔记。路明非在门口安静地等着她。",
    expect: { em_dash_count: 0, simile_count: 0, unknown_names: [], pass: true },
  },
  {
    narration: "月光像水一样洒在诺诺的肩上，她没有回头。",
    expect: { em_dash_count: 0, simile_count: 1, unknown_names: [], pass: false },
  },
  {
    narration: "诺诺说——这是个秘密。凯瑟琳在一旁快速记录。",
    expect: { em_dash_count: 1, simile_count: 0, unknown_names: ["凯瑟琳"], pass: false },
  },
  {
    narration: "古德里安教授推门进来，路明非起身行礼，绘梨衣跟在后面。",
    expect: { em_dash_count: 0, simile_count: 0, unknown_names: [], pass: true },
  },
];

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
    log(`=== ${model.tag}: loading ${model.url} ===`);
    const loaded = await page.evaluate(async ({ modelUrl, threads }) => {
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
        n_threads: Number(threads),
      });
      window.__trialWllama = instance;
      return {
        multithread: instance.isMultithread(),
        numThreads: instance.getNumThreads(),
        meta: instance.getModelMetadata().meta,
      };
    }, { modelUrl: `${baseUrl}${model.url}`, threads });
    log(`loaded: multithread=${loaded.multithread} threads=${loaded.numThreads}`);

    const results = await page.evaluate(
      async ({ parseCases, parseState, parseSchema, checkCases, checkRules, checkSchema, targetMs }) => {
        const wllama = window.__trialWllama;
        const runCase = async (systemText, userText, schema, maxTokens) => {
          const started = performance.now();
          try {
            const response = await wllama.createChatCompletion({
              messages: [
                { role: "system", content: systemText },
                { role: "user", content: userText },
              ],
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
            const text = response.choices?.[0]?.message?.content ?? "";
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

        const parseRuns = [];
        for (const testCase of parseCases) {
          const userText = `${parseState}\n\n玩家行动：${testCase.action}\n\n判断该行动的类型、目标对象，以及基于当前状态是否可行。只输出 JSON。`;
          const run = {
            action: testCase.action,
            expect: testCase.expect,
            ...(await runCase(
              "你是文字冒险游戏的输入解析器。根据给定状态把玩家行动解析为 JSON。目标对象用行动中出现的原文；目标不存在或不在状态中时 feasible 为 false。",
              userText,
              parseSchema,
              200,
            )),
          };
          parseRuns.push(run);
        }

        const checkRuns = [];
        for (const testCase of checkCases) {
          const userText = `${checkRules}\n\n待检查文本：${testCase.narration}\n\n按规则统计违规项并给出 pass。只输出 JSON。`;
          const run = {
            narration: testCase.narration,
            expect: testCase.expect,
            ...(await runCase(
              "你是文字冒险游戏的文本检查器。按规则统计文本中的违规项，输出 JSON。",
              userText,
              checkSchema,
              160,
            )),
          };
          checkRuns.push(run);
        }
        return { parseRuns, checkRuns };
      },
      {
        parseCases: PARSE_CASES,
        parseState: PARSE_STATE,
        parseSchema: PARSE_SCHEMA,
        checkCases: CHECK_CASES,
        checkRules: CHECK_RULES,
        checkSchema: CHECK_SCHEMA,
        targetMs: TARGET_MS,
      },
    );

    const score = (runs, kind) =>
      runs.map((run) => {
        const withinTarget = run.error ? undefined : run.wallMs <= TARGET_MS;
        let fieldResults = null;
        let correct = false;
        if (run.parsed) {
          if (kind === "parse") {
            const targetMatch =
              run.expect.target == null ||
              String(run.parsed.target ?? "").includes(run.expect.target) ||
              run.expect.target.includes(String(run.parsed.target ?? "\u0000"));
            fieldResults = {
              action_type: run.parsed.action_type === run.expect.action_type,
              feasible: run.parsed.feasible === run.expect.feasible,
              target: targetMatch,
            };
            correct = fieldResults.action_type && fieldResults.feasible && fieldResults.target;
          } else {
            const unknownMatch =
              JSON.stringify([...(run.parsed.unknown_names ?? [])].sort()) ===
              JSON.stringify([...run.expect.unknown_names].sort());
            fieldResults = {
              em_dash_count: run.parsed.em_dash_count === run.expect.em_dash_count,
              simile_count: run.parsed.simile_count === run.expect.simile_count,
              unknown_names: unknownMatch,
              pass: run.parsed.pass === run.expect.pass,
            };
            correct = Object.values(fieldResults).every(Boolean);
          }
        }
        return { withinTarget, correct, fieldResults };
      });

    const parseScore = score(results.parseRuns, "parse");
    const checkScore = score(results.checkRuns, "check");
    const summary = {
      parse: {
        withinTargetRate: `${parseScore.filter((s) => s.withinTarget).length}/${parseScore.length}`,
        correctRate: `${parseScore.filter((s) => s.correct).length}/${parseScore.length}`,
        maxWallMs: Math.max(...results.parseRuns.map((r) => r.wallMs)),
      },
      check: {
        withinTargetRate: `${checkScore.filter((s) => s.withinTarget).length}/${checkScore.length}`,
        correctRate: `${checkScore.filter((s) => s.correct).length}/${checkScore.length}`,
        maxWallMs: Math.max(...results.checkRuns.map((r) => r.wallMs)),
      },
    };
    log(`${model.tag} summary: ${JSON.stringify(summary)}`);

    const outPath = path.join(outDir, `task-trial-${Date.now()}-${model.tag}.json`);
    await writeFile(
      outPath,
      JSON.stringify(
        {
          hostCpu: cpu,
          threads: Number(threads),
          model,
          runtime: loaded,
          targetMs: TARGET_MS,
          summary,
          parseRuns: results.parseRuns.map((run, index) => ({ ...run, ...parseScore[index] })),
          checkRuns: results.checkRuns.map((run, index) => ({ ...run, ...checkScore[index] })),
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

  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
