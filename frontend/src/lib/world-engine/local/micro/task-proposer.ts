/** Condition-level task proposer. It keeps a session ledger of which task
 * conditions each settled fact supports, so several facts across turns can
 * jointly complete one task. The proposer only proposes; the existing verifier
 * remains the authority that commits an achievement. */
import type { Id } from '../../types';
import type { MicroTaskProposal, MicroTaskProposerFn } from '../semantics/settlement/types';
import { CONFIRM, conditionRelevant, taskConditions, type TaskCondition } from './task-progress';
import { getMicroTokenizer } from './shared';
import { createMicroRuntime } from './runtime';

const LABELS = ['none', 'keyword', 'attempt', 'satisfied'] as const;
type Label = typeof LABELS[number];
const RANK: Record<Label, number> = { none: 0, keyword: 1, attempt: 2, satisfied: 3 };

interface LedgerEntry {
  conditions: TaskCondition[];
  status: Record<string, Label>;
  evidence: Record<string, { factId: string; text: string }>;
}

/** A satisfied label still needs the condition's own evidence: the action verb,
 * or a confirmation of an entity the task actually names. Cross-turn evidence
 * may supply the named entity (goggles) but never a different task's target. */
function satisfiesProgramFloor(condition: TaskCondition, text: string, entry: LedgerEntry): boolean {
  if (condition.kind === 'action') return text.includes(condition.value) || text.includes(condition.value[0]);
  if (condition.kind === 'confirmation') {
    if (!CONFIRM.some((word) => text.includes(word))) return false;
    const anchors = entry.conditions.filter((row) => row.kind === 'item' || row.kind === 'target' || row.kind === 'location');
    if (!anchors.length) return false;
    const basis = [text, ...Object.values(entry.evidence).map((row) => row.text)].join('；');
    return anchors.some((row) => basis.includes(row.kind === 'item' ? row.value.replace(/^.+?的/u, '') : row.value));
  }
  return true;
}

export interface MicroTaskProposerOptions {
  vocabUrl?: string;
  modelUrl?: string;
  threshold?: { satisfied?: number; attempt?: number; keyword?: number };
  /** Test/embedded scorer; the default runs the int8 condition model. */
  scoring?: (rows: Array<{ condition: TaskCondition; goal: string; text: string }>) => Promise<Array<{ label: Label; confidence: number }> | null> | Array<{ label: Label; confidence: number }> | null;
  onStats?: (record: {
    facts: number; conditions: number; inferences: number; headOutputs: number;
    proposed: number; ms: number; loadMs: number; source: 'micro' | 'abstain'; reason?: string;
  }) => void;
}

function softmax(values: number[]): number[] {
  const max = Math.max(...values);
  const exps = values.map((value) => Math.exp(value - max));
  const sum = exps.reduce((left, right) => left + right, 0);
  return exps.map((value) => value / sum);
}

export function createMicroTaskProposer(options: MicroTaskProposerOptions = {}): MicroTaskProposerFn {
  const runtime = createMicroRuntime({ threads: 1 });
  const ledger = new Map<Id, LedgerEntry>();
  const seenFacts = new Set<string>();
  let worldId: string | null = null;

  async function score(rows: Array<{ condition: TaskCondition; goal: string; text: string }>) {
    const tok = await getMicroTokenizer(options.vocabUrl);
    const session = await runtime.load(options.modelUrl ?? '/micro/task-condition-int8.onnx');
    const ort = await import('onnxruntime-web/wasm');
    const out: Array<{ label: Label; confidence: number }> = [];
    for (const row of rows) {
      const { ids } = tok.encodePair(`条件：${row.condition.label}`, row.text, 160);
      const data = BigInt64Array.from(ids, (value) => BigInt(value));
      const mask = BigInt64Array.from(ids, () => 1n);
      const result = await session.run({
        input_ids: new ort.Tensor('int64', data, [1, ids.length]),
        attention_mask: new ort.Tensor('int64', mask, [1, ids.length]),
      });
      const logits = Array.from((result.labels?.data ?? []) as Float32Array);
      if (logits.length !== LABELS.length) return null;
      const probabilities = softmax(logits);
      const best = probabilities.indexOf(Math.max(...probabilities));
      out.push({ label: LABELS[best], confidence: probabilities[best] });
    }
    return out;
  }

  return async (request): Promise<MicroTaskProposal | null> => {
    const started = performance.now();
    if (worldId !== null && worldId !== request.state.worldId) {
      ledger.clear();
      seenFacts.clear();
    }
    worldId = request.state.worldId;
    const threshold = {
      satisfied: options.threshold?.satisfied ?? 0.6,
      attempt: options.threshold?.attempt ?? 0.55,
      keyword: options.threshold?.keyword ?? 0.5,
    };
    const rows: Array<{ condition: TaskCondition; factId: string; text: string; taskId: Id; goal: string }> = [];
    for (const fact of request.facts) {
      const key = `${fact.memberId}:${fact.text}`;
      if (seenFacts.has(key)) continue;
      seenFacts.add(key);
      const current = request.state.characters[fact.memberId];
      const initial = request.state.initial.characters[fact.memberId];
      if (!current || !initial) continue;
      for (const task of Object.values(current.tasks)) {
        if (task.status !== 'pending') continue;
        let entry = ledger.get(task.id);
        if (!entry) {
          const conditions = taskConditions(task.goal, request.state, initial.name);
          if (!conditions.length) continue;
          entry = { conditions, status: {}, evidence: {} };
          for (const condition of conditions) entry.status[condition.id] = 'none';
          ledger.set(task.id, entry);
        }
        for (const condition of entry.conditions) {
          if (entry.status[condition.id] === 'satisfied') continue;
          if (!conditionRelevant(condition, fact.text)) continue;
          rows.push({ condition, factId: fact.id, text: fact.text, taskId: task.id, goal: task.goal });
        }
      }
    }
    let scores: Array<{ label: Label; confidence: number }> | null = null;
    if (rows.length) {
      try {
        scores = await (options.scoring ?? score)(rows);
      } catch {
        scores = null;
      }
    }
    if (rows.length && (!scores || scores.length !== rows.length)) {
      options.onStats?.({
        facts: request.facts.length, conditions: rows.length, inferences: 0, headOutputs: 0,
        proposed: 0, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs),
        source: 'abstain', reason: 'model_unavailable',
      });
      return null;
    }
    const updates: MicroTaskProposal['updates'] = [];
    for (const [index, row] of rows.entries()) {
      const scored = scores![index];
      const entry = ledger.get(row.taskId);
      if (!entry) continue;
      let label = scored.label;
      if (label === 'satisfied' && !satisfiesProgramFloor(row.condition, row.text, entry)) {
        label = row.condition.kind === 'confirmation' ? 'keyword' : 'attempt';
      }
      const minimum = label === 'satisfied' ? threshold.satisfied
        : label === 'attempt' ? threshold.attempt
          : label === 'keyword' ? threshold.keyword : 1;
      if (scored.confidence < minimum) continue;
      const previous = entry.status[row.condition.id];
      if (RANK[label] <= RANK[previous]) continue;
      entry.status[row.condition.id] = label;
      entry.evidence[row.condition.id] = { factId: row.factId, text: row.text };
      updates.push({ taskId: row.taskId, conditionId: row.condition.id, label, factId: row.factId, text: row.text });
    }
    const supports: MicroTaskProposal['supports'] = [];
    const pending: MicroTaskProposal['pending'] = [];
    for (const [taskId, entry] of ledger) {
      const owner = Object.entries(request.state.characters).find(([, row]) => row.tasks[taskId])?.[0];
      if (!owner) continue;
      const currentTask = request.state.characters[owner]?.tasks[taskId];
      if (!currentTask || currentTask.status !== 'pending') continue;
      const matched = entry.conditions.filter((condition) => entry.status[condition.id] === 'satisfied').length;
      const missing = entry.conditions.filter((condition) => entry.status[condition.id] !== 'satisfied').map((condition) => condition.label);
      pending.push({ taskId, matched, total: entry.conditions.length, missing });
      if (matched === entry.conditions.length) {
        const evidence = entry.conditions.map((condition) => entry.evidence[condition.id]).filter(Boolean);
        const texts = [...new Set(evidence.map((row) => row.text))];
        supports.push({
          characterId: owner, taskId, basis: 'cross_turn',
          basisText: texts.join('；'),
          conditions: entry.conditions.map((condition) => ({ label: condition.label, state: entry.status[condition.id] })),
        });
      }
    }
    options.onStats?.({
      facts: request.facts.length, conditions: rows.length, inferences: rows.length,
      headOutputs: rows.length, proposed: supports.length,
      ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs),
      source: rows.length ? 'micro' : 'abstain',
    });
    return { supports, updates, pending };
  };
}
