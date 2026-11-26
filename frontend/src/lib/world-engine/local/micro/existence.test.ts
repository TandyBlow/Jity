import { describe, expect, it } from 'vitest';
import { createMicroExistence } from './existence';

describe('existence shadow port', () => {
  it('returns the injected scores unchanged', async () => {
    const port = createMicroExistence({ scoring: async () => ({ env: 0.8, info: 0.1 }) });
    await expect(port('路明非把盖子提开。')).resolves.toEqual({ env: 0.8, info: 0.1 });
  });
  it('abstains when the scorer fails', async () => {
    const port = createMicroExistence({ scoring: async () => { throw new Error('missing model'); } });
    await expect(port('路明非把盖子提开。')).resolves.toBeNull();
  });
});
