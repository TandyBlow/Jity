/** Narration input projection and serialization contracts.
 *
 * Two model-facing serializers share one projection:
 *   - `yuyan-prose-legacy-v1`: the exact byte format the existing YuYan
 *     checkpoint was trained on. It has no result block; the previous state,
 *     the delta and the 正文 marker are the whole input.
 *   - `yuyan-prose-result-v2`: the same projection plus a 本回合状态 block that
 *     carries only the changed entities, only their changed fields, and the
 *     settled values after the round.
 *
 * The projection is name-keyed because the training rows are name-keyed.
 * Entity ids, task ids and change ids stay in the runtime metadata used to
 * build the projection; they are never rendered for the model.
 */
import type { Id } from '../../types';

export type RowTaskStatus = '未完成' | '已完成';

export interface RowTask {
  目标: string;
  状态: RowTaskStatus;
}

/** A task in the 本回合状态 result. Only tasks touched by this round appear.
 * `属于大任务` stores the immediate parent goal so a changed child keeps its
 * place in the tree; old rows only had one level, so the field keeps the
 * historical name even when the immediate parent is itself a child. */
export interface RowResultTask extends RowTask {
  属于大任务?: string;
}

export interface RowTasks {
  大任务: RowTask | null;
  小任务: RowTask[];
}

export interface RowPerson {
  位置: string;
  精神值: number;
  外貌: string[];
  个性: string[];
  /** null means the person has no registered tasks. */
  任务: RowTasks | null;
}

export interface RowLocation {
  位于: string | null;
  外貌: string[];
}

export interface RowItem {
  位置: string;
  外貌: string[];
}

/** The 上回合状态 block: the scoped state before this round. */
export interface RowState {
  地点: Record<string, RowLocation>;
  人物: Record<string, RowPerson>;
  物品: Record<string, RowItem>;
}

export interface RowDeltaOps {
  位置?: string;
  精神值?: number;
  解除外貌?: string[];
  新增外貌?: string[];
  解除个性?: string[];
  新增个性?: string[];
  完成任务?: string[];
  新增小任务?: { 目标: string }[];
}

/** The 本回合变化 block. `时间推进` keeps the old "8 分钟" spelling; the
 * serializer squashes it to "8分钟" exactly like the Python converter. */
export interface RowDelta {
  时间推进: string;
  变化: Record<string, RowDeltaOps>;
}

export interface RowResultTaskGroup {
  大任务?: RowTask;
  小任务?: RowResultTask[];
}

export interface RowResultPerson {
  位置?: string;
  精神值?: number;
  外貌?: string[];
  个性?: string[];
  任务?: RowResultTaskGroup;
}

export interface RowResultItem {
  位置?: string;
  外貌?: string[];
}

export interface RowResultLocation {
  外貌?: string[];
}

/** The 本回合状态 block: changed entities only, changed fields only. A
 * missing field means "this result does not carry the field", never "the
 * field was deleted" or "the value is zero". */
export type RowResultEntity = RowResultPerson | RowResultItem | RowResultLocation;

export type RowResultState = Record<string, RowResultEntity>;

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
  | 'unknown_or_null_delta_field';

export interface OmittedField {
  entityId: Id;
  entityName: string;
  entityType: 'character' | 'location' | 'item' | 'unknown';
  field: string;
  reason: OmittedFieldReason;
  /** Present for entity-level omissions so an audit can see what was left
   * out without dumping the whole value into the log. */
  originalValue?: string | number | string[] | null;
}

export interface NarrationLengthPolicy {
  /** Maximum UTF-16 code units in the serialized text. null = no limit. */
  maxChars: number | null;
  /** Maximum UTF-8 bytes in the serialized text. null = no limit. */
  maxUtf8Bytes: number | null;
}

export interface NarrationProjectionPolicy {
  length: NarrationLengthPolicy;
}

export const DEFAULT_NARRATION_PROJECTION_POLICY: NarrationProjectionPolicy = {
  length: { maxChars: null, maxUtf8Bytes: null },
};

export interface NarrationViewpoint {
  id: Id;
  name: string;
  /** Full perspective sentence, including the "；只表达..." restriction.
   * The legacy serializer keeps only the segment before the semicolon, as the
   * Python converter does. */
  text: string;
}

export interface NarrationProjection {
  projectionVersion: 'narration-projection-v1';
  viewpoint: NarrationViewpoint;
  beforeState: RowState;
  delta: RowDelta;
  resultState: RowResultState;
  policy: NarrationProjectionPolicy;
}

export interface NarrationVersionSet {
  projectionVersion: 'narration-projection-v1';
  legacySerializerVersion: 'yuyan-prose-legacy-v1';
  resultSerializerVersion: 'yuyan-prose-result-v2';
}

export interface ProjectNarrationInputResult {
  projection: NarrationProjection;
  includedEntities: NarrationEntitySets;
  visibleEntities: NarrationEntitySets;
  omittedFields: OmittedField[];
  version: NarrationVersionSet;
}

export interface RenderedNarrationInput {
  text: string;
  utf8Bytes: number;
  /** SHA-256 of the UTF-8 bytes. Async because browsers expose SHA-256 only
   * through SubtleCrypto. */
  utf8Sha256: Promise<string>;
  /** Unicode code points (matches Python `len`). */
  charCount: number;
  /** UTF-16 code units (JavaScript string length). */
  utf16CodeUnits: number;
  serializerVersion: 'yuyan-prose-legacy-v1' | 'yuyan-prose-result-v2';
}

export type NarrationInputErrorCode =
  | 'unknown_entity'
  | 'ambiguous_entity'
  | 'duplicate_name'
  | 'unknown_container'
  | 'position_cycle'
  | 'after_mismatch'
  | 'field_not_allowed'
  | 'unresolved_supersedes'
  | 'pure_removal_without_supersedes'
  | 'multiple_task_roots'
  | 'invalid_time'
  | 'whitespace'
  | 'oov'
  | 'too_long'
  | 'invalid_projection';

export class NarrationInputError extends Error {
  readonly name = 'NarrationInputError';
  constructor(
    readonly code: NarrationInputErrorCode,
    detail: string,
    readonly context: Record<string, unknown> = {},
  ) {
    super(`${code}: ${detail}`);
  }
}
