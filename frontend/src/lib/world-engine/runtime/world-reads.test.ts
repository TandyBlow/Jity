import { describe, expect, test } from 'vitest';
import { readAllPoints } from './world-reads';
import type { WorldTransport } from '../transport';
import type { RequestMap, Success, WorldOperation } from '../types';

/** A fake ledger: serves ascending pages of `total` points, recording the
 * after-cursor of every call — enough to pin the pagination contract
 * without a live server. */
function pagedLedger(total: number, pageSize: number) {
  const calls: (number | null)[] = [];
  const points = Array.from({ length: total }, (_, sequence) => ({
    worldId: 'world_p', pointId: `p_${sequence}`, sequence,
    kind: sequence === 0 ? 'root' as const : 'normal' as const,
    previousPointId: sequence === 0 ? '' : `p_${sequence - 1}`,
    roundId: 'round_1', advanceId: 'advance_1', stateDigest: `d_${sequence}`,
  }));
  const transport: WorldTransport = {
    async execute<K extends WorldOperation>(operation: K, request: RequestMap[K]): Promise<Success<K>> {
      if (operation !== 'list_points') throw new Error(`unexpected ${operation}`);
      const after = (request as { after?: number | null }).after ?? null;
      calls.push(after);
      const start = (after ?? -1) + 1;
      const page = points.slice(start, start + pageSize);
      return { data: { points: structuredClone(page) } } as unknown as Success<K>;
    },
  };
  return { transport, calls };
}

describe('point ledger pagination', () => {
  test('a 250-point ledger pages fully and the last point is the head', async () => {
    const { transport, calls } = pagedLedger(250, 100);
    const points = await readAllPoints(transport, 'world_p');
    expect(points).toHaveLength(250);
    expect(points[0]).toMatchObject({ sequence: 0, kind: 'root' });
    expect(points.at(-1)).toMatchObject({ sequence: 249 });
    expect(points.map((point) => point.sequence)).toEqual(Array.from({ length: 250 }, (_, index) => index));
    expect(calls).toEqual([null, 99, 199]);
  });

  test('a short final page stops the walk without an extra call', async () => {
    const { transport, calls } = pagedLedger(101, 100);
    const points = await readAllPoints(transport, 'world_p');
    expect(points).toHaveLength(101);
    expect(points.at(-1)).toMatchObject({ sequence: 100 });
    expect(calls).toEqual([null, 99]);
  });

  test('a ledger within one page reads in a single call', async () => {
    const { transport, calls } = pagedLedger(7, 100);
    const points = await readAllPoints(transport, 'world_p');
    expect(points).toHaveLength(7);
    expect(calls).toEqual([null]);
  });

  test('a full page that fails to advance the cursor stops with an error', async () => {
    const stuck: WorldTransport = {
      async execute<K extends WorldOperation>(operation: K): Promise<Success<K>> {
        if (operation !== 'list_points') throw new Error(`unexpected ${operation}`);
        const page = Array.from({ length: 100 }, (_, sequence) => ({
          worldId: 'w', pointId: `p_${sequence}`, sequence, kind: 'normal' as const,
          previousPointId: '', roundId: 'r', advanceId: 'a', stateDigest: 'd',
        }));
        return { data: { points: page } } as unknown as Success<K>;
      },
    };
    await expect(readAllPoints(stuck, 'w')).rejects.toThrow('list_points_page_makes_no_progress');
  });
});
