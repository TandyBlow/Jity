// Task-level trial v5 (Qwen3 only). Changes from v4, per review of the
// trial5 reports:
// - BUGFIX: the plain arm's dedicated instruction never reached the model —
//   v4 built userText as `plain ? narration : narration + instruction`, so
//   plain ran unconstrained AND uninstructed, and its whole-sentence echoes
//   proved nothing. The instruction is now appended for both arms.
// - postProcessed (raw/stripped/unknownNames) is recorded per names run;
//   v4 computed it for scoring but dropped it from the exported report.
// - message contracts: before any request is sent, every run's actual
//   messages are checked against the arm's instruction / output-convention
//   phrases (ablation arms also against forbidden phrases); a violation
//   aborts the run instead of exporting an uninterpretable report. Run with
//   CONTRACT_CHECK_ONLY=1 to verify contracts without loading the model.
// - parse arms are now the state-ablation pair compact vs no-state: same
//   system prompt, same fewshot, same instruction position, same schema and
//   constrained decoding — the ONLY variable is the scene-state block.
//   minimal (no state, no fewshot, instruction moved into system) is not
//   re-run: its trial5 speed result stands, but it changed three variables
//   at once and cannot attribute anything to state alone.
//
// Usage: node scripts/run-task-trial.mjs [threads]
// Output: artifacts/benchmark/task-trial6-<ts>-<task>-<arm>.json

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

// 旧用例集（此前各轮已用于观察）。校徽用例的 target 改为原文中出现的"闸机"。
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

// 新用例集（held-out）。
const PARSE_CASES_NEW = [
  { action: "我仔细查看旧笔记里的字迹。", expect: { action_type: "inspect", item_used: null, target: "旧笔记", feasible: true } },
  { action: "我用旧笔记垫住门缝。", expect: { action_type: "item_use", item_used: "旧笔记", target: "门缝", feasible: true } },
  { action: "我去找执行部学生问话。", expect: { action_type: "npc_talk", item_used: null, target: "执行部学生", feasible: true } },
  { action: "我用路明非的校徽刷开闸机。", expect: { action_type: "item_use", item_used: "校徽", target: "闸机", feasible: false } },
];

const ENTITY_ALIASES = {
  铜钥匙: ["铜钥匙"],
  旧笔记: ["旧笔记"],
  铁门钥匙: ["铁门钥匙", "生锈的铁门钥匙"],
  剑: ["剑", "长剑"],
  校徽: ["校徽", "路明非的校徽"],
  大门: ["大门", "图书馆大门"],
  闸机: ["闸机"],
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

// ── 任务二：人名抽取 ──────────────────────────────────────────────

const NAMES_SCHEMA = {
  type: "object",
  properties: { names: { type: "array", items: { type: "string" } } },
  required: ["names"],
};

const ROSTER = ["诺诺", "路明非", "古德里安", "绘梨衣"];
const TITLES = ["教授", "老师", "博士", "先生", "女士"];

const NAMES_INSTRUCTION_JSON = `抽出文本中出现的所有人名，放入 names 数组。规则：
- 人名不含称谓与职务："古德里安教授"应输出"古德里安"；"执行部学生"这类职务指代不是人名。
- 不含地名和物品名。
只输出 JSON。`;

// plain 臂的配套指令/示例/空约定（v3 的教训：只关约束不改指令等于没改；
// v4 的教训：改了指令但没接进 messages 等于白跑）。
const NAMES_INSTRUCTION_PLAIN = `抽出文本中出现的所有人名，一行输出一个名字。
- 人名不含称谓与职务："古德里安教授"应输出"古德里安"；"执行部学生"这类职务指代不是人名。
- 不含地名和物品名。
- 文本中没有人名时，只输出三个字：没有人
不要输出 JSON、解释或任何其他内容。`;

const NAMES_CASES_OLD = [
  { narration: "诺诺靠在书架旁，翻着那本旧笔记。路明非在门口安静地等着她。", expect: ["诺诺", "路明非"] },
  { narration: "月光像水一样洒在诺诺的肩上，她没有回头。", expect: ["诺诺"] },
  { narration: "诺诺说——这是个秘密。凯瑟琳在一旁快速记录。", expect: ["诺诺", "凯瑟琳"] },
  { narration: "古德里安教授推门进来，路明非起身行礼，绘梨衣跟在后面。", expect: ["古德里安", "路明非", "绘梨衣"] },
];

const NAMES_CASES_NEW = [
  { narration: "绘梨衣在钟楼下等着路明非。", expect: ["绘梨衣", "路明非"] },
  { narration: "诺诺把报告交给古德里安教授。", expect: ["诺诺", "古德里安"] },
  { narration: "图书馆里只有凯瑟琳和诺诺两个人。", expect: ["凯瑟琳", "诺诺"] },
  { narration: "窗台上放着一杯凉掉的咖啡。", expect: [] },
];

const NAMES_FEWSHOT_JSON = [
  { user: "路明非把笔记本递给诺诺。", assistant: '{"names":["路明非","诺诺"]}' },
];

const NAMES_FEWSHOT_PLAIN = [
  { user: "路明非把笔记本递给诺诺。", assistant: "路明非\n诺诺" },
];

// ── 消息构造与契约检查 ────────────────────────────────────────────
// 消息只在 Node 侧构造；每个臂发送任何请求之前，实际 messages 逐条对
// 契约检查，违反即中止（不再产出无法解释的报告）。

function buildParseMessages(arm, testCase) {
  // 状态消融对 compact / no-state：系统提示、示例、指令位置、schema 与
  // 约束解码全部相同，唯一变量是状态块。
  const stateBlock = arm === "compact" ? `${PARSE_STATE}\n\n` : "";
  const userText = `${stateBlock}玩家行动：${testCase.action}\n\n${PARSE_INSTRUCTION}`;
  return [
    { role: "system", content: "你是文字冒险游戏的输入解析器。" },
    ...PARSE_FEWSHOT.flatMap((example) => [
      { role: "user", content: example.user },
      { role: "assistant", content: example.assistant },
    ]),
    { role: "user", content: userText },
  ];
}

function buildNamesMessages(arm, testCase) {
  const instruction = arm === "plain" ? NAMES_INSTRUCTION_PLAIN : NAMES_INSTRUCTION_JSON;
  const fewshot = arm === "plain" ? NAMES_FEWSHOT_PLAIN : NAMES_FEWSHOT_JSON;
  const userText = `${testCase.narration}\n\n${instruction}`;
  return [
    { role: "system", content: "你是文字冒险游戏的文本检查器。" },
    ...fewshot.flatMap((example) => [
      { role: "user", content: example.user },
      { role: "assistant", content: example.assistant },
    ]),
    { role: "user", content: userText },
  ];
}

// 每臂契约：mustContain 是该臂指令与输出约定的标识短语（含 fewshot 的
// assistant 内容，防示例漏接）；no-state 额外断言状态块短语不出现。
const MESSAGE_CONTRACTS = {
  "parse/compact": {
    mustContain: [
      "把玩家行动解析为 JSON",
      "只输出 JSON",
      '{"action_type":"inspect","item_used":null,"target":"铜钥匙"}',
      "当前地点：卡塞尔学院图书馆",
      "持有物品：铜钥匙",
      "在场 NPC：诺诺",
    ],
  },
  "parse/no-state": {
    mustContain: [
      "把玩家行动解析为 JSON",
      "只输出 JSON",
      '{"action_type":"inspect","item_used":null,"target":"铜钥匙"}',
    ],
    mustNotContain: ["当前地点：", "已知地点：", "持有物品：", "在场 NPC：", "体力 88/100"],
  },
  "names/json": {
    mustContain: ["抽出文本中出现的所有人名", "只输出 JSON", '{"names":["路明非","诺诺"]}'],
  },
  "names/plain": {
    mustContain: [
      "抽出文本中出现的所有人名",
      "一行输出一个名字",
      "没有人",
      "不要输出 JSON",
      "路明非\n诺诺",
    ],
  },
};

function checkMessageContract(taskArm, messages) {
  const { mustContain = [], mustNotContain = [] } = MESSAGE_CONTRACTS[taskArm];
  const text = messages.map((message) => message.content).join("\n");
  for (const phrase of mustContain) {
    if (!text.includes(phrase)) throw new Error(`[contract ${taskArm}] messages 缺少约定："${phrase}"`);
  }
  for (const phrase of mustNotContain) {
    if (text.includes(phrase)) throw new Error(`[contract ${taskArm}] messages 不应包含："${phrase}"`);
  }
}

// 称谓后处理：固定确定性规则——先剥称谓再映射名册。原始与后处理结果都入库。
function stripTitles(name) {
  let text = String(name).trim();
  let changed = true;
  while (changed) {
    changed = false;
    for (const title of TITLES) {
      if (text.endsWith(title)) {
        text = text.slice(0, -title.length);
        changed = true;
      }
    }
  }
  return text;
}

function postProcessNames(rawNames) {
  const raw = [...rawNames];
  const stripped = raw.map(stripTitles).filter(Boolean);
  const unknownNames = stripped.filter((name) => !ROSTER.includes(name));
  return { raw, stripped, unknownNames };
}

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
  // 只验证消息契约，不加载模型（CI / 快速自检用）。
  if (process.env.CONTRACT_CHECK_ONLY === "1") {
    const probes = [
      ["parse/compact", buildParseMessages("compact", PARSE_CASES_OLD[0])],
      ["parse/no-state", buildParseMessages("no-state", PARSE_CASES_OLD[0])],
      ["names/json", buildNamesMessages("json", NAMES_CASES_OLD[0])],
      ["names/plain", buildNamesMessages("plain", NAMES_CASES_OLD[0])],
    ];
    for (const [taskArm, messages] of probes) {
      checkMessageContract(taskArm, messages);
      log(`contract pass: ${taskArm}`);
    }
    log("all message contracts pass");
    return;
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

  const runParams = {
    model: MODEL,
    n_ctx: 2048,
    n_batch: 512,
    n_ubatch: 128,
    n_gpu_layers: 0,
    n_threads: Number(threads),
    temperature: 0,
    seed: 4711,
    cache_prompt: false,
    enable_thinking: false,
  };

  // ── 解析臂：状态消融对 compact / no-state（唯一变量：状态块） ──────
  for (const parseArm of ["compact", "no-state"]) {
    const cases = [...PARSE_CASES_OLD, ...PARSE_CASES_NEW].map((testCase) => ({
      batch: PARSE_CASES_OLD.includes(testCase) ? "old" : "new",
      action: testCase.action,
      expect: testCase.expect,
      messages: buildParseMessages(parseArm, testCase),
    }));
    for (const testCase of cases) checkMessageContract(`parse/${parseArm}`, testCase.messages);
    log(`parse/${parseArm}: message contract pass on ${cases.length} cases`);

    const runs = await page.evaluate(
      async (trial) => {
        const wllama = window.__trialWllama;
        const runs = [];
        for (const testCase of trial.cases) {
          const started = performance.now();
          try {
            const response = await wllama.createChatCompletion({
              messages: testCase.messages,
              max_tokens: 120,
              temperature: 0,
              seed: 4711,
              cache_prompt: false,
              chat_template_kwargs: { enable_thinking: false },
              response_format: {
                type: "json_schema",
                json_schema: { name: "trial", schema: trial.schema, strict: true },
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
            runs.push({
              batch: testCase.batch,
              action: testCase.action,
              expect: testCase.expect,
              messages: testCase.messages,
              contractPass: true,
              wallMs: Math.round(performance.now() - started),
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
            });
          } catch (error) {
            runs.push({
              batch: testCase.batch,
              action: testCase.action,
              expect: testCase.expect,
              messages: testCase.messages,
              contractPass: true,
              wallMs: Math.round(performance.now() - started),
              error: `${error instanceof Error ? error.name : ""} ${error instanceof Error ? error.message : error}`,
            });
          }
        }
        return runs;
      },
      { cases, schema: PARSE_SCHEMA },
    );

    const scored = runs.map((run) => {
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
      return {
        ...run,
        withinTarget: run.error ? undefined : run.wallMs <= TARGET_MS,
        correct,
        fieldResults,
        codeFeasible,
      };
    });
    const old = scored.filter((run) => run.batch === "old");
    const fresh = scored.filter((run) => run.batch === "new");
    const summarize = (runs) => ({
      withinTargetRate: `${runs.filter((run) => run.withinTarget).length}/${runs.length}`,
      correctRate: `${runs.filter((run) => run.correct).length}/${runs.length}`,
      minWallMs: Math.min(...runs.map((run) => run.wallMs)),
      maxWallMs: Math.max(...runs.map((run) => run.wallMs)),
      medianPromptMs: median(runs.map((run) => run.promptMs)),
      medianPredictedMs: median(runs.map((run) => run.predictedMs)),
    });
    const summary = { old: summarize(old), new: summarize(fresh) };
    log(`parse/${parseArm}: ${JSON.stringify(summary)}`);
    const outPath = path.join(outDir, `task-trial6-${Date.now()}-parse-${parseArm}.json`);
    await writeFile(
      outPath,
      JSON.stringify(
        { hostCpu: cpu, task: "parse", arm: parseArm, runParams, runtime: loaded, targetMs: TARGET_MS, summary, runs: scored, exportedAt: new Date().toISOString() },
        null,
        2,
      ),
    );
    log(`saved: ${outPath}`);
  }

  // ── 抽名臂：json（schema 约束）/ plain（指令+示例+空约定，v5 起真正进消息） ──
  for (const namesArm of ["json", "plain"]) {
    const plain = namesArm === "plain";
    const cases = [...NAMES_CASES_OLD, ...NAMES_CASES_NEW].map((testCase) => ({
      batch: NAMES_CASES_OLD.includes(testCase) ? "old" : "new",
      narration: testCase.narration,
      expect: testCase.expect,
      messages: buildNamesMessages(namesArm, testCase),
    }));
    for (const testCase of cases) checkMessageContract(`names/${namesArm}`, testCase.messages);
    log(`names/${namesArm}: message contract pass on ${cases.length} cases`);

    const runs = await page.evaluate(
      async (trial) => {
        const wllama = window.__trialWllama;
        const runs = [];
        for (const testCase of trial.cases) {
          const started = performance.now();
          try {
            const options = {
              messages: testCase.messages,
              max_tokens: 80,
              temperature: 0,
              seed: 4711,
              cache_prompt: false,
              chat_template_kwargs: { enable_thinking: false },
            };
            if (!trial.plain) {
              options.response_format = {
                type: "json_schema",
                json_schema: { name: "trial", schema: trial.schema, strict: true },
              };
            }
            const response = await wllama.createChatCompletion(options);
            const text = (response.choices?.[0]?.message?.content ?? "")
              .replace(/<think>[\s\S]*?<\/think>/g, "")
              .trim();
            let parsed = null;
            if (trial.plain) {
              const lines = text
                .split("\n")
                .map((line) => line.replace(/^[-•\d.、\s]+/, "").replace(/^["']|["']$/g, "").trim())
                .filter(Boolean);
              parsed = { names: lines.includes("没有人") ? [] : lines };
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
            runs.push({
              batch: testCase.batch,
              narration: testCase.narration,
              expect: testCase.expect,
              messages: testCase.messages,
              contractPass: true,
              wallMs: Math.round(performance.now() - started),
              promptTokens: response.usage?.prompt_tokens,
              completionTokens: response.usage?.completion_tokens,
              promptMs: response.timings?.prompt_ms != null ? Math.round(response.timings.prompt_ms) : null,
              predictedMs: response.timings?.predicted_ms != null ? Math.round(response.timings.predicted_ms) : null,
              finishReason: response.choices?.[0]?.finish_reason ?? null,
              text,
              parsed,
              error: null,
            });
          } catch (error) {
            runs.push({
              batch: testCase.batch,
              narration: testCase.narration,
              expect: testCase.expect,
              messages: testCase.messages,
              contractPass: true,
              wallMs: Math.round(performance.now() - started),
              error: `${error instanceof Error ? error.name : ""} ${error instanceof Error ? error.message : error}`,
            });
          }
        }
        return runs;
      },
      { cases, schema: NAMES_SCHEMA, plain },
    );

    const scored = runs.map((run) => {
      let namesMatch = false;
      let namesMatchPost = false;
      let correct = false;
      let postProcessed = null;
      let ruleCheck = null;
      if (run.parsed && Array.isArray(run.parsed.names)) {
        const { raw, stripped, unknownNames } = postProcessNames(run.parsed.names);
        postProcessed = { raw, stripped, unknownNames };
        namesMatch = JSON.stringify([...run.parsed.names].sort()) === JSON.stringify([...run.expect].sort());
        namesMatchPost = JSON.stringify([...stripped].sort()) === JSON.stringify([...run.expect].sort());
        ruleCheck = codeRuleCheck(run.narration, stripped);
        correct = namesMatchPost;
      }
      return {
        ...run,
        withinTarget: run.error ? undefined : run.wallMs <= TARGET_MS,
        namesMatch,
        namesMatchPost,
        postProcessed,
        ruleCheck,
        correct,
      };
    });
    const old = scored.filter((run) => run.batch === "old");
    const fresh = scored.filter((run) => run.batch === "new");
    const summarize = (runs) => ({
      withinTargetRate: `${runs.filter((run) => run.withinTarget).length}/${runs.length}`,
      correctRate: `${runs.filter((run) => run.correct).length}/${runs.length}`,
      minWallMs: Math.min(...runs.map((run) => run.wallMs)),
      maxWallMs: Math.max(...runs.map((run) => run.wallMs)),
      medianPromptMs: median(runs.map((run) => run.promptMs)),
      medianPredictedMs: median(runs.map((run) => run.predictedMs)),
    });
    const summary = { old: summarize(old), new: summarize(fresh) };
    log(`names/${namesArm}: ${JSON.stringify(summary)}`);
    const outPath = path.join(outDir, `task-trial6-${Date.now()}-names-${namesArm}.json`);
    await writeFile(
      outPath,
      JSON.stringify(
        { hostCpu: cpu, task: "names", arm: namesArm, runParams, runtime: loaded, targetMs: TARGET_MS, summary, runs: scored, exportedAt: new Date().toISOString() },
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
