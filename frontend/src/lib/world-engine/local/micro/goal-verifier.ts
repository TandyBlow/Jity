/** Goal-level task verifier: MiniRBT + 2-class head trained on real turns
 * (E57). Scores whether a settled fact supports the task goal.
 *
 * Strict mode (S01/S06) accumulates condition evidence across facts and turns:
 * condition coverage is programmatic; the model judges the joined evidence of
 * all covered facts once. A task is achieved only when every decomposed
 * condition has a completed fact and the joined evidence passes the model. */
import type { Id, WorldState } from '../../types';
import { sharesGoalWording } from '../semantics/settlement/updates';
import {
  decomposeTask, strictConditionHits, taskConditionLabels, type TaskConditions,
} from './task-progress';
import { getMicroTokenizer } from './shared';
import { createMicroRuntime } from './runtime';

export interface GoalVerifierOptions {
  vocabUrl?: string;
  modelUrl?: string;
  /** p(yes) needed to treat a fact or a joined evidence set as supporting. */
  threshold?: number;
  /** Strict mode (S01): accumulate decomposed condition evidence across facts
   * and turns, then judge the joined evidence once. */
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

export interface GoalTaskLedgerSnapshot {
  version: 1;
  worldId: string;
  entries: Array<{
    taskId: Id;
    ownerId: Id;
    goal: string;
    labels: string[];
    covered: Array<{ condition: string; factId: string; factText: string }>;
  }>;
}

export interface GoalVerifierPort {
  (request: { state: WorldState; ownerIds: Id[]; facts: Array<{ id: string; memberId: Id; text: string }> }): Promise<{
    achieved: GoalAchievement[];
    scored: Array<{ characterId: Id; taskId: Id; basis: string; score: number }>;
    source: 'micro';
  } | null>;
  exportLedger(): GoalTaskLedgerSnapshot | null;
  importLedger(snapshot: unknown): void;
  resetLedger(): void;
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
  covered: Map<string, { factId: string; factText: string }>;
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

  async function score(
    rows: Array<{ goal: string; fact: string }>,
  ): Promise<number[] | null> {
    try {
      return await (options.scoring ?? scoreDefault)(rows);
    } catch {
      return null;
    }
  }

  const port = (async (request) => {
    const started = performance.now();
    const threshold = options.threshold ?? 0.5;
    const strict = options.requireProgramCoverage === true;
    if (worldId !== request.state.worldId) {
      ledger.clear();
      worldId = request.state.worldId;
    }
    const owners = new Set(request.ownerIds);

    if (strict) {
      for (const [ownerId, current] of Object.entries(request.state.characters)) {
        if (!owners.has(ownerId)) continue;
        const ownerName = request.state.initial.characters[ownerId]?.name ?? ownerId;
        for (const task of Object.values(current.tasks)) {
          if (task.status !== 'pending') {
            ledger.delete(task.id);
            continue;
          }
          const decomposed: TaskConditions = decomposeTask(task.goal, request.state, ownerName);
          const labels = taskConditionLabels(decomposed);
          if (!labels.length) continue;
          for (const fact of request.facts) {
            if (fact.memberId !== ownerId && !fact.text.includes(ownerName)) continue;
            if (!outcomeCompleted(fact.text)) continue;
            const hits = strictConditionHits(decomposed, fact.text);
            if (!hits.length) continue;
            let entry = ledger.get(task.id);
            if (!entry || entry.ownerId !== ownerId) {
              entry = { ownerId, goal: task.goal, labels, covered: new Map() };
              ledger.set(task.id, entry);
            }
            for (const label of hits) entry.covered.set(label, { factId: fact.id, factText: fact.text });
          }
        }
      }
      const pendingRows: Array<{ characterId: Id; taskId: Id; goal: string; fact: string }> = [];
      for (const [taskId, entry] of ledger) {
        const task = request.state.characters[entry.ownerId]?.tasks[taskId];
        if (!task || task.status !== 'pending') {
          ledger.delete(taskId);
          continue;
        }
        if (!entry.labels.every((label) => entry.covered.has(label))) continue;
        const texts = [...new Set(entry.labels.map((label) => entry.covered.get(label)!.factText))];
        pendingRows.push({ characterId: entry.ownerId, taskId, goal: entry.goal, fact: texts.join('；') });
      }
      if (!pendingRows.length) {
        options.onStats?.({ pairs: 0, inferred: 0, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs), source: 'micro' });
        return { achieved: [], scored: [], source: 'micro' };
      }
      const scores = await score(pendingRows.map((row) => ({ goal: row.goal, fact: row.fact })));
      if (!scores || scores.length !== pendingRows.length) {
        options.onStats?.({ pairs: pendingRows.length, inferred: 0, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs), source: 'abstain', reason: 'model_unavailable' });
        return null;
      }
      const achieved: GoalAchievement[] = [];
      const scored: Array<{ characterId: Id; taskId: Id; basis: string; score: number }> = [];
      for (const [index, row] of pendingRows.entries()) {
        const entry = ledger.get(row.taskId)!;
        const value = scores[index];
        scored.push({ characterId: row.characterId, taskId: row.taskId, basis: 'cross_turn', score: value });
        if (value < threshold) continue;
        const covered = entry.labels.map((label) => {
          const fact = entry.covered.get(label)!;
          return { condition: label, factId: fact.factId, factText: fact.factText, score: value };
        });
        const facts = new Set(covered.map((item) => item.factId));
        achieved.push({
          characterId: row.characterId,
          taskId: row.taskId,
          basis: facts.size === 1 ? [...facts][0] : 'cross_turn',
          score: value,
          covered,
        });
        ledger.delete(row.taskId);
      }
      options.onStats?.({ pairs: pendingRows.length, inferred: pendingRows.length, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs), source: 'micro' });
      return { achieved, scored, source: 'micro' };
    }

    type Row = { characterId: Id; taskId: Id; basis: string; goal: string; fact: string };
    const rows: Row[] = [];
    for (const [ownerId, current] of Object.entries(request.state.characters)) {
      if (!owners.has(ownerId)) continue;
      const ownerName = request.state.initial.characters[ownerId]?.name ?? ownerId;
      for (const task of Object.values(current.tasks)) {
        if (task.status !== 'pending') continue;
        const names = goalEntityNames(request.state, task.goal);
        for (const fact of request.facts) {
          if (fact.memberId !== ownerId && !fact.text.includes(ownerName)) continue;
          const entityHit = names.some((name) => fact.text.includes(name));
          if (!entityHit && !sharesGoalWording(fact.text, task.goal)) continue;
          rows.push({ characterId: ownerId, taskId: task.id, basis: fact.id, goal: task.goal, fact: fact.text });
        }
      }
    }
    if (!rows.length) {
      options.onStats?.({ pairs: 0, inferred: 0, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs), source: 'micro' });
      return { achieved: [], scored: [], source: 'micro' };
    }
    const scores = await score(rows.map((row) => ({ goal: row.goal, fact: row.fact })));
    if (!scores || scores.length !== rows.length) {
      options.onStats?.({ pairs: rows.length, inferred: 0, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs), source: 'abstain', reason: 'model_unavailable' });
      return null;
    }
    const scored = rows.map((row, index) => ({
      characterId: row.characterId, taskId: row.taskId, basis: row.basis, score: scores[index],
    }));
    const best = new Map<string, GoalAchievement>();
    for (const row of scored) {
      const key = `${row.characterId}:${row.taskId}`;
      const previous = best.get(key);
      if (!previous || row.score > previous.score) best.set(key, row);
    }
    const achieved = [...best.values()].filter((row) => row.score >= threshold);
    options.onStats?.({ pairs: rows.length, inferred: rows.length, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs), source: 'micro' });
    return { achieved, scored, source: 'micro' };
  }) as GoalVerifierPort;
  port.exportLedger = () => {
    if (!worldId) return null;
    return {
      version: 1,
      worldId,
      entries: [...ledger].map(([taskId, entry]) => ({
        taskId,
        ownerId: entry.ownerId,
        goal: entry.goal,
        labels: entry.labels,
        covered: [...entry.covered].map(([condition, fact]) => ({ condition, ...fact })),
      })),
    };
  };
  port.importLedger = (snapshot) => {
    port.resetLedger();
    if (!snapshot || typeof snapshot !== 'object') return;
    const value = snapshot as Partial<GoalTaskLedgerSnapshot>;
    if (value.version !== 1 || typeof value.worldId !== 'string' || !Array.isArray(value.entries)) return;
    worldId = value.worldId;
    for (const raw of value.entries) {
      if (!raw || typeof raw.taskId !== 'string' || typeof raw.ownerId !== 'string' || !Array.isArray(raw.labels)) continue;
      const covered = new Map<string, { factId: string; factText: string }>();
      for (const row of raw.covered ?? []) {
        if (row && typeof row.condition === 'string' && typeof row.factId === 'string' && typeof row.factText === 'string') {
          covered.set(row.condition, { factId: row.factId, factText: row.factText });
        }
      }
      ledger.set(raw.taskId, { ownerId: raw.ownerId, goal: raw.goal ?? '', labels: raw.labels, covered });
    }
  };
  port.resetLedger = () => {
    ledger.clear();
    worldId = null;
  };
  return port;
}
