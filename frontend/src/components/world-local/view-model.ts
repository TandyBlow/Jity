/** Pure read-only helpers for the world-local view components.
 *
 * Nothing here mutates or persists a world. The only state input is a committed
 * `WorldState`; the output is a display summary. Room resolution mirrors the
 * canonical traversal in `lib/world-engine/local/prompt.ts` because prompt.ts
 * belongs to the page integration and is being edited there; the rule itself
 * (follow container ids until a location is reached) is unchanged.
 */
import type { Id, NarrationStatus, WorldState } from '@/lib/world-engine/types';

import type {
  ControlPhase,
  HistoryEntry,
  HistoryPointKind,
  NarrationState,
  WorldStatusView,
} from './types';

export const NARRATION_STATUS_LABELS: Record<NarrationStatus, string> = {
  pending: '正文生成中',
  ready: '正文已缓存',
  failed: '上次生成失败',
  missing: '正文缓存缺失',
};

const HISTORY_KIND_LABELS: Record<HistoryPointKind, string> = {
  root: '起点',
  normal: '行动',
  instant: '瞬时',
  linked: '衔接',
};

export function narrationStatusLabel(status: NarrationStatus | null): string {
  return status ? NARRATION_STATUS_LABELS[status] : '正文状态未读取';
}

export function historyKindLabel(kind: HistoryPointKind): string {
  return HISTORY_KIND_LABELS[kind] ?? kind;
}

/** `2009-10-17T15:20:00` → `2009-10-17 15:20`; empty input stays explicit. */
export function formatWorldTime(dateTime: string | null | undefined): string {
  const value = (dateTime ?? '').trim();
  if (!value) return '—';
  return value.replace('T', ' ').slice(0, 16);
}

export function formatElapsed(elapsedMs: number | null | undefined): string {
  if (elapsedMs == null || !Number.isFinite(elapsedMs) || elapsedMs < 0) return '';
  if (elapsedMs < 1000) return `${Math.round(elapsedMs)} 毫秒`;
  return `${(elapsedMs / 1000).toFixed(1)} 秒`;
}

/** Innermost location reached by following container ids. Mirrors the kernel's
 * room traversal; a cycle or unknown id stops at the last known node. */
export function roomOf(state: WorldState, entityId: Id): Id {
  let node = entityId;
  const seen = new Set<Id>();
  while (!state.initial.locations[node]) {
    if (seen.has(node)) return node;
    seen.add(node);
    const entity = state.characters[node] ?? state.items[node];
    if (!entity) return node;
    node = entity.position.containerId;
  }
  return node;
}

export function roomName(state: WorldState, entityId: Id): string {
  return locationName(state, roomOf(state, entityId));
}

export function locationName(state: WorldState, id: Id): string {
  return state.initial.locations[id]?.name
    ?? state.initial.items[id]?.name
    ?? state.initial.characters[id]?.name
    ?? id;
}

/** Build the sidebar summary from a committed state. Read-only: tasks keep
 * their canonical status (achieved/pending); only presentation ordering moves
 * completed tasks to the end. */
export function worldStatusFromState(state: WorldState): WorldStatusView {
  const protagonistId = state.protagonistId;
  const initial = state.initial.characters[protagonistId];
  const current = state.characters[protagonistId];
  const room = roomOf(state, protagonistId);

  const tasks = Object.values(current?.tasks ?? {}).map((task) => ({
    id: task.id,
    goal: task.goal,
    done: task.status === 'achieved',
  }));
  // Pending first, then completed; stable by goal within each group.
  tasks.sort((left, right) => Number(left.done) - Number(right.done)
    || left.goal.localeCompare(right.goal, 'zh-Hans-CN'));

  const nearby = Object.keys(state.characters)
    .filter((id) => id !== protagonistId && roomOf(state, id) === room)
    .map((id) => ({ id, name: state.initial.characters[id]?.name ?? id }));
  const items = Object.keys(state.items)
    .filter((id) => roomOf(state, id) === room)
    .map((id) => ({ id, name: state.initial.items[id]?.name ?? id }));

  const personality = [
    initial?.initialPersonality ?? '',
    ...(current?.personalityChanges ?? []).filter((change) => change.active && change.text).map((change) => change.text as string),
  ].filter(Boolean).join('；');

  return {
    name: initial?.name ?? protagonistId,
    timeLabel: formatWorldTime(state.time.dateTime),
    locationLabel: roomName(state, protagonistId),
    sanity: current?.sanity ?? null,
    personality: personality || null,
    nearby,
    tasks,
    items,
  };
}

/** Presentation-only paragraph split. `※` is the model's existing paragraph
 * marker; converting it here does not change the accepted text, which keeps
 * living in the transport snapshot. */
export function splitNarration(text: string): string[] {
  const normalized = (text ?? '').replace(/\r\n?/g, '\n').replace(/※/g, '\n\n');
  const blocks = normalized.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
  if (blocks.length > 1) return blocks;
  return normalized.split('\n').map((line) => line.trim()).filter(Boolean);
}

export function narrationStreaming(pointId: Id | null, text: string, elapsedMs: number | null = null): NarrationState {
  return { phase: 'streaming', text, pointId, elapsedMs };
}

export function narrationAccepted(
  pointId: Id | null,
  text: string,
  options: { elapsedMs?: number | null; alignmentNote?: string | null } = {},
): NarrationState {
  return {
    phase: 'accepted',
    text,
    pointId,
    elapsedMs: options.elapsedMs ?? null,
    alignmentNote: options.alignmentNote ?? null,
  };
}

export function narrationFailed(reason: string, options: { previousText?: string | null; pointId?: Id | null } = {}): NarrationState {
  return {
    phase: 'failed',
    text: '',
    pointId: options.pointId ?? null,
    failureReason: reason || '生成失败，未提供原因。',
    previousText: options.previousText ?? null,
  };
}

/** Map the transport's `list_points` rows to display entries. Narration status
 * is only filled when the caller has read it; a missing map value stays null
 * and the panel says “未读取” rather than pretending a cache state. */
export function historyEntriesFromPoints(
  points: readonly {
    pointId: Id;
    sequence: number;
    kind: HistoryPointKind;
    stateDigest?: string | null;
    advanceId?: Id | null;
  }[],
  options: {
    narrationStatusById?: Readonly<Record<Id, NarrationStatus>>;
    commandByAdvanceId?: Readonly<Record<Id, string>>;
    advanceIdByPointId?: Readonly<Record<Id, Id | null>>;
  } = {},
): HistoryEntry[] {
  return [...points]
    .sort((left, right) => right.sequence - left.sequence)
    .map((point) => {
      const advanceId = point.advanceId ?? options.advanceIdByPointId?.[point.pointId] ?? null;
      return {
        pointId: point.pointId,
        sequence: point.sequence,
        kind: point.kind,
        command: advanceId ? options.commandByAdvanceId?.[advanceId] ?? null : null,
        status: options.narrationStatusById?.[point.pointId] ?? null,
        stateDigest: point.stateDigest ?? null,
      };
    });
}

export interface ControlAvailabilityInput {
  value: string;
  phase: ControlPhase;
  busy: boolean;
  paused: boolean;
  disabled: boolean;
  disabledReason: string | null;
  submitDisabledReason: string | null;
  pauseDisabledReason: string | null;
  resumeDisabledReason: string | null;
  cancelDisabledReason: string | null;
  hasPause: boolean;
  hasResume: boolean;
  hasCancel: boolean;
}

export interface ControlAvailability {
  canEdit: boolean;
  canSubmit: boolean;
  submitReason: string | null;
  canPause: boolean;
  pauseReason: string | null;
  canResume: boolean;
  resumeReason: string | null;
  canCancel: boolean;
  cancelReason: string | null;
}

/** Single source for button availability and the human-readable reason shown
 * next to a disabled button. Missing callbacks are reported as missing
 * wiring, never silently treated as success. */
export function controlAvailability(input: ControlAvailabilityInput): ControlAvailability {
  const running = input.busy || input.phase === 'thinking' || input.phase === 'streaming';
  const hasText = input.value.trim().length > 0;

  let submitReason: string | null = null;
  if (input.disabled) submitReason = input.disabledReason ?? '页面尚未就绪';
  else if (input.phase === 'loading') submitReason = '模型仍在载入';
  else if (input.paused || input.phase === 'paused') submitReason = '当前已暂停，继续后才能提交行动';
  else if (running) submitReason = '本轮回合尚未交还';
  else if (input.submitDisabledReason) submitReason = input.submitDisabledReason;

  let pauseReason: string | null = null;
  if (!input.hasPause) pauseReason = '当前会话尚未接入暂停';
  else if (input.paused) pauseReason = '当前已暂停';
  else if (!running) pauseReason = '只有本轮回合进行中才能暂停';
  else if (input.pauseDisabledReason) pauseReason = input.pauseDisabledReason;

  let resumeReason: string | null = null;
  if (!input.hasResume) resumeReason = '当前会话尚未接入继续';
  else if (!input.paused) resumeReason = '当前未暂停';
  else if (input.resumeDisabledReason) resumeReason = input.resumeDisabledReason;

  let cancelReason: string | null = null;
  if (!input.hasCancel) cancelReason = '当前会话尚未接入取消';
  else if (!running && !input.paused) cancelReason = '没有正在进行的回合可取消';
  else if (input.cancelDisabledReason) cancelReason = input.cancelDisabledReason;

  const canSubmit = !input.disabled && hasText && !input.paused && input.phase !== 'loading'
    && input.phase !== 'paused' && !running && !input.submitDisabledReason;
  const canPause = !input.disabled && input.hasPause && !input.paused && running && !input.pauseDisabledReason;
  const canResume = !input.disabled && input.hasResume && input.paused && !input.resumeDisabledReason;
  const canCancel = !input.disabled && input.hasCancel && (running || input.paused) && !input.cancelDisabledReason;

  return {
    canEdit: !input.disabled,
    canSubmit,
    submitReason: canSubmit ? null : submitReason,
    canPause,
    pauseReason: canPause ? null : pauseReason,
    canResume,
    resumeReason: canResume ? null : resumeReason,
    canCancel,
    cancelReason: canCancel ? null : cancelReason,
  };
}

export function controlPhaseLabel(phase: ControlPhase, paused: boolean): string {
  if (paused) return '已暂停';
  switch (phase) {
    case 'loading': return '载入中';
    case 'thinking': return '结算中';
    case 'streaming': return '正在写正文';
    case 'error': return '发生错误';
    case 'paused': return '已暂停';
    default: return '就绪';
  }
}

/** Ctrl+Enter on Windows/Linux, ⌘+Enter on macOS. Kept separate so the
 * keyboard path can be checked without a DOM. */
export function isSubmitShortcut(event: { key: string; ctrlKey: boolean; metaKey: boolean; altKey?: boolean }): boolean {
  return event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.altKey;
}
