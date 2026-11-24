import { describe, expect, it } from 'vitest';
import { resolveRuleTargets } from './targets';

const scene = {
  visible: [{ id: 'ally', name: '阿宁' }, { id: 'rival', name: '沈砚' }],
  absent: [{ name: '小满' }],
};
const one = { visible: [{ id: 'ally', name: '阿宁' }], absent: [] as Array<{ name: string }> };

describe('micro targets rules', () => {
  it('names a directly mentioned visible character', () => {
    expect(resolveRuleTargets('我把水壶递给阿宁。', scene, 2)).toEqual(['ally']);
  });
  it('keeps every named visible character up to the cap', () => {
    expect(resolveRuleTargets('我把水递给阿宁和沈砚。', scene, 2)).toEqual(['ally', 'rival']);
    expect(resolveRuleTargets('我把水递给阿宁和沈砚。', scene, 1)).toEqual(['ally']);
  });
  it('resolves a pronoun only when exactly one character is visible', () => {
    expect(resolveRuleTargets('我把水递给他。', one, 2)).toEqual(['ally']);
    expect(resolveRuleTargets('我把水递给他。', scene, 2)).toBeNull();
  });
  it('resolves ordinals and group pronouns', () => {
    expect(resolveRuleTargets('我把水递给第二个人。', scene, 2)).toEqual(['rival']);
    expect(resolveRuleTargets('我把水递给他们。', scene, 2)).toEqual(['ally', 'rival']);
  });
  it('abstains when the action names an absent character', () => {
    expect(resolveRuleTargets('我把水递给小满。', scene, 2)).toBeNull();
  });
  it('returns empty for a no-target action', () => {
    expect(resolveRuleTargets('我在庭院里坐下。', scene, 2)).toEqual([]);
  });
  it('abstains on negation instead of guessing the addressee', () => {
    expect(resolveRuleTargets('我没有把水递给阿宁。', scene, 2)).toBeNull();
    expect(resolveRuleTargets('我没有犹豫，把钥匙递给阿宁。', scene, 2)).toBeNull();
  });
  it('keeps the named addressee of a compound action', () => {
    expect(resolveRuleTargets('我把钥匙交给阿宁，又拿了回来。', scene, 2)).toEqual(['ally']);
  });
});
