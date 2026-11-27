import { describe, expect, it } from 'vitest';
import { createMicroExtraction } from './extraction';

describe('extraction port', () => {
  it('returns injected clause scores unchanged', async () => {
    const port = createMicroExtraction({ scoring: async () => [{ clause: '锁梁完整', score: 0.9 }] });
    await expect(port('查看锁梁', ['锁梁完整'])).resolves.toEqual([{ clause: '锁梁完整', score: 0.9 }]);
  });
  it('abstains when the scorer fails', async () => {
    const port = createMicroExtraction({ scoring: async () => { throw new Error('missing model'); } });
    await expect(port('查看锁梁', ['锁梁完整'])).resolves.toBeNull();
  });
});
