import { describe, expect, test } from 'vitest';
import { actionViolations } from './licensed-action';

const INPUT = '【地点】走廊：明亮的走廊。【人物】周宁：在走廊。'
  + '【物品】盒子（属于周宁）：盒盖关闭。周宁的护目镜（属于周宁）：镜带松着，挂在胸前。';

describe('unlicensed posture and handling', () => {
  test('leaning on a wall is a micro-action, not a world-fact change', () => {
    expect(actionViolations('周宁靠在墙边，看着盒子。', INPUT)).toEqual([]);
  });

  test('an object put on the ground without a settled move is flagged', () => {
    const found = actionViolations('盒子躺在地上。', INPUT);
    expect(found.some((item) => item.kind === 'position')).toBe(true);
  });

  test('holding an object that hangs on the chest is flagged', () => {
    const found = actionViolations('周宁握着护目镜，指节发白。', INPUT);
    expect(found.some((item) => item.kind === 'hand' && item.object === '周宁的护目镜')).toBe(true);
  });

  test('a hand on an object with no stated position is not flagged', () => {
    expect(actionViolations('周宁握着盒子。', INPUT)).toEqual([]);
  });

  test('ordinary prose without these verbs is untouched', () => {
    expect(actionViolations('走廊的灯还亮着，盒子在墙角。', INPUT)).toEqual([]);
  });
});
