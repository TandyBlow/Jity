import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { buildInitialState } from '../state';
import { taskConditions } from './task-progress';

const raw = JSON.parse(readFileSync(resolve('public/worlds/dragon-raja-free-day.world.json'), 'utf8')) as {
  initial: Parameters<typeof buildInitialState>[0];
};

function conditions(goal: string, owner = '路明非') {
  const state = buildInitialState(raw.initial);
  return taskConditions(goal, state, owner).map((row) => row.label);
}

describe('task condition decomposition on the real world', () => {
  it('keeps the goal item when the matcher top pick is an unregistered mention', () => {
    const rows = conditions('在进入交火区前拿到可用的护目镜与演习装备');
    expect(rows).toContain('item：路明非的护目镜');
  });

  it('does not read a precondition verb as the goal action', () => {
    expect(conditions('在进入交火区前拿到可用的护目镜与演习装备')).not.toContain('action：进入');
    expect(conditions('在红方进入顶层前安排旗台的持守与撤退信号', '楚子航')).not.toContain('action：进入');
    expect(conditions('在红方进入顶层前安排旗台的持守与撤退信号', '楚子航')).toContain('action：安排');
  });

  it('still decomposes the goggles goal into item, confirmation and action', () => {
    expect(conditions('把胸前护目镜戴好并确认镜片没有裂纹')).toEqual([
      'item：路明非的护目镜', 'confirmation：确认', 'action：戴好',
    ]);
  });
});
