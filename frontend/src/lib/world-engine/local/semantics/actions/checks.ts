/** Output guards for the action-family tasks.
 *
 * Every value that leaves this module must already satisfy
 * structured-output.ts (the codec check happens before these guards run).
 * The guards add the semantic checks a codec cannot express:
 *   - the action belongs to the actor (not the player, not the protagonist),
 *   - a target is a registered character standing in the scene,
 *   - the reaction responds to the source instead of acting for it,
 *   - nothing names an entity that is not in the scene.
 *
 * They are deliberately asymmetric: a guard rejects only what is provably
 * wrong (an absent person cannot be touched, a character cannot be the action
 * of another character), and never "fixes" a merely unusual answer.
 */
import type { Id, WorldState } from '../../../types';
import type { SceneCharacter, ActionScene } from './scene';
import { sceneMentions } from './scene';
import {
  firstPersonOutsideQuotes, hasAnaphora, longQuotes, longestSharedSpan, rewriteClauseSpeaker, sharedSubsequence, skeleton, splitQuotes, speaksAs, startsWithName,
} from './text';
import type { ActionIssue } from './types';

export interface CheckResult<T> {
  value: T;
  issues: ActionIssue[];
  /** Short, model-facing repair instructions (one per rejected answer). */
  repairs: string[];
}

export interface CheckOptions {
  maxActionChars: number;
  maxReactionChars: number;
  maxTargets: number;
}

function issue(code: ActionIssue['code'], severity: ActionIssue['severity'], message: string, extra: Partial<ActionIssue> = {}): ActionIssue {
  return { code, severity, message, ...extra };
}

function names(mentions: { entry: { name: string } }[]): string {
  return mentions.map((mention) => mention.entry.name).join('、');
}

/** Directed verbs that turn a mentioned absent name into an attempted
 * interaction. Kept wide on purpose: the consequence of a miss is a warning,
 * not a rejection, so the guard errs toward accepting legal prose. */
const DIRECTED = /(说|问|喊|叫|告诉|提醒|回答|解释|递给|交给|递|交|推|拉|拽|扶|抱|救|找|攻击|威胁|拦|挡|追|冲|打|踢)/u;

function interactionNear(text: string, index: number, length: number): boolean {
  const window = text.slice(Math.max(0, index - 5), index + length + 5);
  return DIRECTED.test(window);
}

/** A task goal ("把故障短讯机恢复到能与凯撒联络的状态") is a standing
 * objective, not one action a character performs now. Small models copy it
 * verbatim — the first real probe produced three such "actions" (all three
 * were goal copies). Equality, the short-goal contiguous-span rule and the
 * broad subsequence rule are all keepers: the controlled comparison showed the
 * remaining rejections were exact copies, not paraphrases. */
function taskGoalCopy(text: string, goals: readonly string[]): string | null {
  const value = skeleton(text);
  if (value.length < 4) return null;
  for (const goalText of goals) {
    const goal = skeleton(goalText);
    if (goal.length < 4) continue;
    if (value === goal) return goalText;
    if (goal.length <= 12 && longestSharedSpan(text, goalText).length >= Math.max(4, Math.ceil(goal.length * 0.6))) return goalText;
    // Restored after the 20ee comparison: the real run showed the rejections
    // were exact goal copies, so removing this branch reduced nothing while it
    // would let a long paraphrase through. See
    // results/product/evidence/06-goal-copy-ab-verdict.json.
    if (sharedSubsequence(text, goalText).coverage >= 0.85) return goalText;
  }
  return null;
}

/** Every registered character's pending/achieved goal. A goal copy is wrong
 * even when it is another character's goal: the run-5 probe produced Nono's
 * goal as the protagonist's continuation, which the actor-only list missed. */
function allGoals(state: WorldState): string[] {
  return Object.keys(state.characters).sort()
    .flatMap((id) => Object.values(state.characters[id].tasks).map((task) => task.goal));
}

/** Small instruct models often answer a labelled prompt with the label:
 * 「行动：…」「反应：…」. The label is formatting, not prose; keeping it would
 * stage "行动：" into the frozen action text (and then into results/narration).
 * Only one leading label is removed, and only when content follows. */
export function stripOutputLabel(text: string): string {
  const match = /^\s*(?:行动|动作|反应|回应|回复|回答|台词)\s*[:：]\s*(?=\S)/u.exec(text);
  return match ? text.slice(match[0].length) : text;
}

/** Action text of one character. `actorIsProtagonist` relaxes exactly the
 * checks that a player-authored command is allowed to fail (the player may
 * speak as themselves and may repeat yesterday's words). */
export function checkActionText(text: string, scene: ActionScene, state: WorldState, options: CheckOptions): CheckResult<string> {
  let value = stripOutputLabel(text).normalize('NFC').trim();
  const issues: ActionIssue[] = [];
  const repairs: string[] = [];
  const push = (item: ActionIssue, repair?: string): void => {
    issues.push(item);
    if (repair && !repairs.includes(repair)) repairs.push(repair);
  };

  if ([...value].length > options.maxActionChars) {
    push(issue('action_too_long', 'warn', `行动描述 ${[...value].length} 字，超过建议长度 ${options.maxActionChars}`));
  }
  // Person is a grammatical reference, not a semantic choice: the actor is
  // known, so a clause-initial 我 is rewritten instead of burning a repair
  // call (the 13:21Z run answered twice in first person and fell back to a
  // skip). Mid-clause 我 is still an error below.
  if (!scene.isProtagonist) {
    const rewritten = rewriteClauseSpeaker(value, scene.actorName);
    if (rewritten.count > 0) {
      push(issue('first_person_rewritten', 'info',
        `模型用了第一人称；程序把句首的“我”改成${scene.actorName}（原文：${value}）`, { detail: value }));
      value = rewritten.text;
    }
  }
  const goal = taskGoalCopy(value, allGoals(state));
  if (goal) {
    push(issue('action_is_task_goal', 'error', `行动句照抄了待办任务目标：“${goal}”；这不是这一刻的具体行动`, { detail: goal }),
      `不要照抄待办任务；把“${goal}”变成${scene.actorName}此刻做的第一步（动词+对象），不要出现目标里的连续 8 个字`);
  }
  if (firstPersonOutsideQuotes(value)) {
    push(issue('action_first_person', 'error', '行动用了第一人称“我”；行动句必须是关于该角色的第三人称描述',
      { detail: value }), '用第三人称写这个角色的行动，不要用“我”');
  }

  const player = scene.playerInput ?? '';
  if (player) {
    const shared = longestSharedSpan(value, player);
    const playerSkeleton = skeleton(player);
    const valueSkeleton = skeleton(value);
    if (valueSkeleton.length > 0 && valueSkeleton === playerSkeleton) {
      push(issue('npc_repeats_player', 'error', '行动句逐字复述了玩家原话（原样照抄）', { detail: player }),
        '不要复述玩家的原话，只写这个角色自己做了什么');
    } else if (shared.length >= 8 || (playerSkeleton.length <= 8 && playerSkeleton.length >= 3 && valueSkeleton.includes(playerSkeleton))) {
      push(issue('npc_repeats_player', 'error', `行动句与玩家原话有 ${shared.length} 字连续重合（“${shared.text}”）`, { detail: shared.text }),
        '不要复述玩家的原话，只写这个角色自己做了什么');
    } else {
      // Paraphrase echo: the player's words in order with a token swapped or
      // dropped. Two directions matter: an action that is mostly the player's
      // text (value coverage), and an action that contains most of the
      // player's text behind a subject ("诺诺" + the player's sentence).
      const subsequence = sharedSubsequence(value, player);
      const playerCoverage = playerSkeleton.length ? subsequence.length / playerSkeleton.length : 0;
      const mostlyPlayer = valueSkeleton.length >= 6 && subsequence.coverage >= 0.8;
      const containsPlayer = subsequence.length >= 8 && playerCoverage >= 0.7;
      if (mostlyPlayer || containsPlayer) {
        // Shared scene words are not an echo. An NPC near the same person
        // necessarily reuses "巷口"/"护目镜"; remove the registered names and
        // ask how much of the PREDICATE is left in common. If almost nothing
        // is left, the overlap is the scene, not the player's sentence: make
        // it a warning and let the action stand. If the verb phrase still
        // tracks the player's sentence (run-1 A1: 「靠在巷口墙边，确认护目镜
        // 是否起雾」 vs 「我靠在巷口墙边，先确认护目镜有没有起雾」), it is a
        // paraphrase and stays an error that triggers repair.
        const lexicon = sceneLexicon(state);
        const residual = sharedSubsequence(stripLexicon(valueSkeleton, lexicon), stripLexicon(playerSkeleton, lexicon));
        const sceneOnly = residual.length <= 3;
        push(issue('npc_repeats_player', sceneOnly ? 'warn' : 'error',
          sceneOnly
            ? `行动句与玩家原话共用了现场名词（覆盖 ${Math.round(playerCoverage * 100)}%），但没有复述玩家的动作；请确认这是角色自己的行动`
            : `行动句把玩家原话改写了一遍（覆盖玩家原话 ${Math.round(playerCoverage * 100)}%，共 ${subsequence.length} 字），不是这个角色自己的行动`,
          { detail: value }), sceneOnly ? undefined : '不要改写玩家的原话当成角色的行动；写这个角色自己做了什么');
      }
    }
    for (const quote of longQuotes(value)) {
      if (player.includes(quote)) {
        push(issue('npc_quotes_player', 'error', `引号里的“${quote}”是玩家原话，被当成这个角色的台词`, { detail: quote }),
          '不要把这个角色没说过的话写成他的台词');
      }
    }
  }

  // Absent entities are only rejected in narration; inside quotes the
  // character may legitimately talk about someone who is elsewhere.
  const { plain } = splitQuotes(value);

  if (!scene.isProtagonist) {
    const protagonist = scene.protagonistName;
    const actor = scene.actorName;
    // The actor's name inside a quote must not rescue a sentence whose
    // subject is still the protagonist.
    if (speaksAs(value, protagonist) && !plain.includes(actor)) {
      push(issue('attribution_swap', 'error', `行动把台词记在主角${protagonist}名下，而这个角色是${actor}`, { detail: protagonist }),
        '台词和动作只能属于本次判断的角色，不能替主角说话');
    } else if (startsWithName(value, protagonist) && !plain.includes(actor)) {
      push(issue('attribution_swap', 'error', `行动句以主角${protagonist}开头，而这个角色是${actor}`, { detail: protagonist }),
        '把主语改成本次判断的角色，不能写主角的行动');
    }
  }
  const mentions = sceneMentions(scene, state, plain);
  // A mention of someone elsewhere is legal prose (thought, report, a name on
  // a radio); attempting to interact with them in this action is not.
  const directed = mentions.absentCharacters.filter((mention) => interactionNear(plain, mention.index, mention.alias.length));
  const incidental = mentions.absentCharacters.filter((mention) => !directed.includes(mention));
  if (directed.length) {
    push(issue('absent_character_in_action', 'error',
      `行动句把不在本地点的人当成现场对象：${names(directed)}`, { detail: names(directed) }),
      '只写本地点能看到的人；不在场的人不能参与这个动作');
  }
  if (incidental.length) {
    push(issue('absent_character_in_action', 'warn',
      `行动句提到不在本地点的人：${names(incidental)}`, { detail: names(incidental) }));
  }
  if (mentions.absentItems.length) {
    push(issue('absent_item_in_action', 'warn',
      `行动句提到不在本地点、也不在身上的物品：${names(mentions.absentItems)}`, { detail: names(mentions.absentItems) }));
  }
  return { value, issues, repairs };
}

/** Registered proper names that a scene sentence naturally reuses. Only names
 * of two characters or more: single generic characters ("门", "墙") are part of
 * the scene vocabulary, not an entity reference. */
function sceneLexicon(state: WorldState): string[] {
  const names: string[] = [];
  const add = (name: string | undefined): void => { if (name && [...name].length >= 2) names.push(name); };
  for (const id of Object.keys(state.initial.characters)) add(state.initial.characters[id]?.name);
  for (const id of Object.keys(state.initial.items)) add(state.initial.items[id]?.name);
  for (const id of Object.keys(state.initial.locations)) add(state.initial.locations[id]?.name);
  return [...new Set(names)].sort((a, b) => [...b].length - [...a].length);
}

function stripLexicon(text: string, lexicon: string[]): string {
  let out = text;
  for (const word of lexicon) out = out.split(word).join('');
  return out;
}

function characterNameIndex(state: WorldState): { byId: Map<Id, string>; byAlias: Map<string, Id> } {
  const byId = new Map<Id, string>();
  const byAlias = new Map<string, Id>();
  for (const id of Object.keys(state.initial.characters).sort()) {
    const name = state.initial.characters[id]!.name;
    byId.set(id, name);
    byAlias.set(name, id);
    const chars = [...name];
    // A shortened personal name ("路明非" → "明非") may come back instead of
    // the id. Only add it when it cannot collide with another registered name.
    if (chars.length >= 3) {
      const short = chars.slice(-2).join('');
      if (!byAlias.has(short)) byAlias.set(short, id);
    }
  }
  return { byId, byAlias };
}

/** Targets value (already codec-validated) → scene-valid target list. */
export function checkTargets(value: { targets: { targetId: string }[] }, scene: ActionScene, state: WorldState,
  actionText: string, options: CheckOptions): CheckResult<{ targets: { targetId: Id }[] }> {
  const issues: ActionIssue[] = [];
  const repairs: string[] = [];
  const push = (item: ActionIssue, repair?: string): void => {
    issues.push(item);
    if (repair && !repairs.includes(repair)) repairs.push(repair);
  };
  const index = characterNameIndex(state);
  const itemNames = new Map(Object.keys(state.initial.items).map((id) => [state.initial.items[id]!.name, id] as const));
  const locationNames = new Map(Object.keys(state.initial.locations).map((id) => [state.initial.locations[id]!.name, id] as const));
  const selected: Id[] = [];
  for (const entry of value.targets) {
    const raw = entry.targetId.normalize('NFC').trim();
    const id = index.byAlias.get(raw) ?? (index.byId.has(raw) ? raw : null);
    if (!id) {
      if (itemNames.has(raw) || locationNames.has(raw)) {
        push(issue('target_not_character', 'error', `“${raw}”是物品或地点，不是人物`, { entityId: raw }),
          `“${raw}”不是人物，targetId 只能从在场人物里选`);
      } else {
        push(issue('target_unknown', 'error', `targetId“${raw}”不是已登记角色`, { entityId: raw }),
          `“${raw}”不是已登记角色，targetId 只能从在场人物里选`);
      }
      continue;
    }
    if (id === scene.actorId) {
      push(issue('target_self', 'warn', `行动者${scene.actorName}把自己列为目标，已忽略`, { entityId: id }));
      continue;
    }
    if (selected.includes(id)) {
      push(issue('target_duplicate', 'info', `目标${index.byId.get(id)}重复出现，已合并`, { entityId: id }));
      continue;
    }
    if (!scene.visible.some((character) => character.id === id)) {
      const roomName = scene.absent.find((character) => character.id === id)?.roomName;
      push(issue('target_absent', 'error',
        `目标${index.byId.get(id)}不在本地点${roomName ? `（在${roomName}）` : ''}`, { entityId: id }),
        `${index.byId.get(id)}不在本地点，不能作为目标；只能从在场人物里选`);
      continue;
    }
    selected.push(id);
  }
  const capped = selected.slice(0, Math.max(1, options.maxTargets));
  if (selected.length > capped.length) {
    push(issue('targets_capped', 'info', `模型给出 ${selected.length} 个目标，按上限只保留 ${capped.length} 个`,
      { detail: selected.join(',') }));
  }

  const mentioned = sceneMentions(scene, state, actionText);
  if (mentioned.absentCharacters.length) {
    push(issue('absent_character_named', 'info',
      `行动提到不在场的人：${names(mentioned.absentCharacters)}；他们没有反应机会`, { detail: names(mentioned.absentCharacters) }));
  }
  if (hasAnaphora(actionText)) {
    push(issue('anaphora_present', 'info', '行动用指代而不是姓名，目标由现场判断', { detail: actionText.slice(0, 60) }));
  }
  if (!capped.length) {
    push(issue('empty_targets', 'info', '没有需要立即反应的在场人物'));
  }
  // Naming the target is the model's semantic call, not a wording rule: a
  // visible person who is actually touched can be selected even when the action
  // says it by situation rather than by name. Membership, visibility, self and
  // the cap are still enforced above.
  return { value: { targets: capped.map((targetId) => ({ targetId })) }, issues, repairs };
}

export interface ReactionCheckContext {
  scene: ActionScene;
  state: WorldState;
  source: SceneCharacter;
  sourceActionText: string;
}

/** Reaction text → accepted reaction or a repair request. */
export function checkReactionText(text: string, context: ReactionCheckContext, options: CheckOptions): CheckResult<string> {
  const { scene, state, source, sourceActionText } = context;
  let value = stripOutputLabel(text).normalize('NFC').trim();
  const issues: ActionIssue[] = [];
  const repairs: string[] = [];
  const push = (item: ActionIssue, repair?: string): void => {
    issues.push(item);
    if (repair && !repairs.includes(repair)) repairs.push(repair);
  };
  const memberName = scene.actorName;
  const sourceName = source.name;
  // Same grammar fix as the action text: the member is known, so a
  // clause-initial 我 is the member speaking, not a semantic choice.
  const rewritten = rewriteClauseSpeaker(value, memberName);
  if (rewritten.count > 0) {
    push(issue('first_person_rewritten', 'info',
      `模型用了第一人称；程序把句首的“我”改成${memberName}（原文：${value}）`, { detail: value }));
    value = rewritten.text;
  }

  const reactionGoals = allGoals(state);
  // This comparison changes action_is_task_goal only. Preserve the existing
  // reaction_goal_copy behaviour instead of silently weakening a second guard.
  const copiedGoal = taskGoalCopy(value, reactionGoals) ?? (skeleton(value).length >= 4
    ? reactionGoals.find((goal) => skeleton(goal).length >= 4 && sharedSubsequence(value, goal).coverage >= 0.85)
    : undefined);
  if (copiedGoal) {
    push(issue('reaction_goal_copy', 'error', `反应照抄了${memberName}的任务目标：“${copiedGoal}”`, { detail: copiedGoal }),
      '不要照抄任务目标；写这个角色此刻被这条行动逼出的具体反应');
  }
  if (!value.length) {
    push(issue('reaction_empty', 'error', '反应是空文本'), '写出这个角色针对这条行动的一句反应');
  }
  if ([...value].length > options.maxReactionChars) {
    push(issue('reaction_too_long', 'warn', `反应 ${[...value].length} 字，超过建议长度 ${options.maxReactionChars}`));
  }
  const shared = longestSharedSpan(value, sourceActionText);
  if (shared.length >= 8) {
    push(issue('reaction_echoes_source', 'error',
      `反应与发起者行动有 ${shared.length} 字连续重合（“${shared.text}”），像复述而不是反应`, { detail: shared.text }),
      '不要复述发起者的行动原话，写这个角色自己怎么反应');
  }
  for (const quote of longQuotes(value)) {
    if (sourceActionText.includes(quote)) {
      push(issue('reaction_quotes_source', 'error', `引号里的“${quote}”是发起者的原话，被当成被牵连角色的台词`, { detail: quote }),
        '被牵连角色不能复述发起者的话');
    }
  }
  if (firstPersonOutsideQuotes(value)) {
    push(issue('reaction_first_person', 'error', '反应用了第一人称“我”；反应必须是第三人称'),
      '用第三人称写这个角色的反应，不要用“我”');
  }
  if (speaksAs(value, sourceName) || startsWithName(value, sourceName)) {
    push(issue('reaction_acts_for_source', 'error', `反应以发起者${sourceName}为主语，而不是${memberName}的反应`, { detail: sourceName }),
      `这段要写${memberName}的反应，不能替${sourceName}行动`);
  }
  if (!scene.isProtagonist && (speaksAs(value, scene.protagonistName) || startsWithName(value, scene.protagonistName))) {
    push(issue('reaction_acts_for_protagonist', 'error', `反应把主角${scene.protagonistName}当成行动者`, { detail: scene.protagonistName }),
      `这段要写${memberName}的反应，不能替主角行动`);
  }

  const { plain } = splitQuotes(value);
  const mentions = sceneMentions(scene, state, plain);
  const allowedCharacters = new Set<Id>([scene.actorId, source.id, ...scene.visible.map((character) => character.id), scene.protagonistId]);
  const invented = mentions.characters
    .filter((mention) => !allowedCharacters.has(mention.entry.id))
    .concat(mentions.absentCharacters.filter((mention) => !allowedCharacters.has(mention.entry.id)));
  if (invented.length) {
    push(issue('reaction_invents_character', 'error', `反应里出现现场没有的人：${names(invented)}`, { detail: names(invented) }),
      '只能写现场已有的人物，不能新增人物');
  }
  if (mentions.absentItems.length) {
    push(issue('reaction_mentions_absent_item', 'warn', `反应提到不在现场的物品：${names(mentions.absentItems)}`,
      { detail: names(mentions.absentItems) }));
  }

  // Whether the sentence reads as a reaction to this action is semantic; the
  // runtime keeps only the structural guards (who is named, who acts, who is
  // invented) and shows the model's own sentence unchanged.
  if (source.roomId !== scene.roomId) {
    push(issue('reaction_member_absent', 'warn', `被牵连角色和发起者不在同一地点（${memberName}在${scene.roomName}）`,
      { detail: `${source.roomId}->${scene.roomId}` }));
  }
  return { value, issues, repairs };
}
