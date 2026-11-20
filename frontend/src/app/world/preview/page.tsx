/** 只读展示预览：事实句来自冻结适配器，页面不写任何东西。
 * 三种状态必须分得开：已展示事实、存在尚未展示的变化、该点位事实暂无法恢复。
 * 模型句不参与替换；来源只在诊断区展开。 */
'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { describePreview } from './preview-state';

const BASE = process.env.NEXT_PUBLIC_PREVIEW_URL ?? 'http://127.0.0.1:8711';

interface PointRef { pointId: string; sequence: number; kind: string; previousPointId: string | null }
interface WorldRef { worldId: string; points: PointRef[] }
interface Provenance {
  stateSource?: string | null; fieldsRead?: string[] | null; replayOk?: boolean | null;
  replayAgreesWithCheckpoint?: boolean | null; currentDigestMatchesPoint?: boolean | null;
}
interface Fact { kind: string; sentence: string; provenance: Provenance }
interface Gap { gap: string; replayFailure?: string | null }
interface Preview {
  worldId: string; pointId: string; sequence: number; previousPointId: string | null;
  delta: unknown; facts: Fact[]; gaps: Gap[]; notDisplayed: { reason: string }[];
}

export default function PreviewPage() {
  const [worlds, setWorlds] = useState<WorldRef[]>([]);
  const [worldId, setWorldId] = useState('');
  const [pointId, setPointId] = useState('');
  const [data, setData] = useState<Preview | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch(`${BASE}/worlds`)
      .then((r) => r.json())
      .then((payload: { worlds: WorldRef[] }) => {
        setWorlds(payload.worlds);
        const first = payload.worlds[0];
        if (first) {
          setWorldId(first.worldId);
          setPointId(first.points.at(-1)?.pointId ?? '');
        }
      })
      .catch(() => setError('预览服务不可用：先启动 experiments/world-components/preview_server.py'));
  }, []);

  const points = useMemo(() => worlds.find((w) => w.worldId === worldId)?.points ?? [], [worlds, worldId]);

  // 只认最后一次选择：旧请求被中止，迟到结果也不落地
  const sequence = useRef(0);
  const inflight = useRef<AbortController | null>(null);
  const load = useCallback(async (world: string, point: string) => {
    if (!world || !point) return;
    const id = sequence.current + 1;
    sequence.current = id;
    inflight.current?.abort();
    const controller = new AbortController();
    inflight.current = controller;
    try {
      const response = await fetch(
        `${BASE}/preview?world=${encodeURIComponent(world)}&point=${encodeURIComponent(point)}`,
        { signal: controller.signal },
      );
      if (!response.ok) throw new Error(await response.text());
      const payload = await response.json();
      if (sequence.current !== id) return;
      setData(payload);
      setError('');
    } catch (cause) {
      if (sequence.current !== id) return;
      setData(null);
      setError(`读取失败：${String(cause)}`);
    }
  }, []);

  useEffect(() => { void load(worldId, pointId); }, [worldId, pointId, load]);

  const view = data ? describePreview(data) : null;

  return (
    <main className="preview-page">
      <h1 className="preview-title">只读展示预览</h1>
      <p className="preview-lede">
        事实句由冻结适配器直接读出：按点位取已提交记录，沿 previousPointId 读前态。
        页面不写回回合记录、不改状态，模型句不参与替换。
      </p>

      <div className="preview-bar">
        <label>世界
          <select
            className="preview-select"
            value={worldId}
            onChange={(event) => {
              const next = event.target.value;
              setWorldId(next);
              setPointId(worlds.find((w) => w.worldId === next)?.points.at(-1)?.pointId ?? '');
            }}
          >
            {worlds.map((w) => <option key={w.worldId} value={w.worldId}>{w.worldId}</option>)}
          </select>
        </label>
        <label>点位
          <select className="preview-select" value={pointId} onChange={(e) => setPointId(e.target.value)}>
            {points.map((p) => <option key={p.pointId} value={p.pointId}>{p.sequence} · {p.pointId}</option>)}
          </select>
        </label>
      </div>

      {error && <div className="preview-card preview-card--stop">{error}</div>}

      {data && view && (
        <>
          <div className="preview-card">
            <div className="preview-meta">
              点位 {data.pointId}（第 {data.sequence} 点，前驱 {data.previousPointId ?? '无'}）
            </div>
            {view.sentences.map((sentence) => (
              <p key={sentence} className="preview-fact">{sentence}</p>
            ))}
            {view.band === 'empty' && view.quietPoint && (
              <p className="preview-quiet">这一点位没有实体变化（结构化增量为空）。</p>
            )}
            {view.band === 'empty' && !view.quietPoint && (
              <p className="preview-quiet">这一点位有增量，但当前没有可展示的句子。</p>
            )}
          </div>

          {view.band === 'unshown' && (
            <div className="preview-card preview-card--warn">
              存在尚未展示的变化。
              <div className="preview-meta">
                这部分已提交的变化还没有展示句，因此没有写进上面的句子，也没有被当作“没有变化”。
              </div>
              <div className="preview-meta">{view.unshownReason}</div>
            </div>
          )}

          {view.band === 'gap' && (
            <div className="preview-card preview-card--stop">
              该点位事实暂无法恢复。
              <ul>
                {view.gapMessages.map((message) => <li key={message} className="preview-meta">{message}</li>)}
              </ul>
            </div>
          )}

          <details className="preview-card preview-diagnostics">
            <summary>诊断：来源与结构化增量</summary>
            <pre>{JSON.stringify({ delta: data.delta, facts: data.facts, gaps: data.gaps }, null, 2)}</pre>
          </details>
        </>
      )}
    </main>
  );
}
