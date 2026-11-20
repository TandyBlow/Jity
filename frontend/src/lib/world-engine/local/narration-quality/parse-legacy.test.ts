import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { parseLegacyInput } from './parse-legacy';

const RECORD = new URL('../../../../../../../../results/quality/browser-09.json', import.meta.url);

describe('parseLegacyInput', () => {
  it('recovers the sample row byte-for-byte', () => {
    const text = '【视角】主角视角（周宁）【地点】走廊：明亮的走廊，通往门厅。【人物】林川：在走廊，精神值10，外貌穿灰衣，个性谨慎、恪守职责，任务留在走廊守门，不碰盒子（未完成）。周宁：在走廊，精神值10，外貌穿蓝衣，个性好奇，任务无。【物品】盒子（在走廊里）：盒盖关闭。【变化】时间推进1分钟。这一回合没有结算出变化。【正文】';
    const parsed = parseLegacyInput(text);
    expect(parsed).not.toBeNull();
    expect(parsed?.['上回合状态']?.人物?.['林川'].任务?.大任务).toEqual({ 目标: '留在走廊守门，不碰盒子', 状态: '未完成' });
  });

  it('round-trips the stored browser record', () => {
    const record = JSON.parse(readFileSync(RECORD, 'utf8')) as { runs: { input?: { text?: string } }[] };
    let total = 0;
    let ok = 0;
    const failed: string[] = [];
    for (const run of record.runs) {
      const text = run.input?.text;
      if (!text) continue;
      total += 1;
      if (parseLegacyInput(text)) ok += 1;
      else failed.push(text.slice(0, 60));
    }
    console.log(`parse round-trip ${ok}/${total}`);
    for (const sample of failed.slice(0, 6)) console.log('  fail:', sample);
    expect(total).toBeGreaterThan(0);
    expect(ok / total).toBeGreaterThan(0.9);
  });
});
