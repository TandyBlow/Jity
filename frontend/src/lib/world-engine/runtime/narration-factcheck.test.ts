import { describe, expect, it } from 'vitest';
import type { NarrationFact } from './committed-narration';
import { checkFacts, type FactCheckInput } from './narration-factcheck';

const input = (facts: NarrationFact[], time: FactCheckInput['time'] = null): FactCheckInput => ({
  facts, time, locations: ['走廊', '门厅'], roster: ['林川', '周宁'],
});
const at = (id: 'a' | 'c', location: string): NarrationFact =>
  ({ id: `${id}:pos`, actorId: id, name: id === 'a' ? '林川' : '周宁', kind: 'at', locationId: location, location });
const sanity = (id: 'a' | 'c', value: number): NarrationFact =>
  ({ id: `${id}:san`, actorId: id, name: id === 'a' ? '林川' : '周宁', kind: 'sanity', value });
const moved = (id: 'a' | 'c', from: string, to: string): NarrationFact =>
  ({ id: `${id}:move`, actorId: id, name: id === 'a' ? '林川' : '周宁', kind: 'moved', fromId: from, from, toId: to, to });
const task = (id: 'a' | 'c', goal: string): NarrationFact =>
  ({ id: `${id}:task`, actorId: id, name: id === 'a' ? '林川' : '周宁', kind: 'task_achieved', taskId: 't', goal });

const TIME = { amount: 1, unit: 'second' as const };

describe('independent fact check', () => {
  it('accepts the complete opening with two equal sanity values', () => {
    const facts = [at('a', '走廊'), sanity('a', 10), at('c', '走廊'), sanity('c', 10)];
    const result = checkFacts(input(facts), '林川位于走廊。林川的精神值为10。周宁位于走廊。周宁的精神值为10。');
    expect(result.problems).toEqual([]);
    expect(result.ok).toBe(true);
    expect(result.covered).toHaveLength(4);
  });

  it('accepts a move with both endpoints plus the unchanged actor facts and time', () => {
    const facts = [moved('c', '走廊', '门厅'), at('a', '走廊'), sanity('a', 10), sanity('c', 8)];
    const result = checkFacts(input(facts, TIME),
      '约一秒过去了。林川位于走廊，精神值为10。周宁从走廊走到门厅，精神值为8。');
    expect(result.problems).toEqual([]);
    expect(result.ok).toBe(true);
  });

  it('requires both endpoints of a move (stricter than the aligner)', () => {
    const facts = [moved('c', '走廊', '门厅'), at('a', '走廊'), sanity('a', 10), sanity('c', 8)];
    const result = checkFacts(input(facts, TIME), '一秒过去了。林川在走廊。周宁走进了门厅。周宁的精神值为8。');
    expect(result.ok).toBe(false);
    expect(result.problems.some((problem) => problem.kind === 'missing' && problem.factId === 'c:move')).toBe(true);
  });

  it('flags a missing fact, an actor swap, a wrong number and a reversed direction', () => {
    const facts = [moved('a', '走廊', '门厅'), sanity('a', 10), at('c', '走廊'), sanity('c', 8)];
    const missing = checkFacts(input(facts, TIME), '一秒过去了。林川从走廊走到门厅。周宁位于走廊。');
    expect(missing.problems.some((problem) => problem.kind === 'missing' && problem.factId === 'c:san')).toBe(true);
    const swapped = checkFacts(input(facts, TIME), '一秒过去了。周宁从走廊走到门厅。周宁的精神值为8。');
    expect(swapped.problems.some((problem) => problem.kind === 'actor')).toBe(true);
    const wrong = checkFacts(input(facts, TIME), '一秒过去了。林川从走廊走到门厅。周宁位于走廊。周宁的精神值为9。');
    expect(wrong.problems.some((problem) => problem.kind === 'number')).toBe(true);
    const reversed = checkFacts(input(facts, TIME), '一秒过去了。林川从门厅走到走廊。周宁位于走廊。周宁的精神值为8。');
    expect(reversed.problems.some((problem) => problem.kind === 'direction')).toBe(true);
  });

  it('requires the task goal and description text verbatim', () => {
    const facts = [at('a', '走廊'), sanity('a', 10), at('c', '走廊'), sanity('c', 8), task('c', '完成压力试验')];
    const exact = checkFacts(input(facts), '林川位于走廊，精神值为10。周宁位于走廊，精神值为8，完成了任务「完成压力试验」。');
    expect(exact.problems).toEqual([]);
    const paraphrased = checkFacts(input(facts), '林川位于走廊，精神值为10。周宁位于走廊，精神值为8，完成了「压力试验」。');
    expect(paraphrased.problems.some((problem) => problem.kind === 'frozen_text')).toBe(true);
  });

  it('flags an event verb, an unknown placement, an extra number and a missing time', () => {
    const facts = [at('a', '走廊'), sanity('a', 10), at('c', '走廊'), sanity('c', 8)];
    const event = checkFacts(input(facts, TIME), '一秒过去了。林川位于走廊，精神值为10。周宁推开走廊的门，精神值为8。');
    expect(event.problems.some((problem) => problem.kind === 'added')).toBe(true);
    const placement = checkFacts(input(facts, TIME), '一秒过去了。林川位于门厅，精神值为10。周宁位于走廊，精神值为8。');
    expect(placement.problems.some((problem) => problem.kind === 'added')).toBe(true);
    const number = checkFacts(input(facts, TIME), '一秒过去了。林川位于走廊，精神值为10。周宁位于走廊，精神值为8，走了3步。');
    expect(number.problems.some((problem) => problem.kind === 'number')).toBe(true);
    const time = checkFacts(input(facts, TIME), '林川位于走廊，精神值为10。周宁位于走廊，精神值为8。');
    expect(time.problems.some((problem) => problem.kind === 'time')).toBe(true);
  });

  it('rejects a standing value written as a change and unlicensed intent or meta talk', () => {
    const facts = [at('a', '走廊'), sanity('a', 10), at('c', '走廊'), sanity('c', 10)];
    const changed = checkFacts(input(facts), '林川位于走廊，精神值已降至10。周宁位于走廊，精神值为10。');
    expect(changed.problems.some((problem) => problem.kind === 'added' && problem.detail.includes('站定值'))).toBe(true);
    const intent = checkFacts(input(facts), '林川位于走廊，两人正准备前往某个目的地，精神值为10。周宁位于走廊，精神值为10。');
    expect(intent.problems.some((problem) => problem.kind === 'added')).toBe(true);
    const meta = checkFacts(input(facts), '林川位于走廊，精神值为10。周宁位于走廊，精神值为10，与事实完全一致。');
    expect(meta.problems.some((problem) => problem.kind === 'added')).toBe(true);
  });

  it('allows a movement verb only when the point has a moved fact', () => {
    const still = checkFacts(input([at('a', '走廊'), sanity('a', 10)]), '林川位于走廊，精神值为10，准备走进门厅。');
    expect(still.problems.some((problem) => problem.kind === 'added')).toBe(true);
    const moving = checkFacts(input([moved('a', '走廊', '门厅'), sanity('a', 10)]), '林川从走廊前往门厅，精神值为10。');
    expect(moving.problems.filter((problem) => problem.detail.includes('移动动词'))).toEqual([]);
  });

  it('does not call a missing shared location an actor swap', () => {
    const facts = [at('a', '走廊'), sanity('a', 10), at('c', '走廊'), sanity('c', 10)];
    const result = checkFacts(input(facts), '林川位于走廊，精神值为10。');
    expect(result.problems.some((problem) => problem.kind === 'actor')).toBe(false);
    expect(result.problems.some((problem) => problem.kind === 'missing' && problem.factId === 'c:pos')).toBe(true);
  });

  it('rejects an empty output', () => {
    const result = checkFacts(input([at('a', '走廊'), sanity('a', 10)]), '   ');
    expect(result.ok).toBe(false);
    expect(result.problems[0].kind).toBe('empty');
  });
});
