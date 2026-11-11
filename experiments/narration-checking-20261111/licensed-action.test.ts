import { describe, expect, test } from 'vitest';
import { actionViolations, inventedObjectActions } from './licensed-action';

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

describe('inventedObjectActions (d101 dice)', () => {
  test('drops a pickup sentence whose object is not a world entity', () => {
    const text = '他猛地转身，手忙脚乱地抓起桌上的骰子。骰子在掌心转了个圈。';
    const found = inventedObjectActions(text, '路明非沿着服务巷往里走，先看清墙上的演习规则牌。', ['诺诺', '演习规则牌']);
    expect(found.map((row) => row.word)).toEqual(['抓起']);
  });

  test('keeps a pickup the settled text licensed and a real item', () => {
    expect(inventedObjectActions('他抓起对讲机。', '', ['对讲机'])).toEqual([]);
    expect(inventedObjectActions('他抓起对讲机。', '他抓起对讲机喊了一声。', ['对讲机'])).toEqual([]);
  });
});
