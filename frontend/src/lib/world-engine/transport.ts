import type { RequestMap, Scope, Success, WorldOperation, ErrorResponse } from './types';
export interface WorldTransport {
  execute<K extends WorldOperation>(operation: K, request: RequestMap[K], scope: Scope, signal?: AbortSignal): Promise<Success<K>>;
}
export class WorldApiError extends Error {
  readonly name = 'WorldApiError';
  constructor(readonly response: ErrorResponse) { super(response.error.code); }
}
export class WorldTimeoutError extends Error { readonly name = 'WorldTimeoutError'; }
