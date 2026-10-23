/** B-only fault injection over a strict scenario oracle. No world apply,
 * dice, hashing or inferred success: accepted responses come from the
 * underlying corpus, and a lost response can only replay an actually
 * accepted exchange. Attempts, acceptances and replays remain separate. */
import { type ScenarioTransport, type ServedSnapshot } from './harness';
import { ProtocolError, validateError, validateRequest, validateSuccess } from './protocol';
import { errorBodyFor, errorCatalog } from './schedule';
import { equal } from './trace-runner';
import { WorldApiError, WorldTimeoutError, type WorldTransport } from './transport';
import type { ErrorCode, Json, RequestMap, Scope, Success, WorldOperation } from './types';

export type FaultAction =
  | { kind: 'timeout_before_send' }
  | { kind: 'lose_response' }
  | { kind: 'error'; code: ErrorCode; details?: Record<string, Json>; snapshot?: Partial<ServedSnapshot>; /** Bridge for the refresh_context hop, decoupled from the error envelope: a driver that skips or ignores the hop binds the envelope's (stale) state, so only a bridge-only delta pins adoption. */ bridge?: Partial<ServedSnapshot> };

export interface FaultRule {
  stepId: string;
  operation?: WorldOperation;
  /** Finite, explicit script; once exhausted the oracle or ledger responds. */
  actions: FaultAction[];
}

export interface FaultAttempt {
  stepId: string | null;
  operation: WorldOperation;
  request: Json;
  scope: Scope;
  outcome: 'pending' | 'accepted' | 'replayed' | 'timeout_before_send' | 'lost_response' | 'error' | 'context_bridge';
  code?: ErrorCode;
}

interface ObservedWrite {
  operation: WorldOperation;
  request: Json;
  scope: Scope;
  stepId: string | null;
  response?: Json;
  retired: boolean;
}

export class FaultTransport implements WorldTransport {
  readonly attempts: FaultAttempt[] = [];
  readonly acceptances: { stepId: string | null; operation: WorldOperation; request: Json; response: Json }[] = [];
  private readonly writes = new Map<string, ObservedWrite>();
  private readonly scripts: FaultRule[];
  private latest: Record<string, Json> = {};
  private contextBridge: Partial<ServedSnapshot> | null = null;

  constructor(readonly oracle: ScenarioTransport, rules: FaultRule[], initial?: Json, private readonly activeInput: Json = null) {
    this.scripts = structuredClone(rules);
    if (initial) this.latest = structuredClone(initial) as Record<string, Json>;
  }

  private snapshot(overrides?: Partial<ServedSnapshot>): Record<string, Json> {
    const value: Record<string, Json> = {};
    for (const key of ['world', 'control', 'work'] as const) {
      const candidate = overrides && Object.hasOwn(overrides, key) ? overrides[key] : this.latest[key];
      if (candidate !== undefined) value[key] = structuredClone(candidate) as unknown as Json;
    }
    return value;
  }

  private error(operation: WorldOperation, request: Record<string, unknown>, scope: Scope, code: ErrorCode, details: Record<string, Json> = {}, overrides?: Partial<ServedSnapshot>): WorldApiError {
    const response = validateError({
      protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1',
      serverTimeEpochMilli: this.latest.serverTimeEpochMilli ?? 1,
      replayed: false, operation, requestId: request.requestId ?? null, worldId: scope.worldId ?? request.worldId ?? null,
      error: errorBodyFor(code, details), ...this.snapshot(overrides),
    });
    return new WorldApiError(response);
  }

  async execute<K extends WorldOperation>(operation: K, request: RequestMap[K], scope: Scope): Promise<Success<K>> {
    validateRequest(operation, request);
    const fields = request as Record<string, unknown>;
    const requestId = fields.requestId;
    const key = typeof requestId === 'string' ? JSON.stringify([scope.worldId ?? fields.worldId ?? 'create', requestId]) : null;
    const seen = key ? this.writes.get(key) : undefined;
    const stepId = seen?.stepId ?? this.oracle.nextStepId;
    const attempt: FaultAttempt = { stepId, operation, request: structuredClone(request) as unknown as Json, scope: structuredClone(scope), outcome: 'pending' };
    this.attempts.push(attempt);
    if (seen) {
      if (seen.operation !== operation || !equal(seen.scope, scope) || !equal(seen.request, request)) {
        attempt.outcome = 'error'; attempt.code = 'request_id_reused';
        throw this.error(operation, fields, scope, 'request_id_reused');
      }
      if (seen.retired) throw new ProtocolError(`[fault] retired requestId ${String(requestId)} was reused after a definitive rejection`);
    } else if (key) {
      this.writes.set(key, { operation, request: structuredClone(request) as unknown as Json, scope: structuredClone(scope), stepId, retired: false });
    }
    const observed = key ? this.writes.get(key) : undefined;

    const action = this.scripts.find((rule) => rule.stepId === stepId && (rule.operation === undefined || rule.operation === operation) && rule.actions.length > 0)?.actions.shift();
    if (action?.kind === 'timeout_before_send') {
      attempt.outcome = 'timeout_before_send';
      throw new WorldTimeoutError('injected timeout before oracle acceptance');
    }
    if (action?.kind === 'error') {
      attempt.outcome = 'error'; attempt.code = action.code;
      if (errorCatalog[action.code].clientAction === 'refresh_context') this.contextBridge = action.bridge ?? action.snapshot ?? {};
      if (observed && action.code !== 'request_in_progress') observed.retired = true;
      throw this.error(operation, fields, scope, action.code, action.details, action.snapshot);
    }

    // Only a refresh_context recovery may consume this B-authored bridge.
    // Its snapshot is the declared post-rejection state, never an apply.
    if (operation === 'get_context' && this.contextBridge !== null) {
      const world = this.snapshot(this.contextBridge).world as unknown as { worldId: string; advance?: { inputAvailable: boolean; advanceId: string; inputId: string } } | null;
      if (!world?.advance) throw new ProtocolError('[fault] bridge snapshot lacks world.advance');
      if (!equal(request, {}) || !equal(scope, { worldId: world.worldId })) throw new ProtocolError('[fault] refresh context request/scope mismatch');
      const response = validateSuccess('get_context', {
        protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1',
        serverTimeEpochMilli: this.latest.serverTimeEpochMilli ?? 1,
        ...this.snapshot(this.contextBridge),
        activeInput: world.advance.inputAvailable ? structuredClone(this.activeInput) : null,
        recovery: null,
      });
      this.contextBridge = null;
      this.latest = structuredClone(response) as unknown as Record<string, Json>;
      attempt.outcome = 'context_bridge';
      return response as unknown as Success<K>;
    }

    let response: Success<K>;
    if (observed?.response) {
      const replay = structuredClone(observed.response) as Record<string, Json>;
      Object.assign(replay, this.snapshot(), { replayed: true, requestId });
      // A claim replay is only a summary; it cannot resurrect a claim token.
      if (operation === 'narration_claim') delete (replay.data as Record<string, Json>).claimToken;
      response = validateSuccess(operation, replay);
      attempt.outcome = 'replayed';
    } else {
      response = await this.oracle.execute(operation, request as never, scope as never) as unknown as Success<K>;
      this.acceptances.push({ stepId, operation, request: structuredClone(request) as unknown as Json, response: structuredClone(response) as unknown as Json });
      if (observed) observed.response = structuredClone(response) as unknown as Json;
      attempt.outcome = 'accepted';
    }
    this.latest = structuredClone(response) as unknown as Record<string, Json>;
    if (action?.kind === 'lose_response') {
      if (!observed) throw new ProtocolError('[fault] response loss script requires an idempotent write');
      attempt.outcome = 'lost_response';
      throw new WorldTimeoutError('injected response loss after acceptance');
    }
    return response;
  }

  assertFaultsConsumed(): void {
    const remaining = this.scripts.filter((rule) => rule.actions.length > 0);
    if (remaining.length > 0) throw new ProtocolError(`[fault] unconsumed scripts: ${remaining.map((rule) => rule.stepId).join(', ')}`);
  }
}
