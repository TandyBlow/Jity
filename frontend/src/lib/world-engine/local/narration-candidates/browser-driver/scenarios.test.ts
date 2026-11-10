import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import type { WorldState } from '../../../types';
import { validateCandidateResult } from './run';
import { buildScenarios, freeDayScenarios, projectWorldFacts, sceneFromState, shortWorldScenarios } from './scenarios';

const worldPath = fileURLToPath(new URL('../../../../../../public/worlds/dragon-raja-free-day.world.json', import.meta.url));
const freeDay = JSON.parse(readFileSync(worldPath, 'utf8')) as WorldState;

describe('short-world scenarios', () => {
  it('keeps the public probe identities and product input', async () => {
    const scenarios = await shortWorldScenarios();
    expect(scenarios.map((scenario) => scenario.id)).toEqual(['short-root', 'short-move', 'short-elapsed']);
    const [root, move, elapsed] = scenarios;
    expect(root.identity.version).toBe(0);
    expect(root.identity.previousPointId).toBeNull();
    expect(root.inputText).toContain('【视角】主角视角（周宁）');
    expect(root.inputText).toContain('林川');
    expect(root.identity.changeKinds).toEqual([]);
    expect(move.identity.changeKinds).toEqual(['position']);
    expect(move.identity.previousPointId).toBe('root_short');
    expect(move.inputText).toContain('门厅');
    expect(move.committed.facts.some((fact) => fact.kind === 'moved' && fact.name === '林川' && fact.from === '走廊' && fact.to === '门厅')).toBe(true);
    expect(elapsed.identity.timeAdvance?.duration).toEqual({ amount: 2, unit: 'minute' });
    expect(elapsed.identity.changeKinds).toEqual([]);
    expect(move.identity.stateDigest).toMatch(/^[0-9a-f]{64}$/);
    expect(move.identity.stateDigest).not.toBe(root.identity.stateDigest);
  });
});

describe('free-day scenarios', () => {
  it('projects the real world opening without inventing changes', async () => {
    const [open] = await freeDayScenarios(freeDay);
    expect(open.id).toBe('free-day-open');
    expect(open.identity.worldId).toBe('world_dragon_raja_free_day');
    expect(open.identity.viewpointName).toBe('路明非');
    expect(open.identity.changeKinds).toEqual([]);
    expect(open.inputText).toContain('【视角】主角视角（路明非）');
    expect(open.scene.location).toBe('西侧服务巷');
    expect(open.scene.present.map((person) => person.name)).toContain('诺诺');
    expect(open.scene.objects.map((item) => item.name)).toContain('演习规则牌');
    expect(open.scene.inventory.map((item) => item.name)).toContain('路明非的护目镜');
    expect(open.committed.facts.filter((fact) => fact.kind === 'moved')).toEqual([]);
  });

  it('applies two real moves and keeps slot positions usable', async () => {
    const [, move] = await freeDayScenarios(freeDay);
    expect(move.identity.changeKinds).toEqual(['position']);
    const moved = move.committed.facts.filter((fact) => fact.kind === 'moved');
    expect(moved.map((fact) => `${fact.name}:${fact.from}->${fact.to}`).sort())
      .toEqual(['诺诺:西侧服务巷->西回廊', '路明非:西侧服务巷->西回廊'].sort());
    expect(move.scene.location).toBe('西回廊');
    expect(move.after.characters.lu.position.containerId).toBe('west_arcade');
    expect(move.inputText.length).toBeGreaterThan(200);
  });

  it('expresses the task/personality/sanity chain', async () => {
    const [, , task] = await freeDayScenarios(freeDay);
    expect(task.identity.changeKinds).toEqual(['personality', 'sanity', 'task_achieved']);
    const kinds = task.committed.facts.map((fact) => fact.kind);
    expect(kinds).toContain('task_achieved');
    expect(kinds).toContain('personality_changed');
    expect(kinds).toContain('sanity_changed');
    const sanity = task.committed.facts.find((fact) => fact.kind === 'sanity_changed');
    expect(sanity).toMatchObject({ name: '路明非', from: 43, to: 48 });
    expect(task.after.characters.lu.tasks.task_lu_choice.status).toBe('achieved');
  });
});

describe('fact projection', () => {
  it('reports at-facts for every character and never invents a move without a delta', () => {
    const packet = projectWorldFacts(null, freeDay, { timeAdvance: null, entityDeltas: {} });
    const names = packet.facts.filter((fact) => fact.kind === 'at').map((fact) => fact.name);
    expect(names).toContain('路明非');
    expect(names).toContain('楚子航');
    expect(packet.facts.some((fact) => fact.kind === 'moved')).toBe(false);
    expect(sceneFromState(freeDay, 'lu').location).toBe('西侧服务巷');
  });
});

describe('scenario selection', () => {
  it('selects by id, rejects unknown ids and supports exclusion', async () => {
    const selected = await buildScenarios({ set: 'short', include: ['short-move', 'short-root'] });
    expect(selected.map((scenario) => scenario.id)).toEqual(['short-move', 'short-root']);
    await expect(buildScenarios({ set: 'short', include: ['nope'] })).rejects.toThrow(/unknown_scenarios:nope/);
    const excluded = await buildScenarios({ set: 'short', exclude: ['short-root', 'short-move'] });
    expect(excluded.map((scenario) => scenario.id)).toEqual(['short-elapsed']);
    await expect(buildScenarios({ set: 'free-day', freeDay: null })).rejects.toThrow(/free_day_asset_required/);
  });
});

describe('candidate contract validation', () => {
  const good = {
    text: '正文', accepted: true, rawAttempts: [], issues: [], timings: { totalMs: 1 }, strategyVersion: 'v1',
  };

  it('accepts the documented shape', () => {
    const verdict = validateCandidateResult(good);
    expect(verdict.ok).toBe(true);
    expect(verdict.missing).toEqual([]);
  });

  it('lists every missing field instead of guessing', () => {
    const verdict = validateCandidateResult({ text: 'x' });
    expect(verdict.ok).toBe(false);
    expect(verdict.missing).toEqual(['accepted', 'rawAttempts', 'issues', 'timings', 'strategyVersion']);
  });

  it('flags an accepted-but-empty result and a non-object result', () => {
    expect(validateCandidateResult({ ...good, text: '   ' }).notes).toContain('accepted_with_empty_text');
    expect(validateCandidateResult(null).missing).toEqual(['result_object']);
  });
});
