import {identity, verifyRequest, checkTokens, classifyStop} from './core.mjs';
import {sha256} from './core.mjs';

let config, library, tokenizer, model, gpuDevice, deviceIdentity;
let loading = null, active = null, lost = false;

const emit = (kind, data = {}) => self.postMessage({type: 'event', event: {kind, ...data}});
const fail = (request, reason, extra = {}) => ({...identity(request), status: 'incomplete', reason, ...extra});
const memory = () => ({jsHeapUsedBytes: performance.memory?.usedJSHeapSize ?? null,
  jsHeapTotalBytes: performance.memory?.totalJSHeapSize ?? null,
  gpuAllocatedBytes: null, peakGpuMemoryMeasured: false,
  limitation: 'Standard WebGPU exposes limits, not allocated or peak device memory.'});

async function loadTokenizer() {
  library ??= await import('/runtime/transformers.web.min.js');
  const {env, AutoTokenizer} = library;
  env.allowRemoteModels = false; env.allowLocalModels = true; env.localModelPath = '/model/';
  env.useBrowserCache = false; env.useFSCache = false;
  tokenizer ??= await AutoTokenizer.from_pretrained(config.modelPath, {local_files_only: true});
  return tokenizer;
}

async function tokenizerParity(packet) {
  try {
    const tokenizer = await loadTokenizer();
    const cases = [];
    for (const row of packet.cases) {
      if (await sha256(row.messagesJson) !== row.messagesSha256) throw Error('tokenizer_parity_message_identity');
      const tensor = tokenizer.apply_chat_template(JSON.parse(row.messagesJson), {tokenize: true,
        add_generation_prompt: true, enable_thinking: false, return_dict: true, truncation: false, padding: false});
      const ids = tensor.input_ids.tolist()[0].map(Number);
      cases.push({exampleId: row.exampleId, component: row.component, inputSha256: row.inputSha256,
        messagesSha256: row.messagesSha256, actualInputIds: ids,
        exactMatch: JSON.stringify(ids) === JSON.stringify(row.expectedInputIds)});
    }
    emit('tokenizer_parity_finished', {sourceSha256: packet.sourceSha256, cases,
      modelIdentity: config.modelIdentity, modelForwardCalls: 0, gpuDeviceCreated: Boolean(gpuDevice)});
  } catch (error) {
    emit('webgpu_load_failed', {reason: 'tokenizer_parity_error:' + String(error.message || error)});
  }
}

async function load() {
  if (lost) throw Error('device_lost');
  if (model) return {coldLoad: false, loadMs: 0};
  if (loading) return loading;
  loading = (async () => {
    const start = performance.now();
    if (!self.isSecureContext || !navigator.gpu) throw Error('webgpu_unsupported');
    const adapter = await navigator.gpu.requestAdapter({powerPreference: 'high-performance'});
    if (!adapter) throw Error('webgpu_adapter_unavailable');
    if (!adapter.features.has('shader-f16')) throw Error('webgpu_shader_f16_unsupported');
    if (adapter.info?.isFallbackAdapter === true) throw Error('fallback_adapter_rejected');
    gpuDevice = await adapter.requestDevice({requiredFeatures: ['shader-f16'], requiredLimits: {
      maxBufferSize: adapter.limits.maxBufferSize,
      maxStorageBufferBindingSize: adapter.limits.maxStorageBufferBindingSize,
    }});
    deviceIdentity = {executionProvider: 'webgpu', dtype: 'q4f16', lost: false,
      placementPolicy: {executionProviders: ['webgpu'], disableCpuEpFallback: '1',
        perOperatorPlacementMeasured: false, transportAndTokenization: 'CPU JavaScript'},
      adapterInfo: Object.fromEntries(['vendor', 'architecture', 'device', 'description', 'isFallbackAdapter']
        .map(k => [k, adapter.info?.[k] ?? null])),
      features: [...gpuDevice.features].sort(),
      limits: {maxBufferSize: gpuDevice.limits.maxBufferSize, maxStorageBufferBindingSize: gpuDevice.limits.maxStorageBufferBindingSize},
      userAgent: navigator.userAgent, deviceSessionId: crypto.randomUUID()};
    gpuDevice.lost.then(info => {
      lost = true; deviceIdentity.lost = true;
      emit('webgpu_device_lost', {reason: info.reason, message: info.message, deviceIdentity});
      active?.stop?.interrupt();
    });
    await loadTokenizer();
    const {env, AutoModelForCausalLM} = library;
    env.allowRemoteModels = false;
    env.allowLocalModels = true;
    env.localModelPath = '/model/';
    env.useBrowserCache = false;
    env.useFSCache = false;
    env.backends.onnx.wasm.wasmPaths = '/runtime/ort/';
    env.backends.onnx.wasm.numThreads = 1;
    env.backends.onnx.webgpu.device = gpuDevice;
    emit('webgpu_model_load_started', {modelIdentity: config.modelIdentity, deviceIdentity});
    model = await AutoModelForCausalLM.from_pretrained(config.modelPath, {
      local_files_only: true, dtype: 'q4f16', device: 'webgpu',
      session_options: {executionProviders: ['webgpu'], extra: {session: {disable_cpu_ep_fallback: '1'}}},
      progress_callback: info => emit('webgpu_load_progress', {info}),
    });
    if (await env.backends.onnx.webgpu.device !== gpuDevice || lost) throw Error('runtime_device_mismatch_or_lost');
    const loadMs = performance.now() - start;
    emit('request_model_load', {...(active ? identity(active.request) : {}), role: 'generator', elapsedMs: loadMs, modelIdentity: config.modelIdentity,
      deviceIdentity, memory: memory(), warmupForwardCalls: 0});
    return {coldLoad: true, loadMs};
  })();
  try { return await loading; }
  catch (error) { loading = null; throw error; }
}

async function generate(request) {
  if (active) return self.postMessage({type: 'result', response: fail(request, 'concurrent_worker_call_rejected')});
  const started = performance.now();
  const state = {request, cancelled: false, rawTokenIds: [], stop: null};
  active = state;
  let inputs = [], loadTiming = {coldLoad: false, loadMs: 0};
  let tokenizeMs = 0, forwardMs = 0, rawText = null, rawDecodedText = null;
  let forwardStarted = false, forwardSettled = false;
  const abortReason = () => classifyStop(request, {cancelled: state.cancelled, lost});
  const evidence = () => ({inputTokenIds: inputs, rawTokenIds: state.rawTokenIds,
    rawText, rawDecodedText, enableThinking: false, deviceIdentity: deviceIdentity ?? null,
    memory: memory(),
    timings: {...loadTiming, tokenizeMs, forwardMs, workerTotalMs: performance.now() - started}});
  try {
    const messages = await verifyRequest(request, config);
    loadTiming = await load();
    if (abortReason()) throw Error(abortReason());
    const tick = performance.now();
    const tensors = tokenizer.apply_chat_template(messages, {tokenize: true,
      add_generation_prompt: true, enable_thinking: false, return_dict: true,
      truncation: false, padding: false});
    inputs = tensors.input_ids.tolist()[0].map(Number);
    tokenizeMs = performance.now() - tick;
    if (inputs.length > request.maxInputTokens || inputs.length + request.maxNewTokens > config.maxContextTokens) {
      throw Error('complete_context_exceeds_frozen_token_limit');
    }
    if (abortReason()) throw Error(abortReason());
    state.stop = new library.InterruptableStoppingCriteria();
    const deadline = setTimeout(() => state.stop.interrupt(), Math.max(0, request.deadlineUnixMs - Date.now()));
    const streamer = new library.TextStreamer(tokenizer, {skip_prompt: true, skip_special_tokens: false,
      callback_function: () => {},
      token_callback_function: tokens => {
        state.rawTokenIds.push(...tokens.map(Number));
        emit('generator_token_progress', {...identity(request), rawTokenIds: [...state.rawTokenIds]});
        if (abortReason()) state.stop.interrupt();
      }});
    emit('generator_forward_started', {...identity(request), inputIds: inputs, modelIdentity: config.modelIdentity,
      deviceIdentity, completeInput: true, enableThinking: false});
    forwardStarted = true;
    const forwardStart = performance.now();
    let output;
    try {
      output = await model.generate({...tensors, ...request.decoding, max_new_tokens: request.maxNewTokens,
        eos_token_id: config.eosTokenIds, forced_eos_token_id: null, forced_bos_token_id: null,
        min_new_tokens: 0, min_length: 0, streamer, stopping_criteria: state.stop,
        return_dict_in_generate: false});
    } finally {
      clearTimeout(deadline);
      forwardMs = performance.now() - forwardStart;
    }
    const sequence = output.tolist()[0].map(Number);
    if (sequence.length < inputs.length || inputs.some((v, i) => sequence[i] !== v)) throw Error('generated_input_prefix_changed');
    const returned = sequence.slice(inputs.length);
    if (JSON.stringify(returned) !== JSON.stringify(state.rawTokenIds)) throw Error('stream_returned_token_mismatch');
    rawDecodedText = tokenizer.decode(returned, {skip_special_tokens: false, clean_up_tokenization_spaces: false});
    const eosReached = config.eosTokenIds.includes(returned.at(-1));
    rawText = tokenizer.decode(eosReached ? returned.slice(0, -1) : returned,
      {skip_special_tokens: false, clean_up_tokenization_spaces: false});
    emit('generator_forward_settled', {...identity(request), elapsedMs: forwardMs, rawTokenIds: returned,
      rawTokens: returned, rawText, rawDecodedText, eosReached, deviceIdentity, memory: memory()});
    forwardSettled = true;
    if (abortReason()) throw Error(abortReason());
    checkTokens(inputs, returned, request, config);
    if (!rawText.trim()) throw Error('empty_generation');
    if (rawText.includes('<think>') || rawText.includes('</think>')) throw Error('unexpected_thinking_tokens');
    self.postMessage({type: 'result', response: {...identity(request), status: 'result', ...evidence(),
      eosReached, stopReason: 'eos'}});
  } catch (error) {
    // Token progress survives interruption. No partial text becomes a result.
    const errorEvidence = {type: error.name, message: String(error.message || error), stack: error.stack ?? null};
    if (forwardStarted && !forwardSettled) emit('generator_forward_settled', {...identity(request),
      elapsedMs: forwardMs, rawTokenIds: state.rawTokenIds, rawTokens: state.rawTokenIds,
      completion: 'incomplete', error: errorEvidence, deviceIdentity, memory: memory()});
    self.postMessage({type: 'result', response: fail(request, abortReason() || String(error.message || error),
      {...evidence(), error: errorEvidence})});
  } finally {
    active = null;
  }
}

self.addEventListener('message', event => {
  const data = event.data;
  if (data.type === 'configure') {
    if (config) return emit('configuration_rejected', {reason: 'worker_already_bound'});
    config = data.config;
    emit('webgpu_worker_bound', {modelIdentity: config.modelIdentity, runtimeIdentity: config.runtimeIdentity});
  } else if (data.type === 'generate') {
    if (!config) return self.postMessage({type: 'result', response: fail(data.request, 'worker_not_configured')});
    void generate(data.request);
  } else if (data.type === 'load') {
    if (!config) return emit('webgpu_load_failed', {reason: 'worker_not_configured'});
    void load().catch(error => emit('webgpu_load_failed', {reason: String(error.message || error)}));
  } else if (data.type === 'tokenize') {
    if (!config || active || model) return emit('webgpu_load_failed', {reason: 'tokenizer_parity_requires_idle_before_model_load'});
    void tokenizerParity(data.packet);
  } else if (data.type === 'cancel') {
    if (active && active.request.requestId === data.requestId && active.request.generation === data.generation) {
      active.cancelled = true; active.stop?.interrupt();
    }
  }
});
