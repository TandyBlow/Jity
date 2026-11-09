'use client';

/** Browser-only playable loop. No HTTP game API: the page loads the static
 * world, creates the local transport/controller, runs the two GGUF engines
 * (semantic 0.6B + narration 0.5B) and stores the committed snapshot in
 * localStorage. The server, if present, is never called. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { WllamaInferenceEngine } from '@/lib/world-engine/runtime/wllama-engine';
import { LocalGameModel } from '@/lib/world-engine/local/game-model';
import { LocalGameSession, type LocalGameSnapshot } from '@/lib/world-engine/local/session';
import { locationName, roomOf, visibleCharacters } from '@/lib/world-engine/local/prompt';
import type { Id, InitialTemplate, WorldState } from '@/lib/world-engine/types';

const SAVE_KEY = 'jity.world.local.snapshot.v1';
const SEMANTIC_MODEL = '/models/Qwen3-0.6B-Q4_K_M.gguf';
const NARRATION_MODEL = '/models/qwen25-0.5b-narration-Q4_K_M.gguf';

type Phase = 'loading' | 'ready' | 'thinking' | 'streaming' | 'error';

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

async function loadEngine(url: string): Promise<WllamaInferenceEngine> {
  const engine = new WllamaInferenceEngine({ modelUrl: new URL(url, window.location.href).href, contextSize: 6144, nGpuLayers: 99999 });
  try { await engine.load(); return engine; } catch (gpuError) {
    console.warn('[world-local] WebGPU load failed, retrying CPU', gpuError);
    const cpu = new WllamaInferenceEngine({ modelUrl: new URL(url, window.location.href).href, contextSize: 6144, nGpuLayers: 0 });
    await cpu.load();
    return cpu;
  }
}

export default function WorldLocalPage() {
  const [phase, setPhase] = useState<Phase>('loading');
  const [message, setMessage] = useState('正在载入本地世界与模型…');
  const [prose, setProse] = useState('');
  const [view, setView] = useState<ViewState | null>(null);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const sessionRef = useRef<LocalGameSession | null>(null);
  const semanticRef = useRef<WllamaInferenceEngine | null>(null);
  const narrationRef = useRef<WllamaInferenceEngine | null>(null);
  const modelRef = useRef<LocalGameModel | null>(null);

  const save = useCallback((snapshot: LocalGameSnapshot) => {
    if (snapshot.transport.work) return; // never persist a half-settled point
    try { localStorage.setItem(SAVE_KEY, JSON.stringify(snapshot)); } catch (e) { console.warn('[world-local] save failed', e); }
  }, []);

  const refresh = useCallback(async () => {
    const session = sessionRef.current;
    if (!session) return;
    const state = await session.state();
    setView(viewOf(state));
    const context = await session.transport.execute('get_context', {}, { worldId: session.worldId });
    const latest = Object.values(session.snapshot.transport.narrations).filter((entry) => entry.text).at(-1);
    if (latest?.text) setProse(latest.text.replace(/※/g, '\n\n'));
    setHistory(session.commandsPlayed);
    save(session.snapshot);
    setPhase((current) => current === 'streaming' ? 'ready' : current);
    return context;
  }, [save]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const world = await (await fetch('/worlds/dragon-raja-free-day.world.json')).json() as { worldId: Id; initial: InitialTemplate };
        setMessage('正在加载语义模型（Qwen3-0.6B）…');
        const semantic = await loadEngine(SEMANTIC_MODEL);
        if (!alive) { await semantic.dispose(); return; }
        semanticRef.current = semantic;
        setMessage('正在加载叙事模型（Qwen2.5-0.5B narration）…');
        const narration = await loadEngine(NARRATION_MODEL);
        if (!alive) { await narration.dispose(); return; }
        narrationRef.current = narration;
        const model = new LocalGameModel(semantic, {
          narrationEngine: narration,
          onTask: (task, key, detail) => {
            console.info(`[world-local task] ${task} ${key} ${Math.round(detail.ms)}ms fallback=${detail.fallback} ${detail.error ?? ''}`);
            if (task === 'narration' && detail.fallback) setWarning(detail.error ?? '叙事事实校验未通过');
            if (task === 'narration' && !detail.fallback) setWarning(null);
          },
          onNarrationProgress: (progress) => {
            setPhase('streaming');
            setProse(progress.raw.replace(/※/g, '\n\n'));
          },
          onNarrationComplete: (progress) => {
            setProse(progress.raw.replace(/※/g, '\n\n'));
            setPhase('ready');
          },
        });
        modelRef.current = model;
        const saved = localStorage.getItem(SAVE_KEY);
        let session: LocalGameSession;
        if (saved) {
          try {
            session = await LocalGameSession.restore(JSON.parse(saved) as LocalGameSnapshot, model);
            setMessage('已恢复本地存档。');
          } catch (restoreError) {
            console.warn('[world-local] restore failed; starting new world', restoreError);
            localStorage.removeItem(SAVE_KEY);
            session = await LocalGameSession.create(world.initial, model, { worldId: world.worldId });
            await session.start();
          }
        } else {
          session = await LocalGameSession.create(world.initial, model, { worldId: world.worldId });
          await session.start();
        }
        sessionRef.current = session;
        await refresh();
        if (!alive) return;
        setPhase('ready');
        setMessage('本地世界已就绪。');
      } catch (e) {
        console.error(e);
        setPhase('error');
        setError(e instanceof Error ? `${e.name}: ${e.message}` : String(e));
      }
    })();
    return () => { alive = false; };
  }, [refresh]);

  const submit = useCallback(async () => {
    const session = sessionRef.current;
    const text = input.trim();
    if (!session || !text || busy) return;
    setBusy(true); setError(null); setWarning(null); setProse(''); setPhase('thinking');
    setMessage('正在判断行动、结算并写正文…');
    setInput('');
    modelRef.current?.resetAutoContinuations();
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
      setBusy(false);
    }
  }, [busy, input, refresh, save]);

  const reset = useCallback(async () => {
    if (!confirm('清除本地存档并重新开始？')) return;
    localStorage.removeItem(SAVE_KEY);
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
              <span>{phase === 'thinking' ? '结算中…' : phase === 'streaming' ? '正在写正文…' : message}</span>
            </div>
            <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.9, fontSize: 16 }}>
              {prose || (phase === 'loading' ? '正在加载本地模型，第一次会久一些。' : '等待输入…')}
            </div>
          </div>

          {warning && <div style={{ marginTop: 10, padding: '8px 10px', background: '#fff3d8', border: '1px solid #e4cb91', borderRadius: 6, fontSize: 12, color: '#7a5b19' }}>叙事事实校验未通过：{warning}。正文已保留，可继续游玩；这一问题会作为质量缺陷记录。</div>}
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
