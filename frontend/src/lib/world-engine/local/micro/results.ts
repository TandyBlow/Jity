/** Micro results: per-member head labels plus templated facts. A low-confidence
 * member makes the whole call abstain; the LLM then answers as before. */
import type { MicroResultsFn, MicroResultsRequest } from '../semantics/settlement/types';
import { createBertTokenizer, type BertTokenizer } from './tokenizer';
import { createMicroRuntime } from './runtime';

const RESULT = ['achieved', 'partial', 'not_achieved', 'blocked', 'no_change'];
const PHRASE: Record<string, string> = {
  achieved: '达到目的', partial: '只完成一部分', not_achieved: '没有成功', blocked: '被阻止', no_change: '没有变化',
};
const OUTCOME: Record<string, string> = {
  achieved: 'completed', partial: 'completed', not_achieved: 'failed', blocked: 'blocked', no_change: 'unaffected',
};

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

export interface MicroResultsOptions {
  vocabUrl?: string;
  modelUrl?: string;
  threshold?: number;
  onStats?: (record: { members: number; ms: number; loadMs: number; source: 'micro' | 'abstain' }) => void;
}

export function createMicroResults(options: MicroResultsOptions = {}): MicroResultsFn {
  let tokenizer: Promise<BertTokenizer> | null = null;
  const runtime = createMicroRuntime({ threads: 1 });
  async function ensure() {
    if (!tokenizer) {
      tokenizer = (async () => {
        const response = await fetch(options.vocabUrl ?? '/micro/minirbt-vocab.txt');
        if (!response.ok) throw new Error('micro_vocab_fetch_failed');
        return createBertTokenizer(await response.text());
      })();
    }
    return {
      tok: await tokenizer,
      session: await runtime.load(options.modelUrl ?? '/micro/task-heads-int8.onnx'),
    };
  }

  return async (request) => {
    const started = performance.now();
    const { tok, session } = await ensure();
    const ort = await import('onnxruntime-web/wasm');
    const threshold = options.threshold ?? 0.45;
    const judgments: Array<{ memberId: string; label: string; reason: string }> = [];
    const facts: Array<{ text: string; memberIds: string[]; actorId: string; outcome: string }> = [];
    for (const member of request.members) {
      const name = request.state.initial.characters[member.memberId]?.name ?? member.memberId;
      const roll = member.rolls[0];
      const input = `角色：${name}；行动：${member.actionText.slice(0, 80)}；骰点：${roll ? roll.result : '?'}；资格：${roll ? String(roll.eligible) : '?'}；准入：${roll ? String(roll.admitted) : '?'}`;
      const ids = tok.encode(input, 64);
      const data = BigInt64Array.from(ids, (value) => BigInt(value));
      const mask = BigInt64Array.from(ids, () => 1n);
      const out = await session.run({
        input_ids: new ort.Tensor('int64', data, [1, ids.length]),
        attention_mask: new ort.Tensor('int64', mask, [1, ids.length]),
      });
      const logits = Array.from((out.result?.data ?? []) as Float32Array);
      if (logits.length !== RESULT.length) return null;
      const max = Math.max(...logits);
      const exps = logits.map((value) => Math.exp(value - max));
      const sum = exps.reduce((a, b) => a + b, 0);
      const best = logits.indexOf(max);
      if (exps[best] / sum < threshold) {
        options.onStats?.({ members: request.members.length, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs), source: 'abstain' });
        return null;
      }
      const label = RESULT[best];
      judgments.push({ memberId: member.memberId, label, reason: PHRASE[label] });
      const normalized = member.actionText.replace(/我(?!们)/gu, name);
      const dest = member.structured?.destination;
      const hint = dest
        ? `${dest.entityId}:${dest.containerId}${dest.slotId ? `/${dest.slotId}` : ''}`
        : destinationHint(normalized, request.state, member.memberId);
      facts.push({
        text: `${normalized}（${PHRASE[label]}）${hint ? `；去向=${hint}` : ''}`,
        memberIds: [member.memberId], actorId: member.memberId, outcome: OUTCOME[label],
      });
    }
    options.onStats?.({ members: request.members.length, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs), source: 'micro' });
    return { judgments, facts };
  };
}
