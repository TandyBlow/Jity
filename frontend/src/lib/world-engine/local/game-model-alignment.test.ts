import { describe, expect, it } from 'vitest';
import { buildTestWorld } from './semantics/actions/fixtures';
import { alignmentPacket } from './game-model';

describe('narration position facts', () => {
  it('treats a slot change inside one location as at, not moved', () => {
    const before = buildTestWorld();
    const after = structuredClone(before);
    after.characters.hero.position = { containerId: 'hall', slotId: 'slot_counter' };
    const packet = alignmentPacket(before, {
      entityDeltas: { hero: { entityId: 'hero', positionSet: after.characters.hero.position } },
    }, after);
    expect(packet.facts.find((fact) => fact.id === 'hero:position')?.kind).toBe('at');
  });

  it('keeps a real location change as moved', () => {
    const before = buildTestWorld();
    const after = structuredClone(before);
    after.characters.hero.position = { containerId: 'study', slotId: null };
    const packet = alignmentPacket(before, {
      entityDeltas: { hero: { entityId: 'hero', positionSet: after.characters.hero.position } },
    }, after);
    expect(packet.facts.find((fact) => fact.id === 'hero:position')?.kind).toBe('moved');
  });
});
