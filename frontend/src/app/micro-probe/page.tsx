'use client';

/** Task-level browser probe for the int8 pair scorer. Not part of the game;
 * it exists so the scorer can be measured without a full multi-minute turn. */
import { useEffect } from 'react';
import { createBertTokenizer } from '@/lib/world-engine/local/micro/tokenizer';
import { createMicroRuntime, scorePair } from '@/lib/world-engine/local/micro/runtime';

const CASES = [
  { id: 'direct-1', action: '我把水壶递给诺诺。', candidates: ['诺诺', '芬格尔'], expect: ['诺诺'] },
  { id: 'direct-2', action: '我把干粮递给诺诺和芬格尔。', candidates: ['诺诺', '芬格尔', '秦越'], expect: ['诺诺', '芬格尔'] },
  { id: 'direct-3', action: '路明非朝秦越点了点头。', candidates: ['秦越', '诺诺'], expect: ['秦越'] },
  { id: 'pronoun-1', action: '我把水递给他。', candidates: ['诺诺', '芬格尔'], expect: [] },
  { id: 'pronoun-2', action: '我把水递给他们。', candidates: ['诺诺', '芬格尔'], expect: [] },
  { id: 'absent-1', action: '我把水递给阿豹。', candidates: ['诺诺', '芬格尔'], expect: [] },
  { id: 'empty-1', action: '我在庭院里坐下。', candidates: ['诺诺', '芬格尔'], expect: [] },
  { id: 'negation-1', action: '我没有把水递给诺诺。', candidates: ['诺诺', '芬格尔'], expect: [] },
  { id: 'negation-2', action: '我没有犹豫，把钥匙递给诺诺。', candidates: ['诺诺', '芬格尔'], expect: ['诺诺'] },
  { id: 'compound-1', action: '我把钥匙交给诺诺，又拿了回来。', candidates: ['诺诺', '芬格尔'], expect: ['诺诺'] },
];

export default function MicroProbePage() {
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result: Record<string, unknown> = { ok: false };
      try {
        const tokenizer = createBertTokenizer(await (await fetch('/micro/minirbt-vocab.txt')).text());
        const runtime = createMicroRuntime({ threads: 1 });
        const session = await runtime.load('/micro/pair-scorer-int8.onnx');
        const rows: unknown[] = [];
        let hits = 0;
        for (const item of CASES) {
          const scored: Array<{ name: string; score: number; ms: number }> = [];
          const normalized = item.action.replace(/我(?!们)/gu, '路明非');
          const pairText = `行动：${normalized}\n在场：${item.candidates.join('、')}`;
          for (const name of item.candidates) {
            const { ids } = tokenizer.encodePair(pairText, name);
            const started = performance.now();
            const score = await scorePair(session, ids);
            scored.push({ name, score, ms: Math.round((performance.now() - started) * 100) / 100 });
          }
          const pred = scored.filter((entry) => entry.score > 0).map((entry) => entry.name);
          const ok = pred.length === item.expect.length && pred.every((name) => item.expect.includes(name));
          hits += ok ? 1 : 0;
          rows.push({ ...item, scored, pred, ok });
        }
        result.ok = true;
        result.rows = rows;
        result.hits = `${hits}/${CASES.length}`;
        result.loadMs = Math.round(runtime.stats().loadMs);
      } catch (error) {
        result.error = String(error instanceof Error ? error.stack ?? error.message : error);
      }
      if (!cancelled) (window as unknown as { __probeResult?: unknown }).__probeResult = result;
    })();
    return () => { cancelled = true; };
  }, []);
  return <main style={{ padding: 24, fontFamily: 'monospace' }}>micro probe running…</main>;
}
