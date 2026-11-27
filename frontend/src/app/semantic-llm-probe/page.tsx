'use client';

/** Dev probe: ask the in-page semantic GGUF the same four-state question the
 * existence heads answer, on the frozen holdout rows. Not part of the game. */
import { useEffect } from 'react';
import { WllamaInferenceEngine } from '@/lib/world-engine/runtime/wllama-engine';

const MODEL = '/models/Qwen3-0.6B-Q4_K_M.gguf';

export default function SemanticLlmProbePage() {
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result: Record<string, unknown> = { ok: false };
      const started = performance.now();
      try {
        const samples = await (await fetch('/micro/semantic-probe.json')).json() as Array<{ id: string; field: string; text: string; gold: boolean }>;
        const engine = new WllamaInferenceEngine({ modelUrl: MODEL, contextSize: 4096, cacheTypeK: 'q8_0', cacheTypeV: 'q8_0' });
        await engine.load();
        result.loadMs = Math.round(performance.now() - started);
        const rows: unknown[] = [];
        for (const sample of samples) {
          if (cancelled) break;
          const field = sample.field === 'env' ? '环境' : '信息';
          const prompt = `你是中文跑团游戏的状态判定器。判断下面这回合的结算事实是否为【${field}】字段提供了新的、可提交的状态内容。只输出 JSON，不要解释：{"label":"present"} 或 {"label":"absent"}。\n${sample.text}`;
          const raw = await engine.complete(prompt, { maxTokens: 24, temperature: 0 });
          rows.push({ id: sample.id, field: sample.field, gold: sample.gold, raw });
        }
        result.rows = rows;
        result.ok = !cancelled;
        await engine.dispose();
      } catch (error) {
        result.error = String(error instanceof Error ? error.stack ?? error.message : error);
      }
      (window as unknown as { __probeResult?: unknown }).__probeResult = result;
    })();
    return () => { cancelled = true; };
  }, []);
  return <main style={{ padding: 24, fontFamily: 'monospace' }}>semantic LLM probe running…</main>;
}
