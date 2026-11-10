/** Cross-turn non-regression review for one real play sequence.
 *
 * The four checks come from the product goal: presence, task status, item
 * knowledge and event time must never move backwards across turns. Each is
 * deterministic: it compares what the settled state says at turn N with what
 * the narration of a later turn says, and only reports a conflict when the
 * later text contradicts the earlier settled fact. Anything a machine cannot
 * decide stays `undetermined`, never `pass` by default.
 *
 * Records are shaped for the goal evidence file:
 *   groupId / turn / check / status / conflictsWithTurn / earlierQuote /
 *   currentQuote / sourceRefs / note
 */

import { splitSentences } from './review';
import { projectScene, type DatasetInput } from './scene';

export type SequenceStatus = 'pass' | 'not_applicable' | 'undetermined' | 'conflict';
export type SequenceCheck = 'presence' | 'task' | 'item_knowledge' | 'event_time';

export interface TurnRecord {
  /** Stable group id, e.g. the session id. */
  groupId: string;
  /** 1-based turn number in play order. */
  turn: number;
  input: DatasetInput;
  /** Full narration text of the turn, model prose and fallback kept separate. */
  text: string;
  /** Set when the turn text is a program fallback rather than model prose. */
  textSource?: 'model' | 'program_fallback' | 'mixed';
  /** Optional: per-segment texts, to keep model and fallback apart. */
  segments?: Array<{ kind: 'model' | 'program_fallback'; text: string }>;
}

export interface SequenceFinding {
  groupId: string;
  turn: number;
  check: SequenceCheck;
  status: SequenceStatus;
  conflictsWithTurn: number | null;
  earlierQuote: string;
  currentQuote: string;
  sourceRefs: string[];
  note: string;
}

export interface SequenceReport {
  groupId: string;
  turns: number;
  findings: SequenceFinding[];
  counts: Record<SequenceStatus, number>;
  reviewer: 'ai-independent-checker-v1';
  disclaimer: string;
}

interface SettledPerson {
  place: string | null;
  tasks: Map<string, string>;
  traits: string[];
}

function settledPeople(input: DatasetInput): Map<string, SettledPerson> {
  const projection = projectScene(input);
  const people = new Map<string, SettledPerson>();
  for (const [name, person] of Object.entries(projection.people)) {
    const tasks = new Map<string, string>();
    const raw = (input['本回合状态'] as Record<string, unknown> | undefined)?.[name] as
      | { 任务?: { 大任务?: { 目标?: string; 状态?: string }; 小任务?: Array<{ 目标?: string; 状态?: string }> } }
      | undefined;
    const block = raw?.任务;
    if (block?.大任务?.目标) tasks.set(block.大任务.目标, block.大任务.状态 ?? '未完成');
    for (const task of block?.小任务 ?? []) if (task.目标) tasks.set(task.目标, task.状态 ?? '未完成');
    if (!tasks.size) {
      const before = (input['上回合状态'] as { 人物?: Record<string, { 任务?: any }> }).人物?.[name]?.任务;
      if (before?.大任务?.目标) tasks.set(before.大任务.目标, before.大任务.状态 ?? '未完成');
      for (const task of before?.小任务 ?? []) if (task.目标) tasks.set(task.目标, task.状态 ?? '未完成');
    }
    people.set(name, { place: person.positionAfter ?? person.positionBefore ?? null, tasks, traits: person.personalityAfter });
  }
  return people;
}

const DONE_WORDS = ['已经做完', '做完了', '完成了', '办完了', '收了尾', '结了'];
const UNDONE_WORDS = ['还没做', '没做完', '尚未完成', '还没完成', '没完成', '还没办', '待办', '没来得及'];
const LEAVE_VERBS = ['离开', '走出', '出了', '离开这里', '动身', '走了'];
const KNOW_WORDS = ['不知道', '不认识', '从没见过', '第一次见', '没听说过'];
const TIME_PATTERN_CN = /([零一二三四五六七八九十两半百]+|\d+)\s*(?:分钟|分|个小时|小时)/gu;

function quote(text: string, limit = 60): string {
  const value = text.trim();
  return [...value].length > limit ? [...value].slice(0, limit).join('') + '…' : value;
}

/** Minutes stated in a text, in order of appearance, without ordinals. */
export function statedMinutes(text: string): number[] {
  const values: number[] = [];
  for (const match of text.matchAll(TIME_PATTERN_CN)) {
    const raw = match[1] ?? '';
    if (/^\d+$/u.test(raw)) {
      values.push(Number(raw));
      continue;
    }
    if (raw.includes('半')) {
      values.push(0.5);
      continue;
    }
    let value = 0;
    let current = 0;
    for (const ch of raw) {
      if (ch === '十') {
        value += (current || 1) * 10;
        current = 0;
      } else if (ch === '两') {
        current = 2;
      } else if ('零一二三四五六七八九'.includes(ch)) {
        current = '零一二三四五六七八九'.indexOf(ch);
      }
    }
    values.push(value + current);
  }
  return values;
}

export function reviewSequence(turns: TurnRecord[]): SequenceReport {
  const findings: SequenceFinding[] = [];
  const groupId = turns[0]?.groupId ?? '';
  const ordered = [...turns].sort((a, b) => a.turn - b.turn);
  const seenPeople = new Map<string, { turn: number; place: string | null; quote: string }>();
  const doneTasks = new Map<string, { turn: number; quote: string }>();
  const knownItems = new Map<string, { turn: number; quote: string }>();
  const elapsedSoFar = new Map<number, { turn: number; minutes: number }>();

  ordered.forEach((record, index) => {
    const label = `${record.groupId}#${record.turn}`;
    if (index > 0 && ordered[index - 1].turn === record.turn) {
      throw new Error(`duplicate turn ${record.turn} in ${record.groupId}`);
    }
    const projection = projectScene(record.input);
    const sentences = splitSentences(record.segments?.length ? record.segments.map((s) => s.text).join('\n') : record.text);
    const people = settledPeople(record.input);

    // ------------------------------------------------------------ presence
    for (const [name, person] of people) {
      const earlier = seenPeople.get(name);
      if (earlier && earlier.place && person.place) {
        const textNames = sentences.filter((s) => s.narration.includes(name));
        const left = textNames.find((s) => LEAVE_VERBS.some((verb) => s.narration.includes(verb))
          && !!person.place && s.narration.includes(person.place));
        // A person still settled at the earlier place who is written as having
        // left it, with no settled move between the two turns, regresses.
        const movedMeanwhile = earlier.place !== person.place;
        if (!movedMeanwhile && left) {
          findings.push({
            groupId, turn: record.turn, check: 'presence', status: 'conflict',
            conflictsWithTurn: earlier.turn,
            earlierQuote: earlier.quote, currentQuote: quote(left.text),
            sourceRefs: [`本回合状态.${name}.位置=${person.place}`, `turn ${earlier.turn} 位置=${earlier.place}`],
            note: `${name} was settled at ${earlier.place} and is still settled there, but the prose has them leaving`,
          });
        }
      }
      if (person.place) seenPeople.set(name, { turn: record.turn, place: person.place, quote: quote(`${name} 在 ${person.place}`) });
      else if (!earlier) seenPeople.set(name, { turn: record.turn, place: null, quote: name });
    }

    // ---------------------------------------------------------------- task
    for (const [name, person] of people) {
      for (const [goal, status] of person.tasks) {
        const key = `${name}::${goal}`;
        const previousDone = doneTasks.get(key);
        const textSentences = sentences.filter((s) => s.narration.includes(name) || s.narration.includes(goal));
        if (previousDone) {
          const regressed = textSentences.find((s) => UNDONE_WORDS.some((word) => s.narration.includes(word))
            && (s.narration.includes(goal) || s.narration.includes(name)));
          if (regressed) {
            findings.push({
              groupId, turn: record.turn, check: 'task', status: 'conflict',
              conflictsWithTurn: previousDone.turn, earlierQuote: previousDone.quote, currentQuote: quote(regressed.text),
              sourceRefs: [`本回合状态.${name}.任务[${goal}]=${status}`],
              note: `${name} 的任务「${goal}」此前已完成，本轮正文又写成未完成`,
            });
          }
        }
        if (status === '已完成' && !previousDone) {
          const done = textSentences.find((s) => DONE_WORDS.some((word) => s.narration.includes(word)));
          doneTasks.set(key, { turn: record.turn, quote: quote(done?.text ?? `${name} 完成 ${goal}`) });
        }
      }
    }

    // ------------------------------------------------------- item knowledge
    for (const [item, detail] of Object.entries(projection.items)) {
      const known = knownItems.get(item);
      const textSentences = sentences.filter((s) => s.narration.includes(item));
      if (known) {
        const forgotten = textSentences.find((s) => KNOW_WORDS.some((word) => s.narration.includes(word)));
        if (forgotten) {
          findings.push({
            groupId, turn: record.turn, check: 'item_knowledge', status: 'conflict',
            conflictsWithTurn: known.turn, earlierQuote: known.quote, currentQuote: quote(forgotten.text),
            sourceRefs: [`上回合状态.物品.${item}`],
            note: `${item} 在此前回合已出现，本轮正文却写成不认识/没听过`,
          });
        }
        continue;
      }
      const seen = textSentences[0];
      if (seen) knownItems.set(item, { turn: record.turn, quote: quote(seen.text) });
      else if (detail.positionAfter && detail.positionAfter !== '场景') knownItems.set(item, { turn: record.turn, quote: `${item} 在 ${detail.positionAfter}` });
    }

    // ---------------------------------------------------------- event time
    const minutes = statedMinutes(sentences.map((s) => s.text).join('\n'));
    for (const value of minutes) {
      const previous = elapsedSoFar.get(value);
      if (previous) {
        findings.push({
          groupId, turn: record.turn, check: 'event_time', status: 'conflict',
          conflictsWithTurn: previous.turn,
          earlierQuote: `${previous.minutes} 分钟已在第 ${previous.turn} 回合表达`,
          currentQuote: quote(sentences.find((s) => s.text.includes(String(value)))?.text ?? `${value} 分钟`),
          sourceRefs: [`turn ${record.turn} 时间推进=${projection.timeText ?? 'unknown'}`],
          note: `同一段耗时（${value} 分钟）在两轮里各讲一遍，时间推进被重复计算或倒退`,
        });
      } else {
        elapsedSoFar.set(value, { turn: record.turn, minutes: value });
      }
    }
    const settledMinutes = projection.minutes;
    if (settledMinutes !== null && !minutes.length) {
      findings.push({
        groupId, turn: record.turn, check: 'event_time', status: 'conflict',
        conflictsWithTurn: null, earlierQuote: '', currentQuote: '',
        sourceRefs: [`本回合变化.时间推进=${projection.timeText ?? ''}`],
        note: `本轮结算了 ${settledMinutes} 分钟，正文没有写时间推进`,
      });
    }
    if (settledMinutes === null && minutes.length) {
      findings.push({
        groupId, turn: record.turn, check: 'event_time', status: 'undetermined',
        conflictsWithTurn: null, earlierQuote: '', currentQuote: quote(sentences[0]?.text ?? ''),
        sourceRefs: ['本回合变化.时间推进 缺失'],
        note: '正文写了时间，但输入没有结算时间推进；需要读输入判断这时间从哪来',
      });
    }
  });

  const counts: Record<SequenceStatus, number> = { pass: 0, not_applicable: 0, undetermined: 0, conflict: 0 };
  for (const finding of findings) counts[finding.status] += 1;
  return {
    groupId,
    turns: ordered.length,
    findings,
    counts,
    reviewer: 'ai-independent-checker-v1',
    disclaimer: 'Automated cross-turn review only. No human read, no product acceptance. Undetermined items are not passes.',
  };
}
