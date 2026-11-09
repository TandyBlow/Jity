import { describe, expect, it } from 'vitest';
import { ControllerDriver, initialMemory, type WorldModelPort } from '../controller';
import type { ModelTask } from '../schedule';
import type { InitialTemplate, Json } from '../types';
import { LocalWorldTransport } from './transport';
import { SHORT_STATE } from '../runtime/b3-short-samples';

function template(): InitialTemplate {
  const initial = structuredClone(SHORT_STATE.initial) as InitialTemplate & { worldId?: string };
  delete initial.worldId;
  return initial;
}

/** Scripted model outputs for one normal action round. The point is to
 * exercise the real driver + local transport, not to judge narration. */
function scriptedModel(log: string[]): WorldModelPort {
  return {
    async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
      log.push(`${task}:${key}`);
      if (task === 'pointPlan') return [{ pointId: 'p1', kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, actorIds: ['person_a', 'person_c'] }];
      if (task === 'action') {
        const data = input as { actor: string; advance: { inputText: string | null }; workingState: { protagonistId: string } };
        return data.actor === data.workingState.protagonistId
          ? { kind: 'act', text: data.advance.inputText ?? '我走到门厅。' }
          : { kind: 'skip' };
      }
      if (task === 'targets') return { targets: [] };
      if (task === 'results') return { person_c: '周宁从走廊走进门厅。' };
      if (task === 'updates') {
        return [{ stage: 'position', changes: { person_c: { entityId: 'person_c', positionSet: { containerId: 'hall', slotId: null, relativeTo: null } } } }];
      }
      if (task === 'continuation') return { kind: 'handback', closedBy: 'model', cancelReason: null };
      if (task === 'narration') return key === 'p1' ? '门厅里安静下来。周宁在门厅停下脚步，回头看了一眼走廊。' : '走廊里很安静，盒子还盖着。';
      throw new Error(`unexpected task ${task}`);
    },
  };
}

describe('LocalWorldTransport', () => {
  it('plays one normal round through the real controller and commits state', async () => {
    const initial = template();
    const order = Object.keys(initial.characters).sort();
    const transport = await LocalWorldTransport.create(initial, { roll: () => 13 });
    const log: string[] = [];
    const memory = initialMemory('test_local', 'holder_local');
    memory.initialTemplate = initial;
    memory.playerInput = { text: '我走到门厅。', order };
    memory.allocPlan = {
      allocationKey: 'test_command',
      slots: [
        { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' },
        { slotKey: 'round', kind: 'round' }, { slotKey: 'point', kind: 'point' },
        ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const })),
      ],
    };
    const driver = new ControllerDriver({ transport, model: scriptedModel(log) }, memory);
    const status = await driver.run();
    expect(status.kind).not.toBe('error');
    expect(log.some((entry) => entry.startsWith('narration:'))).toBe(true);
    expect(log).toContain('narration:p1');
    const snapshot = transport.snapshot();
    expect(snapshot.version).toBe(1);
    expect(snapshot.state.characters.person_c.position.containerId).toBe('hall');
    expect(snapshot.narrations.p1.status).toBe('ready');
    expect(snapshot.round?.cursor).toBe(order.length);
    expect(snapshot.control.phase).toBe('complete');
  });
});

import { LocalGameSession } from './session';

describe('LocalGameSession', () => {
  it('starts a world, accepts a command and hands back', async () => {
    const initial = template();
    const log: string[] = [];
    let saved: unknown = null;
    const session = await LocalGameSession.create(initial, scriptedModel(log), { onPersist: (snap) => { saved = snap; } });
    const boot = await session.start();
    expect(boot.kind).not.toBe('error');
    expect(log.some((entry) => entry.startsWith('narration:'))).toBe(true);
    const status = await session.submit('我走到门厅。');
    expect(status.kind).not.toBe('error');
    expect(session.snapshot.transport.version).toBe(1);
    expect(session.snapshot.commands).toEqual(['我走到门厅。']);
    expect(saved).not.toBeNull();
    const state = await session.state();
    expect(state.characters.person_c.position.containerId).toBe('hall');
    const restored = await LocalGameSession.restore(session.snapshot, scriptedModel([]));
    const state2 = await restored.state();
    expect(state2.characters.person_c.position.containerId).toBe('hall');
  });
});

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

describe('free-day static world', () => {
  it('loads the full WorldState and settles a no-change point for the whole roster', async () => {
    const raw = JSON.parse(readFileSync(resolve('public/worlds/dragon-raja-free-day.world.json'), 'utf8'));
    const initial = structuredClone(raw.initial) as InitialTemplate & { worldId?: string };
    delete initial.worldId;
    const order = Object.keys(initial.characters).sort();
    const calls: string[] = [];
    const model: WorldModelPort = {
      async generate(task, key, input): Promise<Json> {
        calls.push(`${task}:${key}`);
        if (task === 'pointPlan') return [{ pointId: 'p_0', kind: 'normal',
          timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, actorIds: order }];
        if (task === 'action') {
          const data = input as { actor: string; workingState: { protagonistId: string }; advance: { inputText: string | null } };
          return data.actor === data.workingState.protagonistId ? { kind: 'act', text: data.advance.inputText ?? '我留在原处观察。' } : { kind: 'skip' };
        }
        if (task === 'targets') return { targets: [] };
        if (task === 'results') return {};
        if (task === 'updates') return [];
        if (task === 'continuation') return { kind: 'handback', closedBy: 'model', cancelReason: null };
        if (task === 'narration') return '西侧服务巷里，路明非停了一下。远处钟楼的影子还压在操场上。';
        throw new Error(`unexpected ${task}`);
      },
    };
    const session = await LocalGameSession.create(initial, model);
    const boot = await session.start();
    expect(boot.kind).not.toBe('error');
    const status = await session.submit('我留在原处观察。');
    expect(status.kind).not.toBe('error');
    const snap = session.snapshot.transport;
    expect(snap.initial.locations).toBeDefined();
    expect(snap.version).toBe(1);
    expect(snap.state.time.dateTime).toBe('2009-10-17T15:21:00');
    expect(snap.round?.cursor).toBe(order.length);
  }, 30000);
});
