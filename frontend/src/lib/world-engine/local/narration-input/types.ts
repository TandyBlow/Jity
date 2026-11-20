/** Types for the four-field narration projection and its two serializers.
 *
 * The projection is the model-facing data shape the v2 arm was trained on:
 *   视角 / 上回合状态 / 本回合变化 / 本回合状态
 * Entity and task ids stay in the runtime metadata, never in the text.
 */
import type { Id } from '../../types';
import type { NarrationVersionSet } from './versions';

export type NarrationStage = 'normalize' | 'build' | 'serialize' | 'tokenizer';

/** Stable serializer refusal. Error codes and paths are part of the contract
 * shared with the Python reference (`v2_render.NarrationSerializeError`). */
export class NarrationInputError extends Error {
  readonly name = 'NarrationInputError';
  /** Reference-compatible stage label, matching the frozen golden vectors. */
  stage?: NarrationStage;
  /** The precise step that threw, for debugging; `stage` can be coarser. */
  detailStage?: NarrationStage;
  readonly path: string;
  readonly context: Record<string, unknown>;
  constructor(
    readonly code: string,
    message: string,
    pathOrContext: string | Record<string, unknown> = '',
    context: Record<string, unknown> = {},
  ) {
    const path = typeof pathOrContext === 'string' ? pathOrContext : '';
    super(`${code}: ${message}${path ? ` [${path}]` : ''}`);
    this.path = path;
    this.context = typeof pathOrContext === 'string' ? context : pathOrContext;
  }

  withStage(stage: NarrationStage): this {
    if (!this.detailStage) this.detailStage = stage;
    if (!this.stage) this.stage = stage;
    return this;
  }

  /** Override the reference stage label while keeping the precise one. */
  withReferenceStage(stage: NarrationStage): this {
    this.stage = stage;
    return this;
  }

  asDict(): { code: string; message: string; path: string; stage: NarrationStage | null; detailStage: NarrationStage | null } {
    return {
      code: this.code,
      message: this.message,
      path: this.path,
      stage: this.stage ?? null,
      detailStage: this.detailStage ?? null,
    };
  }
}

// ------------------------------------------------------------- projection

export interface RowTask {
  目标: string;
  状态: string;
}

export interface RowTasks {
  大任务?: RowTask | null;
  小任务: RowTask[];
}

export interface RowPlace {
  位于: string | null;
  外貌: string[];
}

export interface RowPerson {
  位置: string;
  精神值: number;
  外貌: string[];
  个性: string[];
  任务: RowTasks;
}

export interface RowItem {
  位置: string;
  外貌: string[];
}

export interface ProjectionState {
  地点: Record<string, RowPlace>;
  人物: Record<string, RowPerson>;
  物品: Record<string, RowItem>;
}

export interface DeltaNewTask {
  目标: string;
  属于大任务: string;
  状态: string;
}

export interface DeltaOps {
  位置?: string;
  精神值?: number;
  解除外貌?: string[];
  新增外貌?: string[];
  解除个性?: string[];
  新增个性?: string[];
  完成任务?: string[];
  新增小任务?: DeltaNewTask[];
}

export interface ProjectionDelta {
  时间推进: string;
  变化: Record<string, DeltaOps>;
}

export interface ResultTaskGroup {
  大任务?: RowTask;
  小任务?: RowTask[];
}

export interface ResultPerson {
  位置?: string;
  精神值?: number;
  外貌?: string[];
  个性?: string[];
  任务?: ResultTaskGroup;
}

export interface ResultPlace {
  位于?: string | null;
  外貌?: string[];
}

export interface ResultItem {
  位置?: string;
  外貌?: string[];
}

export type ResultEntity = ResultPerson | ResultPlace | ResultItem;
export type ResultState = Record<string, ResultEntity>;

/** The exact four fields, in the only order the serializer accepts. */
export interface NarrationProjection {
  视角: string;
  上回合状态: ProjectionState;
  本回合变化: ProjectionDelta;
  本回合状态: ResultState;
}

// ---------------------------------------------------------------- output

export interface NormalizationEntry {
  path: string;
  action: 'remove_whitespace';
  removed: string[];
  before: string;
  after: string;
}

export interface SerializedSegment {
  kind: 'state' | 'delta' | 'result';
  block: string;
  entity: string;
  entityType: string;
  field: string;
  value: unknown;
  charStart: number;
  charEnd: number;
}

export interface SerializedProjection {
  text: string;
  blocks: Record<string, string>;
  segments: SerializedSegment[];
}

export interface ResultFill {
  entity: string;
  type: string;
  field: string;
  value: unknown;
  source: 'delta';
}

// ------------------------------------------------------------- metadata

export interface NarrationEntitySets {
  characters: Id[];
  locations: Id[];
  items: Id[];
}

export type OmittedFieldReason =
  | 'item_not_changed'
  | 'character_outside_scene'
  | 'location_not_referenced'
  | 'location_visible_but_not_a_state_dependency'
  | 'field_not_changed'
  | 'unknown_or_unchanged_delta_entity';

export interface OmittedField {
  entityId: Id;
  entityName: string;
  entityType: 'character' | 'location' | 'item' | 'unknown';
  field: string;
  reason: OmittedFieldReason;
}

/** The full task tree stays here. The v2 text only carries goal + status and
 * one flat small-task list, so depth and parent links never reach the model. */
export interface TaskHierarchyEntry {
  entityId: Id;
  entityName: string;
  taskId: Id;
  goal: string;
  status: string;
  parentTaskId: Id | null;
  parentGoal: string | null;
  depth: number;
}

export type TextCarryReason =
  | 'task_parent_relation_not_in_v2_text'
  | 'task_depth_not_in_v2_text';

/** A field that exists in the structured projection but has no representation
 * in the model text. Recorded, never silently dropped. */
export interface TextCarryLimit {
  entityId: Id;
  entityName: string;
  taskId: Id;
  goal: string;
  parentTaskId: Id | null;
  parentGoal: string | null;
  reason: TextCarryReason;
}

export interface ProjectionResult {
  projection: NarrationProjection;
  includedEntities: NarrationEntitySets;
  visibleEntities: NarrationEntitySets;
  omittedFields: OmittedField[];
  tasks: TaskHierarchyEntry[];
  textCarryLimits: TextCarryLimit[];
  version: NarrationVersionSet;
}

export interface RenderedNarrationInput {
  text: string;
  serializerVersion: string;
  sha256: string;
  bytesUtf8Hex: string;
  utf8Bytes: number;
  charCount: number;
  segments: SerializedSegment[];
  projection: NarrationProjection;
  normalization: NormalizationEntry[];
  resultFills: ResultFill[];
  version: NarrationVersionSet;
}

export interface LengthLimits {
  maxChars: number | null;
  maxUtf8Bytes: number | null;
}
