/** Structured action fields computed after the action text is accepted.
 *
 * One member action may contain several sub-actions ("递给诺诺，然后戴上护目镜").
 * Each gets an independent id, order and dependency; category, targets, items
 * and destination are derived per sub-action. The top-level fields keep the
 * single-action shape for callers and prompts that predate sub-actions. */
import type { Id, WorldState } from '../../../types';
import type { ActionScene } from './scene';
import { resolveRuleTargets } from '../../micro/targets';
import { matchLocation } from '../settlement/fact-destinations';

export type ActionCategory = 'move' | 'observe' | 'communicate' | 'assist' | 'guard' | 'hide' | 'use' | 'other';

export interface ActionDestination {
  entityId: Id;
  containerId: Id;
  slotId: Id | null;
}

export interface SubAction {
  id: string;
  text: string;
  category: ActionCategory;
  targetIds: Id[];
  itemIds: Id[];
  destination: ActionDestination | null;
  order: number;
  dependsOn: string[];
}

export interface ActionStructure {
  category: ActionCategory;
  actorId: Id;
  targetIds: Id[];
  itemIds: Id[];
  destination: ActionDestination | null;
  conditions: string[];
  subActions: SubAction[];
}

const CATEGORY_RULES: Array<[ActionCategory, string[]]> = [
  ['move', ['走进', '走入', '走到', '走向', '进入', '来到', '回到', '退回', '退到', '跑到', '冲向', '赶到', '爬上', '走下', '钻出', '穿过', '离开', '前往', '让路']],
  ['assist', ['递给', '交给', '塞给', '扶', '帮助', '掩护', '拉开', '托住', '抬起', '包扎']],
  ['guard', ['守住', '挡住', '拦住', '拦下', '护住', '戒备']],
  ['communicate', ['问', '说', '喊', '告诉', '报告', '回答', '解释', '示意', '呼叫', '对讲']],
  ['hide', ['蹲', '躲', '藏', '伏下', '屏住']],
  ['observe', ['看', '检查', '确认', '查看', '望', '观察', '核对', '清点', '找']],
  ['use', ['用', '换', '装', '拿', '举', '按', '推', '拉', '打开', '关闭', '戴上', '摘下']],
];

function longestOverlap(left: string, right: string): number {
  let best = 0;
  for (let i = 0; i < left.length; i += 1) {
    for (let j = i + 2; j <= left.length; j += 1) {
      if (right.includes(left.slice(i, j))) best = Math.max(best, j - i);
    }
  }
  return best;
}

function coreName(name: string): string {
  const core = name.replace(/^.+?的/u, '');
  return core.length >= 2 ? core : name;
}

/** Registered items whose name overlaps the mention; an ambiguous top score
 * returns nothing instead of guessing. */
export function matchItems(text: string, names: Array<{ id: Id; name: string }>, owner?: string): Id[] {
  const scored = names
    .map((item) => ({ id: item.id, name: item.name, score: Math.max(longestOverlap(coreName(item.name), text), longestOverlap(item.name, text)) }))
    .filter((row) => row.score >= 2)
    .sort((left, right) => right.score - left.score);
  if (!scored.length) return [];
  if (scored.length > 1 && scored[1].score === scored[0].score) {
    // A tie is resolved only by ownership: 路明非的护目镜 beats 备用护目镜.
    const mine = scored.filter((row) => row.score === scored[0].score && owner && row.name.startsWith(`${owner}的`));
    return mine.length === 1 ? [mine[0].id] : [];
  }
  return [scored[0].id];
}

function categoryOf(text: string): ActionCategory {
  for (const [category, words] of CATEGORY_RULES) {
    if (words.some((word) => text.includes(word))) return category;
  }
  return 'other';
}

function slotFor(state: WorldState, locationId: Id, text: string): Id | null {
  let best = 0;
  let slotId: Id | null = null;
  for (const slot of state.initial.locations[locationId].slots ?? []) {
    let score = 0;
    for (let i = 0; i + 3 <= slot.label.length; i += 1) {
      if (text.includes(slot.label.slice(i, i + 3))) score = 3;
    }
    if (score > best) { best = score; slotId = slot.id; }
  }
  return best >= 3 ? slotId : null;
}

/** A comma followed by a sequencing word starts a new sub-action. A clause
 * whose subject is somebody else (他/她/他们) is not split: the results lane
 * judges the other actor, and attributing it here would invent a sub-action. */
function splitSubActions(text: string): string[] {
  const parts = text.split(/[，,]\s*(?:然后|接着|再|同时|并)/u).map((part) => part.trim()).filter(Boolean);
  if (parts.length <= 1) return [text];
  if (parts.slice(1).some((part) => /^(?:他|她|他们|她们|对方|那人)/u.test(part))) return [text];
  return parts;
}

function fieldsFor(text: string, scene: ActionScene, state: WorldState, maxTargets: number, owner?: string): Omit<SubAction, 'id' | 'order' | 'dependsOn'> {
  const items = Object.entries(state.initial.items).map(([id, item]) => ({ id, name: item.name ?? id }));
  const visible = scene.visible.map((character) => ({ id: character.id, name: character.name }));
  const targets = resolveRuleTargets(text, { visible, absent: scene.absent }, maxTargets) ?? [];
  let destination: ActionDestination | null = null;
  const transfer = /把(.+?)(?:递给|交给|塞给|递到)(.+?)(?:[。；，,！？]|$)/u.exec(text);
  if (transfer) {
    const item = matchItems(transfer[1], items, owner)[0];
    const person = visible.find((character) => character.name === transfer[2].trim())?.id;
    if (item && person) destination = { entityId: item, containerId: person, slotId: null };
  }
  if (!destination) {
    const matched = matchLocation(state, text);
    const moves = CATEGORY_RULES[0][1].some((word) => text.includes(word));
    if (matched && moves) {
      destination = { entityId: scene.actorId, containerId: matched.id, slotId: slotFor(state, matched.id, text) };
    }
  }
  return { text, category: categoryOf(text), targetIds: targets, itemIds: matchItems(text, items, owner), destination };
}

export function buildActionStructure(
  text: string,
  scene: ActionScene,
  state: WorldState,
  maxTargets: number,
): ActionStructure {
  const parts = splitSubActions(text);
  const subActions: SubAction[] = parts.map((part, index) => ({
    id: `sa${index + 1}`,
    ...fieldsFor(part, scene, state, maxTargets, scene.actorName),
    order: index + 1,
    dependsOn: index === 0 ? [] : [`sa${index}`],
  }));
  const targets = [...new Set(subActions.flatMap((action) => action.targetIds))];
  const items = [...new Set(subActions.flatMap((action) => action.itemIds))];
  return {
    category: subActions[0].category,
    actorId: scene.actorId,
    targetIds: targets,
    itemIds: items,
    destination: subActions.length === 1 ? subActions[0].destination : null,
    conditions: [],
    subActions,
  };
}
