/** Action-family semantics: one handler per controller model task.
 *
 *   action(key, input)   — should this character act on its own, and what?
 *   targets(key, input)  — which present characters does a confirmed action
 *                          directly touch?
 *   reaction(key, input) — what does one admitted target do in response?
 *
 * The scheduler, group freezing, dice admission, "already acted" bookkeeping
 * and commit stay with the controller. These handlers only turn the declared
 * call input into one codec-valid candidate plus evidence.
 *
 * Wiring (the main agent's game-model adapter, for reference):
 *
 *   const handlers = createActionHandlers({ engine, options: { recentEvents: () => resultsLog } });
 *   const model: WorldModelPort = {
 *     generate: async (task, key, input) => {
 *       if (task === 'action') return (await handlers.action(key, input)).value;
 *       if (task === 'targets') return (await handlers.targets(key, input)).value;
 *       if (task === 'reaction') return (await handlers.reaction(key, input)).value;
 *       return existingLocalGameModel.generate(task, key, input);   // results/updates/...
 *     },
 *   };
 *
 * or simply `createActionModelPort(engine, options)` and delegate the rest.
 */
import type { Json, WorldState } from '../../../types';
import type { InferenceEngine } from '../../../runtime/engine';
import { decodeTaskOutput } from '../../../runtime/structured-output';
import { taskOutputSchema } from '../../../runtime/output-schema';
import type { ModelTask } from '../../../schedule';
import { roomOf } from '../../prompt';
import { actionPrompt, reactionPrompt, targetsPrompt } from './prompts';
import { buildScene, characterView, type ActionScene, type SceneCharacter } from './scene';
import { checkActionText, checkReactionText, checkTargets, type CheckOptions } from './checks';
import { longestSharedSpan } from './text';
import { readActionCall, readReactionCall, readTargetsCall } from './inputs';
import type {
  ActionCallEvidence, ActionHandlerOptions, ActionHandlers, ActionIssue, ActionTask, HandlerResult,
} from './types';

export type {
  ActionCallEvidence, ActionCallInput, ActionHandlerOptions, ActionHandlers, ActionIssue, ActionIssueCode,
  ActionTask, HandlerResult, ReactionCallInput, TargetsCallInput,
} from './types';
export type { ActionScene, NameEntry, SceneCharacter, SceneItem, SceneTask } from './scene';
export { buildScene, findMentions, nameTable, positionLabel, roomChain, sceneMentions } from './scene';
export { actionPrompt, reactionPrompt, targetsPrompt } from './prompts';

const DEFAULT_TOKENS: Record<ActionTask, number> = { action: 96, targets: 96, reaction: 128 };

const TARGETS_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['targets'],
  properties: {
    targets: {
      type: 'array',
      items: { type: 'object', additionalProperties: false, required: ['targetId'], properties: { targetId: { type: 'string', minLength: 1 } } },
    },
  },
};

interface TargetsValue { targets: { targetId: string }[] }

interface Generated<T> {
  accepted: { value: T; raw: string; issues: ActionIssue[] } | null;
  calls: ActionCallEvidence[];
  lastRaw: string;
  lastIssues: ActionIssue[];
}

interface GenerateArgs<T> {
  task: ActionTask;
  key: string;
  prompt: string;
  maxTokens: number;
  schema?: unknown;
  decode: (raw: string) => T;
  check: (value: T) => { value: T; issues: ActionIssue[]; repairs: string[] };
}

export interface ActionHandlerDeps {
  engine: InferenceEngine;
  options?: ActionHandlerOptions;
}

function asJson(value: unknown): Json {
  return value as Json;
}

function describeFailure(issues: ActionIssue[]): string {
  const errors = issues.filter((item) => item.severity === 'error').map((item) => item.message);
  return errors.length ? errors.join('；') : '输出不符合任务要求';
}

export function createActionHandlers(deps: ActionHandlerDeps): ActionHandlers {
  const { engine } = deps;
  const options = deps.options ?? {};
  const now = options.now ?? (() => (typeof performance !== 'undefined' ? performance.now() : Date.now()));
  const attempts = Math.max(1, options.attempts ?? 2);
  const checkOptions: CheckOptions = {
    maxActionChars: options.maxActionChars ?? 80,
    maxReactionChars: options.maxReactionChars ?? 120,
    maxTargets: options.maxTargets ?? 2,
  };
  const schemaEnabled = (options.jsonSchema ?? 'on') !== 'off';
  const tokens = (task: ActionTask): number => options.maxTokens?.[task] ?? DEFAULT_TOKENS[task];

  async function generate<T>(args: GenerateArgs<T>): Promise<Generated<T>> {
    const calls: ActionCallEvidence[] = [];
    // Rejected attempts stay in the evidence: a repair that worked is still a
    // first-attempt failure the reviewer must be able to see.
    const history: ActionIssue[] = [];
    let prompt = args.prompt;
    let lastRaw = '';
    let lastIssues: ActionIssue[] = [];
    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      const started = now();
      let raw = '';
      let decoded = false;
      let error: string | undefined;
      try {
        raw = await engine.complete(prompt, {
          maxTokens: args.maxTokens,
          temperature: attempt === 1 ? options.temperature ?? 0 : options.repairTemperature ?? 0.2,
          seed: options.seed,
          timeoutMs: options.timeoutMs ?? 60_000,
          ...(schemaEnabled && args.schema !== undefined ? { jsonSchema: args.schema } : {}),
        });
        const value = args.decode(raw);
        decoded = true;
        const checked = args.check(value);
        const record: ActionCallEvidence = {
          task: args.task, key: args.key, attempt, promptChars: prompt.length, raw,
          elapsedMs: Math.round(now() - started), decoded,
          ...(options.capturePrompts ? { prompt } : {}),
        };
        calls.push(record);
        options.onCall?.(record);
        lastRaw = raw;
        lastIssues = checked.issues;
        if (!checked.issues.some((item) => item.severity === 'error')) {
          return { accepted: { value: checked.value, raw, issues: [...history, ...checked.issues] }, calls, lastRaw, lastIssues };
        }
        history.push(...checked.issues, {
          code: 'repair_requested', severity: 'warn',
          message: `第 ${attempt} 次输出被拒：${describeFailure(checked.issues)}`,
        });
        if (attempt < attempts) {
          prompt = `${args.prompt}\n\n【上一次输出不能采用】${checked.repairs.join('；')}。请重新判断，只输出规定格式。`;
        }
      } catch (caught) {
        const incomplete = caught as { completion?: { raw?: string } };
        raw = incomplete.completion?.raw ?? raw;
        error = caught instanceof Error ? caught.message : String(caught);
        const record: ActionCallEvidence = {
          task: args.task, key: args.key, attempt, promptChars: prompt.length, raw,
          elapsedMs: Math.round(now() - started), decoded, error,
          ...(options.capturePrompts ? { prompt } : {}),
        };
        calls.push(record);
        options.onCall?.(record);
        lastRaw = raw;
        lastIssues = [{ code: 'decode_failure', severity: 'error', message: `第 ${attempt} 次输出无法解析：${error}` }];
        history.push(...lastIssues);
        if (attempt < attempts) {
          prompt = `${args.prompt}\n\n【上一次输出无法解析】${error}。请只输出规定格式，不要解释。`;
        }
      }
    }
    return { accepted: null, calls, lastRaw, lastIssues: [...history, ...lastIssues] };
  }

  function evidence(task: ActionTask, key: string, value: Json, source: HandlerResult['source'],
    started: number, issues: ActionIssue[], calls: ActionCallEvidence[], raw: string): HandlerResult {
    return {
      task, key, value, source, fallback: source === 'fallback',
      elapsedMs: Math.round(now() - started), attempts: calls.length, raw, issues, calls,
    };
  }

  async function action(key: string, rawInput: Json): Promise<HandlerResult> {
    const started = now();
    const call = readActionCall(key, rawInput);
    const issues: ActionIssue[] = [];
    if (!call.state.characters[call.actor]) throw new Error(`actor_unknown:${call.actor}`);
    // Off-screen means outside the player's scene, not outside the world: the
    // actor is still judged from its own room, but it must not see or answer
    // the protagonist's move. 'skip' keeps those actors out of the model
    // budget; 'judge' (default) lets their own tasks and events evolve the
    // world instead of freezing everyone who is not in the current room.
    const offscreen = call.actor !== call.state.protagonistId
      && roomOf(call.state, call.actor) !== roomOf(call.state, call.state.protagonistId);
    const judgeOffscreen = offscreen && (options.offscreenPolicy ?? 'skip') === 'judge';
    // A same-room NPC may see that the protagonist acted, but not the
    // player's sentence: when a program/narration line repeats the command,
    // the small model copied that line as its own action (16:46 run: nono
    // repeated the player's walk/read on all three attempts). Events that
    // share an 8-char span with the command are dropped for NPCs; the
    // protagonist's own deferred action still receives every event.
    const isNpc = call.actor !== call.state.protagonistId;
    const events = judgeOffscreen
      ? []
      : (options.recentEvents?.() ?? []).filter((event) => !isNpc || !call.inputText || longestSharedSpan(event, call.inputText).length < 8);
    const scene = buildScene(call.state, call.actor, {
      playerInput: judgeOffscreen ? null : call.inputText,
      intentStatus: call.intentStatus,
      events,
      aliases: options.aliases,
    });

    // The player's own pending command is the frozen action: no model may
    // rewrite it, and no name/interaction keyword decides whether it counts.
    if (scene.isProtagonist && call.intentStatus === 'pending') {
      if (!call.inputText) {
        issues.push({ code: 'protagonist_no_input', severity: 'info', message: '主角没有待处理输入，本回合不行动' });
        return evidence('action', key, { kind: 'skip' }, 'program', started, issues, [], '');
      }
      issues.push({ code: 'protagonist_command', severity: 'info', message: '主角的待处理命令原样作为冻结行动' });
      return evidence('action', key, { kind: 'act', text: call.inputText }, 'program', started, issues, [], '');
    }

    // Scene scope: a character in another room is not visible to the player's
    // scene. With 'skip' it is a zero-call scope decision; with 'judge' it is a
    // full judgement of the actor's own room (protagonist context hidden).
    if (offscreen && !judgeOffscreen) {
      issues.push({
        code: 'actor_out_of_scene', severity: 'info',
        message: `${scene.actorName}在${scene.roomName}，不在主角所在的${scene.protagonistRoomName}，本场景不判断`,
        entityId: scene.actorId,
      });
      return evidence('action', key, { kind: 'skip' }, 'program', started, issues, [], '');
    }

    // The protagonist is the player's character: no model call may write their
    // action, not even a "continuation". A consumed input means an earlier
    // opportunity (or an automatic round) already handled it, so the correct
    // answer is skip, never a generated second action. Replaying the frozen
    // text here would also re-execute the player's command.
    if (scene.isProtagonist) {
      issues.push({
        code: 'protagonist_command_consumed', severity: 'info',
        message: call.inputText
          ? '主角这条输入已经被处理过；本机会不再重复执行，也不由模型代写后续动作'
          : '主角没有新的输入；本机会不行动',
      });
      return evidence('action', key, { kind: 'skip' }, 'program', started, issues, [], '');
    }

    const generated = await generate<{ kind: 'act'; text?: string } | { kind: 'skip' }>({
      task: 'action', key, prompt: actionPrompt(scene), maxTokens: tokens('action'),
      schema: taskOutputSchema('action', asJson({})),
      decode: (raw) => decodeTaskOutput('action', raw) as unknown as { kind: 'act'; text?: string } | { kind: 'skip' },
      check: (value) => {
        if (value.kind === 'skip') return { value, issues: [{ code: 'model_skip', severity: 'info', message: `${scene.actorName}此刻不行动` }], repairs: [] };
        const checked = checkActionText(String(value.text ?? ''), scene, call.state, checkOptions);
        return { value: { kind: 'act', text: checked.value }, issues: checked.issues, repairs: checked.repairs };
      },
    });

    if (generated.accepted) {
      return evidence('action', key, asJson(generated.accepted.value), 'model', started,
        [...issues, ...generated.accepted.issues], generated.calls, generated.accepted.raw);
    }
    issues.push(...generated.lastIssues, { code: 'repair_failed', severity: 'error', message: '行动判断没有可用输出，按不行动回退' });
    return evidence('action', key, { kind: 'skip' }, 'fallback', started, issues, generated.calls, generated.lastRaw);
  }

  async function targets(key: string, rawInput: Json): Promise<HandlerResult> {
    const started = now();
    const call = readTargetsCall(key, rawInput);
    const issues: ActionIssue[] = [];
    const scene = buildScene(call.state, call.sourceId, { aliases: options.aliases });
    if (!scene.visible.length) {
      issues.push({ code: 'no_visible_candidates', severity: 'info', message: '本地点没有其他角色，行动不可能牵连到场人物' });
      issues.push({ code: 'empty_targets', severity: 'info', message: '没有需要立即反应的在场人物' });
      return evidence('targets', key, { targets: [] }, 'program', started, issues, [], '');
    }

    const generated = await generate<TargetsValue>({
      task: 'targets', key, prompt: targetsPrompt(scene, call.actionText, checkOptions.maxTargets),
      maxTokens: tokens('targets'), schema: TARGETS_SCHEMA,
      decode: (raw) => decodeTaskOutput('targets', raw) as unknown as TargetsValue,
      check: (value) => checkTargets(value, scene, call.state, call.actionText, checkOptions),
    });

    if (generated.accepted) {
      return evidence('targets', key, asJson(generated.accepted.value), 'model', started,
        [...issues, ...generated.accepted.issues], generated.calls, generated.accepted.raw);
    }
    issues.push(...generated.lastIssues, { code: 'repair_failed', severity: 'error', message: '牵连判断没有可用输出，按无目标回退' });
    issues.push({ code: 'empty_targets', severity: 'info', message: '没有需要立即反应的在场人物' });
    return evidence('targets', key, { targets: [] }, 'fallback', started, issues, generated.calls, generated.lastRaw);
  }

  async function reaction(key: string, rawInput: Json): Promise<HandlerResult> {
    const started = now();
    const call = readReactionCall(key, rawInput);
    const issues: ActionIssue[] = [];
    const state = call.state;
    if (!state.characters[call.sourceId]) throw new Error(`reaction_source_unknown:${call.sourceId}`);
    if (!state.characters[call.memberId]) throw new Error(`reaction_member_unknown:${call.memberId}`);
    const scene = buildScene(state, call.memberId, { aliases: options.aliases });
    const source: SceneCharacter = characterView(state, call.sourceId,
      state.characters[call.sourceId] && scene.visible.some((character) => character.id === call.sourceId) ? 'visible' : 'absent');

    // The player's character is never written by the model. The admitted
    // reaction slot still needs a legal action text, so the program returns
    // an explicit non-action: the player keeps the next decision.
    if (scene.isProtagonist && options.protagonistReaction !== 'model') {
      issues.push({
        code: 'protagonist_reaction_minimal', severity: 'info',
        message: '被牵连的是主角，模型不代写玩家角色的反应；本段记为未反应，决定权留在玩家',
      });
      return evidence('reaction', key, asJson(`${scene.actorName}没有作出反应。`), 'program', started, issues, [], '');
    }

    const generated = await generate<string>({
      task: 'reaction', key, prompt: reactionPrompt(scene, source, call.sourceActionText), maxTokens: tokens('reaction'),
      decode: (raw) => decodeTaskOutput('reaction', raw) as string,
      check: (value) => checkReactionText(value, { scene, state, source, sourceActionText: call.sourceActionText }, checkOptions),
    });

    if (generated.accepted) {
      return evidence('reaction', key, asJson(generated.accepted.value), 'model', started,
        [...issues, ...generated.accepted.issues], generated.calls, generated.accepted.raw);
    }
    issues.push(...generated.lastIssues, { code: 'repair_failed', severity: 'error', message: '反应生成没有可用输出，按最小反应回退' });
    return evidence('reaction', key, asJson(`${scene.actorName}的反应慢了半拍。`), 'fallback', started, issues, generated.calls, generated.lastRaw);
  }

  return { action, targets, reaction };
}

export interface ActionModelPort {
  generate(task: ModelTask, key: string, input: Json): Promise<Json>;
  readonly handlers: ActionHandlers;
  readonly evidence: HandlerResult[];
}

/** Thin WorldModelPort adapter for the three tasks. Any other task throws:
 * results/updates/narration keep their existing owner and must be delegated
 * by the caller instead of silently collapsing to a fallback here. */
export function createActionModelPort(engine: InferenceEngine, options: ActionHandlerOptions = {}): ActionModelPort {
  const handlers = createActionHandlers({ engine, options });
  const evidence: HandlerResult[] = [];
  const record = (result: HandlerResult): Json => {
    evidence.push(result);
    return result.value;
  };
  return {
    handlers,
    evidence,
    async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
      if (task === 'action') return record(await handlers.action(key, input));
      if (task === 'targets') return record(await handlers.targets(key, input));
      if (task === 'reaction') return record(await handlers.reaction(key, input));
      throw new Error(`unsupported_action_port_task:${task}`);
    },
  };
}

/** The scene a handler would see. Exported for probes and tests that need to
 * assert on the exact visible/absent split without calling the model. */
export function sceneFor(state: WorldState, focusId: string, input: { playerInput?: string | null; intentStatus?: string } = {}): ActionScene {
  return buildScene(state, focusId, { playerInput: input.playerInput ?? null, intentStatus: input.intentStatus ?? 'pending' });
}
