import {identity, WorkerRequestGate, BridgeConnectionState} from './core.mjs';

const token = location.hash.slice(1);
const clientId = crypto.randomUUID();
let worker, polling = false, loading = false, activeConfig;
let loadTimer, eventQueue = Promise.resolve();
const gate = new WorkerRequestGate();
const connection = new BridgeConnectionState();
const $ = id => document.getElementById(id);

function show(message) {
  $('status').textContent = message;
  $('events').textContent = ($('events').textContent + '\n' + message).slice(-12000);
}
function rememberResult(message) {
  connection.result(message); $('last-result').textContent = message;
}
function endConnection(reason) {
  if (!connection.end(reason)) return;
  clearTimeout(loadTimer);
  const lease = gate.active;
  if (lease) {clearTimeout(lease.timer); gate.finish(lease);}
  worker?.terminate(); loading = false;
  for (const name of ['connect', 'tokenize', 'load', 'stop']) $(name).disabled = true;
  show('实验连接已结束：' + reason + '。已停止请求；最近结果保留。'
    + (lease ? ' 当前请求未确认完成，不能视为成功。' : ' 断连本身不代表实验通过。'));
}
async function post(path, data) {
  if (connection.ended) throw Error('experiment_connection_ended');
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), 10000);
  try {
    const response = await fetch('/api/' + path, {method: 'POST', signal: abort.signal,
      headers: {'Content-Type': 'application/json', 'X-Jity-Token': token},
      body: JSON.stringify({clientId, ...data})});
    const value = await response.json();
    if (!response.ok) throw Error(value.error || 'bridge_http_' + response.status);
    return value;
  } catch (error) {
    if (connection.connected) endConnection(error.message);
    throw error;
  } finally {clearTimeout(timer);}
}
function journal(event) {
  // Preserve event order and ensure token evidence is uploaded before completion.
  eventQueue = eventQueue.then(() => post('event', {event}));
  // Retain rejection for the result barrier, but avoid detached callbacks
  // producing an unbounded console stream after this session has ended.
  void eventQueue.catch(() => {});
  return eventQueue;
}
function newWorker(config) {
  const instance = new Worker('/worker.mjs', {type: 'module'});
  const workerInstanceId = crypto.randomUUID();
  gate.bind(instance); worker = instance;
  instance.postMessage({type: 'configure', config});
  instance.onmessage = async ({data}) => {
    try {
      if (connection.ended) return;
      if (data.type === 'event') {
        if (gate.worker !== instance) {
          await journal({kind: 'webgpu_stale_worker_event', workerInstanceId, originalEvent: data.event});
          return;
        }
        await journal(data.event);
        if (connection.ended || gate.worker !== instance) return;
        if (['request_model_load', 'webgpu_load_failed'].includes(data.event.kind)) {
          clearTimeout(loadTimer); loading = false; $('stop').disabled = !gate.active;
        }
        if (data.event.kind === 'webgpu_load_failed') rememberResult('未完成：' + data.event.reason);
        if (data.event.kind === 'tokenizer_parity_finished') {
          const passed = data.event.cases.every(c => c.exactMatch);
          $('load').disabled = !passed;
          show(passed ? '四项完整输入的分词逐 token 一致；尚未运行模型。' : '分词不一致，停止加载。');
        }
        if (data.event.deviceIdentity) $('device').textContent = JSON.stringify(data.event.deviceIdentity);
        if (!['generator_token_progress', 'webgpu_load_progress'].includes(data.event.kind)) show(data.event.kind);
      } else if (data.type === 'result') {
        const lease = gate.responseLease(instance, data.response);
        if (lease) clearTimeout(lease.timer);
        const outcome = data.response.status + ': ' + (data.response.reason || data.response.rawText);
        if (lease) rememberResult(outcome + ' [尚待实验端确认]');
        await eventQueue;
        const accepted = await post('result', {response: data.response});
        if (gate.finish(lease)) {
          const message = outcome + (accepted.accepted ? '' : ' [迟到输出，未采纳]');
          rememberResult(message); show(message);
          $('stop').disabled = true;
        } else {
          await journal({kind: 'webgpu_stale_worker_result', workerInstanceId, ...identity(data.response),
            serverAccepted: accepted.accepted, changedCurrentRequest: false});
        }
      }
    } catch (error) { if (!connection.ended) endConnection('日志或桥接失败：' + error.message); }
  };
  instance.onerror = async error => {
    if (connection.ended) return;
    try {
    if (gate.worker !== instance) {
      await journal({kind: 'webgpu_stale_worker_error', workerInstanceId, message: error.message});
      return;
    }
    const lease = gate.active;
    show('Worker 错误：' + error.message);
    if (lease && gate.owns(lease)) {
      clearTimeout(lease.timer);
      await post('result', {response: {...identity(lease.request), status: 'incomplete', reason: 'worker_error:' + error.message}});
      if (gate.finish(lease)) $('stop').disabled = true;
    }
    } catch (failure) { if (!connection.ended) endConnection(failure.message); }
  };
}
async function poll(config) {
  if (!connection.connected || polling) return;
  polling = true;
  try {
    const value = await post('poll', {});
    if (!connection.connected) return;
    for (const control of value.controls) worker.postMessage(control);
    if (value.job) {
      if (gate.active) {
        await post('result', {response: {...identity(value.job), status: 'incomplete', reason: 'browser_busy_after_cancel'}});
      } else {
        const lease = gate.begin(value.job); $('stop').disabled = false;
        lease.worker.postMessage({type: 'generate', request: lease.request});
        show('正在执行 ' + lease.request.component + '；完整输入，Qwen3 非思考模式。');
        // The normal deadline interrupts cooperatively; a bounded hard stop
        // prevents an unresponsive worker from retaining the GPU forever.
        lease.timer = setTimeout(async () => {
          if (!connection.connected || !gate.owns(lease)) return;
          try {
          lease.worker.terminate(); gate.finish(lease);
          // Reserve the journal position before the replacement Worker can emit
          // its readiness. No old readiness event may update the replacement.
          const logged = journal({kind: 'webgpu_worker_terminated', ...identity(lease.request)});
          newWorker(config); $('stop').disabled = true;
          await post('result', {response: {...identity(lease.request), status: 'incomplete', reason: 'worker_hard_timeout'}});
          await logged;
          } catch (error) { if (!connection.ended) endConnection(error.message); }
        }, Math.max(0, lease.request.deadlineUnixMs - Date.now()) + 2000);
      }
    }
  } catch (error) { if (!connection.ended) endConnection(error.message); }
  finally { polling = false; if (connection.connected) setTimeout(() => poll(config), 50); }
}
$('connect').onclick = async () => {
  try {
    if (!token) throw Error('缺少本机实验会话标识');
    const config = await post('claim', {browser: {userAgent: navigator.userAgent,
      secureContext: isSecureContext, webgpuAvailable: Boolean(navigator.gpu)}});
    activeConfig = config; newWorker(config); connection.connect(); $('connect').disabled = true;
    $('tokenize').disabled = !config.tokenizerParitySha256;
    $('load').disabled = Boolean(config.tokenizerParitySha256);
    $('model').textContent = config.modelIdentity;
    show('已连接；模型将在收到实验请求时加载。');
    void poll(config);
  } catch (error) { show('连接失败：' + error.message); }
};
$('stop').onclick = () => {
  if (!connection.connected) return;
  const lease = gate.active;
  if (lease) lease.worker.postMessage({type: 'cancel', requestId: lease.request.requestId, generation: lease.request.generation});
  else if (loading) {
    clearTimeout(loadTimer); worker.terminate(); loading = false; $('stop').disabled = true;
    void journal({kind: 'webgpu_load_failed', reason: 'cancelled_during_model_load'});
    show('模型加载已取消；本次未完成。');
  }
};
$('load').onclick = () => {
  if (!connection.connected) return;
  $('load').disabled = true; loading = true; $('stop').disabled = false;
  const loadingWorker = worker;
  loadingWorker.postMessage({type: 'load'});
  loadTimer = setTimeout(() => {
    if (!connection.connected || !loading || gate.worker !== loadingWorker) return;
    loadingWorker.terminate(); loading = false; $('stop').disabled = true;
    void journal({kind: 'webgpu_load_failed', reason: 'model_load_hard_timeout'});
    show('模型加载超时；本次未完成。');
  }, activeConfig.initializationTimeoutMs);
  show('正在加载固定的 Qwen3 权重；尚未进行语义生成。');
};
$('tokenize').onclick = async () => {
  try {
    if (!connection.connected) return;
    $('tokenize').disabled = true;
    const packet = await post('tokenizer-cases', {});
    worker.postMessage({type: 'tokenize', packet});
    show('正在核对完整输入分词；不创建 GPU 设备、不运行模型。');
  } catch (error) { if (!connection.ended) show('分词核对失败：' + error.message); }
};
window.addEventListener('pagehide', () => {connection.end('pagehide'); worker?.terminate();});
