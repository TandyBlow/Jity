'use client';

/** 最小世界交互页：同一世界连续执行多条规则命令、模板叙事、刷新续接。
 * 世界状态与叙事只来自服务端事实（get_state / narration_get / list_points），
 * 会话续接走 RuleWorldSession 的 H2 recover 路径；刷新前的租约凭据保存在
 * sessionStorage，恢复时先 lease_renew 续租、失败则降级为接管。模型润色
 * 是可选实验：任何加载/生成/校验失败都保持提交模板可用。 */
import { useEffect, useRef, useState } from 'react';
import { HttpWorldTransport } from '@/lib/world-engine/http-transport';
import { WorldTimeoutError, type WorldTransport } from '@/lib/world-engine/transport';
import { RuleWorldSession, type RuleNarrationPolisher, type RuleSessionEvent } from '@/lib/world-engine/runtime/rule-session';
import type { DriverStatus } from '@/lib/world-engine/controller';
import { DEFAULT_POLISH_MODEL, WORLD_POLICY, defaultInitialTemplate } from './world-defaults';
import type { Id, InitialTemplate, Json, RequestMap, Scope, Success, TimeAdvance, WorldOperation, WorldState } from '@/lib/world-engine/types';

interface LeaseGrant { leaseToken: Id; fenceEpoch: number }

/** 页面传输层：记录最新租约凭据（供 sessionStorage 续接），并可注入一次
 * 「提交回执丢失」——服务端已受理 commit_point 之后抛超时，驱动必须以同一
 * requestId 重试并收到 replayed 回执，世界不得被重复消费。 */
class PageTransport implements WorldTransport {
  grant: LeaseGrant | null = null;
  private dropNextCommit = false;
  constructor(private readonly inner: WorldTransport, private readonly onLease: (grant: LeaseGrant | null) => void) {}
  armLostReceipt(): void { this.dropNextCommit = true; }
  async execute<K extends WorldOperation>(operation: K, request: RequestMap[K], scope: Scope, signal?: AbortSignal): Promise<Success<K>> {
    const response = await this.inner.execute(operation, request, scope, signal);
    if (operation === 'commit_point' && this.dropNextCommit) {
      this.dropNextCommit = false;
      throw new WorldTimeoutError('已注入：提交回执丢失（服务端已受理，驱动将以同一 requestId 重试）');
    }
    const data = (response as { data?: Record<string, unknown> }).data ?? {};
    const grant = operation === 'create_world' ? data.lease
      : operation === 'lease_acquire' || operation === 'lease_renew' ? data : undefined;
    if (grant && typeof grant === 'object' && typeof (grant as { leaseToken?: unknown }).leaseToken === 'string') {
      const typed = grant as LeaseGrant;
      this.grant = { leaseToken: typed.leaseToken, fenceEpoch: typed.fenceEpoch };
      this.onLease(this.grant);
    }
    return response;
  }
}

interface PersistedSession { api: string; worldId: Id; leaseToken: Id | null; fenceEpoch: number | null; commands: string[] }
const STORAGE_KEY = 'jity.world.page.v1';
const DEFAULT_API = 'http://127.0.0.1:18784';

function loadPersisted(): PersistedSession | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as PersistedSession;
    return value.worldId ? value : null;
  } catch { return null; }
}
function savePersisted(value: PersistedSession | null): void {
  try {
    if (value) window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else window.sessionStorage.removeItem(STORAGE_KEY);
  } catch { /* 私有模式下持久化不可用：刷新续接退化为手动接管 */ }
}

const UNIT_TEXT: Record<string, string> = { second: '秒', minute: '分', hour: '小时', day: '天', month: '月', year: '年' };
function describeAdvance(advance: TimeAdvance | null): string | null {
  if (!advance) return null;
  if (advance.boundary === 'instant') return '同一时刻';
  return `+${advance.duration.amount}${UNIT_TEXT[advance.duration.unit] ?? advance.duration.unit}`;
}

interface LogRow { pointId: Id; version: number; text: string; timeText: string | null; polished: boolean }
interface StatusView {
  locationId: Id; locationName: string; locationNames: Record<Id, string>; sanity: number; timeText: string;
  tasks: { goal: string; achieved: boolean }[]; personality: string;
}

/** 润色实验的真实实现：懒加载 wllama 引擎与真实提示层（按模型路径缓存）；
 * 输出必须整体通过事实校验（由 rule-session 的 selectFactNarration 把关），
 * 否则回退模板。 */
const polishEngines = new Map<string, Promise<RuleNarrationPolisher>>();
function polishEngine(modelUrl: string): Promise<RuleNarrationPolisher> {
  let engine = polishEngines.get(modelUrl);
  if (!engine) {
    engine = (async () => {
      const [{ WllamaInferenceEngine }, { RuntimeWorldModelPort }] = await Promise.all([
        import('@/lib/world-engine/runtime/wllama-engine'),
        import('@/lib/world-engine/runtime/model-port'),
      ]);
      const wllama = new WllamaInferenceEngine({ modelUrl, contextSize: 2048 });
      const port = new RuntimeWorldModelPort(wllama, undefined, { inputMode: 'focused', taskMaxTokens: { narration: 64 }, timeoutMs: 120_000 });
      return async (input) => {
        const text = await port.generate('narration', input.pointId, input as unknown as Json);
        if (typeof text !== 'string' || !text.trim()) throw new Error('润色输出为空');
        return text.trim();
      };
    })();
    engine.catch(() => polishEngines.delete(modelUrl)); // 失败的加载可重试
    polishEngines.set(modelUrl, engine);
  }
  return engine;
}

// StrictMode 双挂载下只 bootstrap 一次；刷新续接本来就是整页重载。
let booted = false;

interface ActiveSession { session: RuleWorldSession; page: PageTransport }

export default function WorldPage() {
  const [phase, setPhase] = useState<'boot' | 'disconnected' | 'connecting' | 'ready' | 'running'>('boot');
  const [api, setApi] = useState('');
  const [worldId, setWorldId] = useState<Id | null>(null);
  const [leaseLabel, setLeaseLabel] = useState('无租约');
  const [status, setStatus] = useState<StatusView | null>(null);
  const [log, setLog] = useState<LogRow[]>([]);
  const [command, setCommand] = useState('');
  const [lastAction, setLastAction] = useState('');
  const [note, setNote] = useState('');
  const [polishOn, setPolishOn] = useState(false);
  const [polishModel, setPolishModel] = useState(DEFAULT_POLISH_MODEL);
  const [dropNextArmed, setDropNextArmed] = useState(false);
  const activeRef = useRef<ActiveSession | null>(null);
  const commandsRef = useRef<string[]>([]);
  const polishOnRef = useRef(false);
  const polishModelRef = useRef(DEFAULT_POLISH_MODEL);
  polishOnRef.current = polishOn;
  polishModelRef.current = polishModel;

  const persistLease = (grant: LeaseGrant | null) => {
    const saved = loadPersisted();
    if (saved && grant) {
      saved.leaseToken = grant.leaseToken;
      saved.fenceEpoch = grant.fenceEpoch;
      savePersisted(saved);
    }
  };

  /** 会话持有的稳定包装器：开关即时生效。关闭→null（模板，无事件）；开启→
   * 懒加载引擎生成候选。整个尝试受截止时间约束——wllama 加载或生成一旦
   * 挂起（无头环境/wasm 卡住），可选项绝不能阻塞命令回合，超时即回退模板。 */
  const lazyPolisher: RuleNarrationPolisher = async (input, packet) => {
    if (!polishOnRef.current) return null;
    void packet;
    const deadlineMs = 120_000;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const deadline = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error(`润色尝试超过 ${deadlineMs / 1000}s 未完成（加载或生成挂起）`)), deadlineMs);
    });
    try {
      const attempt = async () => (await polishEngine(polishModelRef.current))(input, packet);
      return await Promise.race([attempt(), deadline]);
    } finally {
      clearTimeout(timer);
    }
  };

  const handleEvent = (event: RuleSessionEvent) => {
    if (event.kind === 'narration') {
      setLog((rows) => [...rows, { pointId: event.pointId, version: event.version, text: event.text, timeText: null, polished: event.polished }]);
    } else if (event.kind === 'decision') {
      setLastAction(event.outcome === 'allowed' ? `已执行：${event.text}` : `已拒绝（${event.reason}）：${event.text}`);
    } else if (event.kind === 'unparsed') {
      setLastAction(`未识别的命令「${event.inputText}」——没有产生任何规则动作。`);
    } else if (event.kind === 'polishFallback') {
      setNote(`润色失败，已回退模板：${event.detail}`);
    }
  };

  const describeStatus = (state: WorldState): StatusView => {
    const protagonist = state.characters[state.protagonistId];
    const location = state.initial.locations[protagonist.position.containerId];
    const personality = [...protagonist.personalityChanges].filter((change) => change.active).at(-1)?.text
      ?? state.initial.characters[state.protagonistId].initialPersonality;
    return {
      locationId: protagonist.position.containerId,
      locationName: location?.name ?? protagonist.position.containerId,
      locationNames: Object.fromEntries(Object.entries(state.initial.locations).map(([id, place]) => [id, place.name])),
      sanity: protagonist.sanity,
      timeText: state.time.dateTime,
      tasks: Object.values(protagonist.tasks).map((task) => ({ goal: task.goal, achieved: task.status === 'achieved' })),
      personality,
    };
  };

  /** 以服务端事实重建整页视图：叙事行（含时间推进）与状态面板。 */
  const rebuild = async (wid: Id, transport: WorldTransport) => {
    const points = (await transport.execute('list_points', { after: null, limit: 100 }, { worldId: wid })).data.points;
    const rows: LogRow[] = [];
    let headState: WorldState | null = null;
    for (const point of points) {
      const narration = (await transport.execute('narration_get', {}, { worldId: wid, pointId: point.pointId })).data;
      const read = (await transport.execute('get_state', { point: point.pointId }, { worldId: wid })).data;
      if (point.pointId === points.at(-1)?.pointId) headState = read.state;
      rows.push({
        pointId: point.pointId,
        version: read.version,
        text: narration.text ?? `（叙事状态：${narration.narrationStatus}）`,
        timeText: describeAdvance(read.timeAdvance),
        polished: false,
      });
    }
    setLog(rows);
    if (headState) setStatus(describeStatus(headState));
  };

  const buildTransport = (apiBase: string) => new PageTransport(new HttpWorldTransport(apiBase), persistLease);

  const markTerminalNote = (status: DriverStatus) => {
    if (status.kind === 'stop' && status.reason === 'world_complete') return;
    if (status.kind === 'stop') setNote(`会话停止：${status.reason}`);
    else if (status.kind === 'error') setNote(`会话错误：${status.detail}`);
    else setNote(`等待中：${status.reason}`);
  };

  const stopActive = () => {
    activeRef.current?.session.stop();
    activeRef.current = null;
  };

  /** 恢复既有世界：先读服务端事实派生模板，再走 recover；持约续租失败时
   * 降级为一次接管。 */
  const attach = async (saved: PersistedSession, apiBase: string) => {
    stopActive();
    setPhase('connecting');
    setWorldId(saved.worldId);
    const transport = buildTransport(apiBase);
    const head = await transport.execute('get_state', {}, { worldId: saved.worldId });
    const initial = structuredClone(head.data.state.initial) as InitialTemplate & { worldId?: Id };
    delete initial.worldId;
    const heldLease = saved.leaseToken && saved.fenceEpoch != null ? { leaseToken: saved.leaseToken, fenceEpoch: saved.fenceEpoch } : undefined;
    setLeaseLabel(heldLease ? '续租中' : '接管中');
    const attachOnce = async (lease: { leaseToken: Id; fenceEpoch: number } | undefined): Promise<DriverStatus> => {
      const session = RuleWorldSession.createRecovered({
        transport, initial, policy: WORLD_POLICY, polish: lazyPolisher, onEvent: handleEvent,
      }, saved.worldId, lease);
      activeRef.current = { session, page: transport };
      const terminal = await session.attach();
      return terminal;
    };
    let terminal = await attachOnce(heldLease);
    if (terminal.kind === 'stop' && terminal.reason.startsWith('recovery_refused') && heldLease) {
      setNote('续租被拒，改为接管重连…');
      stopActive();
      terminal = await attachOnce(undefined);
    }
    // 任何恢复 stop（除 handback 边界的 world_complete）都意味着驱动已被
    // recoveryBarrier 闩住——绝不能带着死驱动进入 ready。
    if (terminal.kind === 'stop' && terminal.reason !== 'world_complete') throw new Error(terminal.reason);
    if (terminal.kind === 'error') throw new Error(terminal.detail);
    setLeaseLabel(transport.grant ? `租约有效（epoch ${transport.grant.fenceEpoch}）` : '无租约');
    commandsRef.current = saved.commands;
    await rebuild(saved.worldId, transport);
    setPhase('ready');
    setNote('');
  };

  const connectNew = async (apiBase: string) => {
    stopActive();
    setPhase('connecting');
    setWorldId(null);
    const transport = buildTransport(apiBase);
    const session = RuleWorldSession.createNew({ transport, initial: defaultInitialTemplate(), policy: WORLD_POLICY, polish: lazyPolisher, onEvent: handleEvent });
    activeRef.current = { session, page: transport };
    await session.attach(); // 创建世界＋根叙事；无输入即在 handback 边界停住
    const wid = session.worldId;
    if (!wid) throw new Error('world_creation_missing');
    setWorldId(wid);
    commandsRef.current = [];
    savePersisted({ api: apiBase, worldId: wid, leaseToken: transport.grant?.leaseToken ?? null, fenceEpoch: transport.grant?.fenceEpoch ?? null, commands: [] });
    setLeaseLabel(transport.grant ? `租约有效（epoch ${transport.grant.fenceEpoch}）` : '无租约');
    await rebuild(wid, transport);
    setPhase('ready');
    setNote('');
  };

  const disconnect = () => {
    activeRef.current?.session.stop();
    activeRef.current = null;
    savePersisted(null);
    setWorldId(null);
    setStatus(null);
    setLog([]);
    setLastAction('');
    setLeaseLabel('无租约');
    setPhase('disconnected');
  };

  const submit = async () => {
    const active = activeRef.current;
    const wid = worldId;
    const text = command.trim();
    if (!active || !wid || !text || phase !== 'ready') return;
    if (dropNextArmed) {
      active.page.armLostReceipt();
      setDropNextArmed(false);
    }
    setPhase('running');
    setLastAction('');
    setNote('');
    try {
      const terminal = await active.session.submit(text);
      commandsRef.current = [...commandsRef.current, text];
      const saved = loadPersisted();
      if (saved) { saved.commands = commandsRef.current; savePersisted(saved); }
      markTerminalNote(terminal);
      setLeaseLabel(active.page.grant ? `租约有效（epoch ${active.page.grant.fenceEpoch}）` : '租约失效');
    } finally {
      setCommand('');
      await rebuild(wid, active.page);
      setPhase('ready');
    }
  };

  useEffect(() => {
    if (booted) return;
    booted = true;
    void (async () => {
      try {
        const params = new URLSearchParams(window.location.search);
        const saved = loadPersisted();
        const apiBase = params.get('api') ?? saved?.api ?? window.localStorage.getItem('jity.world.api') ?? DEFAULT_API;
        setApi(apiBase);
        window.localStorage.setItem('jity.world.api', apiBase);
        if (saved?.worldId) await attach(saved, apiBase);
        else setPhase('disconnected');
      } catch (error) {
        setNote(`续接失败：${error instanceof Error ? error.message : String(error)}`);
        setPhase('disconnected');
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const busy = phase === 'running' || phase === 'connecting' || phase === 'boot';
  const moveHints = status
    ? WORLD_POLICY.routes.filter((route) => route.from === status.locationId)
      .map((route) => ({ label: `走到${status.locationNames[route.to] ?? route.to}`, minimumSanity: route.minimumSanity }))
    : [];

  return (
    <main className="mx-auto max-w-3xl space-y-4 p-6 text-sm text-zinc-800">
      <header className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">世界最小交互页</h1>
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          {worldId && <span className="rounded bg-zinc-100 px-2 py-0.5 font-mono">{worldId}</span>}
          <span className={`rounded px-2 py-0.5 ${leaseLabel === '无租约' ? 'bg-zinc-100' : 'bg-emerald-100 text-emerald-700'}`}>{leaseLabel}</span>
        </div>
      </header>

      <section className="rounded border border-zinc-200 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs text-zinc-500" htmlFor="world-api">服务地址</label>
          <input id="world-api" className="min-w-64 flex-1 rounded border border-zinc-300 px-2 py-1 font-mono text-xs"
            value={api} onChange={(event) => setApi(event.target.value)} disabled={busy} />
          <button className="rounded bg-zinc-800 px-3 py-1 text-xs text-white disabled:opacity-50"
            onClick={() => void connectNew(api)} disabled={busy}>
            新世界
          </button>
          {phase === 'disconnected' && loadPersisted()?.worldId && (
            <button className="rounded border border-zinc-400 px-3 py-1 text-xs disabled:opacity-50"
              onClick={() => { const saved = loadPersisted(); if (saved) void attach(saved, api).catch((error) => { setNote(`续接失败：${error instanceof Error ? error.message : String(error)}`); setPhase('disconnected'); }); }}
              disabled={busy}>
              刷新续接
            </button>
          )}
          {worldId && <button className="rounded border border-zinc-400 px-3 py-1 text-xs" onClick={disconnect} disabled={busy}>断开</button>}
        </div>
        {note && <p className="mt-2 text-xs text-amber-700">{note}</p>}
      </section>

      <section className="rounded border border-zinc-200 p-3">
        <h2 className="mb-2 text-xs font-semibold text-zinc-500">状态（服务端事实）</h2>
        {status ? (
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <div><span className="text-zinc-500">地点</span><p className="font-medium">{status.locationName}</p></div>
            <div><span className="text-zinc-500">精神值</span><p className="font-medium">{status.sanity}</p></div>
            <div><span className="text-zinc-500">世界时间</span><p className="font-medium font-mono text-xs">{status.timeText}</p></div>
            <div><span className="text-zinc-500">人格</span><p className="text-xs">{status.personality}</p></div>
            <div className="col-span-2 md:col-span-4">
              <span className="text-zinc-500">任务</span>
              {status.tasks.length ? (
                <ul className="mt-1 space-y-0.5">
                  {status.tasks.map((task) => (
                    <li key={task.goal} className={task.achieved ? 'text-emerald-700' : ''}>
                      {task.achieved ? '✓' : '·'} {task.goal}{task.achieved ? '（已达成）' : ''}
                    </li>
                  ))}
                </ul>
              ) : <p className="text-zinc-400">无登记任务</p>}
            </div>
          </div>
        ) : <p className="text-zinc-400">尚未连接世界。</p>}
      </section>

      <section className="rounded border border-zinc-200 p-3">
        <h2 className="mb-2 text-xs font-semibold text-zinc-500">支持命令与执行状态</h2>
        <div className="flex gap-2">
          <input className="flex-1 rounded border border-zinc-300 px-2 py-1" placeholder="输入命令，例如：走到门厅"
            value={command} onChange={(event) => setCommand(event.target.value)} disabled={phase !== 'ready'}
            onKeyDown={(event) => { if (event.key === 'Enter') void submit(); }} />
          <button className="rounded bg-zinc-800 px-4 py-1 text-xs text-white disabled:opacity-50"
            onClick={() => void submit()} disabled={phase !== 'ready'}>
            {phase === 'running' ? '执行中…' : '执行'}
          </button>
        </div>
        <ul className="mt-2 space-y-0.5 text-xs text-zinc-500">
          <li>移动：走到〈地点〉——当前可选：{moveHints.length
            ? moveHints.map((hint) => `${hint.label}${hint.minimumSanity ? `（精神值≥${hint.minimumSanity}）` : ''}`).join('、')
            : '（无可用路线）'}</li>
          <li>完成压力试验（须在走廊，精神值 −2）</li>
          <li>完成恢复练习（须在走廊，精神值 +1）</li>
          <li>其他文本不会产生任何规则动作；被拒绝的命令会给出原因，世界时间仍按已提交点推进。</li>
        </ul>
        {lastAction && <p className={`mt-2 text-xs ${lastAction.startsWith('已拒绝') || lastAction.startsWith('未识别') ? 'text-red-600' : 'text-emerald-700'}`}>{lastAction}</p>}
      </section>

      <section className="rounded border border-zinc-200 p-3">
        <h2 className="mb-2 text-xs font-semibold text-zinc-500">叙事（提交模板；润色仅为实验）</h2>
        <div className="mb-3 flex flex-wrap items-center gap-3 text-xs">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={polishOn} onChange={(event) => setPolishOn(event.target.checked)} disabled={busy} />
            模型润色（可选实验，失败保持模板）
          </label>
          <input className="w-64 rounded border border-zinc-300 px-2 py-0.5 font-mono text-[11px]" value={polishModel}
            onChange={(event) => setPolishModel(event.target.value)} disabled={busy} aria-label="润色模型路径" />
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={dropNextArmed} onChange={(event) => setDropNextArmed(event.target.checked)} disabled={busy} />
            下一次提交丢回执（验证不重复消费）
          </label>
        </div>
        {log.length ? (
          <ol className="space-y-1">
            {log.map((row) => (
              <li key={row.pointId} className="rounded bg-zinc-50 px-2 py-1 text-xs leading-relaxed">
                <span className="mr-1 font-mono text-[11px] text-zinc-400">v{row.version}{row.timeText ? `·${row.timeText}` : ''}</span>
                {row.text}
                {row.polished && <span className="ml-1 rounded bg-sky-100 px-1 text-[11px] text-sky-700">润色</span>}
              </li>
            ))}
          </ol>
        ) : <p className="text-zinc-400">尚无叙事。</p>}
      </section>
    </main>
  );
}
