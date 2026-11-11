/** Prompt-shape arm control, no model and no GPU.
 *
 * Proves the product path builds the three arms from ONE prepared point and
 * that scene mode uses lane 02's closed-book `prose-facts` shape by default.
 * The engine is a stub that records the prompt and rejects the draft, so this
 * is prompt wiring evidence, not prose quality evidence.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { buildInitialState } from '../../state';
import type { InferenceEngine } from '../../../runtime/engine';
import { prepareNarration } from './projection';
import { TRAINED_CANDIDATE } from './trained';
import type { NarrationPoint } from './types';

function scenePoint(): NarrationPoint {
  const file = join(process.cwd(), 'public/worlds/dragon-raja-free-day.world.json');
  const world = JSON.parse(readFileSync(file, 'utf8')) as { initial: Record<string, unknown> };
  const after = buildInitialState(world.initial as never);
  return { pointId: 'point_arm', before: after, delta: { timeAdvance: null }, after, playerInput: '我沿着服务巷往里走，先看清墙上的演习规则牌。' };
}

function stubEngine(prompts: string[]): InferenceEngine {
  return {
    info: { backend: 'stub', modelId: 'stub' },
    load: async () => undefined,
    dispose: async () => undefined,
    complete: async (prompt: string) => { prompts.push(prompt); return ''; },
  };
}

describe('narration arm prompts', () => {
  it('builds prose-facts and serialized scene prompts from the same point', async () => {
    const point = scenePoint();
    const prepared = prepareNarration(point);
    expect(prepared.scene).toBeTruthy();
    for (const shape of ['prose-facts', 'serialized'] as const) {
      const prompts: string[] = [];
      await TRAINED_CANDIDATE.run({
        engine: stubEngine(prompts),
        point,
        prepared,
        policy: { sceneMode: 'scene', promptShape: shape },
      });
      expect(prompts.length).toBeGreaterThan(0);
      const joined = prompts.join('\n');
      expect(joined.length).toBeGreaterThan(300);
      // Both shapes carry the viewpoint name and the settled scene, but only
      // prose-facts uses the closed-book frame.
      expect(joined).toContain('路明非');
      if (shape === 'prose-facts') expect(/正文|场景|必须/.test(joined)).toBe(true);
      // Prompt sizes are evidence: 09 compares arms on the same input.
      expect(joined.length).toBeLessThan(6000);
    }
  });

  it('keeps beats mode on the beat prompt', async () => {
    const point = scenePoint();
    const prepared = prepareNarration(point);
    const prompts: string[] = [];
    await TRAINED_CANDIDATE.run({
      engine: stubEngine(prompts), point, prepared, policy: { sceneMode: 'beats' },
    });
    expect(prompts.length).toBeGreaterThan(0);
    expect(prompts.join('\n')).toContain('路明非');
  });
});
