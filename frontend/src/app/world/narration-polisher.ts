/** 页面与整链验收共用的模型叙事润色器：懒加载 wllama 引擎（按模型路径缓存），
 * prompt 用聚焦叙事视图（buildTaskPrompt focused——只含事实与允许短语，预填量
 * 极小）生成候选；输出交回 rule-session 的 checkFactNarration 把关，失败由其
 * 重生成/回退模板。（自 page.tsx 原样提取，2026-10-28 整链验收批次；页面行为
 * 保持不变。） */
import type { RuleNarrationPolisher } from '../../lib/world-engine/runtime/rule-session';
import type { WllamaInferenceEngine } from '../../lib/world-engine/runtime/wllama-engine';

const engines = new Map<string, Promise<WllamaInferenceEngine>>();
const polishEngines = new Map<string, Promise<RuleNarrationPolisher>>();

async function engineFor(modelUrl: string): Promise<WllamaInferenceEngine> {
  let engine = engines.get(modelUrl);
  if (!engine) {
    engine = (async () => {
      const { WllamaInferenceEngine } = await import('../../lib/world-engine/runtime/wllama-engine');
      return new WllamaInferenceEngine({ modelUrl, contextSize: 2048 });
    })();
    engine.catch(() => engines.delete(modelUrl)); // 失败的加载可重试
    engines.set(modelUrl, engine);
  }
  return engine;
}

/** 预热：触发模型下载与 wasm 初始化，返回加载耗时与线程拓扑（验收脚本用；
 * 页面保持懒加载路径不变）。 */
export async function warmNarrationEngine(modelUrl: string): Promise<{ loadMs: number; topology: unknown }> {
  const engine = await engineFor(modelUrl);
  const started = performance.now();
  await engine.load(); // 幂等
  return { loadMs: Math.round(performance.now() - started), topology: engine.diagnostics };
}

export function narrationPolisher(modelUrl: string,
  options: { onCompletion?: (evidence: unknown) => void } = {}): Promise<RuleNarrationPolisher> {
  const key = `${modelUrl}|${options.onCompletion ? 'evidence' : 'plain'}`;
  let engine = polishEngines.get(key);
  if (!engine) {
    engine = (async () => {
      const { buildTaskPrompt } = await import('../../lib/world-engine/runtime/prompts');
      const wllama = await engineFor(modelUrl);
      return async (input, _packet, focused, attempt) => {
        // 共享 prompts.ts / focused-input.ts 保持确定性（B3 eval 回放依赖）；
        // 页面实验在提交给引擎前收窄输入：每条事实只展示首个短语（判分器
        // 仍接受任意已登记变体）。实测 0.5B/0.6B 模型在展示两个变体时必然
        // 全部输出（duplicate_fact），逐字拼接是这个量级模型可靠完成的任务
        // 形态；顺序与变体选择是它在严格判分门下保留的自由度，更丰富的
        // 散文表达属于方案 §8.2 的状态对齐评测层（后续批次）。
        const view = focused as { facts?: { id: string; allowedPhrases: string[] }[] };
        const simplified = {
          ...view,
          facts: (view.facts ?? []).map((fact) => ({ id: fact.id, phrase: fact.allowedPhrases[0] })),
        };
        let prompt = buildTaskPrompt('narration', input.pointId, simplified, { inputMode: 'focused' });
        // 编号清单：两个模型的实测失败模式都是「漏掉部分事实」（missing_fact），
        // 编号逐条复制是把任务压到机械形态的最后一步。
        const phrases = (view.facts ?? []).map((fact) => fact.allowedPhrases[0]);
        prompt += `\n[硬性要求] 依次输出下面全部 ${phrases.length} 条短语：逐字复制、每条后面加一个句号（。）、一条一行，从 1 号到 ${phrases.length} 号一条都不能漏，不要输出编号，不要添加任何其他字词：\n${phrases.map((phrase, index) => `${index + 1}. ${phrase}`).join('\n')}`;
        // attempt 2 = 同 prompt 纯温度重采样（0.7）：注入更正文本会被小模型
        // 逐字复读（实测），stop 打空反而浪费掉这次重生机会；
        // attempt.previous 仍随类型传递，供更强模型启用反馈注入。
        await wllama.load(); // 幂等：首次使用触发下载与 wasm 初始化
        const raw = await wllama.complete(prompt, {
          maxTokens: 96,
          temperature: attempt.index === 1 ? 0 : 0.7,
          cachePrompt: true,
          timeoutMs: 110_000,
          stop: ['\n[', '\n正文:', '\n输出:', '[硬性要求]'],
          onCompletion: options.onCompletion,
        });
        const text = raw.trim();
        if (!text) throw new Error('润色输出为空');
        console.info(`[narration-model] attempt ${attempt.index} raw=${JSON.stringify(text)}`);
        return text;
      };
    })();
    engine.catch(() => polishEngines.delete(key)); // 失败的加载可重试
    polishEngines.set(key, engine);
  }
  return engine;
}
