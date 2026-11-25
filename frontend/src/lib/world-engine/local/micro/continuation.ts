/** Continuation micro workflow: structured events + four heads.
 *
 * novelty     the follow-up is a new event, not the same beat replayed
 * unfinished  it advances an unfinished task/interaction
 * necessity   this NPC must act now, not merely could act
 * intervene   the player should decide before it happens
 *
 * The program refuses same-world repeats and wait-only rows before scoring;
 * the heads then decide the joint continuation. A null answer means the port
 * is unavailable (no model/failure) and the caller keeps the LLM path. */
import type { Id, WorldState } from '../../types';
import type {
  MicroContinuationAnswer, MicroContinuationCandidate, MicroContinuationFn, MicroContinuationRequest,
  MicroContinuationScores,
} from '../semantics/settlement/types';
import { buildScene } from '../semantics/actions/scene';
import { behaviorCandidates, type BehaviorCandidate } from '../semantics/actions/candidates';
import { visibleCharacters } from '../prompt';
import { createBertTokenizer, type BertTokenizer } from './tokenizer';
import { createMicroRuntime } from './runtime';
import {
  buildRoundEvents, classifyRepeat, eventLines, repeatLabel, type RepeatKind,
} from './events';

export interface MicroContinuationOptions {
  vocabUrl?: string;
  modelUrl?: string;
  maxCharacters?: number;
  maxCandidatesPerCharacter?: number;
  threshold?: Partial<MicroContinuationScores>;
  /** A/B arm: execute the label rules directly instead of the four heads. */
  ruleOnly?: boolean;
  onStats?: (record: {
    candidates: number; characters: number; inferences: number; headOutputs: number;
    ms: number; loadMs: number; source: 'micro' | 'rule' | 'abstain' | 'handback'; reason?: string;
  }) => void;
  /** Test/embedded scorer; the default runs the int8 ONNX heads. */
  scoring?: (rows: Array<{ context: string; text: string }>) => Promise<MicroContinuationScores[] | null> | MicroContinuationScores[] | null;
}

interface ScoredRow {
  characterId: Id;
  candidate: BehaviorCandidate;
  scores: MicroContinuationScores;
  repeat: RepeatKind;
}

const LABELS = ['novelty', 'unfinished', 'necessity', 'intervene'] as const;

function sigmoid(value: unknown): number {
  return 1 / (1 + Math.exp(-Number(value ?? 0)));
}

/** Stable context format: keep field order identical to training. */
/** Direct execution of the label rules. This is the comparison arm: it uses
 * the same structured records and candidates as the heads, with no encoder. */
export function ruleContinuationScores(input: {
  recent: string[];
  repeat: RepeatKind;
  category: string;
  taskPending: boolean;
  involvesProtagonist: boolean;
}): MicroContinuationScores {
  const response = ['guard', 'observe', 'move', 'communicate', 'assist'];
  const taskAdvance = ['move', 'guard', 'use', 'assist', 'communicate'];
  const recent = input.recent.length > 0;
  const novelty = input.repeat === 'same_world' || input.category === 'wait'
    ? 0
    : recent || input.repeat === 'new_world'
      ? 1
      : input.taskPending && input.category !== 'observe'
        ? 1
        : input.category === 'observe' ? 0 : 1;
  const unfinished = input.category !== 'wait'
    && (input.taskPending || (recent && response.includes(input.category))) ? 1 : 0;
  const necessity = input.repeat !== 'same_world' && input.category !== 'wait'
    && ((recent && response.includes(input.category))
      || (input.taskPending && taskAdvance.includes(input.category))) ? 1 : 0;
  const intervene = input.involvesProtagonist
    && ['communicate', 'assist', 'guard', 'move', 'use'].includes(input.category) ? 1 : 0;
  return { novelty, unfinished, necessity, intervene };
}

export function continuationContext(input: {
  recent: string[];
  repeat: RepeatKind;
  category: string;
  taskPending: boolean;
  involvesProtagonist: boolean;
  actor: string;
  personality: string;
  room: string;
}): string {
  return `现场：本轮事件=${input.recent.join('；') || '无'}；重复=${repeatLabel(input.repeat)}；`
    + `任务状态=${input.taskPending ? '未完成' : '无待办'}；涉及主角=${input.involvesProtagonist ? '是' : '否'}；`
    + `类别=${input.category}；角色=${input.actor}；位置=${input.room}；个性=${input.personality.slice(0, 40)}`;
}

export function createMicroContinuation(options: MicroContinuationOptions = {}): MicroContinuationFn {
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
      session: await runtime.load(options.modelUrl ?? '/micro/continuation-heads-int8.onnx'),
    };
  }

  async function scoreDefault(rows: Array<{ context: string; text: string }>): Promise<MicroContinuationScores[] | null> {
    const { tok, session } = await ensure();
    const ort = await import('onnxruntime-web/wasm');
    const out: MicroContinuationScores[] = [];
    for (const row of rows) {
      const { ids } = tok.encodePair(row.context, row.text, 160);
      const data = BigInt64Array.from(ids, (value) => BigInt(value));
      const mask = BigInt64Array.from(ids, () => 1n);
      const result = await session.run({
        input_ids: new ort.Tensor('int64', data, [1, ids.length]),
        attention_mask: new ort.Tensor('int64', mask, [1, ids.length]),
      });
      const scores = {} as MicroContinuationScores;
      for (const label of LABELS) {
        const value = (result[label]?.data as Float32Array | undefined)?.[0];
        if (value == null) return null;
        scores[label] = sigmoid(value);
      }
      out.push(scores);
    }
    return out;
  }

  return async (request: MicroContinuationRequest): Promise<MicroContinuationAnswer | null> => {
    const started = performance.now();
    const state = request.state;
    const protagonist = state.protagonistId;
    const recent = eventLines(
      buildRoundEvents(request.roundChanges, state, request.roundProgress?.worldDigest),
      4,
    ).map((line) => line.replace(/^[^：]+：/u, ''));
    const characters = visibleCharacters(state, protagonist).filter((id) => id !== protagonist)
      .slice(0, options.maxCharacters ?? 4);
    const rows: Array<{ characterId: Id; candidate: BehaviorCandidate; context: string; repeat: RepeatKind; involvesProtagonist: boolean }> = [];
    const rejected: MicroContinuationAnswer['rejected'] = [];
    for (const characterId of characters) {
      const scene = buildScene(state, characterId, { events: recent, maxEvents: 4 });
      const candidates = behaviorCandidates(scene, state)
        .sort((left, right) => rank(left) - rank(right))
        .slice(0, options.maxCandidatesPerCharacter ?? 6);
      for (const candidate of candidates) {
        const repeat = classifyRepeat(
          { characterId, text: candidate.text },
          request.history,
          request.roundProgress?.worldDigest,
        );
        // Structured records reject the two zero-value rows before any encoder
        // run: an unchanged-world repeat and a wait are not follow-ups.
        if (repeat === 'same_world') {
          rejected.push({ characterId, text: candidate.text, reason: 'repeat_no_new_event' });
          continue;
        }
        if (candidate.category === 'wait') {
          rejected.push({ characterId, text: candidate.text, reason: 'wait_not_followup' });
          continue;
        }
        const involvesProtagonist = candidate.targetIds.includes(protagonist)
          || candidate.text.includes(scene.protagonistName);
        rows.push({
          characterId, candidate, repeat, involvesProtagonist,
          context: continuationContext({
            recent, repeat, category: candidate.category,
            taskPending: Boolean(candidate.taskId),
            involvesProtagonist,
            actor: scene.actorName,
            personality: scene.actor.personality.join('，'),
            room: scene.roomName,
          }),
        });
      }
    }
    if (!rows.length) {
      const reason = characters.length ? 'no_eligible_candidate' : 'no_visible_character';
      options.onStats?.({
        candidates: 0, characters: characters.length, inferences: 0, headOutputs: 0,
        ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs),
        source: 'handback', reason,
      });
      return { decision: 'handback', reason, source: options.ruleOnly ? 'rule' : 'micro', candidates: [], accepted: [], rejected };
    }
    let scores: MicroContinuationScores[] | null;
    try {
      scores = options.ruleOnly
        ? rows.map((row) => ruleContinuationScores({
          recent, repeat: row.repeat, category: row.candidate.category,
          taskPending: Boolean(row.candidate.taskId), involvesProtagonist: row.involvesProtagonist,
        }))
        : await (options.scoring ?? scoreDefault)(rows.map((row) => ({ context: row.context, text: row.candidate.text })));
    } catch {
      scores = null;
    }
    if (!scores || scores.length !== rows.length) {
      options.onStats?.({
        candidates: rows.length, characters: characters.length, inferences: 0, headOutputs: 0,
        ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs),
        source: 'abstain', reason: 'scorer_failed',
      });
      return null;
    }
    const threshold = {
      novelty: options.threshold?.novelty ?? 0.5,
      unfinished: options.threshold?.unfinished ?? 0.4,
      necessity: options.threshold?.necessity ?? 0.5,
      intervene: options.threshold?.intervene ?? 0.5,
    };
    const scored: ScoredRow[] = [];
    for (const [index, row] of rows.entries()) {
      // An NPC whose follow-up targets the protagonist is a player decision,
      // not an automatic beat. Keep the head score as evidence and gate it.
      const scoresForRow: MicroContinuationScores = {
        ...scores[index],
        intervene: Math.max(scores[index].intervene, row.involvesProtagonist ? 0.75 : 0),
      };
      scored.push({ characterId: row.characterId, candidate: row.candidate, scores: scoresForRow, repeat: row.repeat });
    }
    const byCharacter = new Map<Id, ScoredRow>();
    for (const row of scored) {
      const total = row.scores.novelty + row.scores.unfinished + row.scores.necessity - row.scores.intervene;
      const current = byCharacter.get(row.characterId);
      if (!current) {
        byCharacter.set(row.characterId, row);
        continue;
      }
      const currentTotal = current.scores.novelty + current.scores.unfinished + current.scores.necessity - current.scores.intervene;
      if (total > currentTotal) byCharacter.set(row.characterId, row);
    }
    const eligible = [...byCharacter.values()]
      .filter((row) => row.scores.novelty >= threshold.novelty
        && row.scores.unfinished >= threshold.unfinished
        && row.scores.necessity >= threshold.necessity
        && row.scores.intervene < threshold.intervene)
      .sort((left, right) => {
        const total = (row: ScoredRow) => row.scores.novelty + row.scores.unfinished + row.scores.necessity - row.scores.intervene;
        return total(right) - total(left);
      });
    const candidates: MicroContinuationCandidate[] = scored.map((row) => ({
      characterId: row.characterId,
      text: row.candidate.text,
      category: row.candidate.category,
      scores: row.scores,
      repeat: row.repeat,
    }));
    const accepted: MicroContinuationCandidate[] = eligible.map((row) => ({
      characterId: row.characterId,
      text: row.candidate.text,
      category: row.candidate.category,
      scores: row.scores,
      repeat: row.repeat,
    }));
    const reason = accepted.length
      ? 'novel_unfinished_necessary'
      : scored.some((row) => row.scores.intervene >= threshold.intervene)
        ? 'player_intervention'
        : 'no_necessary_followup';
    options.onStats?.({
      candidates: rows.length, characters: characters.length,
      inferences: options.ruleOnly ? 0 : rows.length,
      headOutputs: options.ruleOnly ? 0 : rows.length * LABELS.length,
      ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs),
      source: accepted.length ? (options.ruleOnly ? 'rule' : 'micro') : 'handback', reason,
    });
    return {
      decision: accepted.length ? 'continue' : 'handback',
      reason,
      source: options.ruleOnly ? 'rule' : 'micro',
      candidates,
      accepted,
      rejected,
    };
  };
}

/** Task-linked actions rank before generic room actions; wait stays last so
 * the per-character cap never scores only idle rows. */
function rank(row: BehaviorCandidate): number {
  if (row.category === 'wait') return 3;
  if (row.category === 'observe' && !row.taskId) return 2;
  return row.taskId ? 0 : 1;
}
