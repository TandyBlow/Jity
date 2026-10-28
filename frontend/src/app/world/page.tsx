'use client';

/** 最小世界交互页：同一世界连续执行多条规则命令、模板叙事、刷新续接。
 * 世界状态与叙事只来自服务端事实（get_state / narration_get / list_points），
 * 会话续接走 RuleWorldSession 的 H2 recover 路径；刷新前的租约凭据保存在
 * sessionStorage，恢复时先 lease_renew 续租、失败则降级为接管。模型润色
 * 是可选实验：任何加载/生成/校验失败都保持提交模板可用。 */
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { HttpWorldTransport } from '@/lib/world-engine/http-transport';
import { WorldTimeoutError, type WorldTransport } from '@/lib/world-engine/transport';
import { RuleWorldSession, type RuleNarrationPolisher, type RuleSessionEvent } from '@/lib/world-engine/runtime/rule-session';
import { readAllPoints } from '@/lib/world-engine/runtime/world-reads';
import type { DriverStatus } from '@/lib/world-engine/controller';
import { DEFAULT_POLISH_MODEL, WORLD_POLICY, defaultInitialTemplate } from './world-defaults';
import type { Id, InitialTemplate, RequestMap, Scope, Success, TimeAdvance, WorldOperation, WorldState } from '@/lib/world-engine/types';

interface LeaseGrant { leaseToken: Id; fenceEpoch: number }

/** 取消信号：attach/rebuild 在每个 await 边界与发布点检查 isStale，失效时
 * 抛出。调用方的 stale 分支吞掉它；它绝不应出现在非 stale 路径。 */
class BootstrapCancelled extends Error {
  readonly name = 'BootstrapCancelled';
}
function throwIfStale(isStale: () => boolean): void {
  if (isStale()) throw new BootstrapCancelled();
}

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

/** 润色实验的真实实现：懒加载 wllama 引擎（按模型路径缓存），prompt 用
 * 聚焦叙事视图（buildTaskPrompt focused——只含事实与允许短语，预填量极小）
 * 生成候选；重试注入判分器反馈与更高温度。输出交回 rule-session 的
 * checkFactNarration 把关，失败由其重生成/回退模板。 */
const polishEngines = new Map<string, Promise<RuleNarrationPolisher>>();
function polishEngine(modelUrl: string): Promise<RuleNarrationPolisher> {
  let engine = polishEngines.get(modelUrl);
  if (!engine) {
    engine = (async () => {
      const [{ WllamaInferenceEngine }, { buildTaskPrompt }] = await Promise.all([
        import('@/lib/world-engine/runtime/wllama-engine'),
        import('@/lib/world-engine/runtime/prompts'),
      ]);
      const wllama = new WllamaInferenceEngine({ modelUrl, contextSize: 2048 });
      return async (input, _packet, focused, attempt) => {
        // 共享 prompts.ts / focused-input.ts 保持确定性（B3 eval 回放依赖）；
        // 页面实验在提交给引擎前收窄输入：每条事实只展示首个短语（判分器
        // 仍接受任意已登记变体）。实测 0.5B/0.6B 模型在展示两个变体时必然
        // 全部输出（duplicate_fact），逐字拼接是这个量级模型可靠完成的任务
        // 形态；顺序与变体选择是它在严格判分门下保留的自由度，更丰富的
        // 散文表达属于方案 §8.2 的状态对齐评测层（后续批次）。
        const view = focused as { facts?: { id: string; allowedPhrases: string[] }[] };
        const simplified = {
          ...view,
          facts: (view.facts ?? []).map((fact) => ({ id: fact.id, phrase: fact.allowedPhrases[0] })),
        };
        let prompt = buildTaskPrompt('narration', input.pointId, simplified, { inputMode: 'focused' });
        // 编号清单：两个模型的实测失败模式都是「漏掉部分事实」（missing_fact），
        // 编号逐条复制是把任务压到机械形态的最后一步。
        const phrases = (view.facts ?? []).map((fact) => fact.allowedPhrases[0]);
        prompt += `\n[硬性要求] 依次输出下面全部 ${phrases.length} 条短语：逐字复制、每条后面加一个句号（。）、一条一行，从 1 号到 ${phrases.length} 号一条都不能漏，不要输出编号，不要添加任何其他字词：\n${phrases.map((phrase, index) => `${index + 1}. ${phrase}`).join('\n')}`;
        // attempt 2 = 同 prompt 纯温度重采样（0.7）：注入更正文本会被小模型
        // 逐字复读（实测），stop 打空反而浪费掉这次重生机会；
        // attempt.previous 仍随类型传递，供更强模型启用反馈注入。
        await wllama.load(); // 幂等：首次使用触发下载与 wasm 初始化
        const raw = await wllama.complete(prompt, {
          maxTokens: 96,
          temperature: attempt.index === 1 ? 0 : 0.7,
          cachePrompt: true,
          timeoutMs: 110_000,
          stop: ['\n[', '\n正文:', '\n输出:', '[硬性要求]'],
        });
        const text = raw.trim();
        if (!text) throw new Error('润色输出为空');
        console.info(`[narration-model] attempt ${attempt.index} raw=${JSON.stringify(text)}`);
        return text;
      };
    })();
    engine.catch(() => polishEngines.delete(modelUrl)); // 失败的加载可重试
    polishEngines.set(modelUrl, engine);
  }
  return engine;
}

interface ActiveSession { session: RuleWorldSession; page: PageTransport }

/** 本次文档已请求过隔离自检的整页重载：同一文档内的二次挂载（StrictMode）
 * 不得再起会话——重载已经在路上。文档重建后模块重新求值，标记自然复位。 */
let isoReloadPending = false;

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
  /** 隔离自检的持久告警：boot 成功会清空 note，这条必须活到重载/关闭。 */
  const [isoWarning, setIsoWarning] = useState('');
  const [polishOn, setPolishOn] = useState(false);
  const [polishModel, setPolishModel] = useState(DEFAULT_POLISH_MODEL);
  const [dropNextArmed, setDropNextArmed] = useState(false);
  const activeRef = useRef<ActiveSession | null>(null);
  const commandsRef = useRef<string[]>([]);
  /** 本页面会话内被判分器采纳过模型叙事的点位（服务端不记录生产者，
   * rebuild 重建日志时据此恢复「模型」徽标；整页刷新后清空属预期）。 */
  const polishedPointsRef = useRef(new Set<Id>());
  const bootedRef = useRef(false);
  const generationRef = useRef(0);
  const disposedRef = useRef(false);
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
   * 懒加载引擎生成候选。整个尝试受截止时间约束——引擎加载或生成一旦挂起，
   * 可选项绝不能阻塞命令回合，超时即回退模板。 */
  const lazyPolisher: RuleNarrationPolisher = async (input, packet, focused, attempt) => {
    if (!polishOnRef.current) return null;
    const deadlineMs = 120_000;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const deadline = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error(`润色尝试超过 ${deadlineMs / 1000}s 未完成（加载或生成挂起）`)), deadlineMs);
    });
    try {
      const generate = async () => (await polishEngine(polishModelRef.current))(input, packet, focused, attempt);
      return await Promise.race([generate(), deadline]);
    } finally {
      clearTimeout(timer);
    }
  };

  const handleEvent = (event: RuleSessionEvent) => {
    if (event.kind === 'narration') {
      console.info(`[narration] polished=${event.polished} reason=${event.polishReason} attempts=${event.attempts} text=${JSON.stringify(event.text)}`);
      if (event.polished) polishedPointsRef.current.add(event.pointId);
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

  /** 以服务端事实重建整页视图：叙事行（含时间推进）与状态面板。点位台账
   * 完整分页——单页会把超过一页的世界渲染成旧 head。isStale 必填，在每个
   * await 后与发布前检查：已失效的重建绝不写页面状态。 */
  const rebuild = async (wid: Id, transport: WorldTransport, isStale: () => boolean) => {
    throwIfStale(isStale);
    const points = await readAllPoints(transport, wid);
    throwIfStale(isStale);
    const headPointId = points.at(-1)?.pointId;
    const rows: LogRow[] = [];
    let headState: WorldState | null = null;
    for (const point of points) {
      const narration = (await transport.execute('narration_get', {}, { worldId: wid, pointId: point.pointId })).data;
      throwIfStale(isStale);
      const read = (await transport.execute('get_state', { point: point.pointId }, { worldId: wid })).data;
      throwIfStale(isStale);
      if (point.pointId === headPointId) headState = read.state;
      rows.push({
        pointId: point.pointId,
        version: read.version,
        text: narration.text ?? `（叙事状态：${narration.narrationStatus}）`,
        timeText: describeAdvance(read.timeAdvance),
        polished: polishedPointsRef.current.has(point.pointId),
      });
    }
    throwIfStale(isStale);
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

  const stopOwned = (session: RuleWorldSession) => {
    session.stop();
    if (activeRef.current?.session === session) activeRef.current = null;
  };

  /** 恢复既有世界：先读服务端事实派生模板，再走 recover；持约续租失败时
   * 降级为一次接管。返回创建的会话，供调用方在已失效时按实例停止。
   *
   * isStale 贯穿每个 await 边界：旧代（被卸载/被新代接管的挂载）晚到的
   * 读回包绝不能继续走完 attach——创建会话、发布 activeRef、写页面状态
   * 之前都要闸一次，否则旧代会在新代已发布引用之后覆盖它，外层的按实例
   * 清理随后把 activeRef 清成 null，页面失去对存活会话的引用。参数必填：
   * 自动恢复传代际判断，手动路径传「组件已卸载」判断——漏传在编译期即红。
   * attachOnce 对自己创建的会话兜底 stopOwned：取消检查放在 try 内（恢复
   * 返回后），任何取消、恢复拒绝或终态都经 catch 停止该会话——绝无取消后
   * 仍在外泄漏、继续发心跳的会话。 */
  const attach = async (saved: PersistedSession, apiBase: string, isStale: () => boolean): Promise<RuleWorldSession> => {
    stopActive();
    throwIfStale(isStale);
    setPhase('connecting');
    setWorldId(saved.worldId);
    const transport = buildTransport(apiBase);
    const head = await transport.execute('get_state', {}, { worldId: saved.worldId });
    throwIfStale(isStale); // ★ 竞态闸门：挂起读晚到时到此为止，不创建会话
    const initial = structuredClone(head.data.state.initial) as InitialTemplate & { worldId?: Id };
    delete initial.worldId;
    const heldLease = saved.leaseToken && saved.fenceEpoch != null ? { leaseToken: saved.leaseToken, fenceEpoch: saved.fenceEpoch } : undefined;
    setLeaseLabel(heldLease ? '续租中' : '接管中');
    const attachOnce = async (lease: { leaseToken: Id; fenceEpoch: number } | undefined): Promise<RuleWorldSession> => {
      throwIfStale(isStale); // 创建会话前：晚代已存在时旧代不再产生任何会话
      const session = RuleWorldSession.createRecovered({
        transport, initial, policy: WORLD_POLICY, polish: lazyPolisher, onEvent: handleEvent,
      }, saved.worldId, lease);
      try {
        const terminal = await session.attach();
        throwIfStale(isStale); // ★ 恢复期间取消：异常落在本 try 内，catch 停止该会话
        // 任何恢复 stop（除 handback 边界的 world_complete）都意味着驱动已被
        // recoveryBarrier 闩住——绝不能带着死驱动进入 ready。
        if ((terminal.kind === 'stop' && terminal.reason !== 'world_complete') || terminal.kind === 'error') {
          const reason = terminal.kind === 'error' ? terminal.detail : terminal.reason;
          stopOwned(session);
          throw new Error(reason);
        }
        return session;
      } catch (error) {
        stopOwned(session); // 自己创建的会话自己停（幂等）；不误清新代引用
        throw error;
      }
    };
    let session: RuleWorldSession;
    try {
      session = await attachOnce(heldLease);
    } catch (error) {
      if (error instanceof BootstrapCancelled) throw error;
      const message = error instanceof Error ? error.message : String(error);
      if (!heldLease || !message.startsWith('recovery_refused')) throw error;
      throwIfStale(isStale);
      setNote('续租被拒，改为接管重连…');
      session = await attachOnce(undefined);
    }
    throwIfStale(isStale); // ★ 发布引用前：绝不覆盖新代已发布的会话
    activeRef.current = { session, page: transport };
    setLeaseLabel(transport.grant ? `租约有效（epoch ${transport.grant.fenceEpoch}）` : '无租约');
    commandsRef.current = saved.commands;
    await rebuild(saved.worldId, transport, isStale);
    throwIfStale(isStale);
    setPhase('ready');
    setNote('');
    return session;
  };

  const connectNew = async (apiBase: string) => {
    // 手动路径的取消语义：组件已卸载即失效（busy 禁重入，无代际并发）。
    // 与 attach 同族——创建后、attach 返回后、发布前各闸一次，取消走
    // catch 停止自己创建的会话；引用发布统一后置。
    const isStale = () => disposedRef.current;
    stopActive();
    throwIfStale(isStale);
    setPhase('connecting');
    setWorldId(null);
    const transport = buildTransport(apiBase);
    const session = RuleWorldSession.createNew({ transport, initial: defaultInitialTemplate(), policy: WORLD_POLICY, polish: lazyPolisher, onEvent: handleEvent });
    try {
      await session.attach(); // 创建世界＋根叙事；无输入即在 handback 边界停住
      throwIfStale(isStale); // 卸载后晚到：停止会话，不发布、不写持久化
    } catch (error) {
      stopOwned(session);
      throw error;
    }
    const wid = session.worldId;
    if (!wid) {
      stopOwned(session);
      throw new Error('world_creation_missing');
    }
    throwIfStale(isStale);
    activeRef.current = { session, page: transport };
    setWorldId(wid);
    commandsRef.current = [];
    savePersisted({ api: apiBase, worldId: wid, leaseToken: transport.grant?.leaseToken ?? null, fenceEpoch: transport.grant?.fenceEpoch ?? null, commands: [] });
    setLeaseLabel(transport.grant ? `租约有效（epoch ${transport.grant.fenceEpoch}）` : '无租约');
    await rebuild(wid, transport, isStale);
    throwIfStale(isStale);
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
      try {
        // 卸载后中止重建：已失效的组件不再发读请求，页面状态交给新代。
        await rebuild(wid, active.page, () => disposedRef.current);
      } catch (error) {
        if (!(error instanceof BootstrapCancelled)) throw error;
      }
      setPhase('ready');
    }
  };

  /** 组件级初始化：卸载（或 StrictMode 清理）后重挂载必须重新 bootstrap——
   * 跨实例保留的模块级标记会让客户端导航返回时永远停在 boot。取消语义按
   * 代际判定：cleanup 之后被清除的 disposed 只属于当前代，新 effect 会先
   * 复位 disposed 并推进代数，因此旧 bootstrap 的每个检查点都能识别自己
   * 已失效，且只停止自己创建的会话，绝不误杀新实例的会话。 */
  useEffect(() => {
    // SPA 进入时响应头无法改变既有文档的隔离状态（crossOriginIsolated 是
    // 文档创建时定型的属性）：自检失败就整页重载一次，护栏防循环；重载后
    // 仍不隔离说明部署缺响应头，降级提示（单线程预填实测 ~200ms/token，
    // 模型叙事大概率超时回退模板）。护栏读写包 try：存储不可用就无法防
    // 循环，此时宁可不重载，只降级（告警用独立 state，boot 成功清空 note，
    // 但这降级事实必须持续可见）。
    const isoFlag = 'jity.world.isoReload';
    if (!window.crossOriginIsolated) {
      if (isoReloadPending) return; // 已请求重载（StrictMode 二次挂载不再起会话）
      let reload = false;
      try {
        if (!window.sessionStorage.getItem(isoFlag)) {
          window.sessionStorage.setItem(isoFlag, '1');
          reload = true;
        }
      } catch { /* 存储被禁：无法防循环，直接降级 */ }
      if (reload) {
        isoReloadPending = true;
        window.location.reload();
        return; // 整页重载，本实例随之销毁
      }
      setIsoWarning('跨源隔离不可用（部署响应头缺失）：模型叙事降级为单线程，可能超时回退模板。');
    } else {
      try { window.sessionStorage.removeItem(isoFlag); } catch { /* 无事可清 */ }
    }
    disposedRef.current = false;
    if (bootedRef.current) return;
    bootedRef.current = true;
    const generation = ++generationRef.current;
    const stale = () => disposedRef.current || generationRef.current !== generation;
    void (async () => {
      try {
        const params = new URLSearchParams(window.location.search);
        const saved = loadPersisted();
        const apiBase = params.get('api') ?? saved?.api ?? window.localStorage.getItem('jity.world.api') ?? DEFAULT_API;
        setApi(apiBase);
        window.localStorage.setItem('jity.world.api', apiBase);
        if (stale()) return;
        if (saved?.worldId) {
          // ★ isStale 必传：attach 的每个闸门都靠它识别本代已失效。漏传即
          // 全部闸门死寂（默认恒 false 的旧默认值曾造成晚到旧代覆盖新代）。
          const session = await attach(saved, apiBase, stale);
          if (stale()) stopOwned(session); // 返回后、下一帧前的残余窗口
        } else {
          setPhase('disconnected');
        }
      } catch (error) {
        if (stale()) return;
        setNote(`续接失败：${error instanceof Error ? error.message : String(error)}`);
        setPhase('disconnected');
      }
    })();
    return () => {
      disposedRef.current = true;
      bootedRef.current = false;
      // 仅当代数仍属于本 effect 时才停会话：新一代已接管时不得误停。
      // 刻意读取 ref 的最新值做代际比较，而非闭包快照。
      // eslint-disable-next-line react-hooks/exhaustive-deps
      if (generationRef.current === generation) stopActive();
    };
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
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">世界最小交互页</h1>
          <Link href="/" className="text-xs text-zinc-500 underline hover:text-zinc-700">返回控制台</Link>
        </div>
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
              onClick={() => { const saved = loadPersisted(); if (saved) void attach(saved, api, () => disposedRef.current).catch((error) => { setNote(`续接失败：${error instanceof Error ? error.message : String(error)}`); setPhase('disconnected'); }); }}
              disabled={busy}>
              刷新续接
            </button>
          )}
          {worldId && <button className="rounded border border-zinc-400 px-3 py-1 text-xs" onClick={disconnect} disabled={busy}>断开</button>}
        </div>
        {note && <p className="mt-2 text-xs text-amber-700">{note}</p>}
        {isoWarning && <p className="mt-2 text-xs text-amber-700">{isoWarning}</p>}
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
        <h2 className="mb-2 text-xs font-semibold text-zinc-500">叙事（默认模板；模型叙事为可选实验）</h2>
        <div className="mb-3 flex flex-wrap items-center gap-3 text-xs">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={polishOn} onChange={(event) => setPolishOn(event.target.checked)} disabled={busy} />
            模型叙事（实验：模型为主，判分门控，失败保持模板）
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
                {row.polished && <span className="ml-1 rounded bg-sky-100 px-1 text-[11px] text-sky-700">模型</span>}
              </li>
            ))}
          </ol>
        ) : <p className="text-zinc-400">尚无叙事。</p>}
      </section>
    </main>
  );
}
