import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { EntityDelta, InitialState, TimeAdvance } from '../../types';
import { buildInitialState } from '../state';
import { projectNarrationInput } from './project';
import { buildNarrationInput, renderNarrationInput } from './pipeline';
import { applyDelta } from './test-fixtures';

const raw = JSON.parse(readFileSync(resolve('public/worlds/dragon-raja-free-day.world.json'), 'utf8')) as {
  initial: InitialState;
};
const TIME: TimeAdvance = { boundary: 'elapsed', duration: { amount: 4, unit: 'minute' } };

function project(before = buildInitialState(raw.initial), delta: Record<string, EntityDelta> = {}) {
  const after = applyDelta(before, delta, TIME);
  return {
    before,
    after,
    result: projectNarrationInput({ before, after, delta, timeAdvance: TIME, viewpointId: 'lu' }),
  };
}

function render(result: ReturnType<typeof project>['result'], model: 'result-v2' | 'legacy' = 'result-v2') {
  return renderNarrationInput(result.projection, { model }).text;
}

describe('free-day real world projection', () => {
  it('uses the two lane slots as one visible scene but does not pull in every lane item', () => {
    const before = buildInitialState(raw.initial);
    const delta: Record<string, EntityDelta> = {
      lu: {
        entityId: 'lu', sanitySet: 0,
        appearanceChanges: [{ id: 'ch_lu_coat', text: '校服肩头湿了一片。', supersedes: [] }],
      },
      goggles_lu: {
        entityId: 'goggles_lu',
        positionSet: { containerId: 'lane', slotId: 'slot_entry', relativeTo: null },
        appearanceChanges: [{ id: 'ch_goggles_strap', text: '镜带已经系紧。', supersedes: [] }],
      },
      lane: {
        entityId: 'lane',
        appearanceChanges: [{ id: 'ch_lane_puddle', text: '巷口多了一摊水。', supersedes: [] }],
      },
    };
    const { result } = project(before, delta);
    expect(result.visibleEntities.characters).toEqual(expect.arrayContaining(['lu', 'nono']));
    expect(result.includedEntities.characters).toEqual(expect.arrayContaining(['lu', 'nono']));
    expect(result.includedEntities.items).toEqual(['goggles_lu']);
    expect(result.includedEntities.locations).toEqual(expect.arrayContaining(['lane', 'west']));
    expect(result.includedEntities.locations).not.toContain('campus');
    expect(result.visibleEntities.locations).toEqual(expect.arrayContaining(['lane', 'west', 'campus']));
    expect(result.visibleEntities.items).toHaveLength(7);
    const omittedItems = result.omittedFields.filter((entry) => entry.entityType === 'item');
    expect(omittedItems.map((entry) => entry.entityName)).toEqual(expect.arrayContaining([
      '演习规则牌', '赛区路线图', '路明非的演习背心', '诺诺的演习短枪', '诺诺的故障短讯机', '诺诺的红色识别带',
    ]));
    expect(omittedItems.every((entry) => entry.reason === 'item_not_changed')).toBe(true);
    expect(result.projection.上回合状态.人物['路明非'].精神值).toBe(43);
    expect(result.projection.上回合状态.物品['路明非的护目镜'].位置).toBe('路明非的身上（在西侧服务巷里）');
    expect(result.projection.本回合状态['路明非']).toEqual({
      精神值: 0,
      外貌: expect.arrayContaining(['校服领口松着，膝盖沾了灰；护目镜挂在胸前，右手还空着，身上没有红蓝识别带。听见远处枪声会下意识缩肩。', '校服肩头湿了一片。']),
    });
    expect(result.projection.本回合状态['路明非的护目镜']).toEqual({
      位置: '西侧服务巷（器材棚门外）',
      外貌: expect.arrayContaining(['镜片无裂纹，镜带松着，现挂在胸前而非戴在眼前。', '镜带已经系紧。']),
    });
    expect(result.projection.本回合状态['西侧服务巷']).toMatchObject({ 外貌: expect.arrayContaining(['巷口多了一摊水。']) });

    const legacy = render(result, 'legacy');
    expect(legacy).not.toContain('【本回合状态】');
    expect(legacy).toContain('路明非：在西侧服务巷（低墙后的掩蔽处），精神值43');
    expect(legacy).toContain('精神值变成0');
    expect(legacy).toContain('路明非的护目镜（物品）：移动到西侧服务巷（器材棚门外），多出外貌镜带已经系紧。');
    expect(legacy).toContain('【物品】路明非的护目镜：');
    expect(legacy).not.toContain('【物品】路明非的护目镜（位于');

    const v2 = render(result);
    expect(v2).toContain('【本回合状态】西侧服务巷（地点）：外貌');
    expect(v2).toContain('路明非（人物）：精神值0，外貌');
    expect(v2).toContain('路明非的护目镜（物品）：位置西侧服务巷（器材棚门外），外貌');
    expect(v2).not.toContain('[object Object]');
    expect(v2).not.toContain('；外貌[');
  });

  it('drops a character from the visible set when only the child location changes', () => {
    const delta: Record<string, EntityDelta> = {
      lu: { entityId: 'lu', positionSet: { containerId: 'tower', slotId: null, relativeTo: null } },
    };
    const { result } = project(buildInitialState(raw.initial), delta);
    expect(result.visibleEntities.characters).toEqual(['lu']);
    expect(result.includedEntities.characters).toEqual(['lu']);
    expect(result.includedEntities.locations).toEqual(expect.arrayContaining(['tower', 'lane', 'west', 'campus']));
    const omitted = result.omittedFields.find((entry) => entry.entityId === 'nono');
    expect(omitted).toMatchObject({ reason: 'character_outside_scene' });
    expect(result.projection.本回合状态['路明非']).toEqual({ 位置: '钟楼' });
    expect(render(result)).toContain('路明非（人物）：位置钟楼。');
  });

  it('handles the opening with no delta without inventing an item set', () => {
    const { result } = project(buildInitialState(raw.initial), {});
    expect(result.projection.本回合变化.变化).toEqual({});
    expect(result.projection.本回合状态).toEqual({});
    expect(result.includedEntities.items).toEqual([]);
    expect(result.includedEntities.characters).toEqual(expect.arrayContaining(['lu', 'nono']));
    expect(result.includedEntities.locations).toEqual(expect.arrayContaining(['lane', 'west']));
    expect(Object.keys(result.projection.上回合状态.物品)).toEqual([]);
    const v2 = render(result);
    expect(v2).toContain('这一回合没有结算出变化。');
    expect(v2).not.toContain('【本回合状态】');
    const legacy = render(result, 'legacy');
    expect(legacy).toContain('这一回合没有结算出变化。');
    expect(legacy).not.toContain('【本回合状态】');
  });

  it('exposes the one-shot buildNarrationInput path for lane 02', () => {
    const before = buildInitialState(raw.initial);
    const after = applyDelta(before, {}, TIME);
    const out = buildNarrationInput({ before, after, delta: {}, timeAdvance: TIME, viewpointId: 'lu' });
    expect(out.rendered.serializerVersion).toBe('yuyan-prose-result-v2');
    expect(out.rendered.version.tokenizerHash).toBe('20287a9d1a2ec9d82b2a13f02c10c7b81e8bb015f114134bca6b06e5c8d376b4');
    expect(out.rendered.version.tokenizerVocabSize).toBe(13668);
    expect(out.projection.本回合变化.时间推进).toBe('4分钟');
    expect(out.projection).toEqual(out.rendered.projection);
    expect(out.rendered.text).toContain('时间推进4分钟。');
    expect(out.rendered.sha256).toHaveLength(64);
  });

  it('sorts Chinese names by code point, not by the zh locale', () => {
    const { result } = project(buildInitialState(raw.initial), {});
    const text = render(result);
    // 诺 U+8BFA < 路 U+8DEF, while a pinyin/zh collation puts 路 before 诺.
    expect(text.indexOf('诺诺：')).toBeLessThan(text.indexOf('路明非：'));
  });
});
