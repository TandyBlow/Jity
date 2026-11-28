import { describe, expect, it } from 'vitest';
import fixture from './boundary-model-fixture.json';
import { boundaryDecision, boundaryScore } from './boundary-model';

const NAMES = ['路明非', '诺诺', '芬格尔', '秦越', '林亦舟', '楚子航', '凯撒', '顾岚', '唐骁', '夏弥', '绘梨衣',
  '曼施坦因', '苏茜', '沈澄', '周映', '富山雅史', '阿豹', '对方'];

describe('boundary model parity', () => {
  it('reproduces the exported asset scores on real pairs', () => {
    for (const row of fixture as Array<{ textA: string; kindA: string; textB: string; kindB: string; prev: string; next: string; score: number; pred: number }>) {
      const pair = { textA: row.textA, kindA: row.kindA, textB: row.textB, kindB: row.kindB, prev: row.prev, next: row.next };
      expect(boundaryScore(pair, NAMES)).toBeCloseTo(row.score, 3);
      expect(boundaryDecision(pair, NAMES)).toBe(row.pred === 1);
    }
  });
});
