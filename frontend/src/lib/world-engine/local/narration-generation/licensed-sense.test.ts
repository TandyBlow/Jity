import { describe, expect, test } from 'vitest';
import { senseViolations } from './licensed-sense';

const INPUT = '【地点】走廊：明亮的走廊，通往门厅。【人物】周宁：在走廊。林川：在门厅，手里的短枪枪口压向地面。'
  + '【物品】盒子（在走廊里）：盒盖关闭。';

describe('unlicensed sense nouns', () => {
  test('an invented sound is named with its sentence', () => {
    const found = senseViolations('周宁站在走廊里，远处传来枪声。', INPUT);
    expect(found).toHaveLength(1);
    expect(found[0].noun).toBe('枪声');
  });

  test('a sound sourced by an entity named in the same sentence is allowed', () => {
    const input = `${INPUT}地下书库的除湿机一直响着。`;
    expect(senseViolations('走廊里只有除湿机的声音。', input)).toEqual([]);
  });

  test('a smell the input never mentions is flagged', () => {
    const found = senseViolations('空气里有硝烟味，盒子还在墙角。', INPUT);
    expect(found.some((item) => item.noun === '硝烟')).toBe(true);
  });

  test('a sense noun that the input itself uses is licensed', () => {
    const input = `${INPUT}走廊里有一阵风声。`;
    expect(senseViolations('风从走廊尽头钻进来，就是那阵风声。', input)).toEqual([]);
  });

  test('dialogue, actions and posture are not judged here', () => {
    expect(senseViolations('「走。」周宁蹲下，把盒子推开。', INPUT)).toEqual([]);
  });
});
