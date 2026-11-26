import { describe, expect, it } from 'vitest';
import { buildTestWorld, withPosition } from '../semantics/actions/fixtures';
import { factContradictsPresence, programTransferAllowed } from './results';

describe('micro results transfer guard', () => {
  it('confirms putting a held item into an item container in the room', () => {
    const state = buildTestWorld();
    expect(programTransferAllowed({
      text: '我把手电塞进木箱顶。', category: 'use',
      destination: { entityId: 'torch', containerId: 'crate', slotId: 'slot_top' }, memberId: 'hero', state,
    })).toBe(true);
  });

  it('confirms a transfer when the item is held and the target is in the room', () => {
    const state = buildTestWorld();
    expect(programTransferAllowed({
      text: '我把手电递给阿宁。', category: 'assist',
      destination: { entityId: 'torch', containerId: 'ally' }, memberId: 'hero', state,
    })).toBe(true);
  });

  it('does not confirm when the target is outside the room', () => {
    const state = withPosition(buildTestWorld(), 'ally', { containerId: 'study' });
    expect(programTransferAllowed({
      text: '我把手电递给阿宁。', category: 'assist',
      destination: { entityId: 'torch', containerId: 'ally' }, memberId: 'hero', state,
    })).toBe(false);
  });

  it('does not confirm when the item is not in the actor hands', () => {
    const state = withPosition(buildTestWorld(), 'torch', { containerId: 'study' });
    expect(programTransferAllowed({
      text: '我把手电递给阿宁。', category: 'assist',
      destination: { entityId: 'torch', containerId: 'ally' }, memberId: 'hero', state,
    })).toBe(false);
  });

  it('does not confirm an obstructed transfer', () => {
    const state = buildTestWorld();
    expect(programTransferAllowed({
      text: '我想把手电递给阿宁，却没有开口。', category: 'assist',
      destination: { entityId: 'torch', containerId: 'ally' }, memberId: 'hero', state,
    })).toBe(false);
  });

  it('detects a fact that claims a visible character is absent', () => {
    expect(factContradictsPresence('巷里却没有诺诺。', ['诺诺'])).toBe(true);
    expect(factContradictsPresence('诺诺接过护目镜。', ['诺诺'])).toBe(false);
    expect(factContradictsPresence('唐骁不在庭院。', ['唐骁'])).toBe(true);
  });
});
