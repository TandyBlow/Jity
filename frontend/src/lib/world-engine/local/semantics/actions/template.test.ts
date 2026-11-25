import { describe, expect, it } from 'vitest';
import { buildScene } from './scene';
import { buildTestWorld } from './fixtures';
import { templateAction } from './template';

describe('template action', () => {
  it('moves toward a location named by the pending task', () => {
    const state = buildTestWorld();
    state.characters.ally.tasks.task_ally_watch.goal = '去书房查看情况';
    expect(templateAction('move', buildScene(state, 'ally'), state)).toBe('阿宁走向书房。');
  });
  it('observes, guards and speaks from the sheet', () => {
    const state = buildTestWorld();
    state.characters.ally.tasks.task_ally_watch.goal = '向路明非报告';
    const scene = buildScene(state, 'ally');
    expect(templateAction('observe', scene, state)).toBe('阿宁查看周围环境。');
    expect(templateAction('communicate', scene, state)).toBe('阿宁向路明非询问下一步。');
  });
  it('returns null for an open-ended category', () => {
    const state = buildTestWorld();
    expect(templateAction('other', buildScene(state, 'ally'), state)).toBeNull();
  });
});

describe('template feasibility', () => {
  it('does not treat a goal reference as a move destination', () => {
    const state = buildTestWorld();
    state.characters.ally.tasks.task_ally_watch.goal = '守住东回廊对钟楼的接近线';
    expect(templateAction('move', buildScene(state, 'ally'), state)).toBeNull();
  });
  it('does not move an actor already at the place', () => {
    const state = buildTestWorld();
    state.characters.ally.tasks.task_ally_watch.goal = '去大厅查看';
    expect(templateAction('move', buildScene(state, 'ally'), state)).toBeNull();
  });
});
