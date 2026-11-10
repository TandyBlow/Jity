/** Stable entry point for the page integration. Import components from here so
 * the wiring only depends on this barrel, not on internal file layout. */
export { GameControls } from './game-controls';
export { HistoryPanel } from './history-panel';
export { NarrationView } from './narration-view';
export { ProgressStatus } from './progress-status';
export { WorldLocalLayout } from './world-local-layout';
export { WorldStatusPanel } from './world-status-panel';

export {
  controlAvailability,
  controlPhaseLabel,
  formatElapsed,
  formatWorldTime,
  historyEntriesFromPoints,
  historyKindLabel,
  isSubmitShortcut,
  locationName,
  narrationAccepted,
  narrationFailed,
  narrationStatusLabel,
  narrationStreaming,
  roomName,
  roomOf,
  splitNarration,
  worldStatusFromState,
} from './view-model';

export type { ControlAvailability, ControlAvailabilityInput } from './view-model';

export type {
  ControlPhase,
  ForkOption,
  GameControlsProps,
  HistoryEntry,
  HistoryPanelProps,
  HistoryPointKind,
  NarrationPhase,
  NarrationState,
  NarrationViewProps,
  ProgressStatusProps,
  SaveState,
  SaveStatus,
  SyncState,
  SyncStatus,
  WorldLocalLayoutProps,
  WorldStatusPanelProps,
  WorldStatusPerson,
  WorldStatusTask,
  WorldStatusView,
} from './types';
