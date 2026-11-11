'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';

import {
  GameControls,
  HistoryPanel,
  NarrationView,
  ProgressStatus,
  WorldLocalLayout,
  WorldStatusPanel,
  narrationAccepted,
  narrationFailed,
  narrationStreaming,
  worldStatusFromState,
  type ControlPhase,
  type ForkOption,
  type HistoryEntry,
  type NarrationState,
  type SaveState,
  type SyncState,
} from '@/components/world-local';
import type { WorldState } from '@/lib/world-engine/types';

import preview from './preview.module.css';

/* Handwritten fixture data. It exists only to exercise component states in
 * this preview page; the real /world-local page passes values from the
 * committed local session instead. No model, transport or localStorage call is
 * made here, and submitting an action never produces prose. */

const TIME = { calendar: 'gregorian' as const, dateTime: '2009-10-17T15:31:00', instantOrdinal: 0 };

const FIXTURE_STATE: WorldState = {
  engineVersion: 'world-engine-v1',
  schemaVersion: 1,
  worldId: 'world_preview_only',
  protagonistId: 'lu',
  time: TIME,
  initial: {
    engineVersion: 'world-engine-v1',
    schemaVersion: 1,
    worldId: 'world_preview_only',
    protagonistId: 'lu',
    initialTime: TIME,
    locations: {
      campus: { id: 'campus', name: '卡塞尔学院演习区', parentLocationId: null, initialAppearance: '示例地点', slots: [] },
      lane: { id: 'lane', name: '西侧服务巷', parentLocationId: 'campus', initialAppearance: '示例巷道', slots: [] },
      shed: { id: 'shed', name: '器材棚', parentLocationId: 'campus', initialAppearance: '示例器材棚', slots: [] },
    },
    items: {
      goggles: { id: 'goggles', name: '护目镜', initialPosition: { containerId: 'lane' }, initialAppearance: '示例物品', slots: [] },
    },
    characters: {
      lu: {
        id: 'lu', name: '路明非',
        initialPosition: { containerId: 'lane', slotId: 'slot_wall' },
        initialAppearance: '示例外貌',
        initialPersonality: '习惯先用一句玩笑替自己解围，真见到有人受伤又很难装作没看见。',
        initialSanity: 43,
        slots: [],
        tasks: {
          task_choice: { id: 'task_choice', ownerId: 'lu', parentTaskId: null, goal: '在自由一日结束前作出自己的参赛选择，并安全离场', status: 'pending' },
          task_goggles: { id: 'task_goggles', ownerId: 'lu', parentTaskId: null, goal: '戴上护目镜', status: 'achieved' },
        },
      },
      nono: {
        id: 'nono', name: '诺诺',
        initialPosition: { containerId: 'lane', slotId: 'slot_entry' },
        initialAppearance: '示例外貌',
        initialPersonality: '示例个性',
        initialSanity: 61,
        slots: [],
        tasks: {},
      },
      fingel: {
        id: 'fingel', name: '芬格尔',
        initialPosition: { containerId: 'shed', slotId: 'slot_counter' },
        initialAppearance: '示例外貌',
        initialPersonality: '示例个性',
        initialSanity: 55,
        slots: [],
        tasks: {},
      },
    },
  },
  locations: {
    campus: { id: 'campus', appearanceChanges: [] },
    lane: { id: 'lane', appearanceChanges: [] },
    shed: { id: 'shed', appearanceChanges: [] },
  },
  items: {
    goggles: { id: 'goggles', position: { containerId: 'lane' }, appearanceChanges: [] },
  },
  characters: {
    lu: {
      id: 'lu',
      position: { containerId: 'lane', slotId: 'slot_wall' },
      appearanceChanges: [],
      personalityChanges: [],
      sanity: 43,
      tasks: {
        task_choice: { id: 'task_choice', ownerId: 'lu', parentTaskId: null, goal: '在自由一日结束前作出自己的参赛选择，并安全离场', status: 'pending' },
        task_goggles: { id: 'task_goggles', ownerId: 'lu', parentTaskId: null, goal: '戴上护目镜', status: 'achieved' },
      },
    },
    nono: {
      id: 'nono',
      position: { containerId: 'lane', slotId: 'slot_entry' },
      appearanceChanges: [],
      personalityChanges: [],
      sanity: 61,
      tasks: {},
    },
    fingel: {
      id: 'fingel',
      position: { containerId: 'shed', slotId: 'slot_counter' },
      appearanceChanges: [],
      personalityChanges: [],
      sanity: 55,
      tasks: {},
    },
  },
};

const ACCEPTED_TEXT = [
  '我从墙根往前挪了半步，枪声在回廊另一头炸开，回声贴着石墙滚过来。',
  '诺诺靠在入口的立柱后，抬手示意我别急。她没说话，只用下巴点了点回廊深处。',
  '风从车道尽头吹过来，带着演习弹的硝烟味。我把呼吸压低，听见自己的鞋底在砂石上轻轻一响。',
].join('\n\n');

const STREAMING_TEXT = '我从墙根往前挪了半步，枪声在回廊另一头炸开，回声贴着石墙滚过来。';

const FORKS: ForkOption[] = [
  {
    snapshotId: 'snap_b',
    parentSnapshotIds: ['snap_a'],
    revision: 7,
    savedAtLabel: '10-27 21:14',
    summary: '在回廊听到第二声枪响之后',
  },
  {
    snapshotId: 'snap_a',
    parentSnapshotIds: [],
    revision: 4,
    savedAtLabel: '10-27 20:02',
    summary: '刚离开起点',
  },
];

const HISTORY: HistoryEntry[] = [
  { pointId: 'pt_root', sequence: 0, kind: 'root', timeLabel: '15:20', command: '开局', status: 'ready' },
  { pointId: 'pt_1', sequence: 1, kind: 'normal', timeLabel: '15:23', command: '我沿着车道向西回廊快走，贴着墙。', status: 'ready' },
  { pointId: 'pt_2', sequence: 2, kind: 'instant', timeLabel: '15:26', command: '我停下听枪声。', status: 'pending' },
  { pointId: 'pt_3', sequence: 3, kind: 'normal', timeLabel: '15:28', command: '我把护目镜戴上。', status: 'ready' },
  { pointId: 'pt_4', sequence: 4, kind: 'normal', timeLabel: '15:31', command: '我问诺诺要不要一起走。', status: 'failed' },
];

type NarrationFixture = 'idle' | 'streaming' | 'accepted' | 'warning' | 'failed';

const NARRATION_FIXTURES: { key: NarrationFixture; label: string }[] = [
  { key: 'idle', label: '等待行动' },
  { key: 'streaming', label: '流式生成' },
  { key: 'accepted', label: '已接受' },
  { key: 'warning', label: '校验提示' },
  { key: 'failed', label: '生成失败' },
];

const SAVE_FIXTURES: SaveState[] = ['idle', 'saving', 'saved', 'failed'];
const SYNC_FIXTURES: SyncState[] = ['local-only', 'offline', 'syncing', 'synced', 'failed', 'conflict'];

export function ComponentsPreview() {
  const [narrationFixture, setNarrationFixture] = useState<NarrationFixture>('accepted');
  const [historyMissing, setHistoryMissing] = useState(false);
  const [offline, setOffline] = useState(false);
  const [saveFixture, setSaveFixture] = useState<SaveState>('saved');
  const [syncFixture, setSyncFixture] = useState<SyncState>('synced');
  const [syncWired, setSyncWired] = useState(true);
  const [cancelWired, setCancelWired] = useState(false);
  const [regenerateWired, setRegenerateWired] = useState(false);
  const [forkWired, setForkWired] = useState(true);
  const [forksOn, setForksOn] = useState(true);
  const [activeFork, setActiveFork] = useState('snap_b');
  const [paused, setPaused] = useState(false);
  const [draft, setDraft] = useState('');
  const [selectedPoint, setSelectedPoint] = useState<string | null>('pt_3');
  const [lastRequest, setLastRequest] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const status = useMemo(() => worldStatusFromState(FIXTURE_STATE), []);

  const narration: NarrationState = useMemo(() => {
    switch (narrationFixture) {
      case 'idle':
        return { phase: 'idle', text: '' };
      case 'streaming':
        return narrationStreaming('pt_4', STREAMING_TEXT, 2400);
      case 'warning':
        return narrationAccepted('pt_4', ACCEPTED_TEXT, {
          elapsedMs: 6900,
          alignmentNote: '“退回走廊”在这轮状态变化里没有对应记录。',
        });
      case 'failed':
        return narrationFailed('叙事引擎在 120 秒内没有返回完整正文。', {
          pointId: 'pt_4',
          previousText: ACCEPTED_TEXT,
        });
      default:
        return narrationAccepted('pt_4', ACCEPTED_TEXT, { elapsedMs: 6900 });
    }
  }, [narrationFixture]);

  const history = useMemo(
    () => HISTORY.map((entry) => (
      entry.pointId === 'pt_3' && historyMissing ? { ...entry, status: 'missing' as const } : entry
    )),
    [historyMissing],
  );

  const reset = () => {
    setNarrationFixture('accepted');
    setHistoryMissing(false);
    setOffline(false);
    setSaveFixture('saved');
    setSyncFixture('synced');
    setSyncWired(true);
    setCancelWired(false);
    setRegenerateWired(false);
    setForkWired(true);
    setForksOn(true);
    setActiveFork('snap_b');
    setPaused(false);
    setDraft('');
    setSelectedPoint('pt_3');
    setLastRequest(null);
    setNote(null);
  };

  const phase: ControlPhase = paused ? 'paused' : narrationFixture === 'streaming' ? 'streaming' : 'ready';
  const busy = narrationFixture === 'streaming';

  return (
    <div className={preview.shell}>
      <header className={preview.hero}>
        <p className={preview.kicker}>组件预览</p>
        <h1 className={preview.heroTitle}>world-local 阅读、历史与操作组件</h1>
        <p className={preview.heroText}>
          本页只检查组件状态和回调接线。正文、世界状态、历史时间点与分叉都是手写示例数据；页面不加载模型、
          不读取真实存档，也不能替代真实游戏入口。
        </p>
        <p className={preview.heroText}>
          <Link className={preview.link} href="/world-local">前往真实游戏入口 /world-local</Link>
          <span>（真实入口由主 agent 接线，本页不抢改它的页面文件。）</span>
        </p>
      </header>

      <section aria-label="预览状态开关" className={preview.switches}>
        <div className={preview.switchGroup}>
          <span className={preview.groupLabel}>正文状态</span>
          <div className={preview.buttonRow}>
            {NARRATION_FIXTURES.map((fixture) => (
              <button
                aria-pressed={narrationFixture === fixture.key}
                className={preview.toggle}
                data-preview={`narration-${fixture.key}`}
                key={fixture.key}
                onClick={() => { setNarrationFixture(fixture.key); setPaused(false); }}
                type="button"
              >
                {fixture.label}
              </button>
            ))}
          </div>
        </div>

        <div className={preview.switchGroup}>
          <span className={preview.groupLabel}>数据状态</span>
          <label className={preview.check}>
            <input
              checked={historyMissing}
              data-preview="history-missing"
              onChange={(event) => setHistoryMissing(event.target.checked)}
              type="checkbox"
            />
            #3 正文缓存缺失
          </label>
          <label className={preview.check}>
            <input
              checked={offline}
              data-preview="offline"
              onChange={(event) => setOffline(event.target.checked)}
              type="checkbox"
            />
            离线
          </label>
          <label className={preview.check}>
            本地保存
            <select
              data-preview="save-state"
              onChange={(event) => setSaveFixture(event.target.value as SaveState)}
              value={saveFixture}
            >
              {SAVE_FIXTURES.map((state) => <option key={state} value={state}>{state}</option>)}
            </select>
          </label>
          <label className={preview.check}>
            同步状态
            <select
              data-preview="sync-state"
              onChange={(event) => setSyncFixture(event.target.value as SyncState)}
              value={syncFixture}
            >
              {SYNC_FIXTURES.map((state) => <option key={state} value={state}>{state}</option>)}
            </select>
          </label>
        </div>

        <div className={preview.switchGroup}>
          <span className={preview.groupLabel}>模拟接线</span>
          <label className={preview.check}>
            <input checked={syncWired} data-preview="sync-wired" onChange={(event) => setSyncWired(event.target.checked)} type="checkbox" />
            同步客户端
          </label>
          <label className={preview.check}>
            <input checked={cancelWired} data-preview="cancel-wired" onChange={(event) => setCancelWired(event.target.checked)} type="checkbox" />
            取消本轮
          </label>
          <label className={preview.check}>
            <input checked={regenerateWired} data-preview="regenerate-wired" onChange={(event) => setRegenerateWired(event.target.checked)} type="checkbox" />
            正文重生成
          </label>
          <label className={preview.check}>
            <input checked={forkWired} data-preview="fork-wired" onChange={(event) => setForkWired(event.target.checked)} type="checkbox" />
            分叉选择
          </label>
          <label className={preview.check}>
            <input checked={forksOn} data-preview="forks-on" onChange={(event) => setForksOn(event.target.checked)} type="checkbox" />
            显示分叉
          </label>
        </div>

        <div className={preview.switchGroup}>
          <span className={preview.groupLabel}>预览事件</span>
          <p className={preview.request} data-testid="preview-request">
            {lastRequest ? `最近一次预览提交：${lastRequest}` : '尚未提交行动'}
          </p>
          <p className={preview.note} data-testid="preview-note" role="status">
            {note ?? '切换上方状态即可检查各组件的显示；提交不会生成正文。'}
          </p>
          <button className={preview.toggle} data-preview="reset" onClick={reset} type="button">重置预览状态</button>
        </div>
      </section>

      <WorldLocalLayout
        banner={(
          <div className={preview.banner} role="note">
            <strong>组件预览，不是游戏。</strong>
            <span>所有可见正文与状态均为示例；真实游玩请使用 /world-local。</span>
          </div>
        )}
        controls={(
          <GameControls
            busy={busy}
            onCancel={cancelWired ? () => {
              setPaused(false);
              setLastRequest(null);
              setNote('预览：取消回调已触发；示例正文与历史没有被改动。');
            } : undefined}
            onChange={setDraft}
            onPause={() => {
              setPaused(true);
              setNote('预览：暂停回调已触发；真实页面应在当前回合进行中调用 session.pause()。');
            }}
            onResume={() => {
              setPaused(false);
              setNote('预览：继续回调已触发；真实页面应调用 session.resume()。');
            }}
            onSubmit={(text) => {
              setDraft('');
              setLastRequest(text);
              setNote(`预览收到行动「${text}」。这里不调用模型，正文保持示例数据不变。`);
            }}
            paused={paused}
            phase={phase}
            value={draft}
          />
        )}
        footer={(
          <p>
            组件导出见 <code>frontend/src/components/world-local/index.ts</code>；
            接线片段见 <code>design/parallel-handoff/09-ui.md</code>。
          </p>
        )}
        history={(
          <HistoryPanel
            entries={history}
            headPointId="pt_4"
            onRegenerate={regenerateWired ? (pointId) => {
              setNote(`预览：已请求为时间点 ${pointId} 重新生成正文（未调用模型）。`);
            } : undefined}
            onSelect={(pointId) => {
              setSelectedPoint(pointId);
              setNote(`预览：已选中时间点 ${pointId}；真实页面应从已提交状态读取该点。`);
            }}
            selectedPointId={selectedPoint}
          />
        )}
        meta={<span className={preview.metaBadge}>示例数据</span>}
        narration={(
          <NarrationView
            onRegenerate={regenerateWired ? () => {
              setNote('预览：已请求重新生成本轮正文（未调用模型）。');
            } : undefined}
            state={narration}
            title="本轮正文 · 示例"
          />
        )}
        progress={(
          <ProgressStatus
            activeForkId={activeFork}
            forks={forksOn ? FORKS : []}
            onChooseFork={forkWired ? (snapshotId) => {
              setActiveFork(snapshotId);
              setNote(`预览：已把活跃分支切换为 ${snapshotId}；不合并任何示例状态。`);
            } : undefined}
            online={!offline}
            save={{
              state: saveFixture,
              savedAtLabel: '10-27 21:14:08',
              error: saveFixture === 'failed' ? '示例：浏览器拒绝写入本地存储。' : null,
              onRetry: saveFixture === 'failed' ? () => {
                setSaveFixture('saved');
                setNote('预览：已触发保存重试回调并切回“已保存”示例。');
              } : undefined,
            }}
            sync={syncWired ? {
              state: syncFixture,
              lastSyncedAtLabel: '10-27 21:14:20',
              error: syncFixture === 'failed' ? '示例：进度服务返回 503。' : null,
              onSync: () => {
                setSyncFixture('synced');
                setNote('预览：已触发同步回调（不访问网络）。');
              },
            } : null}
          />
        )}
        status={<WorldStatusPanel status={status} />}
        subtitle="示例数据 · 不连接模型 · 不读写真实存档"
        title="龙族 · 自由一日（组件预览）"
      />
    </div>
  );
}
