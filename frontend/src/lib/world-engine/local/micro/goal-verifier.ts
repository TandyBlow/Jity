/** Goal-level task verifier: MiniRBT + 2-class head trained on real turns
 * (E57). Scores whether a settled fact supports the task goal.
 *
 * Strict mode (S01/S06) accumulates condition evidence across facts and turns:
 * each decomposed condition may be satisfied by a different fact. A task is
 * achieved only when every condition has a completed fact whose model score is
 * above threshold. */
import type { Id, WorldState } from '../../types';
import { sharesGoalWording } from '../semantics/settlement/updates';
import { conditionHits, decomposeTask, taskConditionLabels, type TaskConditions } from './task-progress';
import { getMicroTokenizer } from './shared';
import { createMicroRuntime } from './runtime';

export interface GoalVerifierOptions {
  vocabUrl?: string;
  modelUrl?: string;
  /** p(yes) needed to treat a fact as supporting the goal/condition. */
  threshold?: number;
  /** Strict mode (S01): accumulate decomposed condition evidence across facts
   * and turns instead of requiring one fact to cover the whole goal. */
  requireProgramCoverage?: boolean;
  /** Test/embedded scorer; the default runs the int8 ONNX graph. */
  scoring?: (rows: Array<{ goal: string; fact: string }>) => Promise<number[] | null> | number[] | null;
  onStats?: (record: {
    pairs: number; inferred: number; ms: number; loadMs: number;
    source: 'micro' | 'abstain'; reason?: string;
  }) => void;
}

export interface GoalConditionEvidence {
  condition: string;
  factId: string;
  factText: string;
  score: number;
}

export interface GoalAchievement {
  characterId: Id;
  taskId: Id;
  basis: string;
  score: number;
  /** Present in strict mode: the condition -> fact map behind the achievement. */
  covered?: GoalConditionEvidence[];
}

export interface GoalVerifierPort {
  (request: { state: WorldState; ownerIds: Id[]; facts: Array<{ id: string; memberId: Id; text: string }> }): Promise<{
    achieved: GoalAchievement[];
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

interface LedgerEntry {
  ownerId: Id;
  goal: string;
  labels: string[];
  covered: Map<string, GoalConditionEvidence>;
}

export function createMicroGoalTasks(options: GoalVerifierOptions = {}): GoalVerifierPort {
  const runtime = createMicroRuntime({ threads: 1 });
  const ledger = new Map<Id, LedgerEntry>();
  let worldId: string | null = null;

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
    const strict = options.requireProgramCoverage === true;
    if (worldId !== request.state.worldId) {
      ledger.clear();
      worldId = request.state.worldId;
    }
    const owners = new Set(request.ownerIds);
    type Row = {
      characterId: Id; taskId: Id; basis: string; goal: string; fact: string;
      hits: string[]; labels: string[];
    };
    const rows: Row[] = [];
    for (const [ownerId, current] of Object.entries(request.state.characters)) {
      if (!owners.has(ownerId)) continue;
      const ownerName = request.state.initial.characters[ownerId]?.name ?? ownerId;
      for (const task of Object.values(current.tasks)) {
        if (task.status !== 'pending') {
          ledger.delete(task.id);
          continue;
        }
        const decomposed: TaskConditions = decomposeTask(task.goal, request.state, ownerName);
        const labels = strict ? taskConditionLabels(decomposed) : [];
        if (strict && !labels.length) continue;
        const names = goalEntityNames(request.state, task.goal);
        for (const fact of request.facts) {
          // A fact belongs to its own member; another member's fact may support
          // this task only when it names the task owner (the old reader's rule).
          if (fact.memberId !== ownerId) {
            const factOwnerName = request.state.initial.characters[ownerId]?.name ?? '';
            if (!factOwnerName || !fact.text.includes(factOwnerName)) continue;
          }
          const hits = strict ? conditionHits(decomposed, fact.text) : [];
          if (strict) {
            if (!hits.length) continue;
          } else {
            const entityHit = names.some((name) => fact.text.includes(name));
            if (!entityHit && !sharesGoalWording(fact.text, task.goal)) continue;
          }
          rows.push({ characterId: ownerId, taskId: task.id, basis: fact.id, goal: task.goal, fact: fact.text, hits, labels });
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
    const scored = rows.map((row, index) => ({
      characterId: row.characterId, taskId: row.taskId, basis: row.basis, score: scores![index],
    }));
    let achieved: GoalAchievement[] = [];
    if (strict) {
      for (const [index, row] of rows.entries()) {
        const score = scores[index];
        if (score < threshold || !outcomeCompleted(row.fact)) continue;
        let entry = ledger.get(row.taskId);
        if (!entry || entry.ownerId !== row.characterId) {
          entry = { ownerId: row.characterId, goal: row.goal, labels: row.labels, covered: new Map() };
          ledger.set(row.taskId, entry);
        }
        for (const label of row.hits) {
          const previous = entry.covered.get(label);
          if (!previous || score > previous.score) {
            entry.covered.set(label, { condition: label, factId: row.basis, factText: row.fact, score });
          }
        }
      }
      for (const [taskId, entry] of ledger) {
        const task = request.state.characters[entry.ownerId]?.tasks[taskId];
        if (!task || task.status !== 'pending') {
          ledger.delete(taskId);
          continue;
        }
        if (!entry.labels.length || !entry.labels.every((label) => entry.covered.has(label))) continue;
        const covered = entry.labels.map((label) => entry.covered.get(label)!);
        const facts = new Set(covered.map((row) => row.factId));
        achieved.push({
          characterId: entry.ownerId,
          taskId,
          basis: facts.size === 1 ? covered[0].factId : 'cross_turn',
          score: Math.min(...covered.map((row) => row.score)),
          covered,
        });
        ledger.delete(taskId);
      }
    } else {
      const best = new Map<string, GoalAchievement>();
      for (const row of scored) {
        const key = `${row.characterId}:${row.taskId}`;
        const previous = best.get(key);
        if (!previous || row.score > previous.score) best.set(key, row);
      }
      achieved = [...best.values()].filter((row) => row.score >= threshold);
    }
    options.onStats?.({ pairs: rows.length, inferred: rows.length, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs), source: 'micro' });
    return { achieved, scored, source: 'micro' };
  };
}
