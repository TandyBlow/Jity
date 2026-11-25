/** Structured action fields computed after the action text is accepted.
 *
 * Category and destination are rule-derived; target ids reuse the targets
 * rules; item ids come from a lexical matcher that returns nothing when the
 * mention has no registered counterpart (no forced alias). The fields travel
 * to the results lane so the same action is not re-read there. */
import type { Id, WorldState } from '../../../types';
import type { ActionScene } from './scene';
import { resolveRuleTargets } from '../../micro/targets';

export type ActionCategory = 'move' | 'observe' | 'communicate' | 'assist' | 'guard' | 'hide' | 'use' | 'other';

export interface ActionStructure {
  category: ActionCategory;
  actorId: Id;
  targetIds: Id[];
  itemIds: Id[];
  destination: { entityId: Id; containerId: Id; slotId: Id | null } | null;
  conditions: string[];
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
export function matchItems(text: string, names: Array<{ id: Id; name: string }>): Id[] {
  const scored = names
    .map((item) => ({ id: item.id, score: Math.max(longestOverlap(coreName(item.name), text), longestOverlap(item.name, text)) }))
    .filter((row) => row.score >= 2)
    .sort((left, right) => right.score - left.score);
  if (!scored.length) return [];
  if (scored.length > 1 && scored[1].score === scored[0].score) return [];
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

export function buildActionStructure(
  text: string,
  scene: ActionScene,
  state: WorldState,
  maxTargets: number,
): ActionStructure {
  const items = Object.entries(state.initial.items).map(([id, item]) => ({ id, name: item.name ?? id }));
  const visible = scene.visible.map((character) => ({ id: character.id, name: character.name }));
  const targets = resolveRuleTargets(text, { visible, absent: scene.absent }, maxTargets) ?? [];
  let destination: ActionStructure['destination'] = null;
  const transfer = /把(.+?)(?:递给|交给|塞给|递到)(.+?)(?:[。；，,！？]|$)/u.exec(text);
  if (transfer) {
    const item = matchItems(transfer[1], items)[0];
    const person = visible.find((character) => character.name === transfer[2].trim())?.id;
    if (item && person) destination = { entityId: item, containerId: person, slotId: null };
  }
  if (!destination) {
    let at = -1;
    let locationId: Id | null = null;
    for (const [id, location] of Object.entries(state.initial.locations)) {
      const name = location.name ?? '';
      if (name.length < 2) continue;
      const index = text.lastIndexOf(name);
      if (index > at) { at = index; locationId = id; }
    }
    const moves = CATEGORY_RULES[0][1].some((word) => text.includes(word));
    if (locationId && moves) {
      destination = { entityId: scene.actorId, containerId: locationId, slotId: slotFor(state, locationId, text) };
    }
  }
  return {
    category: categoryOf(text),
    actorId: scene.actorId,
    targetIds: targets,
    itemIds: matchItems(text, items),
    destination,
    conditions: [],
  };
}
