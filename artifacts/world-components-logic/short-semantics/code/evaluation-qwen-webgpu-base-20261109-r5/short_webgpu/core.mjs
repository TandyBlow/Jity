/* Pure transport and completion guards, shared by Worker and Node tests.
 * These checks make no action/result/state judgment. */
export const identityFields = Object.freeze([
  'requestId', 'requestSha256', 'generation', 'component', 'inputSha256',
  'messagesSha256', 'bindingSha256', 'codec', 'modelIdentity',
  'runtimeIdentity', 'codeIdentity',
  'placementPolicySha256',
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
  for (const key of ['modelIdentity', 'runtimeIdentity', 'codeIdentity', 'placementPolicySha256']) {
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

// This pinned ORT JSEP backend creates its own device from env.webgpu.adapter,
// then publishes both actual objects as non-configurable, read-only properties.
// The current common-package device setter documentation is not its contract.
export async function runtimeDeviceBinding(flags, expectedAdapter, requiredFeatures) {
  const device = await flags.device;
  const adapter = await flags.adapter;
  for (const [key, actual] of [['device', device], ['adapter', adapter]]) {
    const descriptor = Object.getOwnPropertyDescriptor(flags, key);
    if (!actual || !descriptor || descriptor.value !== actual || descriptor.writable !== false
      || descriptor.configurable !== false) throw Error('runtime_' + key + '_not_published_by_pinned_backend');
  }
  if (adapter !== expectedAdapter) throw Error('runtime_adapter_mismatch');
  const adapterInfo = adapter.info ?? await adapter.requestAdapterInfo?.();
  const fallback = adapterInfo?.isFallbackAdapter ?? adapter.isFallbackAdapter ?? null;
  if (fallback !== false) throw Error('runtime_nonfallback_adapter_unverified');
  if (!device.features?.has || typeof device.queue?.onSubmittedWorkDone !== 'function'
    || typeof device.lost?.then !== 'function') throw Error('runtime_device_invalid');
  for (const feature of requiredFeatures) {
    if (!device.features.has(feature)) throw Error('runtime_device_feature_missing:' + feature);
  }
  if (device.adapterInfo) {
    for (const key of ['vendor', 'architecture', 'device', 'description']) {
      if (adapterInfo?.[key] != null && device.adapterInfo[key] !== adapterInfo[key]) {
        throw Error('runtime_device_adapter_info_mismatch:' + key);
      }
    }
  }
  return {device, adapter, evidence: {
    bindingSource: 'pinned_ort_jsep_readonly_environment', runtimeDeviceVerified: true,
    adapterReferenceVerified: true, deviceCreatedBy: 'onnxruntime',
    deviceAdapterInfoAvailable: Boolean(device.adapterInfo),
    adapterInfo: Object.fromEntries(['vendor', 'architecture', 'device', 'description', 'isFallbackAdapter']
      .map(k => [k, k === 'isFallbackAdapter' ? fallback : adapterInfo?.[k] ?? null])),
  }};
}

// A failed loopback connection is terminal for this page session. Preserve the
// last observed result separately; disconnect never creates semantic success.
export class BridgeConnectionState {
  constructor() { this.connected = false; this.ended = false; this.reason = null; this.lastResult = null; }
  connect() {
    if (this.ended) throw Error('connection_already_ended_reload_required');
    this.connected = true;
  }
  result(text) { this.lastResult = text; }
  end(reason) {
    if (this.ended) return false;
    this.connected = false; this.ended = true; this.reason = reason;
    return true;
  }
}

export class GpuProfileCollector {
  constructor(request, emitBatch, {minimumStartNs = -1, batchSize = 64} = {}) {
    this.request = identity(request); this.emitBatch = emitBatch;
    this.minimumStartNs = minimumStartNs; this.batchSize = batchSize;
    this.batch = []; this.kernelCount = 0; this.weightKernelCount = 0;
    this.positiveWeightKernelCount = 0; this.totalKernelDurationNs = 0;
    this.kernelTypeCounts = Object.create(null); this.weightWitnesses = [];
    this.invalidCount = 0; this.errors = []; this.maximumEndNs = minimumStartNs;
    this.batchCount = 0;
  }
  invalidate(reason) {
    this.invalidCount += 1;
    if (this.errors.length < 8) this.errors.push(reason);
  }
  record(row) {
    this.kernelCount += 1;
    this.batch.push(row);
    const valid = row?.version === 1 && typeof row.kernelType === 'string'
      && typeof row.kernelName === 'string' && typeof row.programName === 'string'
      && Number.isSafeInteger(row.startTime) && Number.isSafeInteger(row.endTime)
      && row.startTime >= 0 && row.endTime >= row.startTime
      && Array.isArray(row.inputsMetadata) && Array.isArray(row.outputsMetadata);
    if (!valid) this.invalidate('invalid_gpu_timestamp_record');
    else if (row.startTime < this.minimumStartNs) this.invalidate('stale_gpu_timestamp_record');
    else {
      this.maximumEndNs = Math.max(this.maximumEndNs, row.endTime);
      this.totalKernelDurationNs += row.endTime - row.startTime;
      this.kernelTypeCounts[row.kernelType] = (this.kernelTypeCounts[row.kernelType] ?? 0) + 1;
      // MatMulNBits is the actual ORT quantized-weight multiplication kernel.
      // Generic GPU activity or attention-only MatMul is insufficient evidence.
      if (row.kernelType === 'MatMulNBits') {
        this.weightKernelCount += 1;
        if (row.endTime > row.startTime) {
          this.positiveWeightKernelCount += 1;
          if (this.weightWitnesses.length < 8) this.weightWitnesses.push(row);
        }
      }
    }
    if (this.batch.length >= this.batchSize) this.flush();
  }
  flush() {
    if (!this.batch.length) return;
    const rows = this.batch; this.batch = []; this.batchCount += 1;
    this.emitBatch({...this.request, batchIndex: this.batchCount - 1,
      firstKernelIndex: this.kernelCount - rows.length, kernels: rows});
  }
  summary() {
    this.flush();
    return {...this.request, source: 'ort_webgpu_timestamp_query_v1', timestampUnit: 'nanoseconds',
      profilingMode: 'default', kernelCount: this.kernelCount, weightKernelCount: this.weightKernelCount,
      positiveWeightKernelCount: this.positiveWeightKernelCount, totalKernelDurationNs: this.totalKernelDurationNs,
      kernelTypeCounts: {...this.kernelTypeCounts}, weightWitnesses: [...this.weightWitnesses],
      invalidCount: this.invalidCount, errors: [...this.errors], batchCount: this.batchCount,
      maximumEndNs: this.maximumEndNs, cpuNodeCount: null, cpuNodeDurationMs: null,
      placementCoverage: 'observed_GPU_kernels_only_CPU_placement_not_measured',
      provesGpuWeightCompute: this.invalidCount === 0 && this.positiveWeightKernelCount > 0};
  }
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
