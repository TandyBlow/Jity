import { describe, expect, it } from 'vitest';
import type { EntityDelta, InitialState, WorldState } from '../../types';
import { buildInitialState } from '../state';
import { compareCodePoints } from './code-points';
import { projectNarrationInput } from './project';
import { renderLegacyInput } from './render-legacy';
import { renderResultBlock, renderResultInput } from './render-result';
import { applyDelta, tinyWorld } from './test-fixtures';
import {
  DEFAULT_NARRATION_PROJECTION_POLICY,
  NarrationInputError,
  type NarrationProjection,
  type RowPerson,
} from './types';

const TIME = { boundary: 'elapsed' as const, duration: { amount: 3, unit: 'minute' as const } };

function expectCode(fn: () => unknown, code: string): void {
  try {
    fn();
  } catch (error) {
    expect(error).toBeInstanceOf(NarrationInputError);
    expect((error as NarrationInputError).code).toBe(code);
    return;
  }
  throw new Error(`expected NarrationInputError ${code}`);
}

function project(
  before: WorldState,
  delta: Record<string, EntityDelta>,
  viewpointId = 'hero',
  policy?: Parameters<typeof projectNarrationInput>[0]['policy'],
) {
  const after = applyDelta(before, delta, TIME);
  return {
    after,
    result: projectNarrationInput({ before, after, delta, timeAdvance: TIME, viewpointId, policy }),
  };
}

function minimalProjection(overrides: Partial<NarrationProjection> = {}): NarrationProjection {
  return {
    projectionVersion: 'narration-projection-v1',
    viewpoint: { id: 'hero', name: '阿青', text: '主角视角（阿青）；只表达已结算的世界事实' },
    beforeState: { 地点: {}, 人物: {}, 物品: {} },
    delta: { 时间推进: '3 分钟', 变化: {} },
    resultState: {},
    policy: { ...DEFAULT_NARRATION_PROJECTION_POLICY, length: { ...DEFAULT_NARRATION_PROJECTION_POLICY.length } },
    ...overrides,
  };
}

function person(overrides: Partial<RowPerson> = {}): RowPerson {
  return { 位置: '大厅', 精神值: 40, 外貌: [], 个性: [], 任务: null, ...overrides };
}

describe('projection collection rules', () => {
  it('keeps only changed items even when many unchanged items share the room', () => {
    const before = tinyWorld();
    const { result } = project(before, {});
    expect(result.includedEntities.items).toEqual([]);
    expect(result.visibleEntities.items).toHaveLength(3);
    expect(result.visibleEntities.items).toEqual(expect.arrayContaining(['keepsake', 'lamp', 'note']));
    const omitted = result.omittedFields.filter((entry) => entry.entityType === 'item');
    expect(omitted.map((entry) => entry.entityName)).toEqual(expect.arrayContaining(['铜灯', '纸条', '旧照片']));
    expect(omitted.every((entry) => entry.reason === 'item_not_changed')).toBe(true);
    expect(result.projection.beforeState.物品).toEqual({});
  });

  it('includes all changed items without an arbitrary list slice', () => {
    const before = tinyWorld();
    const initial = structuredClone(before.initial) as InitialState;
    const itemIds: string[] = [];
    for (let index = 0; index < 12; index += 1) {
      const id = `extra_${index}`;
      itemIds.push(id);
      initial.items[id] = {
        id, name: `杂物${index}`, initialPosition: { containerId: 'hall', slotId: 'slot_front', relativeTo: null },
        initialAppearance: `杂物${index}的外观。`, slots: [],
      };
    }
    const world = buildInitialState(initial);
    const delta: Record<string, EntityDelta> = {};
    for (const id of itemIds) {
      delta[id] = { entityId: id, appearanceChanges: [{ id: `ch_${id}`, text: `${id}被挪动了。`, supersedes: [] }] };
    }
    const { result } = project(world, delta);
    expect(result.includedEntities.items).toHaveLength(12);
    for (const id of itemIds) {
      expect(result.includedEntities.items).toContain(id);
      expect(Object.keys(result.projection.beforeState.物品)).toContain(`杂物${id.split('_')[1]}`);
    }
  });

  it('keeps every changed location and its immediate parent', () => {
    const before = tinyWorld();
    const initial = structuredClone(before.initial) as InitialState;
    const locationIds: string[] = [];
    for (let index = 0; index < 8; index += 1) {
      const id = `side_${index}`;
      locationIds.push(id);
      initial.locations[id] = {
        id, name: `偏厅${index}`, parentLocationId: 'hall', initialAppearance: `偏厅${index}的描述。`, slots: [],
      };
    }
    const world = buildInitialState(initial);
    const delta: Record<string, EntityDelta> = {};
    for (const id of locationIds) {
      delta[id] = { entityId: id, appearanceChanges: [{ id: `ch_${id}`, text: `${id}多了一道划痕。`, supersedes: [] }] };
    }
    const { result } = project(world, delta);
    expect(result.includedEntities.locations).toEqual(expect.arrayContaining(locationIds));
    expect(result.includedEntities.locations).toContain('hall');
    expect(Object.keys(result.projection.beforeState.地点)).toEqual(expect.arrayContaining([
      '大厅', '偏厅0', '偏厅1', '偏厅2', '偏厅3', '偏厅4', '偏厅5', '偏厅6', '偏厅7',
    ]));
  });

  it('uses the innermost location, not the slot, as the visibility boundary', () => {
    const before = tinyWorld();
    const { result } = project(before, {});
    // hero is behind hall/slot_back, friend is at hall/slot_front; both are visible.
    expect(result.visibleEntities.characters).toEqual(['friend', 'hero']);
    expect(result.visibleEntities.characters).not.toContain('stranger');
    // note is inside hero's pocket; keepsake is inside the visible lamp.
    expect(result.visibleEntities.items).toEqual(['keepsake', 'note', 'lamp']);
    expect(result.includedEntities.locations).toEqual(['hall']);
  });

  it('does not turn a different child location into a visible scene', () => {
    const before = tinyWorld();
    const delta: Record<string, EntityDelta> = {
      friend: { entityId: 'friend', positionSet: { containerId: 'alcove', slotId: null, relativeTo: null } },
      stranger: { entityId: 'stranger', appearanceChanges: [{ id: 'ch_stranger', text: '斗篷湿了。', supersedes: [] }] },
    };
    const { result } = project(before, delta);
    expect(result.visibleEntities.characters).toEqual(['hero']);
    expect(result.includedEntities.characters).toEqual(expect.arrayContaining(['hero', 'friend', 'stranger']));
    expect(result.includedEntities.locations).toEqual(expect.arrayContaining(['hall', 'alcove']));
    expect(result.projection.resultState['阿灰']).toEqual({ 外貌: ['披着旧斗篷。', '斗篷湿了。'] });
  });

  it('projects the before state, never the after state, into 上回合状态', () => {
    const before = tinyWorld();
    const delta: Record<string, EntityDelta> = {
      hero: {
        entityId: 'hero', sanitySet: 0,
        appearanceChanges: [{ id: 'ch_look', text: '额头有伤。', supersedes: [] }],
        personalityChanges: [{ id: 'ch_person', text: '开始怀疑阿白。', supersedes: [] }],
      },
    };
    const { result } = project(before, delta);
    const hero = result.projection.beforeState.人物['阿青'];
    expect(hero.精神值).toBe(50);
    expect(hero.外貌).toEqual(['袖口沾着灰。']);
    expect(hero.个性).toEqual(['谨慎。']);
    expect(result.projection.resultState['阿青']).toMatchObject({ 精神值: 0, 外貌: ['袖口沾着灰。', '额头有伤。'], 个性: ['谨慎。', '开始怀疑阿白。'] });
    const heroOmissions = result.omittedFields.filter((entry) => entry.entityId === 'hero');
    expect(heroOmissions).toEqual(expect.arrayContaining([
      expect.objectContaining({ field: '位置', reason: 'field_not_changed' }),
      expect.objectContaining({ field: '任务', reason: 'field_not_changed' }),
    ]));
    const legacy = renderLegacyInput(result.projection).text;
    expect(legacy).toContain('阿青：在大厅（窗边），精神值50');
    expect(legacy).not.toContain('阿青：在大厅（窗边），精神值0');
    expect(legacy).toContain('精神值变成0');
    expect(legacy).not.toContain('【本回合状态】');
  });

  it('renders an empty appearance list explicitly and removes the old text from the delta', () => {
    const world0 = tinyWorld();
    const before = applyDelta(world0, {
      blank: { entityId: 'blank', appearanceChanges: [{ id: 'ch_old', text: '旧外套', supersedes: [] }] },
    });
    const { result } = project(before, {
      blank: { entityId: 'blank', appearanceChanges: [{ id: 'ch_remove', text: null, supersedes: ['ch_old'] }] },
    });
    expect(result.projection.beforeState.人物['阿空'].外貌).toEqual(['旧外套']);
    expect(result.projection.resultState['阿空']).toEqual({ 外貌: [] });
    const legacy = renderLegacyInput(result.projection).text;
    expect(legacy).toContain('阿空（人物）：去掉外貌旧外套');
    const rendered = renderResultInput(result.projection).text;
    expect(rendered).toContain('阿空（人物）：外貌[]');
  });

  it('renders an empty personality list explicitly too', () => {
    const world0 = tinyWorld();
    const before = applyDelta(world0, {
      blank: { entityId: 'blank', personalityChanges: [{ id: 'ch_p_old', text: '旧脾气', supersedes: [] }] },
    });
    const { result } = project(before, {
      blank: { entityId: 'blank', personalityChanges: [{ id: 'ch_p_remove', text: null, supersedes: ['ch_p_old'] }] },
    });
    expect(result.projection.resultState['阿空']).toEqual({ 个性: [] });
    expect(renderResultInput(result.projection).text).toContain('阿空（人物）：个性[]');
  });

  it('renders item movement with the settled position and keeps the item line legacy-shaped', () => {
    const before = tinyWorld();
    const delta: Record<string, EntityDelta> = {
      lamp: {
        entityId: 'lamp',
        positionSet: { containerId: 'garden', slotId: null, relativeTo: null },
        appearanceChanges: [{ id: 'ch_lamp', text: '灯罩裂了。', supersedes: [] }],
      },
    };
    const { result } = project(before, delta);
    expect(result.projection.beforeState.物品['铜灯'].位置).toBe('大厅（门前）');
    expect(result.projection.resultState['铜灯']).toEqual({ 位置: '庭院', 外貌: ['灯罩擦得很亮。', '灯罩裂了。'] });
    const legacy = renderLegacyInput(result.projection).text;
    expect(legacy).toContain('【物品】铜灯：灯罩擦得很亮。');
    expect(legacy).toContain('铜灯（物品）：移动到庭院，多出外貌灯罩裂了。');
    expect(legacy).not.toContain('（在大厅里）');
    const rendered = renderResultInput(result.projection).text;
    expect(rendered).toContain('铜灯（物品）：位置庭院；外貌[灯罩擦得很亮。、灯罩裂了。]');
  });

  it('keeps the immediate parent relation for a changed grandchild task', () => {
    const before = tinyWorld();
    const delta: Record<string, EntityDelta> = {
      hero: {
        entityId: 'hero',
        tasksAchieved: ['task_grand'],
        subtasksAdded: [{ id: 'task_new', ownerId: 'hero', parentTaskId: 'task_child', goal: '把钥匙放回原处', status: 'pending' }],
      },
    };
    const { result } = project(before, delta);
    expect(result.projection.resultState['阿青']).toEqual({
      任务: {
        小任务: [
          { 目标: '打开木箱看清里面的东西', 状态: '已完成', 属于大任务: '问清地窖的钥匙在谁手里' },
          { 目标: '把钥匙放回原处', 状态: '未完成', 属于大任务: '问清地窖的钥匙在谁手里' },
        ],
      },
    });
    const rendered = renderResultInput(result.projection).text;
    expect(rendered).toContain('任务小任务《打开木箱看清里面的东西》（已完成，属于《问清地窖的钥匙在谁手里》）；小任务《把钥匙放回原处》（未完成，属于《问清地窖的钥匙在谁手里》）');
  });

  it('carries a changed root task as 大任务 and a changed child separately', () => {
    const before = tinyWorld();
    const { result } = project(before, {
      hero: { entityId: 'hero', tasksAchieved: ['task_root', 'task_grand'] },
    });
    expect(result.projection.resultState['阿青']).toEqual({
      任务: {
        大任务: { 目标: '找到父亲留下的箱子', 状态: '已完成' },
        小任务: [{ 目标: '打开木箱看清里面的东西', 状态: '已完成', 属于大任务: '问清地窖的钥匙在谁手里' }],
      },
    });
  });

  it('places an entity inside an item by its full container and innermost location', () => {
    const before = tinyWorld();
    const { result } = project(before, {
      note: { entityId: 'note', appearanceChanges: [{ id: 'ch_note', text: '纸条展开了一角。', supersedes: [] }] },
      keepsake: { entityId: 'keepsake', appearanceChanges: [{ id: 'ch_photo', text: '照片上多了一道折痕。', supersedes: [] }] },
    });
    expect(result.projection.beforeState.人物['阿青'].位置).toBe('大厅（窗边）');
    expect(result.projection.beforeState.物品['纸条'].位置).toBe('阿青的衣袋（在大厅里）');
    expect(result.projection.beforeState.物品['旧照片'].位置).toBe('铜灯（在大厅里）');
  });
});

describe('projection error paths', () => {
  it('rejects a delta whose after state does not reflect it', () => {
    const before = tinyWorld();
    const delta: Record<string, EntityDelta> = { hero: { entityId: 'hero', sanitySet: 0 } };
    expectCode(() => projectNarrationInput({ before, after: before, delta, timeAdvance: TIME, viewpointId: 'hero' }), 'after_mismatch');
  });

  it('rejects an unknown delta entity', () => {
    const before = tinyWorld();
    const delta: Record<string, EntityDelta> = { ghost: { entityId: 'ghost' } };
    expectCode(() => projectNarrationInput({ before, after: before, delta, timeAdvance: TIME, viewpointId: 'hero' }), 'unknown_entity');
  });

  it('rejects two included entities with the same name', () => {
    const before = tinyWorld();
    before.initial.characters.friend.name = '阿青';
    expectCode(() => project(before, {}), 'duplicate_name');
  });

  it('rejects a pure removal without a supersede target', () => {
    const before = tinyWorld();
    const delta: Record<string, EntityDelta> = {
      hero: { entityId: 'hero', appearanceChanges: [{ id: 'ch_bad', text: null, supersedes: [] }] },
    };
    expectCode(() => project(before, delta), 'pure_removal_without_supersedes');
  });
});

describe('serializer safety and limits', () => {
  it('sorts names by code point, including non-BMP characters', () => {
    expect(compareCodePoints('Z', '\uE000')).toBeLessThan(0);
    expect(compareCodePoints('\uE000', '𝄞')).toBeLessThan(0);
    const projection = minimalProjection({
      beforeState: {
        地点: {},
        人物: {
          '𝄞': person({ 位置: '大厅' }),
          '\uE000': person({ 位置: '大厅' }),
          Z: person({ 位置: '大厅' }),
        },
        物品: {},
      },
    });
    const text = renderLegacyInput(projection, { charset: null }).text;
    const order = ['Z：', '\uE000：', '𝄞：'].map((name) => text.indexOf(name));
    expect(order[0]).toBeLessThan(order[1]);
    expect(order[1]).toBeLessThan(order[2]);
  });

  it('rejects whitespace that the old serializer would otherwise send to the model', () => {
    const projection = minimalProjection({
      beforeState: { 地点: {}, 人物: { 阿青: person({ 位置: '大厅 前' }) }, 物品: {} },
    });
    expectCode(() => renderLegacyInput(projection), 'whitespace');
  });

  it('rejects whitespace in a task goal instead of silently squashing it', () => {
    const projection = minimalProjection({
      beforeState: {
        地点: {},
        人物: { 阿青: person({ 任务: { 大任务: { 目标: '打开 木箱', 状态: '未完成' }, 小任务: [] } }) },
        物品: {},
      },
    });
    expectCode(() => renderLegacyInput(projection), 'whitespace');
  });

  it('rejects a character outside the recorded vocabulary', () => {
    const projection = minimalProjection({
      beforeState: { 地点: {}, 人物: { 阿青: person({ 位置: '大厅🚀' }) }, 物品: {} },
    });
    expectCode(() => renderLegacyInput(projection), 'oov');
  });

  it('throws on a configured limit instead of truncating', () => {
    const projection = minimalProjection({
      beforeState: { 地点: {}, 人物: { 阿青: person({ 位置: '大厅深处' }) }, 物品: {} },
      policy: { ...DEFAULT_NARRATION_PROJECTION_POLICY, length: { maxChars: 10, maxUtf8Bytes: null } },
    });
    expectCode(() => renderLegacyInput(projection), 'too_long');
    const rendered = renderLegacyInput(projection, { enforceLength: false });
    expect(rendered.text).toContain('大厅深处');
    expect(rendered.charCount).toBeGreaterThan(10);
  });

  it('records the length limit failure with measured sizes', () => {
    const projection = minimalProjection({
      beforeState: { 地点: {}, 人物: { 阿青: person({ 位置: '大厅深处' }) }, 物品: {} },
      policy: { ...DEFAULT_NARRATION_PROJECTION_POLICY, length: { maxChars: null, maxUtf8Bytes: 10 } },
    });
    try {
      renderLegacyInput(projection);
      throw new Error('expected too_long');
    } catch (error) {
      expect(error).toBeInstanceOf(NarrationInputError);
      expect((error as NarrationInputError).code).toBe('too_long');
      expect((error as NarrationInputError).context.utf8Bytes).toBeGreaterThan(10);
    }
  });

  it('never places reference or evaluation labels in the projection', () => {
    const { result } = project(tinyWorld(), {});
    const forbidden = new Set(['叙事', '参考', 'rubric', 'label', 'labels', 'score', 'evaluation', 'y']);
    const visit = (value: unknown): void => {
      if (!value || typeof value !== 'object') return;
      for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
        expect(forbidden.has(key), key).toBe(false);
        visit(child);
      }
    };
    visit(result.projection);
  });

  it('does not mix the result block into the legacy version', () => {
    const projection = minimalProjection({
      resultState: { 阿青: { 精神值: 0 } },
      beforeState: { 地点: {}, 人物: { 阿青: person() }, 物品: {} },
    });
    const legacy = renderLegacyInput(projection).text;
    const result = renderResultInput(projection).text;
    expect(legacy).not.toContain('【本回合状态】');
    expect(result).toContain('【本回合状态】');
    expect(result.startsWith(legacy.slice(0, legacy.lastIndexOf('【正文】')))).toBe(true);
    expect(result.endsWith('【正文】')).toBe(true);
  });
});

describe('result block format', () => {
  it('renders explicit zero and empty lists', () => {
    const projection = minimalProjection({
      beforeState: { 地点: {}, 人物: { 阿青: person() }, 物品: {} },
      resultState: { 阿青: { 精神值: 0, 外貌: [], 个性: [] } },
    });
    const block = renderResultBlock(projection);
    expect(block).toBe('【本回合状态】阿青（人物）：精神值0；外貌[]；个性[]。');
  });

  it('uses type order 地点/人物/物品 and codepoint order inside a type', () => {
    const projection = minimalProjection({
      beforeState: {
        地点: { 大厅: { 位于: null, 外貌: ['旧。'] } },
        人物: { 阿青: person(), 阿白: person() },
        物品: { 铜灯: { 位置: '大厅', 外貌: ['旧。'] } },
      },
      resultState: {
        铜灯: { 外貌: ['新。'] },
        阿白: { 精神值: 1 },
        大厅: { 外貌: ['大厅新。'] },
        阿青: { 精神值: 2 },
      },
    });
    const block = renderResultBlock(projection);
    const positions = ['大厅（地点）', '阿白（人物）', '阿青（人物）', '铜灯（物品）'].map((name) => block.indexOf(name));
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
    expect(block.startsWith('【本回合状态】大厅（地点）')).toBe(true);
  });

  it('renders tasks with parent relation and item position', () => {
    const projection = minimalProjection({
      beforeState: {
        地点: {},
        人物: { 阿青: person() },
        物品: { 铜灯: { 位置: '大厅', 外貌: ['旧。'] } },
      },
      resultState: {
        阿青: { 任务: { 大任务: { 目标: '找到箱子', 状态: '已完成' }, 小任务: [{ 目标: '打开箱子', 状态: '未完成', 属于大任务: '找到箱子' }] } },
        铜灯: { 位置: '庭院', 外貌: [] },
      },
    });
    const block = renderResultBlock(projection);
    expect(block).toContain('任务大任务《找到箱子》（已完成）；小任务《打开箱子》（未完成，属于《找到箱子》）');
    expect(block).toContain('铜灯（物品）：位置庭院；外貌[]');
  });

  it('rejects a field that does not belong to the result entity type', () => {
    const projection = minimalProjection({
      beforeState: { 地点: { 大厅: { 位于: null, 外貌: [] } }, 人物: {}, 物品: {} },
      resultState: { 大厅: { 外貌: [], 精神值: 0 } as never },
    });
    expectCode(() => renderResultBlock(projection), 'invalid_projection');
  });

  it('treats an entity entry with no operations as no change', () => {
    const projection = minimalProjection({
      beforeState: { 地点: {}, 人物: { 阿青: person() }, 物品: {} },
      delta: { 时间推进: '3 分钟', 变化: { 阿青: {} } },
    });
    expect(renderLegacyInput(projection).text).toContain('这一回合没有结算出变化。');
  });

  it('emits no block for an empty or all-empty result', () => {
    expect(renderResultBlock(minimalProjection())).toBe('');
    expect(renderResultBlock(minimalProjection({
      beforeState: { 地点: {}, 人物: { 阿青: person() }, 物品: {} },
      resultState: { 阿青: {} },
    }))).toBe('');
  });

  it('matches the legacy prefix byte for byte and adds only the block', () => {
    const projection = minimalProjection({
      beforeState: { 地点: {}, 人物: { 阿青: person() }, 物品: {} },
      delta: { 时间推进: '8 分钟', 变化: { 阿青: { 精神值: 0 } } },
      resultState: { 阿青: { 精神值: 0 } },
    });
    const legacy = renderLegacyInput(projection).text;
    const result = renderResultInput(projection).text;
    expect(result).toBe(legacy.replace('【正文】', '【本回合状态】阿青（人物）：精神值0。【正文】'));
    expect(result).toContain('时间推进8分钟。');
  });
});
