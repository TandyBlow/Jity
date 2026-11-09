import test from 'node:test';
import assert from 'node:assert/strict';
import {verifyRequest, checkTokens, classifyStop, sha256, WorkerRequestGate, GpuProfileCollector,
  runtimeDeviceBinding, BridgeConnectionState, GpuCalibrationRegistry} from './core.mjs';

async function fixture() {
  const payload = {world: {a: '完整世界，不筛掉远处人物'}, fragments: []};
  const messages = [{role: 'system', content: '本任务'}, {role: 'user', content: JSON.stringify({component: 'D02.2.text', context: payload})}];
  const request = {requestId: 'r', generation: 0, modelIdentity: 'm', runtimeIdentity: 'rt', codeIdentity: 'c',
    placementPolicySha256: 'policy', profilingMode: 'default', codec: 'fixture-codec',
    decoding: {do_sample: false, num_beams: 1}, requestSha256: 'fixture-request',
    component: 'D02.2.text', enableThinking: false, deadlineUnixMs: Date.now() + 10000, timeoutMs: 10000,
    inputJson: JSON.stringify(payload), messagesJson: JSON.stringify(messages), bindingJson: '{"version":1}',
    maxInputTokens: 100, maxNewTokens: 8};
  for (const [a, b] of [['inputJson', 'inputSha256'], ['messagesJson', 'messagesSha256'], ['bindingJson', 'bindingSha256']]) request[b] = await sha256(request[a]);
  return {request, config: {...request, maxContextTokens: 128, eosTokenIds: [99]}};
}

test('complete context accepted unchanged; truncation is refused', async () => {
  const {request, config} = await fixture();
  assert.equal((await verifyRequest(request, config))[1].content.includes('远处人物'), true);
  const messages = JSON.parse(request.messagesJson);
  messages[1].content = JSON.stringify({component: request.component, context: {fragments: []}});
  request.messagesJson = JSON.stringify(messages);
  request.messagesSha256 = await sha256(request.messagesJson);
  await assert.rejects(verifyRequest(request, config), /context_not_complete/);
});
test('input byte hash, generation, model and thinking flags are enforced', async () => {
  const {request, config} = await fixture();
  for (const patch of [{inputJson: '{}'}, {generation: true}, {modelIdentity: 'other'}, {enableThinking: true}]) {
    await assert.rejects(verifyRequest({...request, ...patch}, config));
  }
});
test('context overlimit is incomplete even when output would fit', async () => {
  const {request, config} = await fixture();
  assert.throws(() => checkTokens(Array(101).fill(1), [4, 99], request, config), /complete_context/);
  assert.throws(() => checkTokens(Array(100).fill(1), [4, 99], request, {...config, maxContextTokens: 104}), /complete_context/);
});
test('EOS must be generated and terminal; never force success at output cap', async () => {
  const {request, config} = await fixture();
  checkTokens([1, 2], [4, 99], request, config);
  assert.throws(() => checkTokens([1, 2], [4, 8], request, config), /no_eos/);
  assert.throws(() => checkTokens([1, 2], [99, 4, 99], request, config), /after_eos/);
  assert.throws(() => checkTokens([1, 2], [true, 99], request, config), /invalid_tokens/);
});
test('cancel, deadline and lost device never become normal completion', async () => {
  const {request} = await fixture();
  assert.equal(classifyStop(request, {cancelled: true}), 'cancelled');
  assert.equal(classifyStop(request, {lost: true}), 'device_lost');
  assert.equal(classifyStop(request, {now: request.deadlineUnixMs}), 'timeout');
  assert.equal(classifyStop(request, {cancelled: false, lost: false}), null);
});

test('late old-worker result cannot release a new request or its timer', () => {
  const gate = new WorkerRequestGate(), oldWorker = {}, currentWorker = {};
  gate.bind(oldWorker);
  const old = gate.begin({requestId: 'old', generation: 0}); old.timer = 'old-timer';
  assert.equal(gate.finish(old), true);
  gate.bind(currentWorker);
  const current = gate.begin({requestId: 'new', generation: 1}); current.timer = 'current-timer';
  assert.equal(gate.responseLease(oldWorker, old.request), null);
  assert.equal(gate.finish(old), false);
  assert.equal(gate.active, current);
  assert.equal(gate.active.timer, 'current-timer');
  assert.equal(gate.responseLease(currentWorker, current.request), current);
});

test('already-queued old timer cannot terminate replacement worker', () => {
  const gate = new WorkerRequestGate();
  const first = {terminated: false}, next = {terminated: false};
  gate.bind(first);
  const old = gate.begin({requestId: 'same-id', generation: 2});
  gate.finish(old); gate.bind(next);
  const current = gate.begin({requestId: 'same-id', generation: 3});
  if (gate.owns(old)) {old.worker.terminated = true; gate.finish(old);}
  assert.equal(first.terminated, false);
  assert.equal(next.terminated, false);
  assert.equal(gate.active, current);
  assert.equal(gate.responseLease(next, {requestId: 'same-id', generation: 2}), null);
});

test('completion held across async logging cannot release a successor', () => {
  const gate = new WorkerRequestGate(), worker = {};
  gate.bind(worker);
  const prior = gate.begin({requestId: 'prior', generation: 0});
  const captured = gate.responseLease(worker, prior.request);
  gate.finish(prior);
  const successor = gate.begin({requestId: 'successor', generation: 0});
  assert.equal(gate.finish(captured), false);
  assert.equal(gate.active, successor);
  assert.equal(gate.responseLease(worker, {requestId: 'successor', generation: true}), null);
});

function kernel(type = 'MatMulNBits', start = 10, end = 20) {
  return {version: 1, kernelId: 1, kernelType: type, kernelName: 'fixture-' + type,
    programName: 'program', startTime: start, endTime: end,
    inputsMetadata: [{dataType: 'float16', dims: [1, 2]}, {dataType: 'uint8', dims: [2, 2]}],
    outputsMetadata: [{dataType: 'float16', dims: [1, 2]}]};
}

test('GPU Cast or attention MatMul cannot prove quantized weight computation', async () => {
  const {request} = await fixture(); const batches = [];
  const p = new GpuProfileCollector(request, row => batches.push(row), {batchSize: 2});
  p.record(kernel('Cast')); p.record(kernel('MatMul', 20, 30));
  assert.equal(p.summary().provesGpuWeightCompute, false);
  p.record(kernel('MatMulNBits', 30, 40));
  const summary = p.summary();
  assert.equal(summary.provesGpuWeightCompute, true);
  assert.equal(summary.kernelCount, 3);
  assert.equal(summary.weightKernelCount, 1);
  assert.equal(summary.totalKernelDurationNs, 30);
  assert.equal(summary.cpuNodeDurationMs, null);
  assert.equal(batches.flatMap(b => b.kernels).length, 3);
});

test('profile for a prior GPU interval is rejected instead of borrowed', async () => {
  const {request} = await fixture();
  const p = new GpuProfileCollector(request, () => {}, {minimumStartNs: 100});
  p.record(kernel('MatMulNBits', 10, 20));
  p.record(kernel('MatMulNBits', 100, 120));
  const summary = p.summary();
  assert.equal(summary.positiveWeightKernelCount, 1);
  assert.equal(summary.invalidCount, 1);
  assert.equal(summary.provesGpuWeightCompute, false);
});

test('profiles retain all rows in emitted batches with bounded in-memory witnesses', async () => {
  const {request} = await fixture(); let emitted = 0;
  const p = new GpuProfileCollector(request, batch => {emitted += batch.kernels.length;}, {batchSize: 64});
  for (let i = 0; i < 200; i++) p.record(kernel('MatMulNBits', i * 10, i * 10 + 5));
  assert.ok(p.batch.length < 64);
  const summary = p.summary();
  assert.equal(emitted, 200);
  assert.equal(summary.weightWitnesses.length, 8);
  assert.equal(summary.positiveWeightKernelCount, 200);
  assert.equal(summary.batchCount, 4);
});

function runtimeFixture() {
  const info = {vendor: 'test-fixture', architecture: 'fixture', device: 'fixture',
    description: 'explicit fake device, no GPU executed', isFallbackAdapter: false};
  const adapter = {info};
  const device = {adapterInfo: info, features: new Set(['shader-f16', 'timestamp-query']),
    queue: {onSubmittedWorkDone: async () => {}}, lost: new Promise(() => {})};
  const flags = {};
  Object.defineProperties(flags, {adapter: {value: adapter, writable: false, configurable: false},
    device: {value: device, writable: false, configurable: false}});
  return {adapter, device, flags};
}

test('runtime binding returns the device published by ORT, without creating a probe', async () => {
  const {adapter, device, flags} = runtimeFixture();
  adapter.requestDevice = () => {throw Error('must_not_create_probe');};
  const bound = await runtimeDeviceBinding(flags, adapter, ['shader-f16', 'timestamp-query']);
  assert.equal(bound.device, device);
  assert.equal(bound.adapter, adapter);
  assert.equal(bound.evidence.runtimeDeviceVerified, true);
  assert.equal(bound.evidence.deviceCreatedBy, 'onnxruntime');
});

test('probe metadata or a different adapter cannot establish actual model device identity', async () => {
  const {adapter, device, flags} = runtimeFixture();
  await assert.rejects(runtimeDeviceBinding({adapter, device}, adapter, []), /not_published/);
  await assert.rejects(runtimeDeviceBinding(flags, {...adapter}, []), /adapter_mismatch/);
  device.adapterInfo = {...adapter.info, device: 'other'};
  await assert.rejects(runtimeDeviceBinding(flags, adapter, []), /adapter_info_mismatch/);
});

test('runtime device must itself expose required features and nonfallback provenance', async () => {
  const {adapter, device, flags} = runtimeFixture();
  device.features.delete('timestamp-query');
  await assert.rejects(runtimeDeviceBinding(flags, adapter, ['timestamp-query']), /feature_missing/);
  adapter.info.isFallbackAdapter = true;
  await assert.rejects(runtimeDeviceBinding(flags, adapter, []), /nonfallback/);
});

test('connection end is terminal and preserves the last observation without creating completion', () => {
  const state = new BridgeConnectionState();
  state.connect(); state.result('incomplete: original_error');
  assert.equal(state.end('Failed to fetch'), true);
  assert.equal(state.connected, false);
  assert.equal(state.end('another fetch'), false);
  assert.equal(state.reason, 'Failed to fetch');
  assert.equal(state.lastResult, 'incomplete: original_error');
  assert.throws(() => state.connect(), /reload_required/);
});

test('profiling-off requires a prior audited identical input on the same device session', async () => {
  const {request} = await fixture();
  const device = {runtimeDeviceVerified: true, deviceSessionId: 'actual-fixture-session', lost: false};
  const registry = new GpuCalibrationRegistry();
  await assert.rejects(registry.require({...request, profilingMode: 'off', calibration: null}, device), /missing_same_input/);
  const calibration = await registry.record(request, device, {provesGpuWeightCompute: true, positiveWeightKernelCount: 4});
  const off = {...request, requestId: 'off', profilingMode: 'off', calibration};
  assert.equal((await registry.require(off, device)).requestId, request.requestId);
  for (const change of [{inputSha256: 'new-input'}, {bindingSha256: 'new-binding'},
    {maxNewTokens: 99}, {timeoutMs: 120000}, {modelIdentity: 'changed'}, {messagesSha256: 'changed-prompt'}]) {
    await assert.rejects(registry.require({...off, ...change}, device), /missing_same_input/);
  }
  await assert.rejects(registry.require(off, {...device, deviceSessionId: 'other'}), /missing_same_input/);
  await assert.rejects(new GpuCalibrationRegistry().require(off, device), /missing_same_input/);
  await assert.rejects(registry.record(off, device, {provesGpuWeightCompute: true, positiveWeightKernelCount: 4}), /invalid_gpu_calibration/);
});

test('off mode is explicitly registered and has its own immutable placement identity', async () => {
  const {request, config} = await fixture();
  await assert.rejects(verifyRequest({...request, profilingMode: 'off'}, config), /not_registered/);
  const allowed = {...config, allowProfilingComparison: true, placementPolicies: {off: {sha256: 'off-policy'}}};
  await assert.rejects(verifyRequest({...request, profilingMode: 'off'}, allowed), /identity_mismatch/);
  assert.ok(await verifyRequest({...request, profilingMode: 'off', placementPolicySha256: 'off-policy'}, allowed));
});

test('page stops after server loss, terminates worker, and keeps the original load error', async () => {
  const originals = new Map(['document', 'location', 'navigator', 'window', 'Worker', 'fetch',
    'setTimeout', 'clearTimeout', 'isSecureContext'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  const elements = new Map(); const timers = new Map(); const calls = [];
  let instance, rejectPoll, timerId = 0;
  const element = id => {if (!elements.has(id)) elements.set(id, {textContent: '', disabled: false}); return elements.get(id);};
  const replacements = {document: {getElementById: element}, location: {hash: '#fixture'},
    navigator: {userAgent: 'node-engineering-fixture'}, window: {addEventListener() {}}, isSecureContext: true,
    Worker: class {constructor() {instance = this; this.terminated = false;} postMessage() {} terminate() {this.terminated = true;}},
    setTimeout: (fn, ms) => {timers.set(++timerId, {fn, ms}); return timerId;}, clearTimeout: id => timers.delete(id),
    fetch: async url => {
      calls.push(url);
      if (url === '/api/poll') return new Promise((_, reject) => {rejectPoll = reject;});
      return {ok: true, json: async () => ({modelIdentity: 'fixture'})};
    }};
  try {
    for (const [key, value] of Object.entries(replacements)) Object.defineProperty(globalThis, key, {value, configurable: true, writable: true});
    await import('./page.mjs?connection-test');
    await element('connect').onclick();
    await instance.onmessage({data: {type: 'event', event: {kind: 'webgpu_load_failed', reason: 'original_model_load_failure'}}});
    const last = element('last-result').textContent;
    rejectPoll(Error('Failed to fetch'));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(instance.terminated, true);
    assert.match(element('status').textContent, /实验连接已结束/);
    assert.equal(element('last-result').textContent, last);
    assert.match(last, /original_model_load_failure/);
    assert.equal(calls.filter(url => url === '/api/poll').length, 1);
    assert.equal([...timers.values()].filter(row => row.ms === 50).length, 0);
    const status = element('status').textContent;
    await instance.onmessage({data: {type: 'event', event: {kind: 'webgpu_load_failed', reason: 'late_error'}}});
    assert.equal(element('status').textContent, status);
    assert.equal(element('last-result').textContent, last);
  } finally {
    for (const [key, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key];
    }
  }
});
