import { operationRegistry, protocolHeader, ProtocolError, validateError, validateRequest, validateSuccess } from './protocol';
import { WorldApiError, WorldTimeoutError, type WorldTransport } from './transport';
import type { RequestMap, Scope, Success, WorldOperation } from './types';

export class HttpWorldTransport implements WorldTransport {
  private readonly base: URL;
  constructor(baseUrl: string, private readonly fetcher: typeof fetch = fetch, private readonly timeoutMs = 15000) {
    this.base = new URL(baseUrl.endsWith('/') ? baseUrl : baseUrl + '/');
    if (!['https:', 'http:'].includes(this.base.protocol) || !Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new ProtocolError('Invalid transport configuration');
  }
  async execute<K extends WorldOperation>(operation: K, input: RequestMap[K], scope: Scope, signal?: AbortSignal): Promise<Success<K>> {
    const request = validateRequest(operation, input);
    const spec = operationRegistry[operation];
    const fields = request as unknown as Record<string, unknown>;
    const path = spec.path.replace(/\{(worldId|pointId)\}/g, (_, key: 'worldId' | 'pointId') => {
      const value = scope[key] ?? fields[key];
      if (typeof value !== 'string' || !value.length) throw new ProtocolError(`Missing path ${key}`);
      if (fields[key] !== undefined && fields[key] !== value) throw new ProtocolError(`Path ${key} differs from request`);
      return encodeURIComponent(value);
    });
    // Keep an optional deployment path prefix such as /api; registry paths are absolute to the API.
    const url = new URL(path.replace(/^\//, ''), this.base);
    const headers = new Headers({ [protocolHeader]: '2', Accept: 'application/json' });
    let body: string | undefined;
    if (spec.method === 'GET' || spec.method === 'DELETE') {
      for (const key of spec.queryBindings) if (fields[key] !== undefined && fields[key] !== null) url.searchParams.set(key, String(fields[key]));
    } else { headers.set('Content-Type', 'application/json'); body = JSON.stringify(request); }
    const controller = new AbortController();
    let timedOut = false;
    const abort = () => controller.abort(signal?.reason);
    if (signal?.aborted) abort();
    else signal?.addEventListener('abort', abort, { once: true });
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, this.timeoutMs);
    // A timeout must settle even if a supplied fetch implementation ignores abort.
    let rejectAbort: ((reason: unknown) => void) | undefined;
    const aborted = new Promise<never>((_, reject) => { rejectAbort = reject; });
    const rejectOnAbort = () => rejectAbort?.(timedOut ? new WorldTimeoutError('World request timed out; retry with the same requestId') : new DOMException('Aborted', 'AbortError'));
    controller.signal.addEventListener('abort', rejectOnAbort, { once: true });
    if (controller.signal.aborted) rejectOnAbort();
    try {
      return await Promise.race([aborted, (async (): Promise<Success<K>> => {
        const response = await this.fetcher(url, { method: spec.method, headers, body, signal: controller.signal });
        let value: unknown;
        try { value = await response.json(); } catch { throw new ProtocolError('Invalid JSON response'); }
        if (!response.ok) {
          const error = validateError(value);
          if (response.status !== error.error.httpStatus || !spec.errorCodes.some((e) => e.code === error.error.code)) throw new ProtocolError('HTTP/error contract mismatch');
          if (error.operation !== null && error.operation !== operation) throw new ProtocolError('Error operation mismatch');
          if (fields.requestId && error.requestId !== null && error.requestId !== fields.requestId) throw new ProtocolError('Error requestId mismatch');
          throw new WorldApiError(error);
        }
        if (response.status !== spec.successHttpStatus) throw new ProtocolError('Unexpected success status');
        const result = validateSuccess<K>(operation, value);
        if ('requestId' in result && fields.requestId !== result.requestId) throw new ProtocolError('Response requestId mismatch');
        const worldId = scope.worldId ?? fields.worldId;
        if (worldId && result.world.worldId !== worldId) throw new ProtocolError('Response worldId mismatch');
        return result;
      })()]);
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
      controller.signal.removeEventListener('abort', rejectOnAbort);
    }
  }
}
