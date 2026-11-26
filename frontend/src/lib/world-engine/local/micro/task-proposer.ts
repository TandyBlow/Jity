/** Condition-level task proposer. It keeps a session ledger of which task
 * conditions each settled fact supports, so several facts across turns can
 * jointly complete one task. The proposer only proposes; the existing verifier
 * remains the authority that commits an achievement. */
import type { Id, WorldState } from '../../types';
import type { MicroTaskProposal, MicroTaskProposerFn } from '../semantics/settlement/types';
import { CONFIRM, conditionRelevant, taskConditions, type TaskCondition } from './task-progress';
import { getMicroTokenizer } from './shared';
import { createMicroRuntime, runBatch } from './runtime';

const LABELS = ['none', 'keyword', 'attempt', 'satisfied'] as const;
type Label = typeof LABELS[number];
const RANK: Record<Label, number> = { none: 0, keyword: 1, attempt: 2, satisfied: 3 };
export const TASK_LEDGER_VERSION = 1 as const;

/** Serializable ledger carried inside the local game snapshot. It is not part
 * of WorldState: the world digest never depends on proposer bookkeeping. */
export interface TaskLedgerSnapshot {
  version: typeof TASK_LEDGER_VERSION;
  worldId: string;
  seenFacts: string[];
  entries: Array<{
    taskId: Id;
    ownerId: Id;
    conditions: TaskCondition[];
    status: Record<string, Label>;
    active: Record<string, boolean>;
    evidence: Record<string, { factId: string; text: string }>;
    invalidatedAt: Record<string, string | null>;
  }>;
}

export interface MicroTaskProposerPort extends MicroTaskProposerFn {
  exportLedger(): TaskLedgerSnapshot | null;
  importLedger(snapshot: unknown): void;
  resetLedger(): void;
}

interface LedgerEntry {
  ownerId: Id;
  conditions: TaskCondition[];
  status: Record<string, Label>;
  /** False only for a satisfied condition that no longer holds (item lost). */
  active: Record<string, boolean>;
  evidence: Record<string, { factId: string; text: string }>;
  invalidatedAt: Record<string, string | null>;
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
    proposed: number; invalidated?: number; ms: number; loadMs: number;
    source: 'micro' | 'abstain'; reason?: string;
  }) => void;
}

function softmax(values: number[]): number[] {
  const max = Math.max(...values);
  const exps = values.map((value) => Math.exp(value - max));
  const sum = exps.reduce((left, right) => left + right, 0);
  return exps.map((value) => value / sum);
}

export function createMicroTaskProposer(options: MicroTaskProposerOptions = {}): MicroTaskProposerPort {
  const runtime = createMicroRuntime({ threads: 1 });
  const ledger = new Map<Id, LedgerEntry>();
  const seenFacts = new Set<string>();
  let worldId: string | null = null;

  function resetLedger(): void {
    ledger.clear();
    seenFacts.clear();
    worldId = null;
  }

  /** Item conditions are continuous; everything else is historical. */
  function itemHeldBy(state: WorldState, ownerId: Id, name: string): boolean | null {
    const core = name.replace(/^.+?的/u, '');
    const ids = Object.keys(state.initial.items);
    const itemId = ids.find((id) => state.initial.items[id].name === name)
      ?? ids.find((id) => state.initial.items[id].name === core)
      ?? ids.find((id) => (state.initial.items[id].name ?? '').includes(core));
    if (!itemId) return null;
    let container: Id | null = state.items[itemId]?.position.containerId ?? null;
    const seen = new Set<Id>();
    while (container && !state.characters[container] && state.items[container] && !seen.has(container)) {
      seen.add(container);
      container = state.items[container].position.containerId;
    }
    return container === ownerId;
  }

  function refreshLifetimes(state: WorldState): void {
    const now = state.time.dateTime;
    for (const entry of ledger.values()) {
      for (const condition of entry.conditions) {
        if (condition.kind !== 'item' || entry.status[condition.id] !== 'satisfied') continue;
        const held = itemHeldBy(state, entry.ownerId, condition.value);
        if (held === null) continue;
        if (!held && entry.active[condition.id] !== false) {
          entry.active[condition.id] = false;
          entry.invalidatedAt[condition.id] = now;
        } else if (held && entry.active[condition.id] === false) {
          entry.active[condition.id] = true;
          entry.invalidatedAt[condition.id] = null;
        }
      }
    }
  }

  function exportLedger(): TaskLedgerSnapshot | null {
    if (!worldId) return null;
    return {
      version: TASK_LEDGER_VERSION,
      worldId,
      seenFacts: [...seenFacts],
      entries: [...ledger].map(([taskId, entry]) => ({
        taskId,
        ownerId: entry.ownerId,
        conditions: entry.conditions,
        status: entry.status,
        active: entry.active,
        evidence: entry.evidence,
        invalidatedAt: entry.invalidatedAt,
      })),
    };
  }

  function importLedger(snapshot: unknown): void {
    resetLedger();
    if (!snapshot || typeof snapshot !== 'object') return;
    const value = snapshot as Partial<TaskLedgerSnapshot>;
    if (value.version !== TASK_LEDGER_VERSION || typeof value.worldId !== 'string' || !Array.isArray(value.entries)) return;
    worldId = value.worldId;
    for (const key of value.seenFacts ?? []) if (typeof key === 'string') seenFacts.add(key);
    for (const raw of value.entries) {
      if (!raw || typeof raw.taskId !== 'string' || typeof raw.ownerId !== 'string' || !Array.isArray(raw.conditions)) continue;
      const status: Record<string, Label> = { ...(raw.status ?? {}) };
      const active: Record<string, boolean> = { ...(raw.active ?? {}) };
      for (const condition of raw.conditions) {
        if (!LABELS.includes(status[condition.id])) status[condition.id] = 'none';
        if (typeof active[condition.id] !== 'boolean') active[condition.id] = status[condition.id] === 'satisfied';
      }
      ledger.set(raw.taskId, {
        ownerId: raw.ownerId,
        conditions: raw.conditions,
        status,
        active,
        evidence: { ...(raw.evidence ?? {}) },
        invalidatedAt: { ...(raw.invalidatedAt ?? {}) },
      });
    }
  }

  async function score(rows: Array<{ condition: TaskCondition; goal: string; text: string }>) {
    const tok = await getMicroTokenizer(options.vocabUrl);
    const session = await runtime.load(options.modelUrl ?? '/micro/task-condition-int8.onnx');
    const encodings = rows.map((row) => tok.encodePair(`条件：${row.condition.label}`, row.text, 160).ids);
    const batches = await runBatch(session, encodings);
    if (batches.length !== rows.length) return null;
    const out: Array<{ label: Label; confidence: number }> = [];
    for (const logits of batches) {
      if (logits.length !== LABELS.length) return null;
      const probabilities = softmax(logits);
      const best = probabilities.indexOf(Math.max(...probabilities));
      out.push({ label: LABELS[best], confidence: probabilities[best] });
    }
    return out;
  }

  const port = (async (request): Promise<MicroTaskProposal | null> => {
    const started = performance.now();
    if (worldId !== null && worldId !== request.state.worldId) resetLedger();
    worldId = request.state.worldId;
    refreshLifetimes(request.state);
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
          entry = { ownerId: fact.memberId, conditions, status: {}, active: {}, evidence: {}, invalidatedAt: {} };
          for (const condition of conditions) {
            entry.status[condition.id] = 'none';
            entry.active[condition.id] = false;
            entry.invalidatedAt[condition.id] = null;
          }
          ledger.set(task.id, entry);
        }
        for (const condition of entry.conditions) {
          if (entry.status[condition.id] === 'satisfied' && entry.active[condition.id]) continue;
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
      const reactivating = label === 'satisfied' && previous === 'satisfied' && entry.active[row.condition.id] === false;
      if (!reactivating && RANK[label] <= RANK[previous]) continue;
      entry.status[row.condition.id] = label;
      if (label === 'satisfied') {
        entry.active[row.condition.id] = true;
        entry.invalidatedAt[row.condition.id] = null;
      }
      entry.evidence[row.condition.id] = { factId: row.factId, text: row.text };
      updates.push({ taskId: row.taskId, conditionId: row.condition.id, label, factId: row.factId, text: row.text });
    }
    const supports: MicroTaskProposal['supports'] = [];
    const pending: MicroTaskProposal['pending'] = [];
    for (const [taskId, entry] of ledger) {
      const owner = entry.ownerId;
      const currentTask = request.state.characters[owner]?.tasks[taskId];
      if (!currentTask || currentTask.status !== 'pending') continue;
      const live = (condition: TaskCondition) => entry.status[condition.id] === 'satisfied' && entry.active[condition.id];
      const matched = entry.conditions.filter(live).length;
      const missing = entry.conditions.filter((condition) => !live(condition))
        .map((condition) => (entry.status[condition.id] === 'satisfied' ? `${condition.label}（已失效）` : condition.label));
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
    const invalidated = [...ledger.values()].reduce((sum, entry) => sum
      + entry.conditions.filter((condition) => entry.status[condition.id] === 'satisfied' && entry.active[condition.id] === false).length, 0);
    options.onStats?.({
      facts: request.facts.length, conditions: rows.length, inferences: rows.length,
      headOutputs: rows.length, proposed: supports.length, invalidated,
      ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs),
      source: rows.length ? 'micro' : 'abstain',
    });
    return { supports, updates, pending };
  }) as MicroTaskProposerPort;
  port.exportLedger = exportLedger;
  port.importLedger = importLedger;
  port.resetLedger = resetLedger;
  return port;
}
