import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { LocalGameSession } from './session';
import type { WorldModelPort } from '../controller';
import type { ModelTask } from '../schedule';
import type { InitialTemplate, Json } from '../types';

/** The page's recovery after a failed settlement that committed a point whose
 * narration never ran: cancel is refused while the head narration is pending,
 * so the page asks the session to finish the narration, then cancels again.
 * Without that, every later submit is refused as turn_in_progress (the 6042
 * 10-turn run, turns 5-10). */
function world(): InitialTemplate {
  const raw = JSON.parse(readFileSync(resolve('public/worlds/dragon-raja-free-day.world.json'), 'utf8'));
  const initial = structuredClone(raw.initial) as InitialTemplate & { worldId?: string };
  delete initial.worldId;
  return initial;
}

describe('failed-turn recovery', () => {
  it('closes the advance after the committed point is narrated', async () => {
    const initial = world();
    const order = Object.keys(initial.characters).sort();
    let narrationCalls = 0;
    let failNarration = 0;
    const model: WorldModelPort = {
      async generate(task: ModelTask): Promise<Json> {
        if (task === 'pointPlan') return [{ pointId: 'p_0', kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, actorIds: order }];
        if (task === 'action') return { kind: 'act', text: '我沿着巷子走。' };
        if (task === 'targets') return { targets: [] };
        if (task === 'results') return {};
        if (task === 'updates') return [];
        if (task === 'continuation') return { kind: 'handback', closedBy: 'model', cancelReason: null };
        if (task === 'narration') {
          narrationCalls += 1;
          if (failNarration > 0) { failNarration -= 1; throw new Error('narration_engine_failed'); }
          return '路明非沿着巷子走，墙上的规则牌看得很清楚。';
        }
        throw new Error(`unexpected ${task}`);
      },
    };
    const session = await LocalGameSession.create(initial, model);
    await session.start();
    const first = await session.submit('我沿着服务巷往里走。');
    expect(first.kind).not.toBe('error');

    failNarration = 4;
    // The failed turn may surface as a stop or as a rejection, depending on
    // where the engine error lands. Either way the advance must be recoverable.
    let failed = false;
    try {
      const result = await session.submit('我看看墙上的规则牌。');
      failed = result.kind === 'stop' || result.kind === 'error';
    } catch { failed = true; }
    failNarration = 0;
    expect(failed).toBe(true);
    expect(session.snapshot.transport.advance).not.toBeNull();

    // What the page does: cancel is refused while the head narration is
    // pending; finish the narration, then cancel.
    await session.cancel('turn_failed').catch(() => undefined);
    if (session.snapshot.transport.advance) await session.start();
    await session.cancel('turn_failed').catch(() => undefined);
    expect(session.snapshot.transport.advance).toBeNull();

    const third = await session.submit('我继续往里走。');
    expect(third.kind).not.toBe('error');
    expect(third).not.toEqual({ kind: 'stop', reason: 'turn_in_progress' });
    expect(narrationCalls).toBeGreaterThan(0);
  }, 60000);
});
