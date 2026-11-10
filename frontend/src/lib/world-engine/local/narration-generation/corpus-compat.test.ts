/** Manual compatibility check: run the narration verifier over the authored
 * short-scene corpus (lane 01). The corpus is the human gold for the training
 * route; if this verifier rejects it, the model will be rejected for writing
 * in the very style it was trained on.
 *
 * Skipped by default. Run:
 *   NARRATION_CORPUS=.../rows.jsonl \
 *   NARRATION_CORPUS_REPORT=.../corpus-compat-02.json \
 *   npx vitest run src/lib/world-engine/local/narration-generation/corpus-compat.test.ts
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { describe, expect, test } from 'vitest';
import type { CommittedNarration, NarrationFact } from '../../runtime/committed-narration';
import type { TimeAdvance } from '../../types';
import { buildLedger } from './ledger';
import type { NarrationPolicy } from './types';
import { verifyNarration } from './verify';

interface CorpusInput {
  上回合状态?: { 人物?: Record<string, Record<string, unknown>>; 地点?: Record<string, unknown>; 物品?: Record<string, unknown> };
  本回合变化?: { 变化?: Record<string, Record<string, unknown>>; 时间推进?: string };
  本回合状态?: Record<string, Record<string, unknown>>;
  视角?: string;
}
interface CorpusRow {
  id: string;
  targetText: string;
  input: CorpusInput;
  requiredFacts: Array<Record<string, unknown>>;
  knowledgeBoundary?: { viewpoint?: string };
  licensedDetails?: string[];
}

const corpusPath = process.env.NARRATION_CORPUS;
const reportPath = process.env.NARRATION_CORPUS_REPORT;

const EVENT_VERBS = ['推开', '踢开', '踹开', '冲进', '冲出', '奔跑', '跑向', '攻击', '开枪', '拔出',
  '举起', '捡起', '拾起', '递给', '塞进', '敲门', '打开', '关上', '锁上', '躲到', '藏在', '翻过',
  '爬上', '跳下', '喊住', '大叫', '大喊', '呼喊', '点燃', '砸碎', '撕开', '取出', '拿出', '握住',
  '攥住', '松开', '放下', '抬起', '低头', '转身', '走到', '走向', '走进', '走出', '站起', '坐下',
  '停下', '点头', '摇头', '蹭', '擦', '翻', '看', '听', '写', '签', '撕', '折', '按', '拉'];

const namesOf = (input: CorpusInput): string[] => {
  const names = new Set<string>();
  for (const section of [input.上回合状态?.人物, input.本回合状态]) {
    for (const name of Object.keys(section ?? {})) names.add(name);
  }
  for (const location of Object.keys(input.上回合状态?.地点 ?? {})) names.add(location);
  for (const item of Object.keys(input.上回合状态?.物品 ?? {})) names.add(item);
  return [...names];
};

const positionsOf = (input: CorpusInput): { name: string; location: string }[] => {
  const before = input.上回合状态?.人物 ?? {};
  const delta = input.本回合状态 ?? {};
  const names = new Set([...Object.keys(before), ...Object.keys(delta)]);
  const positions: { name: string; location: string }[] = [];
  for (const name of names) {
    const location = { ...(before[name] ?? {}), ...(delta[name] ?? {}) }['位置'];
    if (typeof location === 'string') positions.push({ name, location });
  }
  return positions;
};

const timeOf = (input: CorpusInput): TimeAdvance | null => {
  const raw = input.本回合变化?.时间推进;
  const match = typeof raw === 'string' ? /^(\d+)\s*分钟$/u.exec(raw) : null;
  return match ? { boundary: 'elapsed', duration: { amount: Number(match[1]), unit: 'minute' } } : null;
};

const factFor = (row: CorpusRow, raw: Record<string, unknown>, index: number): NarrationFact | null => {
  const viewpoint = row.knowledgeBoundary?.viewpoint ?? namesOf(row.input)[0] ?? '主角';
  const entity = typeof raw.entity === 'string' ? raw.entity
    : typeof raw.actor === 'string' ? raw.actor
      : typeof raw.owner === 'string' ? raw.owner : viewpoint;
  const id = `corpus:${row.id}:${index}`;
  switch (raw.kind) {
    case 'task_completed':
    case 'task_complete': {
      const goal = typeof raw.task === 'string' ? raw.task : raw.goal;
      if (typeof goal !== 'string') return null;
      return { id, actorId: entity, name: entity, kind: 'task_achieved', taskId: `task:${index}`, goal };
    }
    case 'personality_change':
    case 'personality_added': {
      const text = typeof raw.text === 'string' ? raw.text
        : Array.isArray(raw.add) ? raw.add.filter((entry): entry is string => typeof entry === 'string').join('；')
          : typeof raw.add === 'string' ? raw.add : null;
      if (!text) return null;
      return { id, actorId: entity, name: entity, kind: 'personality_changed', changeId: `chg:${index}`, text };
    }
    case 'sanity':
    case 'sanity_change':
      if (typeof raw.from !== 'number' || typeof raw.to !== 'number') return null;
      return { id, actorId: entity, name: entity, kind: 'sanity_changed', from: raw.from, to: raw.to };
    case 'movement':
    case 'moved': {
      const from = typeof raw.from === 'string' ? raw.from : typeof raw.fromLocation === 'string' ? raw.fromLocation : null;
      const to = typeof raw.to === 'string' ? raw.to : typeof raw.toLocation === 'string' ? raw.toLocation : null;
      if (!from || !to) return null;
      return { id, actorId: entity, name: entity, kind: 'moved', fromId: `loc:${from}`, from, toId: `loc:${to}`, to };
    }
    default:
      return null;
  }
};

const packetFor = (row: CorpusRow): CommittedNarration => {
  const facts: NarrationFact[] = [];
  const seen = new Set<string>();
  const before = row.input.上回合状态?.人物 ?? {};
  const delta = row.input.本回合状态 ?? {};
  const names = new Set([...Object.keys(before), ...Object.keys(delta)]);
  const changedSanity = new Set(row.requiredFacts
    .filter((raw) => (raw.kind === 'sanity' || raw.kind === 'sanity_change') && typeof raw.from === 'number')
    .map((raw) => (typeof raw.entity === 'string' ? raw.entity
      : typeof raw.actor === 'string' ? raw.actor
        : typeof raw.owner === 'string' ? raw.owner : '')).filter(Boolean));
  for (const name of names) {
    const value = { ...(before[name] ?? {}), ...(delta[name] ?? {}) };
    const location = value['位置'];
    if (typeof location === 'string' && !seen.has(`${name}:at`)) {
      seen.add(`${name}:at`);
      facts.push({ id: `corpus:${row.id}:at:${name}`, actorId: name, name, kind: 'at', locationId: `loc:${location}`, location });
    }
    const sanity = value['精神值'];
    if (typeof sanity === 'number' && !changedSanity.has(name)) {
      facts.push({ id: `corpus:${row.id}:sanity:${name}`, actorId: name, name, kind: 'sanity', value: sanity });
    }
  }
  row.requiredFacts.forEach((raw, index) => {
    const fact = factFor(row, raw, index);
    if (fact) facts.push(fact);
  });
  return {
    anchor: { worldId: 'corpus', pointId: row.id, version: 0, stateDigest: row.id, previousPointId: null },
    facts,
  };
};

const policyFor = (row: CorpusRow): NarrationPolicy => {
  const viewpoint = row.knowledgeBoundary?.viewpoint ?? namesOf(row.input)[0] ?? '主角';
  const licensedJson = JSON.stringify(row.input);
  return {
    viewpoint: { name: viewpoint },
    roster: [...new Set([...Object.keys(row.input.上回合状态?.人物 ?? {}), ...Object.keys(row.input.本回合状态 ?? {})])],
    locations: Object.keys(row.input.上回合状态?.地点 ?? {}),
    knownPositions: positionsOf(row.input),
    knownEntities: namesOf(row.input),
    visibleEntities: [...Object.keys(row.input.上回合状态?.物品 ?? {}), ...Object.keys(row.input.本回合状态 ?? {}).flatMap((name) => {
      const appearance = row.input.本回合状态?.[name]?.['外貌'];
      return Array.isArray(appearance) ? appearance.filter((entry): entry is string => typeof entry === 'string') : [];
    })],
    licensedEvents: EVENT_VERBS.filter((verb) => licensedJson.includes(verb)),
    time: timeOf(row.input),
    minChars: 60,
    targetChars: 160,
    maxAttempts: 1,
  };
};

describe.skipIf(!corpusPath)('authored short-scene corpus compatibility', () => {
  test('the verifier does not reject the human gold', () => {
    const rows = readFileSync(corpusPath!, 'utf8').split(/\r?\n/u).filter(Boolean).map((line) => JSON.parse(line) as CorpusRow);
    const failures: Array<{ id: string; hard: Array<{ kind: string; detail: string; sentence?: string }>; text: string }> = [];
    const softByKind: Record<string, number> = {};
    for (const row of rows) {
      const committed = packetFor(row);
      const policy = policyFor(row);
      const ledger = buildLedger(committed, JSON.stringify(row.input), null, policy);
      const result = verifyNarration({
        text: row.targetText, finishReason: 'stop', committed, ledger, policy,
        priorText: null, attempt: 0, promptEchoMarkers: [],
      });
      for (const issue of result.issues) {
        if (issue.severity === 'soft') softByKind[issue.kind] = (softByKind[issue.kind] ?? 0) + 1;
      }
      const hard = result.issues.filter((issue) => issue.severity === 'hard');
      if (hard.length) failures.push({ id: row.id, hard, text: row.targetText });
    }
    const report = {
      corpus: corpusPath,
      rows: rows.length,
      hardFailures: failures.length,
      softByKind,
      failures,
    };
    if (reportPath) writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
    // A human gold failure is a verifier defect to inspect, not a corpus verdict.
    expect(failures, JSON.stringify(failures.slice(0, 3), null, 2)).toHaveLength(0);
  }, 120_000);
});
