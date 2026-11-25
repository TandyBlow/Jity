/** Micro updates: the movement head votes per scanned entity; a move is kept
 * only when the entity's own settled fact names a registered destination. Any
 * unexplained move abstains to the LLM, so a missed label can never silently
 * drop state. Appearances stay with the LLM for now. */
import type { Id } from '../../types';
import type { MicroUpdatesFn, MicroUpdatesRequest } from '../semantics/settlement/types';
import { resultFacts } from '../semantics/settlement/support';
import { destinationOfFact } from '../semantics/settlement/updates';
import { readDestinations } from '../semantics/settlement/fact-destinations';
import { createBertTokenizer, type BertTokenizer } from './tokenizer';
import { createMicroRuntime, scoreSingle } from './runtime';

export interface MicroUpdatesOptions {
  vocabUrl?: string;
  modelUrl?: string;
  /** Probability of "moved" above which the head claims a move. */
  threshold?: number;
  onStats?: (record: {
    entities: number; ms: number; loadMs: number;
    source: 'micro' | 'abstain'; moved: string[]; reason?: string;
  }) => void;
}

/** Same text `build_movement_inputs.py` trained on. */
function factsText(state: MicroUpdatesRequest['state'], results: MicroUpdatesRequest['results']): string {
  return resultFacts(results)
    .slice(0, 3)
    .map(({ memberId, text }) => {
      const name = state.initial.characters[memberId]?.name ?? '';
      return `${memberId}${name ? ` ${name}` : ''}: ${text.slice(0, 50)}`;
    })
    .join(' | ')
    .slice(0, 160);
}

function entityText(request: MicroUpdatesRequest, entityId: Id, facts: string): string {
  const { state } = request;
  const name = state.initial.characters[entityId]?.name
    ?? state.initial.items[entityId]?.name ?? entityId;
  const position = state.characters[entityId]?.position ?? state.items[entityId]?.position;
  const container = position?.containerId ?? '?';
  const slot = position?.slotId ?? '-';
  return `实体：${name}；当前：${container}/${slot}；本组结果：${facts}`;
}

export { readDestinations } from '../semantics/settlement/fact-destinations';

export function createMicroUpdates(options: MicroUpdatesOptions = {}): MicroUpdatesFn {
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
      session: await runtime.load(options.modelUrl ?? '/micro/movement-head-int8.onnx'),
    };
  }

  return async (request) => {
    const started = performance.now();
    const threshold = options.threshold ?? 0.5;
    const { tok, session } = await ensure();
    const facts = factsText(request.state, request.results);
    const moved: Id[] = [];
    for (const entityId of request.scanned) {
      const ids = tok.encode(entityText(request, entityId, facts), 64);
      const logits = await scoreSingle(session, ids);
      if (logits.length !== 2) return null;
      const max = Math.max(...logits);
      const exps = logits.map((value) => Math.exp(value - max));
      const p = exps[1] / (exps[0] + exps[1]);
      if (p >= threshold) moved.push(entityId);
    }
    const stats = (source: 'micro' | 'abstain', reason?: string) => options.onStats?.({
      entities: request.scanned.length, ms: Math.round(performance.now() - started),
      loadMs: Math.round(runtime.stats().loadMs), source, moved, ...(reason ? { reason } : {}),
    });
    const hints = readDestinations(Object.values(request.results));
    if (!moved.length) {
      // A missed move must not erase an explicit structured destination.
      if (hints.size) {
        const positions: { entityId: Id; containerId: Id; slotId: Id | null }[] = [];
        for (const [entityId, hint] of hints) {
          if (!request.scanned.includes(entityId)) {
            stats('abstain', `hint_outside_scene:${entityId}`);
            return null;
          }
          positions.push({ entityId, containerId: hint.containerId, slotId: hint.slotId });
        }
        stats('micro');
        return { positions };
      }
      stats('micro');
      return { positions: [] };
    }
    const positions: { entityId: Id; containerId: Id; slotId: Id | null }[] = [];
    for (const entityId of moved) {
      const hint = hints.get(entityId);
      if (hint) {
        positions.push({ entityId, containerId: hint.containerId, slotId: hint.slotId });
        continue;
      }
      const own = resultFacts(request.results).find((fact) => fact.memberId === entityId);
      const destination = own ? destinationOfFact(request.state, own.text) : null;
      const name = request.state.initial.characters[entityId]?.name ?? '';
      const named = destination && name && own!.text.indexOf(name) >= 0
        && own!.text.indexOf(name) <= destination.at;
      if (!destination || !named) {
        stats('abstain', `no_destination:${entityId}`);
        return null;
      }
      positions.push({ entityId, containerId: destination.locationId, slotId: null });
    }
    stats('micro');
    return { positions };
  };
}
