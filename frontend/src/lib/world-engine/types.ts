/** Handwritten consumer types. Shared Python/JSON Schema is the wire authority. */
export type Id = string;
export type Digest = string;
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export const worldOperations = [
  'create_world', 'get_context', 'checkpoint_start_advance', 'checkpoint_begin_point',
  'checkpoint_set_point_time', 'checkpoint_discover_group', 'checkpoint_extend_group',
  'checkpoint_close_group', 'checkpoint_stage_unit', 'checkpoint_record_skip',
  'checkpoint_stage_time_scan', 'checkpoint_seal_point', 'checkpoint_prepare_successor',
  'checkpoint_restore_group_work', 'checkpoint_pause', 'checkpoint_resume',
  'round_conclusion_conclude', 'round_conclusion_cancel', 'lease_acquire', 'lease_renew',
  'lease_release', 'allocate_ids', 'preview_point', 'create_rolls', 'commit_point',
  'list_points', 'get_state', 'narration_claim', 'narration_claim_renew', 'narration_submit',
  'narration_get', 'narration_delete',
] as const;
export type WorldOperation = typeof worldOperations[number];
export type Phase = 'select_actor' | 'build_group' | 'settle_group' | 'continue_round' | 'assess_continuation' | 'complete';
export type ClientAction = 'retry_same_request' | 'reacquire_lease' | 'refresh_context' | 'wait_narration' | 'regenerate_narration' | 'resolve_gate' | 'pause' | 'fix_request' | 'none';
export type ErrorCode = 'narration_blocked' | 'cache_missing' | 'claim_expired' | 'claim_fenced' | 'paused' | 'stale_epoch' | 'lease_invalid' | 'revision_mismatch' | 'phase_invalid' | 'version_mismatch' | 'protocol_version_unsupported' | 'request_id_reused' | 'request_in_progress' | 'point_time_locked' | 'frozen_work_missing' | 'frozen_work_corrupt' | 'preview_budget_exceeded' | 'request_malformed';
export type BlockedReason = 'narration_pending' | 'narration_failed' | 'cache_missing' | 'claim_expired' | 'claim_fenced' | 'paused' | 'phase_not_computable' | 'lease_invalid';
export type NarrationStatus = 'pending' | 'ready' | 'failed' | 'missing';
export type Intent = 'pending' | 'consumed' | 'expired';
export interface WorldTime { calendar: 'gregorian'; dateTime: string; instantOrdinal: number }
export interface TimeAdvance { boundary: 'elapsed' | 'instant'; duration: { amount: number; unit: 'second' | 'minute' | 'hour' | 'day' | 'month' | 'year' } }
export interface Position { containerId: Id; slotId?: Id | null; relativeTo?: { entityId: Id; relation: 'under' | 'above' | 'beside' | 'in_front_of' | 'behind' } | null }
export interface Change { id: Id; text: string | null; supersedes: Id[] }
export interface StoredChange extends Change { sourcePointId: Id; sourceSequence: number; active: boolean }
export interface Task { id: Id; ownerId: Id; parentTaskId: Id | null; goal: string; status: 'pending' | 'achieved' }
export interface Location { id: Id; name: string; parentLocationId: Id | null; initialAppearance: string; slots?: { id: Id; label: string }[] }
export interface Item { id: Id; name: string; initialPosition: Position; initialAppearance: string; slots?: { id: Id; label: string }[] }
export interface Character extends Item { initialPersonality: string; initialSanity: number; tasks: Record<Id, Task> }
export interface InitialTemplate { engineVersion: 'world-engine-v1'; schemaVersion: 1; protagonistId: Id; initialTime: WorldTime; locations: Record<Id, Location>; items: Record<Id, Item>; characters: Record<Id, Character> }
export interface InitialState extends InitialTemplate { worldId: Id }
export interface WorldState { engineVersion: 'world-engine-v1'; schemaVersion: 1; worldId: Id; protagonistId: Id; time: WorldTime; initial: InitialState; locations: Record<Id, { id: Id; appearanceChanges: StoredChange[] }>; items: Record<Id, { id: Id; appearanceChanges: StoredChange[]; position: Position }>; characters: Record<Id, { id: Id; appearanceChanges: StoredChange[]; position: Position; personalityChanges: StoredChange[]; sanity: number; tasks: Record<Id, Task> }> }
export interface EntityDelta { entityId: Id; positionSet?: Position | null; appearanceChanges?: Change[]; personalityChanges?: Change[]; sanitySet?: number | null; tasksAchieved?: Id[]; subtasksAdded?: Task[] }
export interface TimelinePoint { worldId: Id; id: Id; sequence: number; kind: 'normal' | 'instant' | 'linked'; previousPointId: Id; roundId: Id; advanceId: Id; trigger: 'player' | 'automatic'; linkedFromPointId: Id | null; timeAdvance: TimeAdvance; entityDeltas: Record<Id, EntityDelta> }
export type Conclusion = { kind: 'continue'; closedBy: 'model'; cancelReason: null; candidateCharacterIds: Id[]; nextRoundId: Id } | { kind: 'handback'; closedBy: 'model'; cancelReason: null };
export type CancelConclusion = { kind: 'handback'; closedBy: 'cancel'; cancelReason: string };
export interface Baseline { headPointId: Id; version: number; stateDigest: Digest }
export interface Successor { pointId: Id; predecessorPointId: Id; timeAdvance: TimeAdvance; expectedPredecessorVersion: number; prefixDigest: Digest; expectedPredecessorStateDigest: Digest; baseline: Baseline }
export interface WorldContext { worldId: Id; head: { pointId: Id; version: number; stateDigest: Digest; narrationStatus: NarrationStatus }; advance: { advanceId: Id | null; inputId: Id | null; intentStatus: Intent; inputAvailable: boolean }; round: { roundId: Id; trigger: 'player' | 'automatic'; order: Id[]; cursor: number; actedIds: Id[]; visitedIds: Id[]; conclusion: Conclusion | CancelConclusion | null } | null; time: WorldTime; lease: { fenceEpoch: number; expiresAtEpochMilli: number } | null; successor: Successor | null; activePointId: Id | null; activeRoundId: Id | null }
export type Gate = { status: 'none'; generation?: null; issuedAtEpochMilli?: null; expiresAtEpochMilli?: null }
  | { status: 'pending'; generation: number; issuedAtEpochMilli: number; expiresAtEpochMilli: number };
export interface ControlState { phase: Phase; paused: boolean; revision: number; gate: Gate; blockedReasons: BlockedReason[]; canCompute: boolean }
export interface Working { cursor: number; actedIds: Id[]; visitedIds: Id[]; settledUnitIds: Id[]; intentStatus: Intent }
export interface PendingGroup { groupId: Id; sourceId: Id; memberIds: Id[]; targetIds: Id[]; frontierIds: Id[]; closed: boolean }
export interface PointWork { pointId: Id; kind: 'normal' | 'instant' | 'linked'; timeAdvance: TimeAdvance; timeLocked: boolean; sealed: boolean; prefixDigest: Digest | null; predecessorWorkDigest: Digest | null; timeScanComplete: boolean; baseline: Baseline; phase: 'select_actor' | 'build_group' | 'settle_group'; working: Working; settledUnits: { unitId: Id; groupId: Id; memberIds: Id[]; contentHash: Digest }[]; pendingGroup: PendingGroup | null; successor: Successor | null }
export interface SettlementGroup { groupId: Id | null; actorIds: Id[]; positions: Record<Id, Position>; appearances: Record<Id, Change[]>; tasksAchieved: Record<Id, Id[]>; subtasksAdded: Record<Id, Task[]>; personalities: Record<Id, Change[]>; sanities: Record<Id, number>; taskCoverageIds: Id[]; personalityCoverageIds: Id[] }
export interface ManifestItem { memberId: Id; actionContentHash: Digest; targetsContentHash: Digest | null; resultContentHash: Digest | null; candidatesContentHash: Digest | null }
export interface GroupSource { pointId: Id; groupId: Id; sourceEpoch: number; sourceAttempt: number; manifest: ManifestItem[] }
export interface RollRef { sourceId: Id; targetId: Id; triggerKey: Id; rollId: Id }
export interface FrozenGroup { groupId: Id; pointId: Id; inputProjectionHash: Digest; members: { memberId: Id; actionText: string | null; targets: { targetId: Id; triggerKey: Id }[] | null; resultText: string | null; rollRefs: RollRef[] }[]; acceptedSources: (ManifestItem & { sourceEpoch: number; sourceAttempt: number })[]; candidates: SettlementGroup | null }
export interface PointRecovery { work: PointWork; payloadStatus: 'available' | 'restore_required'; restoreSources: GroupSource[]; groups: FrozenGroup[]; timeScanCandidates: SettlementGroup | null }
export interface Recovery { fenceEpoch: number; current: PointRecovery | null; successor: PointRecovery | null }
export interface VersionBlock { protocolVersion: 2; engineVersion: 'world-engine-v1'; schemaVersion: 2; canonicalVersion: 'world-canonical-v1'; serverTimeEpochMilli: number }
export interface ContextResponse extends VersionBlock { world: WorldContext; control: ControlState; work: PointWork | null; activeInput: { advanceId: Id; inputId: Id; text: string } | null; recovery: Recovery | null }
export interface ErrorResponse extends VersionBlock { replayed: boolean; operation: WorldOperation | null; requestId: Id | null; worldId: Id | null; error: { code: ErrorCode; httpStatus: number; retryable: boolean; clientAction: ClientAction; details: Record<string, Json> }; world?: WorldContext | null; control?: ControlState | null; work?: PointWork | null }
export interface LeaseGrant { leaseToken: Id; fenceEpoch: number; expiresAtEpochMilli: number }
export interface WriteRequest { protocolVersion: 2; requestId: Id; worldId: Id }
export interface LeaseBound extends WriteRequest { leaseToken: Id; fenceEpoch: number }
export interface CheckpointRequest extends LeaseBound { expectedPointId: Id; expectedVersion: number; expectedCheckpointRevision: number }
export interface PointRequest extends CheckpointRequest { pointId: Id }
export interface CurrentClaim { claimToken: Id; generation: number; issuedAtEpochMilli: number }
export type NarrationBinding = { mode: 'head'; leaseToken: Id; fenceEpoch: number } | { mode: 'history'; leaseToken?: null; fenceEpoch?: null };
export interface RollSpec { advanceId: Id; roundId: Id; groupId: Id; sourceId: Id; targetId: Id; triggerKey: Id; ruleVersion: 'reaction-fixture-v1' | 'reaction-d20-v1'; target: number }
export interface RollOutcome extends Omit<RollSpec, 'advanceId' | 'roundId'> { rollId: Id; result: number; eligibilityBaselineDigest: Digest; eligible: boolean; admitted: boolean }
export interface ClaimSummary { pointId: Id; mode: 'head' | 'history'; generation: number; fenceEpoch: number | null; issuedAtEpochMilli: number; expiresAtEpochMilli: number }
export interface PreviewRequest { protocolVersion: 2; worldId: Id; advanceId: Id; roundId: Id; pointId: Id; expectedPointId: Id; expectedVersion: number; expectedCheckpointRevision: number; timeAdvance: TimeAdvance; settlementGroups: SettlementGroup[] }
export interface RequestMap {
  create_world: { protocolVersion: 2; requestId: Id; initial: InitialTemplate };
  get_context: { includeRecovery?: boolean; leaseToken?: Id | null; fenceEpoch?: number | null };
  checkpoint_start_advance: CheckpointRequest & { operation: 'start_advance'; advanceId: Id; inputId: Id; roundId: Id; inputText: string; order: Id[] };
  checkpoint_begin_point: PointRequest & { operation: 'begin_point'; kind: 'normal' | 'instant' | 'linked'; timeAdvance: TimeAdvance };
  checkpoint_set_point_time: PointRequest & { operation: 'set_point_time'; timeAdvance: TimeAdvance };
  checkpoint_discover_group: PointRequest & { operation: 'discover_group'; groupId: Id; initiatorId: Id; actionText: string; targetIds?: Id[] | null };
  checkpoint_extend_group: PointRequest & { operation: 'extend_group'; groupId: Id; sourceId: Id } & ({ targets: { targetId: Id; triggerKey: Id }[]; admittedMember?: null } | { targets?: null; admittedMember: { memberId: Id; actionText?: string | null; rollRefs: RollRef[] } });
  checkpoint_close_group: PointRequest & { operation: 'close_group'; groupId: Id };
  checkpoint_stage_unit: PointRequest & { operation: 'stage_unit'; groupId: Id; candidates: SettlementGroup; results: Record<Id, string> };
  checkpoint_record_skip: PointRequest & { operation: 'record_skip'; slotActorId: Id };
  checkpoint_stage_time_scan: PointRequest & { operation: 'stage_time_scan'; candidates: SettlementGroup };
  checkpoint_seal_point: PointRequest & { operation: 'seal_point' };
  checkpoint_prepare_successor: PointRequest & { operation: 'prepare_successor'; successorPointId: Id; timeAdvance: TimeAdvance };
  checkpoint_restore_group_work: PointRequest & GroupSource & { operation: 'restore_group_work' };
  checkpoint_pause: CheckpointRequest & { operation: 'pause' };
  checkpoint_resume: CheckpointRequest & { operation: 'resume' };
  round_conclusion_conclude: CheckpointRequest & { operation: 'conclude'; advanceId: Id; roundId: Id; conclusion: Conclusion };
  round_conclusion_cancel: CheckpointRequest & { operation: 'cancel'; advanceId: Id; roundId: Id; cancelReason: string };
  lease_acquire: WriteRequest & { holderId: Id };
  lease_renew: LeaseBound;
  lease_release: { protocolVersion: 2; requestId: Id; leaseToken: Id; fenceEpoch: number };
  allocate_ids: LeaseBound & { allocationKey: Id; slots: { slotKey: Id; kind: 'advance' | 'input' | 'round' | 'group' | 'task' | 'change' | 'point' | 'trigger'; scope?: Id | null }[] };
  preview_point: PreviewRequest;
  create_rolls: CheckpointRequest & { rolls: RollSpec[] };
  commit_point: CheckpointRequest & { advanceId: Id; roundId: Id; pointId: Id; point: TimelinePoint; settlementGroups: SettlementGroup[] };
  list_points: { after?: number | null; limit?: number };
  get_state: { point?: Id | null };
  narration_claim: WriteRequest & NarrationBinding & { pointId: Id; currentClaim?: CurrentClaim | null };
  narration_claim_renew: WriteRequest & NarrationBinding & CurrentClaim & { pointId: Id };
  narration_submit: WriteRequest & NarrationBinding & CurrentClaim & { pointId: Id } & ({ outcome: 'ready'; text: string; failureReason: null } | { outcome: 'failed'; text: null; failureReason: string });
  narration_get: Record<string, never>;
  narration_delete: { protocolVersion: 2; requestId: Id } & NarrationBinding & CurrentClaim;
}
export interface DataMap {
  create_world: { worldId: Id; rootPointId: Id; lease: LeaseGrant };
  get_context: never;
  checkpoint_start_advance: { advanceId: Id; inputId: Id; roundId: Id };
  checkpoint_begin_point: { pointId: Id };
  checkpoint_set_point_time: { pointId: Id; timeAdvance: TimeAdvance };
  checkpoint_discover_group: { groupId: Id; targetIds: Id[] | null };
  checkpoint_extend_group: { groupId: Id; memberIds: Id[]; frontierIds: Id[] };
  checkpoint_close_group: { groupId: Id; closed: true };
  checkpoint_stage_unit: { groupId: Id; unitId: Id; working: Working };
  checkpoint_record_skip: { pointId: Id; working: Working };
  checkpoint_stage_time_scan: { pointId: Id; working: Working };
  checkpoint_seal_point: { pointId: Id; prefixDigest: Digest };
  checkpoint_prepare_successor: { pointId: Id; successorPointId: Id; prefixDigest: Digest; successor: Successor };
  checkpoint_restore_group_work: { pointId: Id; groupId: Id; fenceEpoch: number; attempt: number; sourceEpoch: number; sourceAttempt: number; restoredMemberIds: Id[] };
  checkpoint_pause: { paused: true };
  checkpoint_resume: { paused: false };
  round_conclusion_conclude: { kind: 'continue'; roundId: Id; nextRoundId: Id } | { kind: 'handback'; roundId: Id; nextRoundId: null };
  round_conclusion_cancel: { roundId: Id; abandonedGroupIds: Id[] };
  lease_acquire: LeaseGrant & { holderId: Id };
  lease_renew: LeaseGrant;
  lease_release: { released: true };
  allocate_ids: { allocations: { slotKey: Id; id: Id }[] };
  preview_point: { pointId: Id; pointProjection: TimelinePoint; mergedEntityDeltas: Record<Id, EntityDelta>; workingStateDigest: Digest; pointProjectionDigest: Digest; workingState: WorldState };
  create_rolls: { rolls: RollOutcome[] };
  commit_point: { pointId: Id; version: number; stateDigest: Digest };
  list_points: { points: { pointId: Id; sequence: number; kind: 'root' | 'normal' | 'instant' | 'linked'; roundId: Id | null; advanceId: Id | null; stateDigest: Digest }[] };
  get_state: { pointId: Id; version: number; state: WorldState; stateDigest: Digest; /** 该点自身已保存的记录（§7.1/§8.2 叙事组装）：根点为 null/null/{}；缺任一字段=读取能力不完整，客户端必须停止叙事生成，不得默认为空增量。 */ previousPointId: Id | null; timeAdvance: TimeAdvance | null; entityDeltas: Record<Id, EntityDelta> };
  narration_claim: ClaimSummary & { claimToken?: Id };
  narration_claim_renew: ClaimSummary;
  narration_submit: { pointId: Id; narrationStatus: NarrationStatus; generation: number };
  narration_get: { pointId: Id; narrationStatus: NarrationStatus; generation: number | null; text: string | null };
  narration_delete: { pointId: Id; narrationStatus: 'missing'; invalidatedGeneration: number };
}
export type WriteResult<K extends WorldOperation> = VersionBlock & { replayed: boolean; operation: K; requestId: Id; requestHash: Digest; world: WorldContext; control: ControlState; work: PointWork | null; data: DataMap[K] };
export type Success<K extends WorldOperation> = K extends 'get_context' ? ContextResponse
  : K extends 'list_points' | 'get_state' | 'narration_get' ? VersionBlock & { world: WorldContext; data: DataMap[K] }
  : K extends 'preview_point' ? VersionBlock & { operation: K; world: WorldContext; control: ControlState; work: PointWork | null; data: DataMap[K] }
  : K extends 'narration_claim' ? Omit<WriteResult<K>, 'data' | 'replayed'> & ({ replayed: false; data: ClaimSummary & { claimToken: Id } } | { replayed: true; data: ClaimSummary })
  : WriteResult<K>;
export interface Scope { worldId?: Id; pointId?: Id }
export interface OperationSpec { operation: WorldOperation; method: 'GET' | 'POST' | 'PUT' | 'DELETE'; path: string; requestSchema?: string | null; successSchema: string; successHttpStatus: number; queryBindings: string[]; errorCodes: { code: ErrorCode; controlRequired: boolean }[] }
