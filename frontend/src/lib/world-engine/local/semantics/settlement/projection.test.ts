import { describe, expect, it } from 'vitest';
import { buildTestWorld } from '../actions/fixtures';
import { projectPoint } from './projection';

describe('position projection', () => {
  it('includes the item and container named by a structured destination', () => {
    const state = buildTestWorld();
    const projection = projectPoint(state, state, {
      hero: '路明非把手电递给阿宁（达到目的）；去向=torch:ally',
    });
    expect(projection.affectedMovable).toContain('torch');
    expect(projection.affectedMovable).toContain('ally');
  });
});
