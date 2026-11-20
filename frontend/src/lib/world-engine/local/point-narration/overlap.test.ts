import { describe, expect, it } from 'vitest';
import { ControllerDriver, initialMemory, type WorldModelPort } from '../../controller';
import type { ModelTask } from '../../schedule';
import type { InitialTemplate, Json } from '../../types';
import { SHORT_STATE } from '../../runtime/b3-short-samples';
import { LocalWorldTransport } from '../transport';

/** The shortest real template with two characters. The test holds p1's
 * narration answer open, lets p2 settle through the real transport/controller,
 * then releases the old text. */
function template(): InitialTemplate {
  const initial = structuredClone(SHORT_STATE.initial) as InitialTemplate & { worldId?: string };
  delete initial.worldId;
  return initial;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

describe('per-point narration overlaps the next settlement', () => {
  it('p2 commits while p1 narration is held, then p1 lands on its own point', async () => {
    const initial = template();
    const order = Object.keys(initial.characters).sort();
    const [firstActor, secondActor] = order;
    const p1NarrationStarted = deferred<void>();
    const releaseP1 = deferred<string>();
    const p2Committed = deferred<void>();
    let p1NarrationResolved = false;
    const log: string[] = [];
    const committed: string[] = [];

    const model: WorldModelPort = {
      async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
        log.push(`${task}:${key}`);
        if (task === 'pointPlan') {
          return [
            { pointId: 'p1', kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, actorIds: [firstActor] },
            { pointId: 'p2', kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, actorIds: [secondActor] },
          ];
        }
        if (task === 'action') return { kind: 'act', text: `我${key === firstActor ? '先走进门厅' : '随后走到窗边'}。` };
        if (task === 'targets') return { targets: [] };
        if (task === 'results') {
          const pointId = (input as { pointId?: string }).pointId ?? '';
          return { [key]: `${pointId === 'p1' ? '第一点' : '第二点'}完成了自己的行动。` };
        }
        if (task === 'updates') return [];
        if (task === 'continuation') return { kind: 'handback', closedBy: 'model', cancelReason: null };
        if (task === 'narration') {
          if (key === 'root') return '根点叙事。';
          if (key === 'p1') {
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
    const memory = initialMemory('overlap', 'holder_overlap');
    memory.initialTemplate = initial;
    memory.playerInput = { text: '我走进门厅。', order };
    memory.allocPlan = {
      allocationKey: 'overlap_command',
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
        if (request.pointId === 'p2') p2Committed.resolve();
      },
    }, memory, undefined, { narrationOverlap: true });

    const run = driver.run();
    await p1NarrationStarted.promise;
    // p1 has committed, its narration is awaiting release; p2's settlement
    // must still reach commit without waiting for that text.
    await p2Committed.promise;
    expect(p1NarrationResolved).toBe(false);
    expect(committed).toEqual(['p1', 'p2']);
    const interrupted = transport.snapshot();
    const interruptedMemory = driver.getMemory();
    releaseP1.resolve('门厅先亮了一下，随后才安静下来。');
    const status = await run;
    expect(status.kind).not.toBe('error');

    const record = transport.snapshot();
    expect(record.version).toBe(2);
    expect(record.narrations.p1).toMatchObject({ status: 'ready', text: '门厅先亮了一下，随后才安静下来。' });
    expect(record.narrations.p2).toMatchObject({ status: 'ready', text: '窗边的光落在桌面上。' });
    // The narration model saw only its own point's frozen snapshot; the queue
    // never re-reads the later head to fill p1.
    expect(log).toContain('narration:p1');
    expect(log).toContain('narration:p2');
    expect(record.narrations.p1.text).not.toContain('窗边');

    // Refresh recovery: p1/p2 are committed but their narrations are pending
    // in the saved record. A new driver must finish those same points without
    // re-settling either one or taking a new action.
    const restoredTransport = await LocalWorldTransport.restore(interrupted, { roll: () => 13 });
    const restoredContext = await restoredTransport.execute('get_context', {}, { worldId: restoredTransport.worldId });
    const restoredLog: string[] = [];
    const restoredModel: WorldModelPort = {
      async generate(task: ModelTask, key: string): Promise<Json> {
        restoredLog.push(`${task}:${key}`);
        if (task === 'narration') return key === 'p1' ? '恢复后的第一点。' : '恢复后的第二点。';
        if (task === 'continuation') return { kind: 'handback', closedBy: 'model', cancelReason: null };
        throw new Error(`recovery must not settle: ${task}:${key}`);
      },
    };
    const restoredMemory = { ...structuredClone(interruptedMemory), requestId: 'restored_overlap_0' };
    const restored = new ControllerDriver({ transport: restoredTransport, model: restoredModel },
      restoredMemory,
      { world: restoredContext.world, control: restoredContext.control, work: restoredContext.work, activeInput: restoredContext.activeInput },
      { narrationOverlap: true });
    await restored.run();
    const restoredRecord = restoredTransport.snapshot();
    expect(restoredRecord.version).toBe(2);
    expect(restoredRecord.narrations.p1).toMatchObject({ status: 'ready', text: '恢复后的第一点。' });
    expect(restoredRecord.narrations.p2).toMatchObject({ status: 'ready', text: '恢复后的第二点。' });
    expect(restoredLog.filter((entry) => entry.startsWith('action:'))).toEqual([]);
  }, 30000);
});
