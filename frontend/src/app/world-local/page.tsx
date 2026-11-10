'use client';

/** Browser-only playable loop. No HTTP game API: the page loads the static
 * world, creates the local transport/controller, runs the two GGUF engines
 * (semantic 0.6B + narration 0.5B) and stores the committed snapshot in
 * localStorage. The server, if present, is never called. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { WllamaInferenceEngine } from '@/lib/world-engine/runtime/wllama-engine';
import type { InferenceEngine } from '@/lib/world-engine/runtime/engine';
import { LocalGameModel } from '@/lib/world-engine/local/game-model';
import { LocalGameSession, type LocalGameSnapshot } from '@/lib/world-engine/local/session';
import { openLocalProgressStore, migrateLegacySnapshot, type LocalProgressStore } from '@/lib/world-engine/local/persistence';
import { locationName, roomOf, visibleCharacters } from '@/lib/world-engine/local/prompt';
import { loadStaticWorld, StaticWorldError } from '@/lib/world-engine/local/world-loader';
import { stateDigest } from '@/lib/world-engine/local/state';
import { STATIC_WORLD_ASSET, STATIC_WORLD_REGISTRATION } from '@/lib/world-engine/local/static-world-registration';
import type { WorldState } from '@/lib/world-engine/types';

const SAVE_KEY = 'jity.world.local.snapshot.v1';
const SEMANTIC_MODEL = '/models/Qwen3-0.6B-Q4_K_M.gguf';
const NARRATION_MODEL = '/models/qwen25-1.5b-narr-Q4_K_M.gguf';

type Phase = 'loading' | 'ready' | 'thinking' | 'streaming' | 'error';

interface TurnEntry {
  key: number; input: string; text: string; note: string | null; ms: number | null;
  /** Wall time from submit to the first streamed character. A draft stream is
   * shown for reading, but it is NOT the acceptance number: a draft is not
   * fact-checked yet and can still be replaced or cancelled. */
  draftMs: number | null;
  /** Wall time from submit to the fact-verified text that was committed to the
   * page. This is the only "readable" number used for product acceptance. */
  acceptedMs: number | null;
  cancelled?: boolean;
}

interface ViewState {
  time: string;
  place: string;
  name: string;
  sanity: number;
  tasks: { goal: string; done: boolean }[];
  visible: string[];
}

function viewOf(state: WorldState): ViewState {
  const me = state.characters[state.protagonistId];
  return {
    time: state.time.dateTime.replace('T', ' ').slice(0, 16),
    place: locationName(state, roomOf(state, state.protagonistId)),
    name: state.initial.characters[state.protagonistId]?.name ?? state.protagonistId,
    sanity: me?.sanity ?? 0,
    tasks: Object.values(me?.tasks ?? {}).sort((a, b) => Number(a.status === 'achieved') - Number(b.status === 'achieved')).slice(0, 5)
      .map((task) => ({ goal: task.goal, done: task.status === 'achieved' })),
    visible: visibleCharacters(state, state.protagonistId).filter((id) => id !== state.protagonistId).map((id) => state.initial.characters[id]?.name ?? id),
  };
}

async function loadEngine(url: string, contextSize = 8192): Promise<WllamaInferenceEngine> {
  const modelUrl = new URL(url, window.location.href).href;
  // A cold load is 32-46 s, so it is bounded and cancellable; a stuck compile
  // must not leave the first player turn waiting forever.
  const engine = new WllamaInferenceEngine({ modelUrl, contextSize, nGpuLayers: 99999, abortGraceMs: 2500, loadTimeoutMs: 120_000 });
  try { await engine.ensureLoaded(); return engine; } catch (gpuError) {
    console.warn('[world-local] WebGPU load failed, retrying CPU', gpuError);
    await engine.dispose().catch(() => undefined);
    const cpu = new WllamaInferenceEngine({ modelUrl, contextSize, nGpuLayers: 0, abortGraceMs: 2500, loadTimeoutMs: 120_000 });
    await cpu.ensureLoaded();
    return cpu;
  }
}

/** A model port that survives a hard-stopped generation. wllama terminates the
 * worker when an abort does not settle in time, which unloads the model; the
 * game must reload it instead of failing every later turn of the session. */
interface ProductEnginePort extends InferenceEngine {
  /** Forwarded to the real runtime so the stop button can cancel a cold load. */
  cancelActive(): number;
  runtime(): { needsReload: boolean; workersCreated: number; workersExited: number; generations: number; loadCount: number } | null;
}

function resilientEngine(url: string, contextSize: number, label: string): ProductEnginePort {
  let current: WllamaInferenceEngine | null = null;
  let loading: Promise<WllamaInferenceEngine> | null = null;
  const ensure = async (): Promise<WllamaInferenceEngine> => {
    if (current) return current;
    if (!loading) {
      loading = loadEngine(url, contextSize).then((engine) => {
        current = engine;
        loading = null;
        return engine;
      }, (error) => {
        loading = null;
        throw error;
      });
    }
    return loading;
  };
  const drop = async (engine: WllamaInferenceEngine) => {
    if (current === engine) current = null;
    try { await engine.dispose(); } catch { /* the worker may already be gone */ }
  };
  return {
    get info() { return { backend: current?.info.backend ?? 'wllama', modelId: current?.info.modelId ?? null }; },
    load: async () => { await ensure(); },
    dispose: async () => { if (current) await drop(current); },
    // The stop button reaches the real runtime through this port, so a cold
    // load can be cancelled before the first turn ever starts.
    cancelActive: () => current?.cancelActive() ?? 0,
    runtime: () => current?.runtime ?? null,
    complete: async (prompt, options) => {
      for (let attempt = 0; attempt < 2; attempt += 1) {
        const engine = await ensure();
        // After a hard stop the worker is gone but the same weights can be
        // reloaded. Reload instead of constructing a second runtime or
        // switching models.
        if (engine.runtime.needsReload) {
          console.warn(`[world-local] ${label} worker exited; reloading the same weights`);
          await engine.ensureLoaded();
        }
        try {
          return await engine.complete(prompt, options);
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          if (attempt === 0 && /not loaded/i.test(message)) {
            console.warn(`[world-local] ${label} engine was unloaded; reloading once`, message);
            await drop(engine);
            continue;
          }
          throw error;
        }
      }
      throw new Error(`${label} engine could not be reloaded`);
    },
  };
}

export default function WorldLocalPage() {
  const [phase, setPhase] = useState<Phase>('loading');
  const [message, setMessage] = useState('正在载入本地世界与模型…');
  const [entries, setEntries] = useState<TurnEntry[]>([]);
  /** Submit wall-clock origin for this turn; the narration callbacks run outside
   * the submit closure, so the origin lives in a ref. */
  const submittedAtRef = useRef(0);
  /** Seconds since the page opened while the cold load is still running, so a
   * 120 s bounded load never looks like a frozen page. */
  const [loadSeconds, setLoadSeconds] = useState(0);
  const loadStartedRef = useRef(0);
  const [view, setView] = useState<ViewState | null>(null);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [stage, setStage] = useState<string>('');
  const sessionRef = useRef<LocalGameSession | null>(null);
  const semanticRef = useRef<ProductEnginePort | null>(null);
  const narrationRef = useRef<ProductEnginePort | null>(null);
  const modelRef = useRef<LocalGameModel | null>(null);
  const storeRef = useRef<LocalProgressStore | null>(null);
  const [durable, setDurable] = useState<boolean | null>(null);

  /** Fallback only: when the platform has no IndexedDB the session runs in
   * memory and the page keeps a best-effort localStorage copy so a refresh is
   * not a guaranteed loss. Durable sessions save through the store instead. */
  const save = useCallback((snapshot: LocalGameSnapshot) => {
    if (snapshot.transport.work) return; // never persist a half-settled point
    if (storeRef.current?.durable) return;
    try { localStorage.setItem(SAVE_KEY, JSON.stringify(snapshot)); } catch (e) { console.warn('[world-local] save failed', e); }
  }, []);

  const refresh = useCallback(async () => {
    const session = sessionRef.current;
    if (!session) return;
    const state = await session.state();
    // Independent check: the state the page is about to render must hash to the
    // digest the transport recorded for the head point. A mismatch means the
    // in-memory state and the committed record disagree; refuse to continue
    // rather than play on a silently diverged world.
    const snapshot = session.snapshot;
    const expected = snapshot.transport.pointStates[snapshot.transport.headPointId]?.stateDigest ?? null;
    const actual = await stateDigest(state);
    if (expected && actual !== expected) {
      throw new Error(`state_digest_mismatch: head=${snapshot.transport.headPointId} expected=${expected.slice(0, 12)} actual=${actual.slice(0, 12)}`);
    }
    setView(viewOf(state));
    const context = await session.transport.execute('get_context', {}, { worldId: session.worldId });
    setHistory(session.commandsPlayed);
    await session.flushPersistence();
    save(session.snapshot);
    setPhase((current) => current === 'streaming' ? 'ready' : current);
    return context;
  }, [save]);

  useEffect(() => {
    let alive = true;
    loadStartedRef.current = performance.now();
    const ticker = setInterval(() => {
      setLoadSeconds(Math.max(0, Math.round((performance.now() - loadStartedRef.current) / 1000)));
    }, 1000);
    (async () => {
      try {
        // The static world is verified, not merely parsed: asset hash, initial
        // digest, canonical state digest and S0 equality must all match the
        // registration, or the game refuses to start.
        const assetUrl = new URL(STATIC_WORLD_ASSET, window.location.href).href;
        const assetResponse = await fetch(assetUrl, { cache: 'no-store' });
        if (!assetResponse.ok) throw new StaticWorldError('file_hash', `world asset HTTP ${assetResponse.status}`);
        const world = await loadStaticWorld(await assetResponse.text(), STATIC_WORLD_REGISTRATION);
        setMessage('正在加载语义模型（Qwen3-0.6B）…');
        const semantic = resilientEngine(SEMANTIC_MODEL, 8192, 'semantic');
        await semantic.load();
        if (!alive) { await semantic.dispose(); return; }
        semanticRef.current = semantic;
        setMessage('正在加载叙事模型（Qwen2.5-1.5B LoRA）…');
        const narration = resilientEngine(NARRATION_MODEL, 3072, 'narration');
        await narration.load();
        if (!alive) { await narration.dispose(); return; }
        narrationRef.current = narration;
        const model = new LocalGameModel(semantic, {
          narrationEngine: narration,
          narrationMode: 'instruct',
          narrationMaxTokens: 200,
          narrationTemperature: 0.45,
          onTask: (task, key, detail) => {
            console.info(`[world-local task] ${task} ${key} ${Math.round(detail.ms)}ms fallback=${detail.fallback} ${detail.error ?? ''}`);
            setStage(STAGE_LABEL[task] ?? task);
            if (task === 'narration') setStage('');
            if (task !== 'narration') return;
            setEntries((list) => updateLast(list, (entry) => ({ ...entry, note: detail.fallback ? (detail.error ?? '正文已按已结算事实修正') : null, ms: Math.round(detail.ms) })));
          },
          onNarrationDebug: (debug) => { (window as unknown as { __worldDebug?: unknown }).__worldDebug = debug; },
          onNarrationProgress: (progress) => {
            setPhase('streaming');
            const text = progress.raw.split(String.fromCharCode(8251)).join(String.fromCharCode(10, 10));
            // Draft only: recorded separately from the accepted, fact-checked text.
            const draftMs = Math.round(performance.now() - submittedAtRef.current);
            setEntries((list) => updateLast(list, (entry) => ({
              ...entry, text, draftMs: entry.draftMs ?? draftMs,
            })));
          },
          onNarrationComplete: (progress) => {
            const text = progress.raw.split(String.fromCharCode(8251)).join(String.fromCharCode(10, 10));
            const acceptedMs = Math.round(performance.now() - submittedAtRef.current);
            setEntries((list) => updateLast(list, (entry) => ({
              ...entry, text, acceptedMs, ms: acceptedMs,
            })));
            setPhase('ready');
          },
        });
        modelRef.current = model;
        // Durable progress lives in IndexedDB with a writer lease; the old
        // single-slot localStorage snapshot is migrated non-destructively.
        const store = await openLocalProgressStore();
        storeRef.current = store;
        setDurable(store.durable);
        if (!store.durable) {
          setWarning('浏览器没有提供 IndexedDB：本局进度只保存在内存里，刷新会丢失。');
        }
        const migration = await migrateLegacySnapshot(store, { removeSource: true });
        if (migration.status === 'migrated') console.info('[world-local] migrated legacy snapshot', migration.revision);
        if (migration.status !== 'absent' && migration.status !== 'migrated') {
          console.warn('[world-local] legacy migration', migration.status, migration.backupKey ?? '');
        }
        let session: LocalGameSession;
        let restored = false;
        try {
          const opened = await LocalGameSession.open(store, { worldId: world.worldId, initial: world.template }, model);
          session = opened.session;
          restored = !opened.created;
          if (opened.created) await session.start();
        } catch (openError) {
          // Never delete the only save. Archive the readable record first, tell
          // the player, then start a new world.
          console.error('[world-local] saved progress could not be opened', openError);
          const record = await store.load(world.worldId).catch(() => null);
          let archived = false;
          if (record) {
            try {
              await store.backupLegacy({
                key: `corrupt:${world.worldId}:${Date.now()}`,
                sourceKey: `progress:${world.worldId}`,
                raw: JSON.stringify(record.snapshot),
                capturedAtEpochMilli: Date.now(),
              });
              archived = true;
            } catch (archiveError) {
              console.error('[world-local] failed to archive the corrupt save', archiveError);
            }
          }
          if (!archived) throw openError;
          await store.delete(world.worldId, { force: true });
          setWarning('旧存档无法恢复，已保留原始副本并开始新的一局。');
          session = await LocalGameSession.create(world.template, model, { worldId: world.worldId, storage: store });
          await session.start();
        }
        sessionRef.current = session;
        await refresh();
        if (!alive) return;
        setPhase('ready');
        setMessage(restored ? '已恢复本地存档，继续上次的进度。' : '本地世界已就绪。');
      } catch (e) {
        console.error(e);
        setPhase('error');
        setError(e instanceof Error ? `${e.name}: ${e.message}` : String(e));
      }
    })();
    return () => { alive = false; clearInterval(ticker); };
  }, [refresh]);

  // Flush the queued save when the tab is hidden or closed, so a refresh after
  // the last write does not lose a settled point.
  useEffect(() => {
    const flush = () => { void sessionRef.current?.flushPersistence().catch(() => undefined); };
    window.addEventListener('pagehide', flush);
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flush(); });
    return () => { window.removeEventListener('pagehide', flush); };
  }, []);

  const submit = useCallback(async () => {
    const session = sessionRef.current;
    const text = input.trim();
    if (!session || !text || busy) return;
    setBusy(true); setError(null); setWarning(null); setPhase('thinking');
    const key = Date.now();
    const submittedAt = performance.now();
    submittedAtRef.current = submittedAt;
    setEntries((list) => [...list, { key, input: text, text: '', note: null, ms: null, draftMs: null, acceptedMs: null }]);
    setMessage('正在判断行动、结算并写正文…');
    setInput('');
    modelRef.current?.beginTurn();
    // The settlement side keeps its own per-submission ledger (which stages
    // ran, model calls, milliseconds). It is evidence, not page text.
    modelRef.current?.beginSubmission(text);
    save(session.snapshot);
    try {
      const status = await session.submit(text);
      console.info('[world-local] turn status', status);
      await refresh();
      setMessage(status.kind === 'stop' && status.reason === 'world_complete' ? '本轮已交还，继续输入下一步行动。' : status.kind === 'stop' ? `本轮停止：${status.reason}` : '本轮完成。');
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? `${e.name}: ${e.message}` : String(e));
      setPhase('error');
    } finally {
      const submission = modelRef.current?.endSubmission() ?? null;
      if (submission) {
        console.info('[world-local submission]', JSON.stringify({
          input: submission.inputText,
          ms: Math.round((submission.endedAtMs ?? 0) - submission.startedAtMs),
          resultsCalls: submission.resultsCalls,
          updatesCalls: submission.updatesCalls,
          continuationCalls: submission.continuationCalls,
          decision: submission.continuationDecision,
          stops: submission.stops,
        }));
        (window as unknown as { __worldSubmission?: unknown }).__worldSubmission = submission;
      }
      setBusy(false);
    }
  }, [busy, input, refresh, save]);

  const cancelTurn = useCallback(async () => {
    const session = sessionRef.current;
    if (!session) return;
    setMessage('正在取消本轮…');
    // Stop the device work first (including a cold load), then let the
    // controller conclude the round. The cancel gate discards any answer that
    // still arrives; the engine stays usable for the next turn.
    modelRef.current?.abortTurn();
    for (const engine of [semanticRef.current, narrationRef.current]) {
      const typed = engine as unknown as { cancelActive?: () => number } | null;
      try { typed?.cancelActive?.(); } catch { /* best effort: signal already aborts */ }
    }
    // A cancelled draft is not a committed turn: keep the text visible for
    // diagnosis but label it and drop any accepted timing.
    setEntries((list) => updateLast(list, (entry) => (entry.acceptedMs == null && entry.text
      ? { ...entry, cancelled: true, ms: null, note: entry.note ?? '本轮已取消，正文草稿未通过核对。' }
      : entry)));
    try {
      const status = await session.cancel('player_cancelled');
      console.info('[world-local] cancel status', status);
      await refresh();
      setMessage('本轮已取消。可以重新输入行动。');
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? `${e.name}: ${e.message}` : String(e));
    } finally {
      setPhase('ready');
      setBusy(false);
    }
  }, [refresh]);

  const reset = useCallback(async () => {
    if (!confirm('清除本地存档并重新开始？')) return;
    const session = sessionRef.current;
    const store = storeRef.current;
    try {
      await session?.flushPersistence();
      if (store) await store.delete(session?.worldId ?? '', { force: true, sessionId: session?.sessionIdUsed });
    } catch (e) {
      console.warn('[world-local] could not delete the stored progress', e);
    }
    try { localStorage.removeItem(SAVE_KEY); } catch { /* ignored */ }
    window.location.reload();
  }, []);

  return (
    <main style={{ maxWidth: 920, margin: '0 auto', padding: '28px 20px 60px', fontFamily: 'system-ui, "Noto Serif CJK SC", serif', color: '#222', background: '#f7f3ea', minHeight: '100vh' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', borderBottom: '1px solid #d8ccb8', paddingBottom: 12, marginBottom: 18 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 24, letterSpacing: 1 }}>龙族 · 自由一日</h1>
          <div style={{ fontSize: 12, color: '#7c6f5d', marginTop: 4 }}>全部在浏览器本地运行 · 服务器只负责存档</div>
        </div>
        <button onClick={reset} style={{ border: '1px solid #c9bda8', background: 'transparent', padding: '6px 10px', borderRadius: 6, cursor: 'pointer', color: '#6b5d4a' }}>重新开始</button>
      </header>

      <section style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 20 }}>
        <div>
          <div style={{ background: '#fffdf8', border: '1px solid #ded4c2', borderRadius: 10, padding: 18, minHeight: 280 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#7b6d59', marginBottom: 10 }}>
              <span>{view?.time ?? '—'} · {view?.place ?? '—'}</span>
              <span>
                {phase === 'thinking' ? (stage ? `结算中：${stage}` : '结算中…') : phase === 'streaming' ? '正在写正文…' : message}
                {busy && <button onClick={cancelTurn} style={{ marginLeft: 10, border: '1px solid #c9bda8', background: 'transparent', padding: '2px 8px', borderRadius: 6, cursor: 'pointer', color: '#6b5d4a' }}>取消本轮</button>}
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              {entries.length === 0 && <div style={{ color: '#8a7c68' }}>{phase === 'loading' ? `正在加载本地模型，第一次会久一些（已等待 ${loadSeconds}s，上限 120s）。` : '等待输入…'}</div>}
              {entries.map((entry) => (
                <article key={entry.key} style={{ borderLeft: '3px solid #e2d6c1', paddingLeft: 12 }}>
                  <div style={{ fontSize: 12, color: '#9a8b74', marginBottom: 6 }}>
                    你：{entry.input}
                    {entry.acceptedMs != null ? ` · 可读正文 ${(entry.acceptedMs / 1000).toFixed(1)}s（已核对）` : ''}
                    {entry.acceptedMs == null && entry.draftMs != null ? ` · 草稿 ${(entry.draftMs / 1000).toFixed(1)}s（未核对）` : ''}
                  </div>
                  <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.9, fontSize: 16 }}>{entry.text || '…'}</div>
                  {entry.cancelled && <div style={{ fontSize: 12, color: '#8b2a1e', marginTop: 6 }}>本轮已取消，上方文字未通过核对，不计入正文。</div>}
                  {entry.note && <div style={{ fontSize: 12, color: '#a2762a', marginTop: 6 }}>{entry.cancelled ? '' : '正文已按已结算事实修正：'}{entry.note}</div>}
                </article>
              ))}
            </div>
          </div>

          {durable === false && <div style={{ marginTop: 10, padding: '8px 10px', background: '#fff6e0', border: '1px solid #e6cf9d', borderRadius: 6, fontSize: 12, color: '#7a5a1c' }}>这个浏览器没有可用的本地数据库，本局进度只保存在内存里，刷新会丢。</div>}
          {warning && <div style={{ marginTop: 10, padding: '8px 10px', background: '#fff6e0', border: '1px solid #e6cf9d', borderRadius: 6, fontSize: 12, color: '#7a5a1c', whiteSpace: 'pre-wrap' }}>{warning}</div>}
          {error && <div style={{ marginTop: 10, padding: '8px 10px', background: '#ffe8e5', border: '1px solid #e7b1a9', borderRadius: 6, fontSize: 12, color: '#8b2a1e', whiteSpace: 'pre-wrap' }}>{error}</div>}

          <div style={{ marginTop: 16 }}>
            <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void submit(); }} rows={3}
              placeholder="输入你要做的事，例如：我沿着车道向西回廊快走，贴着墙，注意听枪声。"
              style={{ width: '100%', boxSizing: 'border-box', padding: 12, font: 'inherit', lineHeight: 1.6, border: '1px solid #cfc3ae', borderRadius: 8, background: '#fffdf8', resize: 'vertical' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
              <span style={{ fontSize: 12, color: '#8a7c68' }}>Ctrl/⌘ + Enter 提交 · 模型只读取已结算状态</span>
              <button onClick={() => void submit()} disabled={busy || phase === 'loading' || !input.trim()}
                style={{ padding: '9px 20px', borderRadius: 7, border: 0, background: busy || phase === 'loading' ? '#b9ac96' : '#6d5232', color: '#fff', font: 'inherit', cursor: busy || phase === 'loading' ? 'default' : 'pointer' }}>
                {busy ? '结算中…' : '行动'}
              </button>
            </div>
          </div>
        </div>

        <aside style={{ fontSize: 13, color: '#5f5343' }}>
          <div style={{ background: '#fffdf8', border: '1px solid #ded4c2', borderRadius: 10, padding: 14 }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: '#3b2f20', marginBottom: 8 }}>{view?.name ?? '路明非'}</div>
            <div>精神值：{view?.sanity ?? '—'}</div>
            <div style={{ marginTop: 4 }}>地点：{view?.place ?? '—'}</div>
            <div style={{ marginTop: 12, fontWeight: 600 }}>在附近</div>
            <div style={{ marginTop: 4 }}>{view?.visible.length ? view.visible.join('、') : '没有别人'}</div>
            <div style={{ marginTop: 12, fontWeight: 600 }}>当前任务</div>
            <ul style={{ paddingLeft: 18, margin: '6px 0 0', lineHeight: 1.6 }}>
              {(view?.tasks ?? []).map((task, index) => <li key={index} style={{ color: task.done ? '#9b8d78' : '#4b3d2b', textDecoration: task.done ? 'line-through' : 'none' }}>{task.goal}</li>)}
            </ul>
          </div>
          <div style={{ background: '#fffdf8', border: '1px solid #ded4c2', borderRadius: 10, padding: 14, marginTop: 12 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>本地存档</div>
            <div style={{ fontSize: 12, color: '#7b6d59' }}>每次完整结算后写入浏览器 localStorage；刷新页面会恢复。中途刷新会回到上一次完整结算。</div>
            <div style={{ fontSize: 12, color: '#7b6d59', marginTop: 8 }}>已行动：{history.length} 次</div>
          </div>
        </aside>
      </section>
    </main>
  );
}

function updateLast(list: TurnEntry[], update: (entry: TurnEntry) => TurnEntry): TurnEntry[] {
  if (!list.length) return list;
  const copy = list.slice();
  copy[copy.length - 1] = update(copy[copy.length - 1]);
  return copy;
}


const STAGE_LABEL: Record<string, string> = {
  targets: '判断牵连',
  action: '角色行动',
  reaction: '即时反应',
  results: '结算',
  updates: '状态更新',
  continuation: '继续判断',
  narration: '写正文',
  pointPlan: '安排回合',
};
