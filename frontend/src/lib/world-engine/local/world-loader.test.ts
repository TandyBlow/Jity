/** Static-world loading, strict JSON and registered-digest refusal checks. The
 * free-day asset anchors come from the pinned Python reference, not from this
 * loader's own output. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { WorldState } from '../types';
import { buildInitialState, stateDigest } from './state';
import {
  loadStaticWorld, parseStaticWorldJson, readStaticWorldValue, StaticWorldError,
} from './world-loader';

const fixture = JSON.parse(readFileSync(
  resolve('scripts/parallel-kernel/fixtures/kernel-differential.json'), 'utf8'));
const worldText = readFileSync(resolve('public/worlds/dragon-raja-free-day.world.json'), 'utf8');

function smallWorld(initial = fixture.worlds.fixture): WorldState {
  return buildInitialState(structuredClone(initial));
}

function registration(): { stateDigest: string; fileSha256Lf: string; initialDigest: string } {
  return {
    stateDigest: fixture.source.world.stateDigest,
    fileSha256Lf: fixture.source.world.textSha256Lf,
    initialDigest: fixture.source.world.initialDigest,
  };
}

async function reasonOf(run: () => Promise<unknown>): Promise<string> {
  try {
    await run();
  } catch (error) {
    expect(error).toBeInstanceOf(StaticWorldError);
    return (error as StaticWorldError).reason;
  }
  throw new Error('expected a StaticWorldError');
}

describe('strict JSON parser', () => {
  it('accepts integer-valued decimals and exponents the contract accepts', () => {
    expect(parseStaticWorldJson('{"a":1.0,"b":1e3,"c":-0,"d":0.0e2}'))
      .toEqual({ a: 1, b: 1000, c: 0, d: 0 });
  });

  const refusals: [string, string][] = [
    ['duplicate top-level key', '{"a":1,"a":2}'],
    ['duplicate nested key', '{"a":{"b":1,"b":2}}'],
    ['fraction', '{"a":1.5}'],
    ['unsafe integer', '{"a":9007199254740993}'],
    ['rounded fraction above the safe range', '{"a":9007199254740991.4}'],
    ['huge exponent', '{"a":1e999}'],
    ['non-ASCII object key', '{"é":1}'],
    ['unpaired high surrogate', '{"a":"\\ud800"}'],
    ['unpaired low surrogate', '{"a":"\\udc00"}'],
    ['leading zero', '{"a":01}'],
    ['unterminated object', '{"a":1'],
    ['trailing text', '{"a":1} x'],
    ['control character in string', '{"a":"x\u0001"}'],
  ];
  for (const [name, text] of refusals) {
    it(`refuses ${name}`, () => {
      expect(() => parseStaticWorldJson(text)).toThrow(StaticWorldError);
    });
  }
});

describe('free-day static world', () => {
  it('loads the asset, recomputes the Python digest and returns S0/template', async () => {
    const loaded = await loadStaticWorld(worldText, registration());
    expect(loaded.stateDigest).toBe(fixture.source.world.stateDigest);
    expect(loaded.s0Digest).toBe(fixture.source.world.stateDigest);
    expect(loaded.initialDigest).toBe(fixture.source.world.initialDigest);
    expect(loaded.fileSha256Lf).toBe(fixture.source.world.textSha256Lf);
    expect(loaded.counts).toEqual(fixture.source.world.counts);
    expect(loaded.worldId).toBe('world_dragon_raja_free_day');
    expect(loaded.initial.worldId).toBe(loaded.worldId);
    expect(loaded.template).not.toHaveProperty('worldId');
    expect(loaded.state).toEqual(loaded.s0);
  });

  it('refuses a registered state digest mismatch', async () => {
    expect(await reasonOf(() => loadStaticWorld(worldText, { ...registration(), stateDigest: '0'.repeat(64) })))
      .toBe('digest');
  });

  it('refuses a registered file hash mismatch', async () => {
    expect(await reasonOf(() => loadStaticWorld(worldText, { ...registration(), fileSha256Lf: 'f'.repeat(64) })))
      .toBe('file_hash');
  });

  it('refuses a registered initial digest mismatch', async () => {
    expect(await reasonOf(() => loadStaticWorld(worldText, { ...registration(), initialDigest: 'f'.repeat(64) })))
      .toBe('initial_digest');
  });

  it('refuses malformed registration digests', async () => {
    expect(await reasonOf(() => loadStaticWorld(worldText, { stateDigest: 'ABC' }))).toBe('digest');
  });
});

describe('static snapshot and S0', () => {
  it('refuses a current snapshot that is not S0 even with a matching digest', async () => {
    const tampered = JSON.parse(JSON.stringify(smallWorld()));
    tampered.characters.person_a.sanity = 51;
    const text = JSON.stringify(tampered);
    const read = readStaticWorldValue(JSON.parse(text));
    const digest = await stateDigest(read.state);
    expect(await reasonOf(() => loadStaticWorld(text, { stateDigest: digest }))).toBe('s0');
    const inspection = await loadStaticWorld(text, { stateDigest: digest }, { requireS0: false });
    expect(inspection.stateDigest).toBe(digest);
    expect(inspection.stateDigest).not.toBe(inspection.s0Digest);
  });

  it('accepts the untouched small world as S0', async () => {
    const text = JSON.stringify(smallWorld());
    const loaded = await loadStaticWorld(text, { stateDigest: await stateDigest(smallWorld()) });
    expect(loaded.counts).toEqual({ locations: 1, items: 1, characters: 1, tasks: 1 });
  });

  const schemaRefusals: [string, (world: WorldState) => void][] = [
    ['unsupported engine version', (world) => { (world as unknown as { engineVersion: string }).engineVersion = 'world-engine-v2'; }],
    ['unsupported state schema', (world) => { world.schemaVersion = 2 as unknown as 1; }],
    ['protagonist not registered', (world) => { world.protagonistId = 'ghost'; }],
    ['current registry differs from initial', (world) => { delete (world.characters as Record<string, unknown>).person_a; }],
    ['unknown initial container', (world) => { (world.initial.characters.person_a.initialPosition as { containerId: string }).containerId = 'ghost'; }],
    ['relative target in another room', (world) => {
      world.initial.locations.room_b = { id: 'room_b', name: 'B', parentLocationId: null, initialAppearance: 'x', slots: [] };
      world.locations.room_b = { id: 'room_b', appearanceChanges: [] };
      (world.initial.characters.person_a.initialPosition as { relativeTo: unknown }).relativeTo = { entityId: 'item_b', relation: 'beside' };
      world.initial.items.item_b = { id: 'item_b', name: 'B', initialPosition: { containerId: 'room_b', slotId: null, relativeTo: null }, initialAppearance: 'x', slots: [] };
      world.items.item_b = { id: 'item_b', appearanceChanges: [], position: { containerId: 'room_b', slotId: null, relativeTo: null } };
    }],
    ['unknown task parent', (world) => { world.initial.characters.person_a.tasks.task_a.parentTaskId = 'ghost'; }],
    ['unknown top-level field', (world) => { (world as unknown as { extra: number }).extra = 1; }],
    ['unknown initial entity field', (world) => { (world.initial.characters.person_a as unknown as { extra: number }).extra = 1; }],
    ['unknown current task field', (world) => { (world.characters.person_a.tasks.task_a as unknown as { extra: number }).extra = 1; }],
    ['duplicate task id across owners', (world) => {
      world.initial.characters.person_b = {
        ...structuredClone(world.initial.characters.person_a),
        id: 'person_b', name: 'B',
      };
      world.characters.person_b = structuredClone(world.characters.person_a);
      world.characters.person_b.id = 'person_b';
    }],
  ];
  for (const [name, mutate] of schemaRefusals) {
    it(`refuses ${name}`, () => {
      const world = smallWorld();
      mutate(world);
      expect(() => readStaticWorldValue(JSON.parse(JSON.stringify(world)))).toThrow(StaticWorldError);
    });
  }
});
