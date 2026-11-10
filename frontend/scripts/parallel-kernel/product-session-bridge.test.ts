/** Continuity checks against the real recovery session (06's tree, read-only).
 * This is an explicit local bridge test, not part of the product build: it
 * imports the sibling 06 worktree and is skipped by the default vitest include.
 * Run it with `npx vitest run scripts/parallel-kernel/product-session-bridge.test.ts`.
 * @ts-nocheck keeps a normal product checkout type-checkable without 06.
 * The session is constructed and driven exactly as the product does; every
 * checkpoint is replayed by the read-only invariant verifier before the next
 * turn. This file does not modify 06's tree or page. */
import { describe, expect, it } from 'vitest';
import type { WorldModelPort } from '../../../../06-recovery/frontend/src/lib/world-engine/controller';
import type { ModelTask } from '../../../../06-recovery/frontend/src/lib/world-engine/schedule';
import type { InitialTemplate, Json } from '../../../../06-recovery/frontend/src/lib/world-engine/types';
import { SHORT_STATE } from '../../../../06-recovery/frontend/src/lib/world-engine/runtime/b3-short-samples';
import { LocalGameSession } from '../../../../06-recovery/frontend/src/lib/world-engine/local/session';
import {
  createLocalProgressStore, MemoryProgressBackend,
} from '../../../../06-recovery/frontend/src/lib/world-engine/local/persistence';
import { verifyWorldRecord } from '../../src/lib/world-engine/local/state-invariants/index';

function template(): InitialTemplate {
  const initial = structuredClone(SHORT_STATE.initial) as InitialTemplate & { worldId?: string };
  delete initial.worldId;
  return initial;
}

interface Hooks {
  crashOn?: (task: ModelTask, key: string) => Error | null;
  blockOn?: (task: ModelTask, key: string) => Promise<void> | null;
}

function scriptedModel(log: string[], hooks: Hooks = {}): WorldModelPort {
  return {
    async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
      log.push(`${task}:${key}`);
      const crash = hooks.crashOn?.(task, key);
      if (crash) throw crash;
      const blocked = hooks.blockOn?.(task, key);
      if (blocked) await blocked;
      const data = input as {
        actor?: string;
        workingState?: { protagonistId: string };
        advance?: { inputText: string | null };
      };
      switch (task) {
        case 'pointPlan': {
          const round = (input as { round?: { roundId?: string; order?: string[] } }).round;
          return [{
            pointId: `point_${round?.roundId ?? 'round'}_1`,
            kind: 'normal',
            timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
            actorIds: round?.order ?? ['person_a', 'person_c'],
          }];
        }
        case 'action':
          return data.actor === data.workingState?.protagonistId
            ? { kind: 'act', text: data.advance?.inputText ?? '我走到门厅。' }
            : { kind: 'skip' };
        case 'targets':
          return key === 'person_c' ? { targets: [{ targetId: 'person_a' }] } : { targets: [] };
        case 'reaction':
          return '林川侧过身，让开半步。';
        case 'results':
          return { person_c: '周宁掀开盒盖。', person_a: '林川侧过身。' };
        case 'updates':
          return [{ stage: 'position', changes: {} }];
        case 'continuation':
          return { kind: 'handback', closedBy: 'model', cancelReason: null };
        case 'narration':
          return '门厅里安静下来，盒盖开着。';
        default:
          throw new Error(`unexpected task ${task}`);
      }
    },
  };
}

async function waitFor(predicate: () => boolean, timeoutMs = 3000): Promise<void> {
  const started = Date.now();
  while (!predicate()) {
    if (Date.now() - started > timeoutMs) throw new Error('wait_for_timeout');
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

describe('real recovery session continuity', () => {
  it('replays every one of ten consecutive turns without a digest or chain divergence', async () => {
    const session = await LocalGameSession.create(template(), scriptedModel([]), { roll: () => 13 });
    await session.start();
    let previousHead = (await verifyWorldRecord(session.snapshot.transport)).headPointId;
    for (let turn = 1; turn <= 10; turn += 1) {
      const status = await session.submit(`第 ${turn} 回合：我把盒盖打开一点。`);
      expect(status.kind, `turn ${turn} status`).not.toBe('error');
      const report = await verifyWorldRecord(session.snapshot.transport);
      expect(report.ok, `turn ${turn}: ${JSON.stringify(report.errors)}`).toBe(true);
      expect(report.version).toBe(turn);
      expect(report.headPointId).not.toBe(previousHead);
      previousHead = report.headPointId;
    }
    expect(session.commandsPlayed).toHaveLength(10);
    expect(session.snapshot.transport.advance).toBeNull();
    expect(session.snapshot.transport.round?.conclusion).toEqual({ kind: 'handback', closedBy: 'model', cancelReason: null });
  }, 30_000);

  it('replays twenty consecutive turns without a digest or chain divergence', async () => {
    const session = await LocalGameSession.create(template(), scriptedModel([]), { roll: () => 13 });
    await session.start();
    for (let turn = 1; turn <= 20; turn += 1) {
      const status = await session.submit(`第 ${turn} 回合：我把盒盖打开一点。`);
      expect(status.kind, `turn ${turn} status`).not.toBe('error');
      const report = await verifyWorldRecord(session.snapshot.transport);
      expect(report.ok, `turn ${turn}: ${JSON.stringify(report.errors)}`).toBe(true);
      expect(report.version).toBe(turn);
    }
    expect(session.commandsPlayed).toHaveLength(20);
    expect(session.snapshot.transport.advance).toBeNull();
  }, 60_000);

  it('checkpoints mid-settlement, restores it, and finishes without rerolling or duplicating the point', async () => {
    const backend = new MemoryProgressBackend();
    const clock = { value: 1_000_000 };
    const store = createLocalProgressStore(backend, { now: () => clock.value });
    const log: string[] = [];
    const crashing = scriptedModel(log, { crashOn: (task) => task === 'reaction' ? new Error('simulated_refresh') : null });
    const session = await LocalGameSession.create(template(), crashing, {
      storage: store, sessionId: 'tab_a', leaseHeartbeat: false, leaseTtlMs: 1_000, roll: () => 13,
    });
    await session.start();
    await expect(session.submit('我打开盒盖。')).rejects.toThrow('simulated_refresh');

    const saved = await store.load(session.worldId);
    expect(saved).not.toBeNull();
    const savedReport = await verifyWorldRecord(saved!.snapshot.transport);
    expect(savedReport.ok, JSON.stringify(savedReport.errors)).toBe(true);
    expect(savedReport.version).toBe(0);
    const rollKeys = Object.keys(saved!.snapshot.transport.rolls);
    const rollBefore = saved!.snapshot.transport.rolls[rollKeys[0]];

    clock.value += 5_000;
    const restored = await LocalGameSession.restoreFromStore(store, session.worldId, scriptedModel([]), {
      sessionId: 'tab_b', leaseHeartbeat: false, leaseTtlMs: 1_000, roll: () => 13,
    });
    expect(restored).not.toBeNull();
    expect(await restored!.submit('另一次行动')).toEqual({ kind: 'stop', reason: 'turn_in_progress' });
    expect(restored!.commandsPlayed).toEqual(['我打开盒盖。']);
    const status = await restored!.start();
    expect(status.kind).not.toBe('error');
    const record = restored!.snapshot.transport;
    expect(record.version).toBe(1);
    expect(Object.keys(record.rolls)).toEqual(rollKeys);
    expect(record.rolls[rollKeys[0]].rollId).toBe(rollBefore.rollId);
    expect(record.rolls[rollKeys[0]].result).toBe(rollBefore.result);
    const report = await verifyWorldRecord(record);
    expect(report.ok, JSON.stringify(report.errors)).toBe(true);
  });

  it('shows the recovery gap: session restore accepts a tampered state that the invariant gate rejects', async () => {
    const session = await LocalGameSession.create(template(), scriptedModel([]), { roll: () => 13 });
    await session.start();
    expect((await session.submit('我打开盒盖。')).kind).not.toBe('error');
    const tampered = structuredClone(session.snapshot);
    tampered.transport.state.characters.person_c.position = { containerId: 'hall', slotId: null, relativeTo: null };
    const report = await verifyWorldRecord(tampered.transport);
    expect(report.ok).toBe(false);
    expect(report.errors.map((item) => item.code)).toContain('state_mismatch');

    const restored = await LocalGameSession.restore(tampered, scriptedModel([]), { roll: () => 13 });
    // 06's current restore path trusts the record; this is the counterexample
    // the guarded restore must close before the page wires recovery.
    expect(restored.snapshot.transport.state.characters.person_c.position.containerId).toBe('hall');
  });

  it('refuses a second submit while the first point is in flight and commits exactly one point', async () => {
    const log: string[] = [];
    let release!: () => void;
    const blocked = new Promise<void>((resolve) => { release = resolve; });
    const session = await LocalGameSession.create(template(), scriptedModel(log, {
      blockOn: (task, key) => task === 'action' && key === 'person_c' ? blocked : null,
    }), { roll: () => 13 });
    await session.start();
    const first = session.submit('我打开盒盖。');
    await waitFor(() => log.includes('action:person_c'));
    expect(await session.submit('我打开盒盖。')).toEqual({ kind: 'stop', reason: 'turn_in_progress' });
    expect(session.commandsPlayed).toEqual(['我打开盒盖。']);
    release();
    expect((await first).kind).not.toBe('error');
    const report = await verifyWorldRecord(session.snapshot.transport);
    expect(report.ok, JSON.stringify(report.errors)).toBe(true);
    expect(report.version).toBe(1);
  });

  it('cancels mid-turn, restores the abandoned round, and starts the next turn from the same head', async () => {
    const backend = new MemoryProgressBackend();
    const clock = { value: 2_000_000 };
    const store = createLocalProgressStore(backend, { now: () => clock.value });
    let release!: () => void;
    const blocked = new Promise<void>((resolve) => { release = resolve; });
    const log: string[] = [];
    const session = await LocalGameSession.create(template(), scriptedModel(log, {
      blockOn: (task, key) => task === 'action' && key === 'person_c' ? blocked : null,
    }), { storage: store, sessionId: 'tab_a', leaseHeartbeat: false, leaseTtlMs: 1_000, roll: () => 13 });
    await session.start();
    const turn = session.submit('我打开盒盖。');
    await waitFor(() => log.includes('action:person_c'));
    const cancelled = session.cancel('player_abort');
    release();
    expect((await cancelled).kind).not.toBe('error');
    await turn;
    expect((await verifyWorldRecord(session.snapshot.transport)).ok).toBe(true);

    clock.value += 5_000;
    const restored = await LocalGameSession.restoreFromStore(store, session.worldId, scriptedModel([]), {
      sessionId: 'tab_b', leaseHeartbeat: false, leaseTtlMs: 1_000, roll: () => 13,
    });
    expect(restored).not.toBeNull();
    expect(await restored!.start()).toEqual(expect.objectContaining({ kind: expect.any(String) }));
    expect((await verifyWorldRecord(restored!.snapshot.transport)).ok).toBe(true);
    const next = await restored!.submit('我退回走廊。');
    expect(next.kind).not.toBe('error');
    const report = await verifyWorldRecord(restored!.snapshot.transport);
    expect(report.ok, JSON.stringify(report.errors)).toBe(true);
    expect(restored!.commandsPlayed).toEqual(['我打开盒盖。', '我退回走廊。']);
  });
});
