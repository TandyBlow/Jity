// One-off narration sample capture: same prompt shape as the benchmark's
// 2048-token tier, full text saved and printed for quality review.
// Usage: node scripts/narration-sample.mjs [threads]

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const frontendRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const baseUrl = process.env.BASE_URL ?? "http://localhost:3100";
const threads = process.argv[2] ?? "4";

const MODELS = process.env.MODELS ? JSON.parse(process.env.MODELS) : [
  { tag: "qwen3-0.6b", url: "/models/Qwen3-0.6B-Q4_K_M.gguf", qwen3: true },
  { tag: "qwen2.5-0.5b", url: "/models/qwen2.5-0.5b-instruct-q4_k_m.gguf", qwen3: false },
];

const SYSTEM = "你是桌面 RPG 的中文 GM。根据当前状态、记忆和玩家行动，写出下一段剧情正文：第二人称沉浸叙事，15 到 20 句，包含 NPC 反应和新的可行动局面。不要使用破折号，最多出现一次比喻。只输出剧情正文，不要任何说明、标题或选项列表。";

const SECTIONS = [
  "## 战役上下文\n当前战役：黑月之潮。当前章节：龙族Ⅲ — 高天原的阴影。章节目标：查明蛇岐八家的真正目的。\n锚点进度：2/9 已揭示。人物关系变化：绘梨衣 信任上升(+2)，源稚生 中性(+0)。",
  "## 当前状态\n当前地点：卡塞尔学院图书馆。血统稳定：72/100。体力：88/100。回合：23。\n玩家状态：调查中 · danger_level=medium · 当前目标：找到那本被撕掉登记页的值班记录。",
  "## 长期叙事记忆\n- 图书馆高窗外的云影缓缓掠过石质书架，尘埃在斜照的光柱里浮动。（记忆0）\n- 走廊尽头的挂钟停在三点半，齿轮上覆着一层没有人擦拭过的灰。（记忆1）\n- 他用指尖抚过摊开的地图，纸页边缘已经被人反复翻阅得起了毛。（记忆2）\n- 远处的操场传来隐约的哨声，随即又被风声揉碎在楼宇之间。（记忆3）\n- 她把校徽翻转过来，背面刻着的编号在灯光下几乎看不清楚。（记忆4）\n- 地下室的水管发出规律的滴答声，像某种耐心的倒计时。（记忆5）\n- 名单上的第三个名字被红笔划掉了，划痕深得几乎穿透纸背。（记忆6）\n- 楼梯间的灯又熄了一盏，黑暗从顶层开始一段一段地漫下来。（记忆7）\n- 信封里只有半张车票，撕口整齐得像是有人用尺子比着裁开的。（记忆8）\n- 教室后排的椅子上放着一本没人认领的笔记本，扉页写着日期。（记忆9）",
  "## 生成规则（节选）\n- 必须回应玩家刚才的行动，描述直接后果、NPC 反应和新的可行动局面。\n- 普通失败也应推动故事继续，而不是直接结束。\n- 状态变化要能从剧情中解释。\n- 不要写与已知信息无关的空洞细节描写。",
  "## 最近对话历史\n[玩家]: 我要查阅上周的值班登记簿。\n[主持人]: 管理员说登记簿就在值班室，但当你翻开时，最后一页已经被撕掉了。\n[玩家]: 询问管理员谁最后接触过登记簿。\n[主持人]: 管理员想了想，说深夜只有巡夜的学生来过。",
  "## 玩家行动\n我去调查巡夜学生的名单，并核对当晚的出入记录。",
];

const USER = SECTIONS.join("\n\n");

const log = (...parts) => console.log(new Date().toISOString().slice(11, 19), ...parts);

async function main() {
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
  log(`prompt chars: ${[...USER].length}`);

  const outDir = path.join(frontendRoot, "..", "artifacts", "benchmark", "narration-samples");
  await mkdir(outDir, { recursive: true });

  for (const model of MODELS) {
    log(`=== ${model.tag} ===`);
    await page.evaluate(async ({ modelUrl, threads, qwen3, seed }) => {
      window.__seed = seed;
      const { Wllama } = await import("/wllama/index.min.js");
      const instance = new Wllama(
        { default: "/wasm/wllama.wasm" },
        { logger: { ...console, debug: () => undefined } },
      );
      await instance.loadModelFromUrl(modelUrl, {
        useCache: false,
        n_ctx: 4096,
        n_batch: 512,
        n_ubatch: 128,
        n_gpu_layers: 0,
        warmup: false,
        n_threads: Number(threads),
      });
      window.__sampleWllama = instance;
      window.__qwen3 = qwen3;
    }, { modelUrl: `${baseUrl}${model.url}`, threads, qwen3: model.qwen3, seed: Number(process.env.SEED ?? 20261008) });
    log("model loaded");

    const result = await page.evaluate(
      async ({ systemText, userText }) => {
        const started = performance.now();
        const response = await window.__sampleWllama.createChatCompletion({
          messages: [
            { role: "system", content: systemText },
            { role: "user", content: userText },
          ],
          max_tokens: 512,
          temperature: 0.7,
          top_p: 0.9,
          seed: window.__seed,
          cache_prompt: false,
          ...(window.__qwen3
            ? { chat_template_kwargs: { enable_thinking: false } }
            : {}),
        });
        return {
          wallMs: Math.round(performance.now() - started),
          text: response.choices?.[0]?.message?.content ?? "",
          finishReason: response.choices?.[0]?.finish_reason ?? null,
          promptTokens: response.usage?.prompt_tokens,
          completionTokens: response.usage?.completion_tokens,
        };
      },
      { systemText: SYSTEM, userText: USER },
    );

    const seconds = (result.wallMs / 1000).toFixed(1);
    log(`generated: ${result.completionTokens} tok in ${seconds}s (${(result.completionTokens / (result.wallMs / 1000)).toFixed(1)} tok/s), finish=${result.finishReason}, prompt=${result.promptTokens} tok`);
    console.log("----- 叙事全文 -----");
    console.log(result.text);
    console.log("--------------------");

    await writeFile(
      path.join(outDir, `${model.tag}-2048in.txt`),
      result.text,
    );
    await writeFile(
      path.join(outDir, `${model.tag}-2048in.meta.json`),
      JSON.stringify({ ...result, model: model.tag, threads: Number(threads), promptChars: [...USER].length }, null, 2),
    );

    await page.evaluate(async () => {
      await window.__sampleWllama.exit();
      delete window.__sampleWllama;
    });
  }

  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
