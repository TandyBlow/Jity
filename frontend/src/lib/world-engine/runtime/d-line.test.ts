import { expect, test, vi } from 'vitest';
import { DLinePort, createDLineDriver } from './d-line';
import { updateStages } from '../schedule';
import { initialMemory } from '../controller';
import type { Json } from '../types';
const stages = () => updateStages.map(stage => ({ stage, changes: {} }));
const state = { characters: { tian: {}, sun: {}, zeng: {} } };
const source = { groupId: 'g', workingState: state, members: [{ memberId: 'tian', actionText: '尝试拿钥匙', rollRefs: [] }] } as Json;
const narrator = { generate: vi.fn(async () => '正式叙事') };
function setup(responses: Json[] = [{ kind: 'act', text: '田尝试拿钥匙' }, { results: { tian: '未拿到钥匙' }, updates: stages() }]) {
  const api = vi.fn(async () => { if (!responses.length) throw Error('unexpected API'); return responses.shift()!; });
  const d03 = vi.fn(async () => ({ targetIds: ['sun'] }));
  return { port: new DLinePort(api, d03, narrator, 1), api, d03 };
}
test('normal unit makes exactly two API calls; D03 is local; six stages are cached', async () => {
  const { port, api, d03 } = setup();
  expect(await port.generate('action', 'tian', { actor: 'tian', workingState: state })).toEqual({ kind: 'act', text: '田尝试拿钥匙' });
  expect(await port.generate('targets', 'tian', { sourceId: 'tian', actionText: '尝试拿钥匙', workingState: state })).toEqual({ targets: [{ targetId: 'sun' }] });
  await port.generate('results', 'g', source);
  for (const stage of updateStages) await port.generate('updates', `g#${stage}`, { groupId: 'g', stage, workingState: state });
  expect(api).toHaveBeenCalledTimes(2); expect(d03).toHaveBeenCalledTimes(1);
});
test('skip costs only one API; incomplete is never skip', async () => {
  const { port } = setup([{ kind: 'skip' }, { kind: 'incomplete', reason: 'missing state' }]);
  expect(await port.generate('action', 'tian', {})).toEqual({ kind: 'skip' });
  await expect(port.generate('action', 'sun', {})).rejects.toThrow('missing state');
});
test('local failure never falls back to paid API', async () => {
  const api = vi.fn();
  const port = new DLinePort(api, async () => { throw Error('too long'); }, narrator);
  await expect(port.generate('targets', 'tian', { sourceId: 'tian', actionText: '拿钥匙', workingState: state })).rejects.toThrow('too long');
  expect(api).not.toHaveBeenCalled();
});
test('reaction adds exactly one API and preserves input', async () => {
  const { port, api } = setup([{ action: '孙握紧钥匙' }]);
  expect(await port.generate('reaction', 'tian', { rollId: 'actual-roll', sourceActionText: '拿钥匙' })).toBe('孙握紧钥匙');
  expect(api).toHaveBeenCalledTimes(1);
});
test('U3 failure preserves U1/U2 and frozen action; repairs suffix once then stops', async () => {
  const { port, api } = setup([{ results: { tian: '未拿到钥匙' }, updates: stages() }, { updates: stages().slice(2) }]);
  await port.generate('results', 'g', source);
  const prefix = stages().slice(0, 2);
  expect(await port.repairUpdates('g', prefix, { preview: 'U2' }, 'bad task')).toBe(true);
  expect(await port.repairUpdates('g', prefix, {}, 'bad again')).toBe(false);
  expect(api).toHaveBeenCalledTimes(2);
  expect(api.mock.calls[1]).toBeDefined();
  expect(await port.generate('updates', 'g#tasks', { groupId: 'g', stage: 'tasks' })).toEqual(stages()[2]);
});
test('unknown stages, missing results and cross-stage fields are rejected', async () => {
  const { port } = setup([{ results: {}, updates: stages() }]);
  await expect(port.generate('results', 'g', source)).rejects.toThrow('coverage');
  const bad = stages() as { stage: string; changes: object }[];
  bad[0].changes = { tian: { entityId: 'tian', sanitySet: 3 } };
  const second = setup([{ results: { tian: '未拿到' }, updates: bad } as Json]).port;
  await second.generate('results', 'g', source);
  await expect(second.generate('updates', 'g#position', { groupId: 'g', stage: 'position' })).rejects.toThrow('Wrong field');
});
test('empty point still requests one full time scan', async () => {
  const { port, api } = setup([{ results: {}, updates: stages() }]);
  for (const stage of updateStages) await port.generate('updates', `time_scan:p#${stage}`, { mode: 'time_scan', stage, workingState: state });
  expect(api).toHaveBeenCalledTimes(1);
});
test('same group cannot reuse settlement after source changes', async () => {
  const { port } = setup([{ results: { tian: '未拿到' }, updates: stages() }]);
  await port.generate('results', 'g', source);
  await expect(port.generate('results', 'g', { ...source as object, workingState: {} } as Json)).rejects.toThrow('changed');
});
test('composition forces six-stage preview and does not write at construction', () => {
  const transport = { execute: vi.fn() };
  const { driver } = createDLineDriver({ transport, memory: initialMemory('d', 'holder'), api: vi.fn(), d03: vi.fn(), narration: narrator });
  expect(driver.getMemory().updatesStages).toEqual(updateStages);
  expect(transport.execute).not.toHaveBeenCalled();
});
test('D07 only accepts both semantic conditions, and round IDs come from program', async () => {
  const api = vi.fn(async () => ({ candidates: [{ actorId: 'sun', action: '守住钥匙', likely: true, relatedToProtagonist: true }] }));
  const allocate = vi.fn(async () => 'program-round');
  const port = new DLinePort(api, vi.fn(), narrator, 1, undefined, allocate);
  expect(await port.generate('continuation', 'r1', { workingState: state })).toMatchObject({ nextRoundId: 'program-round', candidateCharacterIds: ['sun'] });
  expect(allocate).toHaveBeenCalledTimes(1);
  await port.generate('continuation', 'r1', { workingState: state });
  expect(api).toHaveBeenCalledTimes(2); // no speculative advice cache
});
