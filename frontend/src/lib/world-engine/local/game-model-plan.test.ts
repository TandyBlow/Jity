import { describe, expect, it } from 'vitest';
import type { InferenceEngine } from '../runtime/engine';
import { LocalGameModel } from './game-model';

/** No call is expected for a point plan; the model only segments the round. */
const engine: InferenceEngine = {
  info: { backend: 'scripted', modelId: 'plan-only' },
  async load() { /* nothing */ },
  async complete() { throw new Error('the point plan must not call the model'); },
  async dispose() { /* nothing */ },
};

type Point = { pointId: string; kind: string; timeAdvance: { boundary: string; duration: { amount: number; unit: string } }; actorIds: string[] };

async function plan(model: LocalGameModel, round: { roundId: string; trigger: 'player' | 'automatic'; order: string[] }): Promise<Point[]> {
  return await model.generate('pointPlan', 'round', { round } as never) as unknown as Point[];
}

describe('a player round is split so the player point can commit first', () => {
  it('puts the player alone in the first point and the roster in a zero-duration instant point', async () => {
    const model = new LocalGameModel(engine, { protagonistId: 'lu' });
    const points = await plan(model, { roundId: 'round_3', trigger: 'player', order: ['lu', 'nono', 'lin'] });
    expect(points).toHaveLength(2);
    expect(points[0]).toMatchObject({ pointId: 'point_round_3_1', kind: 'normal', actorIds: ['lu'] });
    expect(points[0]!.timeAdvance).toEqual({ boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } });
    expect(points[1]).toMatchObject({ pointId: 'point_round_3_2', kind: 'instant', actorIds: ['nono', 'lin'] });
    // An instant point must carry a zero duration; the round's time already
    // advanced with the first point.
    expect(points[1]!.timeAdvance).toEqual({ boundary: 'instant', duration: { amount: 0, unit: 'second' } });
  });

  it('keeps one point for an automatic round, a lone roster or an unknown player', async () => {
    const model = new LocalGameModel(engine, { protagonistId: 'lu' });
    const automatic = await plan(model, { roundId: 'round_4', trigger: 'automatic', order: ['nono', 'lin'] });
    expect(automatic).toHaveLength(1);
    expect(automatic[0]!.actorIds).toEqual(['nono', 'lin']);

    const lone = await plan(model, { roundId: 'round_5', trigger: 'player', order: ['lu'] });
    expect(lone).toHaveLength(1);

    const unknown = await plan(new LocalGameModel(engine), { roundId: 'round_6', trigger: 'player', order: ['lu', 'nono'] });
    expect(unknown).toHaveLength(1);
    expect(unknown[0]!.actorIds).toEqual(['lu', 'nono']);
  });

  it('learns the player id from a working state when the options omit it', async () => {
    const model = new LocalGameModel(engine);
    const state = { protagonistId: 'lu', characters: {}, items: {}, locations: {}, time: {} } as never;
    // Any action input carries the working state, even for a skip.
    const handlerPlan = await plan(model, { roundId: 'round_7', trigger: 'player', order: ['lu', 'nono'] });
    expect(handlerPlan).toHaveLength(1);
    (model as unknown as { noteProtagonist: (value: unknown) => void }).noteProtagonist(state);
    const after = await plan(model, { roundId: 'round_8', trigger: 'player', order: ['lu', 'nono'] });
    expect(after).toHaveLength(2);
    expect(after[0]!.actorIds).toEqual(['lu']);
  });
});

// --- the split goes through the real controller ---------------------------

import { ControllerDriver, initialMemory, type WorldModelPort } from '../controller';
import type { ModelTask } from '../schedule';
import type { InitialTemplate, Json } from '../types';
import { SHORT_STATE } from '../runtime/b3-short-samples';
import { LocalWorldTransport } from './transport';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

describe('the split plan commits the player point before the rest settles', () => {
  it('narrates the first point while the instant second point is still settling', async () => {
    const initial = structuredClone(SHORT_STATE.initial) as InitialTemplate & { worldId?: string };
    delete initial.worldId;
    const order = Object.keys(initial.characters).sort();
    const protagonist = order[0]!;
    const other = order[1]!;
    // The real product model owns the plan; everything else is scripted.
    const planner = new LocalGameModel(engine, { protagonistId: protagonist });
    const points = await plan(planner, { roundId: 'round_1', trigger: 'player', order });

    const p1NarrationStarted = deferred<void>();
    const releaseP1 = deferred<string>();
    const p2Committed = deferred<void>();
    const log: string[] = [];
    const committed: string[] = [];
    let p1NarrationResolved = false;

    const model: WorldModelPort = {
      async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
        log.push(`${task}:${key}`);
        if (task === 'pointPlan') return points as unknown as Json;
        if (task === 'action') return { kind: 'act', text: key === protagonist ? '我先走进门厅。' : '随后走到窗边。' };
        if (task === 'targets') return { targets: [] };
        if (task === 'results') return { [key]: (input as { pointId?: string }).pointId === points[0]!.pointId ? '第一点完成。' : '第二点完成。' };
        if (task === 'updates') return [];
        if (task === 'continuation') return { kind: 'handback', closedBy: 'model', cancelReason: null };
        if (task === 'narration') {
          if (key === 'root') return '根点叙事。';
          if (key === points[0]!.pointId) {
            p1NarrationStarted.resolve();
            const text = await releaseP1.promise;
            p1NarrationResolved = true;
            return text;
          }
          return '窗边的光落在桌面上。';
        }
        throw new Error(`unexpected task ${task}`);
      },
    };

    const transport = await LocalWorldTransport.create(initial, { roll: () => 13 });
    const memory = initialMemory('split', 'holder_split');
    memory.initialTemplate = initial;
    memory.playerInput = { text: '我走进门厅。', order };
    memory.allocPlan = {
      allocationKey: 'split_command',
      slots: [
        { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' },
        { slotKey: 'round', kind: 'round' }, { slotKey: 'point', kind: 'point' },
        ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const })),
      ],
    };
    const driver = new ControllerDriver({
      transport, model,
      onCommit: (event) => {
        if (event.phase !== 'committed') return;
        const request = event.request as { pointId?: string };
        if (request.pointId) committed.push(request.pointId);
        if (request.pointId === points[1]!.pointId) p2Committed.resolve();
      },
    }, memory, undefined, { narrationOverlap: true });

    const run = driver.run();
    await p1NarrationStarted.promise;
    // The player point committed and is being written; the instant second
    // point must still reach commit without waiting for that prose.
    await p2Committed.promise;
    expect(p1NarrationResolved).toBe(false);
    expect(committed).toEqual([points[0]!.pointId, points[1]!.pointId]);
    releaseP1.resolve('门厅先亮了一下，随后才安静下来。');
    const status = await run;
    expect(status.kind).not.toBe('error');
    const record = transport.snapshot();
    expect(record.narrations[points[0]!.pointId]).toMatchObject({ status: 'ready', text: '门厅先亮了一下，随后才安静下来。' });
    expect(record.narrations[points[1]!.pointId]).toMatchObject({ status: 'ready' });
    expect(record.advance).toBeNull();
  }, 30000);
});
