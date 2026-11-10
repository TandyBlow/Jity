/** Presentational contracts for the browser-local world UI.
 *
 * These are view models, not a second world state: every value below is either
 * passed in by the page that owns the session or derived read-only from an
 * already committed `WorldState` by `worldStatusFromState`. The components in
 * this directory never call the transport, the model or localStorage; the
 * callbacks only ask the owning page to perform an action it already offers.
 */
import type { ReactNode } from 'react';

import type { Id, NarrationStatus } from '@/lib/world-engine/types';

export type NarrationPhase = 'idle' | 'streaming' | 'accepted' | 'failed';

/** What the reading area is showing right now. `text` is raw output: either
 * the in-flight stream or the last accepted text. The view never composes or
 * invents prose; an empty string renders an explicit empty state. */
export interface NarrationState {
  phase: NarrationPhase;
  text: string;
  pointId?: Id | null;
  elapsedMs?: number | null;
  /** Only for `failed`: why this attempt produced no accepted text. */
  failureReason?: string | null;
  /** Only for `accepted`: a non-blocking fact-check hint (e.g. `align:...`). */
  alignmentNote?: string | null;
  /** Only for `failed`: the last accepted text, offered as a collapsible fallback. */
  previousText?: string | null;
}

export interface NarrationViewProps {
  state: NarrationState;
  title?: string;
  idleHint?: string;
  /** Omit when the session has no separate narration-regeneration path. */
  onRegenerate?: () => void;
  regenerateDisabledReason?: string | null;
}

export type HistoryPointKind = 'root' | 'normal' | 'instant' | 'linked';

/** One committed timeline point. `status: null` means the page has not read
 * narration status for that point yet; the panel labels it as unread instead
 * of guessing “cached” or “missing”. */
export interface HistoryEntry {
  pointId: Id;
  sequence: number;
  kind: HistoryPointKind;
  timeLabel?: string | null;
  command?: string | null;
  status: NarrationStatus | null;
  stateDigest?: string | null;
}

export interface HistoryPanelProps {
  entries: HistoryEntry[];
  headPointId?: Id | null;
  selectedPointId?: Id | null;
  onSelect?: (pointId: Id) => void;
  /** Omit when the session cannot regenerate narration for stored points. */
  onRegenerate?: (pointId: Id) => void;
  regenerateDisabledReason?: string | null;
  loading?: boolean;
  emptyHint?: string;
}

export interface WorldStatusTask {
  id: Id;
  goal: string;
  done: boolean;
}

export interface WorldStatusPerson {
  id: Id;
  name: string;
}

/** Read-only summary of the committed state, built by `worldStatusFromState`. */
export interface WorldStatusView {
  name: string;
  timeLabel: string;
  locationLabel: string;
  sanity: number | null;
  personality?: string | null;
  nearby: WorldStatusPerson[];
  tasks: WorldStatusTask[];
  items?: WorldStatusPerson[];
}

export interface WorldStatusPanelProps {
  status: WorldStatusView;
  /** Pending tasks shown before completed ones are collapsed into a count. */
  pendingTaskLimit?: number;
}

export type ControlPhase = 'loading' | 'ready' | 'thinking' | 'streaming' | 'paused' | 'error';

export interface GameControlsProps {
  value: string;
  onChange: (next: string) => void;
  onSubmit: (text: string) => void;
  phase?: ControlPhase;
  busy?: boolean;
  paused?: boolean;
  /** Extra reason for a disabled submit, e.g. "模型尚未载入完成". */
  submitDisabledReason?: string | null;
  onPause?: () => void;
  onResume?: () => void;
  onCancel?: () => void;
  pauseDisabledReason?: string | null;
  resumeDisabledReason?: string | null;
  cancelDisabledReason?: string | null;
  placeholder?: string;
  hint?: string;
  disabled?: boolean;
  disabledReason?: string | null;
}

export type SaveState = 'idle' | 'saving' | 'saved' | 'failed';

export interface SaveStatus {
  state: SaveState;
  savedAtLabel?: string | null;
  detail?: string | null;
  error?: string | null;
  onRetry?: () => void;
  retryDisabledReason?: string | null;
}

export type SyncState = 'local-only' | 'offline' | 'syncing' | 'synced' | 'failed' | 'conflict';

export interface SyncStatus {
  state: SyncState;
  lastSyncedAtLabel?: string | null;
  error?: string | null;
  onSync?: () => void;
  syncDisabledReason?: string | null;
}

/** Metadata-compatible subset of the 07 progress-sync snapshot record. The
 * parent chain and server revision stay visible; the panel never merges
 * payloads or rewrites local state when a branch is selected. */
export interface ForkOption {
  snapshotId: Id;
  parentSnapshotIds: Id[];
  revision: number;
  savedAtLabel: string;
  summary?: string | null;
}

export interface ProgressStatusProps {
  online: boolean;
  save: SaveStatus;
  /** Omit when no sync client is wired: the panel then says so explicitly. */
  sync?: SyncStatus | null;
  forks?: ForkOption[];
  activeForkId?: Id | null;
  onChooseFork?: (snapshotId: Id) => void;
  chooseForkDisabledReason?: string | null;
}

export interface WorldLocalLayoutProps {
  title: string;
  subtitle?: string;
  meta?: ReactNode;
  /** Page-level notices (model warnings, fatal errors, offline banners). */
  banner?: ReactNode;
  narration: ReactNode;
  controls: ReactNode;
  status: ReactNode;
  progress?: ReactNode;
  history?: ReactNode;
  footer?: ReactNode;
}
