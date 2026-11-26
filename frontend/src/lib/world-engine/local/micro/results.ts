/** Micro results: per-member head labels plus templated facts. A low-confidence
 * member makes the whole call abstain; the LLM then answers as before. */
import type { MicroResultsFn, MicroResultsRequest } from '../semantics/settlement/types';
import type { WorldState } from '../../types';
import { roomOf } from '../prompt';
import { environmentHint, environmentPhrase } from '../semantics/settlement/fact-environments';
import { matchLocation } from '../semantics/settlement/fact-destinations';
import { getMicroTokenizer } from './shared';
import { createMicroRuntime } from './runtime';

const RESULT = ['achieved', 'partial', 'not_achieved', 'blocked', 'no_change'];
const PHRASE: Record<string, string> = {
  achieved: '达到目的', partial: '只完成一部分', not_achieved: '没有成功', blocked: '被阻止', no_change: '没有变化',
};
const OBSTRUCTION = ['被阻止', '拦住', '拦下', '被挡住', '锁', '关着', '紧闭', '无法', '没有', '不能', '失败'];
/** A declared walk is program-confirmed only when nothing in its text
 * obstructs it, the destination is a registered location, and the actor is the
 * protagonist. Prior failed sub-actions are checked by the caller. */
export function programMoveAllowed(input: {
  text: string; category: string; destination: { entityId: string; containerId: string } | null | undefined;
  memberId: string; protagonistId: string; currentContainer: string | null; isLocation: boolean;
}): boolean {
  return input.category === 'move'
    && input.destination?.entityId === input.memberId
    && input.memberId === input.protagonistId
    && input.isLocation
    && input.currentContainer !== input.destination.containerId
    && !OBSTRUCTION.some((word) => input.text.includes(word));
}

export function programEnvAllowed(input: {
  text: string; itemIds: string[]; memberId: string; state: WorldState;
}): boolean {
  if (input.itemIds.length !== 1) return false;
  const itemId = input.itemIds[0];
  if (!input.state.initial.items[itemId]) return false;
  if (!environmentPhrase(input.text)) return false;
  if (OBSTRUCTION.some((word) => input.text.includes(word))) return false;
  return roomOf(input.state, itemId) === roomOf(input.state, input.memberId);
}

const OUTCOME: Record<string, string> = {
  achieved: 'completed', partial: 'partial', not_achieved: 'failed', blocked: 'blocked', no_change: 'unaffected',
};

const TRANSFER = ['递给', '交给', '塞给', '递到', '送给', '递上', '塞进', '放进', '装进', '放到', '放在', '塞到', '装入'];

/** A transfer is program-confirmed only when the item is in the actor's hands,
 * the target is in the same room, the text names a transfer verb, and nothing
 * obstructs it. This prevents the results head from inventing an absent target
 * (the single-action goggles turn did exactly that). */
export function programTransferAllowed(input: {
  text: string;
  category: string;
  destination: { entityId: string; containerId: string; slotId?: string | null } | null | undefined;
  memberId: string;
  state: WorldState;
}): boolean {
  if (!['assist', 'use'].includes(input.category) || !input.destination) return false;
  const item = input.state.items[input.destination.entityId];
  const targetCharacter = input.state.initial.characters[input.destination.containerId];
  const targetItem = input.state.initial.items[input.destination.containerId];
  if (!item || (!targetCharacter && !targetItem)) return false;
  if (item.position.containerId === input.destination.containerId) return false;
  const heldByActor = item.position.containerId === input.memberId;
  const sourceRoom = roomOf(input.state, item.position.containerId);
  const actorRoom = roomOf(input.state, input.memberId);
  // Taking from an open container in the same room is as valid as from the hand.
  if (!heldByActor && (!sourceRoom || sourceRoom !== actorRoom)) return false;
  if (targetCharacter) {
    if (roomOf(input.state, input.destination.containerId) !== actorRoom) return false;
  } else if (roomOf(input.state, input.destination.containerId) !== actorRoom
    && input.state.items[input.destination.containerId]?.position.containerId !== input.memberId) {
    return false;
  }
  if (!TRANSFER.some((word) => input.text.includes(word))) return false;
  if (OBSTRUCTION.some((word) => input.text.includes(word))) return false;
  return true;
}

/** A fact may not claim a visible character is absent. If it does, the micro
 * answer abstains and the LLM results lane decides from the full scene. */
export function factContradictsPresence(text: string, visibleNames: readonly string[]): boolean {
  return visibleNames.some((name) => {
    const at = text.indexOf(name);
    if (at < 0) return false;
    const around = text.slice(Math.max(0, at - 4), at) + text.slice(at + name.length, at + name.length + 4);
    return /没有|不在|不见|却不在/u.test(around);
  });
}

/** A structured movement hint from the action text: `entity:container`.
 * The updates port reads it instead of guessing a destination from prose. */
export function destinationHint(action: string, state: MicroResultsRequest['state'], memberId: string): string | null {
  const byName = (name: string) => {
    const trimmed = name.trim();
    for (const group of [state.initial.characters, state.initial.items, state.initial.locations]) {
      for (const [id, entity] of Object.entries(group) as Array<[string, { name?: string }]>) {
        if (entity.name === trimmed) return id;
      }
    }
    return null;
  };
  const transfer = /把(.+?)(?:递给|交给|塞给|递到)(.+?)(?:[。；，,！？]|$)/u.exec(action);
  if (transfer) {
    const item = byName(transfer[1]);
    const person = byName(transfer[2]);
    if (item && person && state.initial.items[item]) return `${item}:${person}`;
  }
  const walk = /(?:走进|走入|走到|走向|进入|来到|回到|退回|退到|跑到|冲向|赶到|爬上|走下)([^。；，,！？]+)/u.exec(action);
  if (walk) {
    const location = byName(walk[1]);
    if (location && state.initial.locations[location]) return `${memberId}:${location}`;
  }
  return null;
}

/** A settled fact may assert the intended destination only for an achieved
 * action. Partial, failed and blocked actions must not move anything. */
export function settledDestination(
  label: string,
  destination: { entityId: string; containerId: string; slotId?: string | null } | null | undefined,
  fallback: () => string | null,
): string | null {
  if (label !== 'achieved') return null;
  if (destination) return `${destination.entityId}:${destination.containerId}${destination.slotId ? `/${destination.slotId}` : ''}`;
  return fallback();
}

export interface MicroResultsOptions {
  vocabUrl?: string;
  modelUrl?: string;
  threshold?: number;
  onStats?: (record: { members: number; inferences?: number; ms: number; loadMs: number; source: 'micro' | 'abstain' }) => void;
}

export function createMicroResults(options: MicroResultsOptions = {}): MicroResultsFn {
  const runtime = createMicroRuntime({ threads: 1 });
  async function ensure() {
    return {
      tok: await getMicroTokenizer(options.vocabUrl),
      session: await runtime.load(options.modelUrl ?? '/micro/task-heads-int8.onnx'),
    };
  }

  return async (request) => {
    const started = performance.now();
    const { tok, session } = await ensure();
    const ort = await import('onnxruntime-web/wasm');
    const threshold = options.threshold ?? 0.45;
    const judgments: Array<{ memberId: string; label: string; reason: string }> = [];
    let judged = 0;
    const facts: Array<{ text: string; memberIds: string[]; actorId: string; outcome: string }> = [];
    for (const member of request.members) {
      const name = request.state.initial.characters[member.memberId]?.name ?? member.memberId;
      const roll = member.rolls[0];
      const rollText = `骰点：${roll ? roll.result : '?'}；资格：${roll ? String(roll.eligible) : '?'}；准入：${roll ? String(roll.admitted) : '?'}`;
      const subActions = member.structured?.subActions?.length
        ? member.structured.subActions
        : [{ id: 'sa1', text: member.actionText, category: member.structured?.category ?? 'other', itemIds: member.structured?.itemIds ?? [], destination: member.structured?.destination ?? null, order: 1, dependsOn: [] as string[] }];
      const labels: string[] = [];
      const visibleNames = Object.entries(request.state.characters)
        .filter(([id]) => id !== member.memberId && roomOf(request.state, id) === roomOf(request.state, member.memberId))
        .map(([, row]) => request.state.initial.characters[row.id]?.name ?? row.id)
        .filter(Boolean);
      for (const subAction of subActions) {
        const priorBlocked = (subAction.dependsOn ?? []).some((id) => {
          const index = Number(id.replace('sa', '')) - 1;
          const label = labels[index];
          return label === 'blocked' || label === 'not_achieved';
        });
        const destination = subAction.destination;
        const current = request.state.characters[member.memberId]?.position;
        // A free walk is program-confirmed only when nothing in the text
        // obstructs it, the destination is a registered location, and no prior
        // sub-action it depends on failed.
        const programMove = !priorBlocked && programMoveAllowed({
          text: subAction.text, category: subAction.category, destination,
          memberId: member.memberId, protagonistId: request.state.protagonistId,
          currentContainer: current?.containerId ?? null,
          isLocation: Boolean(destination?.containerId && request.state.initial.locations[destination.containerId]),
        });
        const programTransfer = !priorBlocked && programTransferAllowed({
          text: subAction.text, category: subAction.category, destination,
          memberId: member.memberId, state: request.state,
        });
        const programEnv = !priorBlocked && programEnvAllowed({
          text: subAction.text, itemIds: subAction.itemIds ?? [],
          memberId: member.memberId, state: request.state,
        });
        const prior = labels.length
          ? `前序：${labels.map((label, index) => `sa${index + 1}=${label}`).join('、')}；`
          : '';
        let label: string;
        if (priorBlocked) {
          label = 'blocked';
        } else if (programMove || programTransfer || programEnv) {
          label = 'achieved';
        } else {
          const input = `角色：${name}；子动作：${subAction.text.slice(0, 80)}；${prior}${rollText}`;
          const ids = tok.encode(input, 64);
          const data = BigInt64Array.from(ids, (value) => BigInt(value));
          const mask = BigInt64Array.from(ids, () => 1n);
          const out = await session.run({
            input_ids: new ort.Tensor('int64', data, [1, ids.length]),
            attention_mask: new ort.Tensor('int64', mask, [1, ids.length]),
          });
          judged += 1;
          const logits = Array.from((out.result?.data ?? []) as Float32Array);
          if (logits.length !== RESULT.length) return null;
          const max = Math.max(...logits);
          const exps = logits.map((value) => Math.exp(value - max));
          const sum = exps.reduce((a, b) => a + b, 0);
          const best = logits.indexOf(max);
          if (exps[best] / sum < threshold) {
            options.onStats?.({ members: request.members.length, inferences: judged, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs), source: 'abstain' });
            return null;
          }
          label = RESULT[best];
        }
        labels.push(label);
        let normalized = subAction.text.replace(/我(?!们)/gu, name);
        if (factContradictsPresence(normalized, visibleNames)) return null;
        // A fact may not name a character outside the group; the action text can.
        // The id is kept in a structured marker so the outsider is not lost.
        const outsiderIds: string[] = [];
        for (const [id, character] of Object.entries(request.state.initial.characters)) {
          if (id === member.memberId || !character.name) continue;
          if (request.members.some((row) => row.memberId === id)) continue;
          if (normalized.includes(character.name)) outsiderIds.push(id);
          normalized = normalized.split(character.name).join('对方');
        }
        // Only an achieved sub-action may assert its destination. A partial,
        // failed or blocked sub-action must not move anything; updates reads
        // this hint as a settled state change.
        const hint = settledDestination(label, destination,
          () => destinationHint(normalized, request.state, member.memberId));
        // Physical manipulation of one registered item is the program half of
        // the env channel; semantic env judgment replaces it when trained.
        let env = !priorBlocked
          ? environmentHint(subAction.text, subAction.itemIds ?? [], request.state, destination, label)
          : null;
        if (!env && !priorBlocked) {
          const phrase = environmentPhrase(subAction.text, label);
          const location = phrase ? matchLocation(request.state, subAction.text) : null;
          if (phrase && location) env = { entityId: location.id, text: phrase };
        }
        const involved = outsiderIds.length ? `；涉及=${outsiderIds.join(',')}` : '';
        facts.push({
          text: `${normalized}（${PHRASE[label]}）${hint ? `；去向=${hint}` : ''}${env ? `；环境=${env.entityId}:${env.text}` : ''}${involved}`,
          memberIds: [member.memberId], actorId: member.memberId, outcome: OUTCOME[label],
        });
      }
      const overall = labels.every((label) => label === labels[0]) ? labels[0] : 'partial';
      judgments.push({ memberId: member.memberId, label: overall, reason: PHRASE[overall] });
    }
    options.onStats?.({ members: request.members.length, inferences: judged, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs), source: 'micro' });
    return { judgments, facts };
  };
}
