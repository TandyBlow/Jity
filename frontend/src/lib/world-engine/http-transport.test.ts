import { describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { HttpWorldTransport } from './http-transport';
import { protocolHeader } from './protocol';
import type { Success, WorldOperation } from './types';

const root = new URL('../../../../design/world-protocol/v2/', import.meta.url);
const load = <T = unknown>(name: string): T => JSON.parse(readFileSync(new URL(name, root), 'utf8'));

/**
 * Chromium's native fetch throws TypeError("Illegal invocation") when its
 * receiver is anything but the global object — exactly what the transport's
 * `this.fetcher(...)` call site used to do with the unbound default. This
 * stub reproduces that contract in Node, where undici tolerates any receiver
 * and the defect was invisible.
 */
function chromiumLikeFetch(this: unknown, url: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  if (this !== undefined && this !== globalThis) throw new TypeError("Failed to execute 'fetch' on 'Window': Illegal invocation");
  const success = load<typeof success>('fixtures/api/get_context/success.json') as Success<'get_context'>;
  expect(String(url)).toBe('https://example.invalid/api/worlds/world_school/context');
  expect(new Headers(init?.headers).get(protocolHeader)).toBe('2');
  return Promise.resolve(Response.json(success, { status: 200 }));
}

describe('HttpWorldTransport default fetch binding', () => {
  it('calls the platform fetch with a legal receiver when no fetcher is injected', async () => {
    vi.stubGlobal('fetch', chromiumLikeFetch);
    try {
      const transport = new HttpWorldTransport('https://example.invalid/api');
      const success = await transport.execute('get_context', {}, { worldId: 'world_school' });
      expect(success.world.worldId).toBe('world_school');
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('rejects before any network work when the base URL is invalid', () => {
    expect(() => new HttpWorldTransport('ftp://example.invalid')).toThrow(/Invalid transport configuration/);
  });
});
