/** Public types for the action-family semantics handlers.
 *
 * The handlers replace one model task each (action / targets / reaction) and
 * keep the controller's wire shapes untouched: inputs are the declared call
 * inputs the scheduler already sends, values are exactly what
 * structured-output.ts validates. Evidence rides alongside the value instead
 * of being smuggled into it, so the controller never sees a non-contract
 * field.
 *
 * `fallback` has one meaning here: the returned value did NOT come from an
 * accepted model answer. `source` says what produced it instead:
 *   model    — the last accepted model output (possibly normalized)
 *   program  — a rule from this module (frozen player command, scene scope,
 *              protagonist reaction floor)
 *   fallback — the model was asked but no answer passed the checks
 */
import type { Id, Json } from '../../../types';

export type ActionTask = 'action' | 'targets' | 'reaction';

export type ActionIssueCode =
  // input / scope
  | 'actor_unknown'
  | 'actor_out_of_scene'
  | 'protagonist_command'
  | 'protagonist_no_input'
  | 'protagonist_command_consumed'
  | 'protagonist_reaction_minimal'
  | 'protagonist_reaction_model'
  // action value
  | 'model_skip'
  | 'action_too_long'
  | 'action_is_task_goal'
  | 'action_first_person'
  | 'npc_repeats_player'
  | 'npc_quotes_player'
  | 'attribution_swap'
  | 'absent_character_in_action'
  | 'absent_item_in_action'
  // targets value
  | 'no_visible_candidates'
  | 'target_unknown'
  | 'target_self'
  | 'target_duplicate'
  | 'target_absent'
  | 'target_not_character'
  | 'targets_capped'
  | 'target_unmentioned'
  | 'absent_character_named'
  | 'anaphora_present'
  | 'empty_targets'
  // reaction value
  | 'reaction_too_long'
  | 'reaction_echoes_source'
  | 'reaction_quotes_source'
  | 'reaction_acts_for_source'
  | 'reaction_acts_for_protagonist'
  | 'reaction_first_person'
  | 'reaction_invents_character'
  | 'reaction_mentions_absent_item'
  | 'reaction_off_topic'
  | 'reaction_member_absent'
  | 'reaction_empty'
  | 'reaction_goal_copy'
  // generation plumbing
  | 'repair_requested'
  | 'repair_failed'
  | 'decode_failure'
  | 'model_failure';

export interface ActionIssue {
  code: ActionIssueCode;
  severity: 'info' | 'warn' | 'error';
  message: string;
  entityId?: Id;
  detail?: string;
}

export interface ActionCallEvidence {
  task: ActionTask;
  key: string;
  attempt: number;
  promptChars: number;
  raw: string;
  elapsedMs: number;
  decoded: boolean;
  error?: string;
  /** Present only when options.capturePrompts is on (archives, probes). */
  prompt?: string;
}

export interface HandlerResult {
  task: ActionTask;
  key: string;
  /** Codec-valid value: {kind:'act'|'skip'} | {targets:[...]} | reaction text. */
  value: Json;
  source: 'model' | 'program' | 'fallback';
  fallback: boolean;
  elapsedMs: number;
  /** Model calls actually made, including the failed repair attempt. */
  attempts: number;
  raw: string;
  issues: ActionIssue[];
  calls: ActionCallEvidence[];
}

export interface ActionHandlerOptions {
  /** Calls per task: 1 = no repair retry, 2 = generation + one repair. */
  attempts?: number;
  temperature?: number;
  repairTemperature?: number;
  seed?: number;
  timeoutMs?: number;
  maxTokens?: Partial<Record<ActionTask, number>>;
  /** Constrained decoding on/off (the codec validates either way). */
  jsonSchema?: 'on' | 'off';
  maxActionChars?: number;
  maxReactionChars?: number;
  maxTargets?: number;
  /** Off-screen characters are outside the player's scene but still part of
   * the world. 'skip' (default) keeps them out of the round's model budget —
   * a scene-scope decision, not a name rule: every same-room character is
   * judged regardless of naming. 'judge' asks the model from the actor's own
   * room and hides the protagonist's move/events from it (full simulation;
   * measured ~6s per call, so a 14-actor round does not fit the wait budget).
   * Either way the reason is logged. */
  offscreenPolicy?: 'skip' | 'judge';
  /** When the protagonist is the admitted reaction target, the player's own
   * character must not be written by a model. 'minimal' returns a program
   * line that asserts no decision (default); 'model' opts into generation. */
  protagonistReaction?: 'minimal' | 'model';
  /** Recent committed happenings (results / narration summaries). The caller
   * owns the log; this module never invents events. */
  recentEvents?: () => readonly string[];
  /** Extra names the model may use for an entity (nicknames, titles). */
  aliases?: Record<Id, string[]>;
  capturePrompts?: boolean;
  onCall?: (call: ActionCallEvidence) => void;
  now?: () => number;
}

export interface ActionHandlers {
  action(key: string, input: Json): Promise<HandlerResult>;
  targets(key: string, input: Json): Promise<HandlerResult>;
  reaction(key: string, input: Json): Promise<HandlerResult>;
}

/** Structural mirrors of the scheduler's declared call inputs. Kept local so
 * this module does not claim ownership of schedule.ts types. */
export interface ActionCallInput {
  actor?: Id;
  advance?: { inputText?: string | null; intentStatus?: string } | null;
  workingState?: unknown;
}

export interface TargetsCallInput {
  sourceId?: Id;
  actionText?: string | null;
  workingState?: unknown;
}

export interface ReactionCallInput {
  sourceId?: Id;
  sourceActionText?: string | null;
  memberId?: Id;
  rollId?: Id;
  workingState?: unknown;
}
