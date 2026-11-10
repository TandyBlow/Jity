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
  firstPersonOutsideQuotes, hasAnaphora, longQuotes, longestSharedSpan, skeleton, splitQuotes, speaksAs, startsWithName,
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

function interactionNear(text: string, alias: string): boolean {
  const index = text.indexOf(alias);
  if (index < 0) return false;
  const window = text.slice(Math.max(0, index - 5), index + alias.length + 5);
  return DIRECTED.test(window);
}

/** Action text of one character. `actorIsProtagonist` relaxes exactly the
 * checks that a player-authored command is allowed to fail (the player may
 * speak as themselves and may repeat yesterday's words). */
export function checkActionText(text: string, scene: ActionScene, state: WorldState, options: CheckOptions): CheckResult<string> {
  const value = text.normalize('NFC').trim();
  const issues: ActionIssue[] = [];
  const repairs: string[] = [];
  const push = (item: ActionIssue, repair?: string): void => {
    issues.push(item);
    if (repair && !repairs.includes(repair)) repairs.push(repair);
  };

  if ([...value].length > options.maxActionChars) {
    push(issue('action_too_long', 'warn', `行动描述 ${[...value].length} 字，超过建议长度 ${options.maxActionChars}`));
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
    }
    for (const quote of longQuotes(value)) {
      if (player.includes(quote)) {
        push(issue('npc_quotes_player', 'error', `引号里的“${quote}”是玩家原话，被当成这个角色的台词`, { detail: quote }),
          '不要把这个角色没说过的话写成他的台词');
      }
    }
  }

  if (!scene.isProtagonist) {
    const protagonist = scene.protagonistName;
    const actor = scene.actorName;
    if (speaksAs(value, protagonist) && !value.includes(actor)) {
      push(issue('attribution_swap', 'error', `行动把台词记在主角${protagonist}名下，而这个角色是${actor}`, { detail: protagonist }),
        '台词和动作只能属于本次判断的角色，不能替主角说话');
    } else if (startsWithName(value, protagonist) && !value.includes(actor)) {
      push(issue('attribution_swap', 'error', `行动句以主角${protagonist}开头，而这个角色是${actor}`, { detail: protagonist }),
        '把主语改成本次判断的角色，不能写主角的行动');
    }
  }

  // Absent entities are only rejected in narration; inside quotes the
  // character may legitimately talk about someone who is elsewhere.
  const { plain } = splitQuotes(value);
  const mentions = sceneMentions(scene, state, plain);
  // A mention of someone elsewhere is legal prose (thought, report, a name on
  // a radio); attempting to interact with them in this action is not.
  const directed = mentions.absentCharacters.filter((mention) => interactionNear(plain, mention.alias));
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

function characterNameIndex(state: WorldState): { byId: Map<Id, string>; byAlias: Map<string, Id> } {
  const byId = new Map<Id, string>();
  const byAlias = new Map<string, Id>();
  for (const id of Object.keys(state.initial.characters).sort()) {
    const name = state.initial.characters[id]!.name;
    byId.set(id, name);
    byAlias.set(name, id);
    const chars = [...name];
    if (chars.length >= 3) byAlias.set(chars.slice(-2).join(''), id);
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
  } else if (!hasAnaphora(actionText)) {
    const unmentioned = capped.filter((id) => {
      const name = index.byId.get(id) ?? id;
      const alias = [...index.byAlias.entries()].filter(([, value]) => value === id).map(([key]) => key);
      return ![name, ...alias].some((value) => actionText.includes(value));
    });
    if (unmentioned.length) {
      push(issue('target_unmentioned', 'warn',
        `行动句没有点名${unmentioned.map((id) => index.byId.get(id)).join('、')}，目标来自模型的现场推断`,
        { detail: unmentioned.join(',') }));
    }
  }
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
  const value = text.normalize('NFC').trim();
  const issues: ActionIssue[] = [];
  const repairs: string[] = [];
  const push = (item: ActionIssue, repair?: string): void => {
    issues.push(item);
    if (repair && !repairs.includes(repair)) repairs.push(repair);
  };
  const memberName = scene.actorName;
  const sourceName = source.name;

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

  const sourceAliases = [sourceName, ...[...sourceName].slice(-2).join('')].filter((alias) => [...alias].length >= 2);
  const mentionsMember = plain.includes(memberName);
  const refersToSource = sourceAliases.some((alias) => plain.includes(alias)) || hasAnaphora(plain);
  const tiedToThreat = refersToSource || shared.length >= 2;
  if (!tiedToThreat && !mentionsMember) {
    push(issue('reaction_off_topic', 'error', '反应既没有提到发起者或现场指代，也没有提到被牵连角色，读不出和这条行动的因果关系',
      { detail: value.slice(0, 60) }), '反应要针对发起者刚才这条行动，写清被牵连角色在回应什么');
  } else if (!tiedToThreat) {
    push(issue('reaction_off_topic', 'warn', '反应只提到被牵连角色，没有明确呼应发起者的行动', { detail: value.slice(0, 60) }));
  }
  if (source.roomId !== scene.roomId) {
    push(issue('reaction_member_absent', 'warn', `被牵连角色和发起者不在同一地点（${memberName}在${scene.roomName}）`,
      { detail: `${source.roomId}->${scene.roomId}` }));
  }
  return { value, issues, repairs };
}
