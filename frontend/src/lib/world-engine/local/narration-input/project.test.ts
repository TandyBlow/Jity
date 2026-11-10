import { describe, expect, it } from 'vitest';
import type { EntityDelta, InitialState, TimeAdvance, WorldState } from '../../types';
import { buildInitialState } from '../state';
import { compareCodePoints } from './code-points';
import { projectNarrationInput } from './project';
import { renderNarrationInput } from './pipeline';
import { applyDelta, tinyWorld } from './test-fixtures';
import { NarrationInputError } from './types';

const TIME: TimeAdvance = { boundary: 'elapsed', duration: { amount: 3, unit: 'minute' } };

function expectCode(fn: () => unknown, code: string): NarrationInputError {
  try {
    fn();
  } catch (error) {
    expect(error).toBeInstanceOf(NarrationInputError);
    expect((error as NarrationInputError).code).toBe(code);
    return error as NarrationInputError;
  }
  throw new Error(`expected NarrationInputError ${code}`);
}

function project(
  before: WorldState,
  delta: Record<string, EntityDelta>,
  viewpointId = 'hero',
  timeAdvance: TimeAdvance = TIME,
) {
  const after = applyDelta(before, delta, timeAdvance);
  return {
    after,
    result: projectNarrationInput({ before, after, delta, timeAdvance, viewpointId }),
  };
}

function render(result: ReturnType<typeof project>['result'], model: 'result-v2' | 'legacy' = 'result-v2') {
  return renderNarrationInput(result.projection, { model });
}

describe('projection collection rules', () => {
  it('projects the before state and keeps the after state only in the result block', () => {
    const before = tinyWorld();
    const { result } = project(before, {
      hero: {
        entityId: 'hero', sanitySet: 0,
        appearanceChanges: [{ id: 'ch_look', text: '额头有伤。', supersedes: [] }],
        personalityChanges: [{ id: 'ch_person', text: '开始怀疑阿白。', supersedes: [] }],
      },
    });
    const heroBefore = result.projection.上回合状态.人物['阿青'];
    expect(heroBefore.精神值).toBe(50);
    expect(heroBefore.外貌).toEqual(['袖口沾着灰。']);
    expect(heroBefore.个性).toEqual(['谨慎。']);
    expect(result.projection.本回合状态['阿青']).toEqual({
      精神值: 0,
      外貌: ['袖口沾着灰。', '额头有伤。'],
      个性: ['谨慎。', '开始怀疑阿白。'],
    });
    const v2 = render(result).text;
    expect(v2).toContain('阿青：在大厅（窗边），精神值50，外貌袖口沾着灰，个性谨慎，任务找到父亲留下的箱子（未完成）；问清地窖的钥匙在谁手里（未完成）；打开木箱看清里面的东西（未完成）。');
    expect(v2).toContain('阿青（人物）：精神值0，外貌袖口沾着灰、额头有伤，个性谨慎、开始怀疑阿白。');
    const legacy = render(result, 'legacy').text;
    expect(legacy).toContain('精神值50');
    expect(legacy).toContain('精神值变成0');
    expect(legacy).not.toContain('【本回合状态】');
    expect(legacy).not.toContain('精神值0，外貌');
  });

  it('keeps only changed items and lists the unchanged same-room items as omitted', () => {
    const before = tinyWorld();
    const { result } = project(before, {});
    expect(result.includedEntities.items).toEqual([]);
    expect(result.visibleEntities.items).toHaveLength(3);
    expect(result.visibleEntities.items).toEqual(expect.arrayContaining(['keepsake', 'lamp', 'note']));
    const omitted = result.omittedFields.filter((entry) => entry.entityType === 'item');
    expect(omitted.map((entry) => entry.entityName)).toEqual(expect.arrayContaining(['铜灯', '纸条', '旧照片']));
    expect(omitted.every((entry) => entry.reason === 'item_not_changed')).toBe(true);
    expect(result.projection.上回合状态.物品).toEqual({});
    expect(render(result).text).toContain('这一回合没有结算出变化。');
    expect(render(result).text).not.toContain('【本回合状态】');
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
      expect(Object.keys(result.projection.上回合状态.物品)).toContain(`杂物${id.split('_')[1]}`);
    }
  });

  it('uses the innermost location, not the slot, as the visibility boundary', () => {
    const before = tinyWorld();
    const { result } = project(before, {
      note: { entityId: 'note', appearanceChanges: [{ id: 'ch_note', text: '纸条展开了一角。', supersedes: [] }] },
      keepsake: { entityId: 'keepsake', appearanceChanges: [{ id: 'ch_photo', text: '照片上多了一道折痕。', supersedes: [] }] },
    });
    // hero is behind hall/slot_back, friend is at hall/slot_front; both are visible.
    expect(result.visibleEntities.characters).toEqual(['friend', 'hero']);
    expect(result.visibleEntities.characters).not.toContain('stranger');
    // note is inside hero's pocket; keepsake is inside the visible lamp.
    expect(result.visibleEntities.items).toEqual(['keepsake', 'note', 'lamp']);
    expect(result.includedEntities.items).toEqual(['keepsake', 'note']);
    expect(result.includedEntities.locations).toEqual(['hall']);
    const projection = result.projection;
    expect(projection.上回合状态.人物['阿青'].位置).toBe('大厅（窗边）');
    expect(projection.上回合状态.物品['纸条'].位置).toBe('阿青的衣袋（在大厅里）');
    expect(projection.上回合状态.物品['旧照片'].位置).toBe('铜灯（在大厅里）');
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
    expect(result.projection.本回合状态['阿灰']).toEqual({ 外貌: ['披着旧斗篷。', '斗篷湿了。'] });
  });

  it('includes a changed location and its immediate parent, not the whole ancestor chain', () => {
    const before = tinyWorld();
    const { result } = project(before, {
      towerRoom: { entityId: 'towerRoom', appearanceChanges: [{ id: 'ch_dust', text: '灰尘被扫开了。', supersedes: [] }] },
    });
    expect(result.includedEntities.locations).toEqual(expect.arrayContaining(['towerRoom', 'tower', 'hall']));
    expect(result.includedEntities.locations).not.toContain('garden');
    expect(result.projection.本回合状态['塔顶小屋']).toEqual({ 外貌: ['屋里落满灰。', '灰尘被扫开了。'] });
  });
});

describe('item positions and the result block', () => {
  it('keeps the item 位于 in v2 and reproduces the legacy loss only on the legacy path', () => {
    const before = tinyWorld();
    const { result } = project(before, {
      lamp: {
        entityId: 'lamp',
        positionSet: { containerId: 'garden', slotId: null, relativeTo: null },
        appearanceChanges: [{ id: 'ch_lamp', text: '灯罩裂了。', supersedes: [] }],
      },
    });
    expect(result.projection.上回合状态.物品['铜灯'].位置).toBe('大厅（门前）');
    expect(result.projection.本回合状态['铜灯']).toEqual({ 位置: '庭院', 外貌: ['灯罩擦得很亮。', '灯罩裂了。'] });
    const v2 = render(result).text;
    expect(v2).toContain('【物品】铜灯（位于大厅（门前））：灯罩擦得很亮。');
    expect(v2).toContain('铜灯（物品）：移动到庭院，多出外貌灯罩裂了。');
    expect(v2).toContain('【本回合状态】铜灯（物品）：位置庭院，外貌灯罩擦得很亮、灯罩裂了。');
    const legacy = render(result, 'legacy').text;
    expect(legacy).toContain('【物品】铜灯：灯罩擦得很亮。');
    expect(legacy).not.toContain('（位于大厅（门前））');
    expect(legacy).toContain('铜灯（物品）：移动到庭院，多出外貌灯罩裂了。');
    expect(legacy).not.toContain('【本回合状态】');
  });

  it('renders explicit zero and empty lists in the result block', () => {
    const world0 = tinyWorld();
    const before = applyDelta(world0, {
      blank: { entityId: 'blank', appearanceChanges: [{ id: 'ch_old', text: '旧外套', supersedes: [] }], personalityChanges: [{ id: 'ch_p_old', text: '旧脾气', supersedes: [] }] },
    });
    const { result } = project(before, {
      blank: {
        entityId: 'blank', sanitySet: 0,
        appearanceChanges: [{ id: 'ch_remove', text: null, supersedes: ['ch_old'] }],
        personalityChanges: [{ id: 'ch_p_remove', text: null, supersedes: ['ch_p_old'] }],
      },
    });
    expect(result.projection.上回合状态.人物['阿空'].外貌).toEqual(['旧外套']);
    expect(result.projection.本回合状态['阿空']).toEqual({ 精神值: 0, 外貌: [], 个性: [] });
    const v2 = render(result).text;
    expect(v2).toContain('阿空（人物）：精神值0，外貌（空），个性（空）。');
    const legacy = render(result, 'legacy').text;
    expect(legacy).toContain('阿空（人物）：精神值变成0，去掉外貌旧外套，去掉个性旧脾气。');
    expect(legacy).not.toContain('外貌（空）');
  });

  it('formats time-advance units and rejects an invalid one', () => {
    const before = tinyWorld();
    const hour = { boundary: 'elapsed' as const, duration: { amount: 2, unit: 'hour' as const } };
    expect(render(project(before, {}, 'hero', hour).result).text).toContain('时间推进2小时。');
    const month = { boundary: 'elapsed' as const, duration: { amount: 1, unit: 'month' as const } };
    expect(render(project(before, {}, 'hero', month).result).text).toContain('时间推进1个月。');
    expectCode(() => projectNarrationInput({
      before, after: before, delta: {}, timeAdvance: { boundary: 'elapsed', duration: { amount: Number.NaN, unit: 'minute' } }, viewpointId: 'hero',
    }), 'invalid_time');
  });
});

describe('task hierarchy and what the text can carry', () => {
  it('keeps the hierarchy in structured metadata while the text stays flat', () => {
    const before = tinyWorld();
    const { result } = project(before, {
      hero: {
        entityId: 'hero',
        tasksAchieved: ['task_grand'],
        subtasksAdded: [{ id: 'task_new', ownerId: 'hero', parentTaskId: 'task_child', goal: '把钥匙放回原处', status: 'pending' }],
      },
    });
    expect(result.projection.本回合状态['阿青']).toEqual({
      任务: {
        小任务: [
          { 目标: '打开木箱看清里面的东西', 状态: '已完成' },
          { 目标: '把钥匙放回原处', 状态: '未完成' },
        ],
      },
    });
    const grand = result.tasks.find((entry) => entry.taskId === 'task_grand')!;
    expect(grand.depth).toBe(2);
    expect(grand.parentGoal).toBe('问清地窖的钥匙在谁手里');
    expect(result.textCarryLimits).toEqual(expect.arrayContaining([
      expect.objectContaining({ taskId: 'task_grand', reason: 'task_parent_relation_not_in_v2_text' }),
      expect.objectContaining({ taskId: 'task_grand', reason: 'task_depth_not_in_v2_text' }),
      expect.objectContaining({ taskId: 'task_child', reason: 'task_parent_relation_not_in_v2_text' }),
    ]));
    expect(result.textCarryLimits.some((entry) => entry.taskId === 'task_child' && entry.reason === 'task_depth_not_in_v2_text')).toBe(false);

    const v2 = render(result).text;
    // The before-state line lists the big task and every small task, flat.
    expect(v2).toContain('任务找到父亲留下的箱子（未完成）；问清地窖的钥匙在谁手里（未完成）；打开木箱看清里面的东西（未完成）。');
    // The result line lists only the changed tasks, also flat.
    expect(v2).toContain('阿青（人物）：任务打开木箱看清里面的东西（已完成）；把钥匙放回原处（未完成）。');
    // The text never claims a parent relation or a depth.
    expect(v2).not.toContain('属于');
    expect(v2).not.toContain('大任务《');
    expect(v2).not.toContain('小任务《');
  });

  it('carries a changed root task as 大任务 and a changed child separately', () => {
    const before = tinyWorld();
    const { result } = project(before, {
      hero: { entityId: 'hero', tasksAchieved: ['task_root', 'task_grand'] },
    });
    expect(result.projection.本回合状态['阿青']).toEqual({
      任务: {
        大任务: { 目标: '找到父亲留下的箱子', 状态: '已完成' },
        小任务: [{ 目标: '打开木箱看清里面的东西', 状态: '已完成' }],
      },
    });
    expect(render(result).text).toContain('阿青（人物）：任务找到父亲留下的箱子（已完成）；打开木箱看清里面的东西（已完成）。');
  });
});

describe('projection errors', () => {
  it('rejects a delta whose after state does not reflect it', () => {
    const before = tinyWorld();
    expectCode(() => projectNarrationInput({
      before, after: before, delta: { hero: { entityId: 'hero', sanitySet: 0 } }, timeAdvance: TIME, viewpointId: 'hero',
    }), 'after_mismatch');
  });

  it('rejects an unknown delta entity', () => {
    const before = tinyWorld();
    expectCode(() => projectNarrationInput({
      before, after: before, delta: { ghost: { entityId: 'ghost' } }, timeAdvance: TIME, viewpointId: 'hero',
    }), 'unknown_entity');
  });

  it('rejects two included entities with the same name', () => {
    const before = tinyWorld();
    before.initial.characters.friend.name = '阿青';
    expectCode(() => project(before, {}), 'ambiguous_entity');
  });

  it('rejects a pure removal without a supersede target', () => {
    const before = tinyWorld();
    expectCode(() => project(before, {
      hero: { entityId: 'hero', appearanceChanges: [{ id: 'ch_bad', text: null, supersedes: [] }] },
    }), 'pure_removal_without_supersedes');
  });

  it('rejects a supersede target that is not active in the before state', () => {
    const before = tinyWorld();
    const after = structuredClone(before);
    after.characters.hero.appearanceChanges.push({
      id: 'ch_new', text: null, supersedes: ['nope'], sourcePointId: 'manual', sourceSequence: 99, active: true,
    });
    expectCode(() => projectNarrationInput({
      before,
      after,
      delta: { hero: { entityId: 'hero', appearanceChanges: [{ id: 'ch_new', text: null, supersedes: ['nope'] }] } },
      timeAdvance: TIME,
      viewpointId: 'hero',
    }), 'unresolved_supersedes');
  });

  it('rejects a character with no task tree instead of inventing one', () => {
    const before = tinyWorld();
    const delta = { blank: { entityId: 'blank', appearanceChanges: [{ id: 'ch_x', text: '衣角湿了。', supersedes: [] }] } };
    const after = applyDelta(before, delta);
    (before.characters.blank as unknown as { tasks?: Record<string, never> }).tasks = undefined;
    expectCode(() => projectNarrationInput({ before, after, delta, timeAdvance: TIME, viewpointId: 'hero' }), 'empty_tasks');
  });

  it('rejects more than one root task', () => {
    const initial = structuredClone(tinyWorld().initial) as InitialState;
    initial.characters.blank.tasks.blank_second = {
      id: 'blank_second', ownerId: 'blank', parentTaskId: null, goal: '第二个根任务', status: 'pending',
    };
    const world = buildInitialState(initial);
    expectCode(() => project(world, {
      blank: { entityId: 'blank', appearanceChanges: [{ id: 'ch_x', text: '衣角湿了。', supersedes: [] }] },
    }), 'multiple_task_roots');
  });

  it('rejects a task parent cycle', () => {
    const initial = structuredClone(tinyWorld().initial) as InitialState;
    initial.characters.hero.tasks.task_child.parentTaskId = 'task_grand';
    const world = buildInitialState(initial);
    expectCode(() => project(world, {}), 'position_cycle');
  });

  it('rejects a non-character viewpoint and a field that does not belong to the entity', () => {
    const before = tinyWorld();
    expectCode(() => project(before, {}, 'lamp'), 'invalid_projection');
    expectCode(() => projectNarrationInput({
      before, after: before, delta: { lamp: { entityId: 'lamp', sanitySet: 5 } }, timeAdvance: TIME, viewpointId: 'hero',
    }), 'field_not_allowed');
  });
});

describe('serializer binding and safety', () => {
  it('sorts names by code point, including non-BMP characters', () => {
    expect(compareCodePoints('Z', '\uE000')).toBeLessThan(0);
    expect(compareCodePoints('\uE000', '𝄞')).toBeLessThan(0);
    const initial = structuredClone(tinyWorld().initial) as InitialState;
    initial.characters.friend.name = '𝄞';
    initial.characters.stranger.name = '\uE000';
    initial.characters.stranger.initialPosition = { containerId: 'hall', slotId: null, relativeTo: null };
    initial.characters.blank.name = 'Z';
    initial.characters.blank.initialPosition = { containerId: 'hall', slotId: null, relativeTo: null };
    const world = buildInitialState(initial);
    const { result } = project(world, {});
    const text = renderNarrationInput(result.projection, { checkTokenizer: false }).text;
    const order = ['Z', '\uE000', '𝄞'].map((name) => text.indexOf(`${name}：`));
    expect(order[0]).toBeLessThan(order[1]);
    expect(order[1]).toBeLessThan(order[2]);
  });

  it('refuses newlines and unsupported whitespace instead of sending them to the model', () => {
    const before = tinyWorld();
    const newline = expectCode(() => render(project(before, {
      hero: { entityId: 'hero', appearanceChanges: [{ id: 'ch_nl', text: '外套\n湿了。', supersedes: [] }] },
    }).result), 'newline_not_allowed');
    expect(newline.stage).toBe('normalize');
    expect(newline.path).toBe('本回合变化/变化/阿青/新增外貌[0]');
    const nbsp = expectCode(() => render(project(before, {
      hero: { entityId: 'hero', appearanceChanges: [{ id: 'ch_nbsp', text: '外套\u00a0湿了。', supersedes: [] }] },
    }).result), 'unsupported_whitespace');
    expect(nbsp.stage).toBe('normalize');
  });

  it('squashes ordinary spaces and records the change', () => {
    const before = tinyWorld();
    const { result } = project(before, {
      hero: { entityId: 'hero', appearanceChanges: [{ id: 'ch_space', text: '外套 湿了。', supersedes: [] }] },
    }, 'hero', { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } });
    const v2 = render(result).text;
    expect(v2).toContain('时间推进2分钟。');
    expect(v2).not.toContain('2 分钟');
    expect(v2).toContain('多出外貌外套湿了');
    expect(render(result).normalization).toEqual(expect.arrayContaining([
      expect.objectContaining({ path: '本回合变化/时间推进', before: '2 分钟', after: '2分钟' }),
    ]));
  });

  it('refuses a character outside the YuYan vocabulary with the tokenizer stage', () => {
    const before = tinyWorld();
    const error = expectCode(() => render(project(before, {
      hero: { entityId: 'hero', appearanceChanges: [{ id: 'ch_emoji', text: '外套🚀湿了。', supersedes: [] }] },
    }).result), 'tokenizer_oov');
    expect(error.stage).toBe('tokenizer');
    expect(error.path).toMatch(/^index \d+$/);
  });

  it('throws on a configured limit instead of truncating, with measured sizes', () => {
    const before = tinyWorld();
    const error = expectCode(() => renderNarrationInput(project(before, {}).result.projection, {
      limits: { maxChars: 10 },
    }), 'input_too_long');
    expect(error.context.charCount).toBeGreaterThan(10);
    expect(error.context.utf8Bytes).toBeGreaterThan(10);
  });

  it('binds the serializer to the trained version and tokenizer hash', () => {
    const before = tinyWorld();
    const rendered = render(project(before, {}).result);
    expect(rendered.serializerVersion).toBe('yuyan-prose-result-v2');
    expect(rendered.version.projectionVersion).toBe('narration-result-view-v2');
    expect(rendered.version.tokenizerHash).toBe('20287a9d1a2ec9d82b2a13f02c10c7b81e8bb015f114134bca6b06e5c8d376b4');
    expect(rendered.version.tokenizerVocabSize).toBe(13668);
    const legacy = render(project(before, {}).result, 'legacy');
    expect(legacy.serializerVersion).toBe('yuyan-prose-legacy-v1');
    expect(legacy.version.projectionVersion).toBe('narration-result-view-v1');
    expect(legacy.version.tokenizerVocabSize).toBe(13668);
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

  it('adds only the result block to the legacy prefix when item rows are absent', () => {
    const before = tinyWorld();
    const noItems = structuredClone(before.initial) as InitialState;
    noItems.items = {};
    for (const character of Object.values(noItems.characters)) character.initialPosition = { containerId: 'hall', slotId: null, relativeTo: null };
    const world = buildInitialState(noItems);
    const { result } = project(world, { hero: { entityId: 'hero', sanitySet: 0 } });
    const v2 = render(result).text;
    const legacy = render(result, 'legacy').text;
    const block = '【本回合状态】阿青（人物）：精神值0。';
    expect(v2).toBe(legacy.replace('【正文】', `${block}【正文】`));
    expect(v2.endsWith('【正文】')).toBe(true);
  });
});
