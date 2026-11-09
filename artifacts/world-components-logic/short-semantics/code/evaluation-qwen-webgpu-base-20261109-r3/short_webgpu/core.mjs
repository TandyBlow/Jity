/* Pure transport and completion guards, shared by Worker and Node tests.
 * These checks make no action/result/state judgment. */
export const identityFields = Object.freeze([
  'requestId', 'requestSha256', 'generation', 'component', 'inputSha256',
  'messagesSha256', 'bindingSha256', 'codec', 'modelIdentity',
  'runtimeIdentity', 'codeIdentity',
]);

export function identity(request) {
  return Object.fromEntries(identityFields.map(k => [k, request[k]]));
}

export async function sha256(text) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))))
    .map(x => x.toString(16).padStart(2, '0')).join('');
}

export async function verifyRequest(request, config) {
  if (!Number.isSafeInteger(request.generation) || request.generation < 0) throw Error('invalid_generation');
  for (const key of ['modelIdentity', 'runtimeIdentity', 'codeIdentity']) {
    if (request[key] !== config[key]) throw Error('asset_identity_mismatch:' + key);
  }
  if (request.enableThinking !== false) throw Error('thinking_mode_changed');
  if (typeof request.deadlineUnixMs !== 'number' || !Number.isFinite(request.deadlineUnixMs)) throw Error('invalid_deadline');
  if (Date.now() >= request.deadlineUnixMs) throw Error('timeout_before_model');
  for (const [text, hash] of [['inputJson', 'inputSha256'], ['messagesJson', 'messagesSha256'], ['bindingJson', 'bindingSha256']]) {
    if (typeof request[text] !== 'string' || await sha256(request[text]) !== request[hash]) throw Error('input_identity_mismatch:' + text);
  }
  const messages = JSON.parse(request.messagesJson);
  if (!Array.isArray(messages) || !messages.length || messages.some(m => typeof m.content !== 'string')) throw Error('invalid_messages');
  const user = messages.find(m => m.role === 'user');
  const envelope = user && JSON.parse(user.content);
  if (envelope?.component !== request.component || !Object.hasOwn(envelope, 'context')) throw Error('missing_complete_context');
  // Compare parsed complete inputs, preserving the canonical JSON text as the
  // audit authority. Neither path selects facts or truncates the world.
  if (JSON.stringify(envelope.context) !== JSON.stringify(JSON.parse(request.inputJson))) throw Error('context_not_complete');
  for (const key of ['maxInputTokens', 'maxNewTokens']) {
    if (!Number.isSafeInteger(request[key]) || request[key] < 1) throw Error('invalid_token_budget');
  }
  return messages;
}

export function checkTokens(inputIds, rawIds, request, config) {
  const valid = xs => Array.isArray(xs) && xs.every(x => Number.isSafeInteger(x) && x >= 0);
  if (!valid(inputIds) || !inputIds.length || !valid(rawIds)) throw Error('invalid_tokens');
  if (inputIds.length > request.maxInputTokens || inputIds.length + request.maxNewTokens > config.maxContextTokens) {
    throw Error('complete_context_exceeds_frozen_token_limit');
  }
  if (!rawIds.length || rawIds.length > request.maxNewTokens) throw Error('output_token_limit');
  if (!config.eosTokenIds.includes(rawIds.at(-1))) throw Error('truncated_no_eos');
  if (rawIds.slice(0, -1).some(x => config.eosTokenIds.includes(x))) throw Error('tokens_after_eos');
}

export function classifyStop(request, {cancelled, lost, now = Date.now()}) {
  if (lost) return 'device_lost';
  if (cancelled) return 'cancelled';
  if (now >= request.deadlineUnixMs) return 'timeout';
  return null;
}

// Page-side resource ownership. A server already rejects stale semantic output;
// this additionally prevents an old Worker callback from clearing a new timer.
export class WorkerRequestGate {
  constructor() { this.worker = null; this.active = null; this.epoch = 0; }
  bind(worker) {
    if (this.active) throw Error('cannot_replace_worker_with_active_request');
    this.worker = worker; this.epoch += 1;
  }
  begin(request) {
    if (!this.worker || this.active) throw Error('worker_unavailable_or_busy');
    if (!request.requestId || !Number.isSafeInteger(request.generation)) throw Error('invalid_request_identity');
    const lease = {worker: this.worker, epoch: this.epoch, request, timer: null};
    this.active = lease;
    return lease;
  }
  owns(lease) {
    return Boolean(lease && this.active === lease && this.worker === lease.worker && this.epoch === lease.epoch);
  }
  responseLease(worker, response) {
    const lease = this.active;
    return this.owns(lease) && worker === lease.worker
      && response.requestId === lease.request.requestId && response.generation === lease.request.generation ? lease : null;
  }
  finish(lease) {
    if (!this.owns(lease)) return false;
    this.active = null;
    return true;
  }
}
