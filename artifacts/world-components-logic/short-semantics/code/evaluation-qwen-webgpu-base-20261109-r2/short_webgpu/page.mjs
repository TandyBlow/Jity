import {identity} from './core.mjs';

const token = location.hash.slice(1);
const clientId = crypto.randomUUID();
let worker, connected = false, active = null, polling = false, loading = false, activeConfig;
let hardTimer, loadTimer, eventQueue = Promise.resolve();
const $ = id => document.getElementById(id);

function show(message) {
  $('status').textContent = message;
  $('events').textContent = ($('events').textContent + '\n' + message).slice(-12000);
}
async function post(path, data) {
  const response = await fetch('/api/' + path, {method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Jity-Token': token},
    body: JSON.stringify({clientId, ...data})});
  const value = await response.json();
  if (!response.ok) throw Error(value.error || 'bridge_http_' + response.status);
  return value;
}
function journal(event) {
  // Preserve event order and ensure token evidence is uploaded before completion.
  eventQueue = eventQueue.then(() => post('event', {event}));
  return eventQueue;
}
function newWorker(config) {
  worker = new Worker('/worker.mjs', {type: 'module'});
  worker.postMessage({type: 'configure', config});
  worker.onmessage = async ({data}) => {
    try {
      if (data.type === 'event') {
        await journal(data.event);
        if (['request_model_load', 'webgpu_load_failed'].includes(data.event.kind)) {
          clearTimeout(loadTimer); loading = false; $('stop').disabled = !active;
        }
        if (data.event.kind === 'tokenizer_parity_finished') {
          const passed = data.event.cases.every(c => c.exactMatch);
          $('load').disabled = !passed;
          show(passed ? '四项完整输入的分词逐 token 一致；尚未运行模型。' : '分词不一致，停止加载。');
        }
        if (data.event.deviceIdentity) $('device').textContent = JSON.stringify(data.event.deviceIdentity);
        if (!['generator_token_progress', 'webgpu_load_progress'].includes(data.event.kind)) show(data.event.kind);
      } else if (data.type === 'result') {
        clearTimeout(hardTimer);
        await eventQueue;
        const accepted = await post('result', {response: data.response});
        show(data.response.status + ': ' + (data.response.reason || data.response.rawText) + (accepted.accepted ? '' : ' [迟到输出，未采纳]'));
        active = null; $('stop').disabled = true;
      }
    } catch (error) { show('日志或桥接失败：' + error.message); }
  };
  worker.onerror = async error => {
    show('Worker 错误：' + error.message);
    if (active) {
      await post('result', {response: {...identity(active), status: 'incomplete', reason: 'worker_error:' + error.message}});
      active = null;
    }
  };
}
async function poll(config) {
  if (!connected || polling) return;
  polling = true;
  try {
    const value = await post('poll', {});
    for (const control of value.controls) worker.postMessage(control);
    if (value.job) {
      if (active) {
        await post('result', {response: {...identity(value.job), status: 'incomplete', reason: 'browser_busy_after_cancel'}});
      } else {
        active = value.job; $('stop').disabled = false;
        worker.postMessage({type: 'generate', request: active});
        show('正在执行 ' + active.component + '；完整输入，Qwen3 非思考模式。');
        // The normal deadline interrupts cooperatively; a bounded hard stop
        // prevents an unresponsive worker from retaining the GPU forever.
        hardTimer = setTimeout(async () => {
          if (!active) return;
          const old = active; worker.terminate(); active = null;
          await post('result', {response: {...identity(old), status: 'incomplete', reason: 'worker_hard_timeout'}});
          await journal({kind: 'webgpu_worker_terminated', requestId: old.requestId});
          newWorker(config); $('stop').disabled = true;
        }, Math.max(0, active.deadlineUnixMs - Date.now()) + 2000);
      }
    }
  } catch (error) { show('连接错误：' + error.message); }
  finally { polling = false; if (connected) setTimeout(() => poll(config), 50); }
}
$('connect').onclick = async () => {
  try {
    if (!token) throw Error('缺少本机实验会话标识');
    const config = await post('claim', {browser: {userAgent: navigator.userAgent,
      secureContext: isSecureContext, webgpuAvailable: Boolean(navigator.gpu)}});
    activeConfig = config; newWorker(config); connected = true; $('connect').disabled = true;
    $('tokenize').disabled = !config.tokenizerParitySha256;
    $('load').disabled = Boolean(config.tokenizerParitySha256);
    $('model').textContent = config.modelIdentity;
    show('已连接；模型将在收到实验请求时加载。');
    void poll(config);
  } catch (error) { show('连接失败：' + error.message); }
};
$('stop').onclick = () => {
  if (active) worker.postMessage({type: 'cancel', requestId: active.requestId, generation: active.generation});
  else if (loading) {
    clearTimeout(loadTimer); worker.terminate(); loading = false; $('stop').disabled = true;
    void journal({kind: 'webgpu_load_failed', reason: 'cancelled_during_model_load'});
    show('模型加载已取消；本次未完成。');
  }
};
$('load').onclick = () => {
  $('load').disabled = true; loading = true; $('stop').disabled = false;
  worker.postMessage({type: 'load'});
  loadTimer = setTimeout(() => {
    if (!loading) return;
    worker.terminate(); loading = false; $('stop').disabled = true;
    void journal({kind: 'webgpu_load_failed', reason: 'model_load_hard_timeout'});
    show('模型加载超时；本次未完成。');
  }, activeConfig.initializationTimeoutMs);
  show('正在加载固定的 Qwen3 权重；尚未进行语义生成。');
};
$('tokenize').onclick = async () => {
  try {
    $('tokenize').disabled = true;
    const packet = await post('tokenizer-cases', {});
    worker.postMessage({type: 'tokenize', packet});
    show('正在核对完整输入分词；不创建 GPU 设备、不运行模型。');
  } catch (error) { show('分词核对失败：' + error.message); }
};
window.addEventListener('pagehide', () => {connected = false; worker?.terminate();});
