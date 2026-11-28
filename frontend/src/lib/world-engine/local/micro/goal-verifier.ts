/** Goal-level task verifier: MiniRBT + 2-class head trained on real turns
 * (E57). Scores whether a settled fact completes the task goal. */
import type { Id, WorldState } from '../../types';
import { sharesGoalWording } from '../semantics/settlement/updates';
import { conditionCoverage, decomposeTask } from './task-progress';
import { getMicroTokenizer } from './shared';
import { createMicroRuntime } from './runtime';

export interface GoalVerifierOptions {
  vocabUrl?: string;
  modelUrl?: string;
  /** p(yes) needed to treat a fact as completing the goal. */
  threshold?: number;
  /** Strict mode (S01): the decomposed goal conditions must all be covered and
   * the fact outcome completed before the model is asked. */
  requireProgramCoverage?: boolean;
  /** Test/embedded scorer; the default runs the int8 ONNX graph. */
  scoring?: (rows: Array<{ goal: string; fact: string }>) => Promise<number[] | null> | number[] | null;
  onStats?: (record: {
    pairs: number; inferred: number; ms: number; loadMs: number;
    source: 'micro' | 'abstain'; reason?: string;
  }) => void;
}

export interface GoalVerifierPort {
  (request: { state: WorldState; ownerIds: Id[]; facts: Array<{ id: string; memberId: Id; text: string }> }): Promise<{
    achieved: Array<{ characterId: Id; taskId: Id; basis: string; score: number }>;
    scored: Array<{ characterId: Id; taskId: Id; basis: string; score: number }>;
    source: 'micro';
  } | null>;
}

function softmax(values: number[]): number[] {
  const max = Math.max(...values);
  const exps = values.map((value) => Math.exp(value - max));
  const sum = exps.reduce((left, right) => left + right, 0);
  return exps.map((value) => value / sum);
}

/** Names the goal is about. A fact that mentions one of them is a candidate
 * even when the sentence-level wording overlap is low ("检查了护目镜" vs
 * "把护目镜戴好并确认镜片"). */
function goalEntityNames(state: WorldState, goal: string): string[] {
  const names: string[] = [];
  for (const group of [state.initial.characters, state.initial.items, state.initial.locations]) {
    for (const entity of Object.values(group ?? {})) {
      const name = (entity as { name?: string }).name ?? '';
      const core = name.split('的').pop() ?? '';
      if (name && goal.includes(name)) names.push(name);
      if (core && core.length >= 2 && core !== name && goal.includes(core)) names.push(core);
    }
  }
  return names;
}

/** A strict reading of the result marker: only «达到目的» counts as completed;
 * partial, blocked, failed and no-change never complete a task (S01). */
function outcomeCompleted(text: string): boolean {
  return text.includes('达到目的') && !/只完成一部分|没有成功|被阻止|没有变化/u.test(text);
}

function programCovered(state: WorldState, ownerName: string, goal: string, fact: string): boolean {
  const conditions = decomposeTask(goal, state, ownerName);
  const coverage = conditionCoverage(conditions, fact);
  return coverage.total > 0 && coverage.matched === coverage.total && outcomeCompleted(fact);
}

export function createMicroGoalTasks(options: GoalVerifierOptions = {}): GoalVerifierPort {
  const runtime = createMicroRuntime({ threads: 1 });
  async function scoreDefault(rows: Array<{ goal: string; fact: string }>): Promise<number[] | null> {
    const tok = await getMicroTokenizer(options.vocabUrl);
    const session = await runtime.load(options.modelUrl ?? '/micro/goal-verifier-v1-int8.onnx');
    const ort = await import('onnxruntime-web/wasm');
    const out: number[] = [];
    for (const row of rows) {
      const ids = tok.encode(`${row.goal} ␟ ${row.fact}`, 192);
      const data = BigInt64Array.from(ids, (value) => BigInt(value));
      const mask = BigInt64Array.from(ids, () => 1n);
      const result = await session.run({
        input_ids: new ort.Tensor('int64', data, [1, ids.length]),
        attention_mask: new ort.Tensor('int64', mask, [1, ids.length]),
      });
      const logits = Array.from((result.logits?.data ?? []) as Float32Array);
      if (logits.length !== 2) return null;
      out.push(softmax(logits)[1]);
    }
    return out;
  }

  return async (request) => {
    const started = performance.now();
    const threshold = options.threshold ?? 0.5;
    const owners = new Set(request.ownerIds);
    const rows: Array<{ characterId: Id; taskId: Id; basis: string; goal: string; fact: string }> = [];
    for (const [ownerId, current] of Object.entries(request.state.characters)) {
      if (!owners.has(ownerId)) continue;
      const ownerName = request.state.initial.characters[ownerId]?.name ?? ownerId;
      for (const task of Object.values(current.tasks)) {
        if (task.status !== 'pending') continue;
        const names = goalEntityNames(request.state, task.goal);
        for (const fact of request.facts) {
          // A fact belongs to its own member; another member's fact may support
          // this task only when it names the task owner (the old reader's rule).
          if (fact.memberId !== ownerId) {
            const factOwnerName = request.state.initial.characters[ownerId]?.name ?? '';
            if (!factOwnerName || !fact.text.includes(factOwnerName)) continue;
          }
          const entityHit = names.some((name) => fact.text.includes(name));
          if (!entityHit && !sharesGoalWording(fact.text, task.goal)) continue;
          if (options.requireProgramCoverage && !programCovered(request.state, ownerName, task.goal, fact.text)) continue;
          rows.push({ characterId: ownerId, taskId: task.id, basis: fact.id, goal: task.goal, fact: fact.text });
        }
      }
    }
    if (!rows.length) {
      options.onStats?.({ pairs: 0, inferred: 0, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs), source: 'micro' });
      return { achieved: [], scored: [], source: 'micro' };
    }
    let scores: number[] | null;
    try {
      scores = await (options.scoring ?? scoreDefault)(rows.map((row) => ({ goal: row.goal, fact: row.fact })));
    } catch {
      scores = null;
    }
    if (!scores || scores.length !== rows.length) {
      options.onStats?.({ pairs: rows.length, inferred: 0, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs), source: 'abstain', reason: 'model_unavailable' });
      return null;
    }
    const scored = rows.map((row, index) => ({ characterId: row.characterId, taskId: row.taskId, basis: row.basis, score: scores![index] }));
    const best = new Map<string, { characterId: Id; taskId: Id; basis: string; score: number }>();
    for (const row of scored) {
      const key = `${row.characterId}:${row.taskId}`;
      const previous = best.get(key);
      if (!previous || row.score > previous.score) best.set(key, row);
    }
    const achieved = [...best.values()].filter((row) => row.score >= threshold);
    options.onStats?.({ pairs: rows.length, inferred: rows.length, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs), source: 'micro' });
    return { achieved, scored, source: 'micro' };
  };
}
