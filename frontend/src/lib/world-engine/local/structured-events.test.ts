import { describe, expect, it } from 'vitest';
import { buildTestWorld } from './semantics/actions/fixtures';
import { buildStructuredEvents } from './structured-events';

function states() {
  const before = buildTestWorld();
  const after = structuredClone(before);
  return { before, after };
}

describe('structured events adapter', () => {
  it('keeps actor, target, location, result and source from a settled fact', () => {
    const { before, after } = states();
    after.characters.hero.position = { containerId: 'study', slotId: null, relativeTo: null };
    const [event] = buildStructuredEvents({
      facts: [{ id: 'f1', memberId: 'hero', text: '路明非走进书房（达到目的）；去向=hero:study；涉及=ally' }],
      before, after, turn: 3,
    });
    expect(event).toMatchObject({
      actorId: 'hero', targetIds: ['ally'], location: 'study', result: 'completed',
      evidence: 'present', source: { factId: 'f1', turn: 3 },
    });
  });

  it('marks a completed move whose state disagrees as conflict', () => {
    const { before, after } = states();
    const [event] = buildStructuredEvents({
      facts: [{ id: 'f1', memberId: 'hero', text: '路明非走进书房（达到目的）；去向=hero:study' }],
      before, after,
    });
    expect(event.evidence).toBe('conflict');
  });

  it('keeps a fact without an outcome marker as insufficient', () => {
    const { before, after } = states();
    const [event] = buildStructuredEvents({
      facts: [{ id: 'f1', memberId: 'hero', text: '路明非看着门口。' }], before, after,
    });
    expect(event.evidence).toBe('insufficient');
    expect(event.result).toBe('unaffected');
  });
});
