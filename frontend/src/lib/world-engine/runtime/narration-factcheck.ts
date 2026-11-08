/** Independent fact check for the narration model experiment (not the page gate).
 *
 * It answers a narrower question than the alignment grader: are ALL committed
 * facts present, attributed to their owner, with exact frozen text and no extra
 * claims? It is deliberately stricter (a move needs both endpoints, task and
 * description text must be verbatim) and is written separately from
 * `narration-alignment.ts` so the experiment does not grade itself with the
 * instrument that also decides adoption.
 *
 * This module is experiment code. It is not wired into the page.
 */
import type { TimeAdvance } from '../types';
import type { NarrationFact } from './committed-narration';

export type FactCheckKind = 'missing' | 'actor' | 'number' | 'direction' | 'frozen_text' | 'added' | 'time' | 'empty';
export interface FactCheckProblem {
  kind: FactCheckKind;
  detail: string;
  factId?: string;
  sentence?: string;
}
export interface FactCheckResult { ok: boolean; problems: FactCheckProblem[]; covered: string[] }
export interface FactCheckInput {
  facts: readonly NarrationFact[];
  time: { amount: number; unit: TimeAdvance['duration']['unit'] } | null;
  locations: readonly string[];
  roster: readonly string[];
}

const UNIT_WORDS: Record<TimeAdvance['duration']['unit'], string[]> = {
  second: ['秒'], minute: ['分钟'], hour: ['小时'], day: ['天', '日'], month: ['个月'], year: ['年'],
};
const CN_DIGITS = ['零', '一', '二', '两', '三', '四', '五', '六', '七', '八', '九', '十'];
const cnNumber = (value: number): string | null => {
  if (!Number.isSafeInteger(value) || value < 0 || value > 10) return null;
  return CN_DIGITS[value];
};
const hasValue = (text: string, value: number): boolean => {
  const arabic = new RegExp(`(?<![0-9])${value}(?![0-9])`, 'u');
  const chinese = cnNumber(value);
  return arabic.test(text) || (chinese !== null && text.includes(chinese));
};
const maskQuotes = (text: string): string => text.replace(/「[^」]*」/g, '「」');
const hasAnyNumber = (text: string): boolean =>
  /(?<![0-9])[0-9]+(?![0-9])/u.test(text) || /[零一二两三四五六七八九十]/u.test(text);

const sentences = (text: string): string[] => text.split(/[。！？\n]+/).map((part) => part.trim()).filter(Boolean);
const clauses = (sentence: string): string[] => sentence.split(/[，,；;]/).map((part) => part.trim()).filter(Boolean);
const EVENT_VERBS = ['推开', '踢开', '踹开', '冲进', '冲出', '奔跑', '跑向', '攻击', '开枪', '拔出', '举起',
  '捡起', '拾起', '递给', '塞进', '敲门', '打开', '关上', '锁上', '躲到', '藏在', '翻过', '爬上', '跳下',
  '喊住', '大叫', '大喊', '呼喊', '点燃', '砸碎', '撕开', '停下'];
const MOVEMENT_VERBS = ['走到', '走向', '来到', '走进', '进入', '赶往', '前往', '抵达', '离开', '跑向', '奔向'];
const UNLICENSED_PHRASES = ['准备', '打算', '想要', '决定', '因为', '所以', '为了', '于是', '与事实', '完全一致'];

/** Attribute each clause to the actor it names; a clause without a name keeps
 * the previous actor. A clause naming two actors is attributed to both. */
function scopesByActor(text: string, roster: readonly string[]): Map<string, string[]> {
  const scopes = new Map<string, string[]>();
  for (const sentence of sentences(text)) {
    let current: string | null = null;
    for (const clause of clauses(sentence)) {
      const named = roster.filter((name) => maskQuotes(clause).includes(name));
      if (named.length === 1) current = named[0];
      const targets = named.length ? named : current ? [current] : [];
      for (const name of targets) {
        const list = scopes.get(name) ?? [];
        list.push(clause);
        scopes.set(name, list);
      }
    }
  }
  return scopes;
}

function direction(text: string, from: number, to: number): 'forward' | 'reverse' | null {
  const at = (value: number): number => {
    const arabic = new RegExp(`(?<![0-9])${value}(?![0-9])`, 'u').exec(text);
    const chinese = cnNumber(value);
    const chineseAt = chinese ? text.indexOf(chinese) : -1;
    if (arabic && (chineseAt < 0 || arabic.index < chineseAt)) return arabic.index;
    return chineseAt;
  };
  const fromAt = at(from), toAt = at(to);
  if (fromAt < 0 || toAt < 0 || fromAt === toAt) return null;
  const source = /(?:从|由|自|原来|原本|此前|之前|先前)(?:有|是|为)?的?\s*$/u;
  const target = /(?:(?:降|升|变|下降|上升)?(?:到|至|为|成)了?)\s*$/u;
  const sourceAt = source.test(text.slice(0, fromAt)) ? fromAt : source.test(text.slice(0, toAt)) ? toAt : null;
  const targetAt = target.test(text.slice(0, toAt)) ? toAt : target.test(text.slice(0, fromAt)) ? fromAt : null;
  if (sourceAt !== null && targetAt !== null) {
    const sourceValue = sourceAt === fromAt ? from : to;
    const targetValue = targetAt === toAt ? to : from;
    return sourceValue === from && targetValue === to ? 'forward' : 'reverse';
  }
  return fromAt < toAt ? 'forward' : 'reverse';
}

/** Does the actor's own scope carry this fact exactly? */
function factInScope(fact: NarrationFact, scope: string): { ok: true } | { ok: false; kind: FactCheckProblem['kind']; detail: string } {
  switch (fact.kind) {
    case 'at':
      return scope.includes(fact.location) ? { ok: true } : { ok: false, kind: 'missing', detail: `位置 ${fact.location} 未出现` };
    case 'moved': {
      const fromAt = scope.indexOf(fact.from), toAt = scope.indexOf(fact.to);
      if (fromAt < 0 || toAt < 0) return { ok: false, kind: 'missing', detail: `移动需要两个端点 ${fact.from}→${fact.to}（现：${fromAt < 0 ? '缺起点' : ''}${toAt < 0 ? '缺终点' : ''}）` };
      // 终点写在前面时，只有“从/由/离开”标记仍指向起点才不算颠倒（“到达门厅，从走廊来”）。
      const sourceMarked = /(?:从|由|自|离开)\s*$/u.test(scope.slice(0, fromAt));
      if (fromAt > toAt && !sourceMarked) return { ok: false, kind: 'direction', detail: `方向颠倒：先写 ${fact.to} 后写 ${fact.from}` };
      return { ok: true };
    }
    case 'sanity':
      if (!hasValue(scope, fact.value)) return hasAnyNumber(scope)
        ? { ok: false, kind: 'number', detail: `精神值 ${fact.value} 未出现（句中有其他数字）` }
        : { ok: false, kind: 'missing', detail: `精神值 ${fact.value} 未出现` };
      // 站定值不是变化：本点没有 sanity_changed 事实，写“降至/升到”就是新增变化。
      if (/(?:降|升|减|增|恢复|回落|涨)(?:到|至|为|了)|变为|变成|变到/u.test(scope)) {
        return { ok: false, kind: 'added', detail: `本点精神值是站定值 ${fact.value}，被写成了变化` };
      }
      return { ok: true };
    case 'sanity_changed': {
      const dir = direction(scope, fact.from, fact.to);
      if (dir === null) return { ok: false, kind: 'missing', detail: `变化需要两个数值 ${fact.from}→${fact.to}` };
      if (dir === 'reverse') return { ok: false, kind: 'direction', detail: `方向颠倒：应为 ${fact.from}→${fact.to}` };
      return { ok: true };
    }
    case 'task_achieved':
      return scope.includes(fact.goal) ? { ok: true } : { ok: false, kind: 'frozen_text', detail: `任务目标必须原文出现：「${fact.goal}」` };
    case 'personality_changed':
      return scope.includes(fact.text) ? { ok: true } : { ok: false, kind: 'frozen_text', detail: `人格原文必须出现：「${fact.text}」` };
    case 'appearance_changed':
      return scope.includes(fact.text) ? { ok: true } : { ok: false, kind: 'frozen_text', detail: `外貌原文必须出现：「${fact.text}」` };
  }
}

export function checkFacts(input: FactCheckInput, text: string): FactCheckResult {
  const problems: FactCheckProblem[] = [];
  const covered: string[] = [];
  if (!text.trim()) {
    return { ok: false, problems: [{ kind: 'empty', detail: '模型输出为空' }], covered };
  }
  const scopes = scopesByActor(text, input.roster);
  const masked = maskQuotes(text);
  const byOwner = new Map<string, string[]>();
  for (const fact of input.facts) {
    const list = byOwner.get(fact.name) ?? [];
    if (!list.includes(fact.id)) list.push(fact.id);
    byOwner.set(fact.name, list);
    const scope = (scopes.get(fact.name) ?? []).join('，');
    const verdict = scope ? factInScope(fact, scope) : { ok: false, kind: 'missing' as const, detail: `${fact.name} 的分句不存在` };
    if (verdict.ok) { covered.push(fact.id); continue; }
    // Same payload attached to another actor = attribution problem, not a mere omission.
    // An `at` location is shared vocabulary, not a payload: another actor standing
    // in the same place does not turn an omission into an attribution.
    const others = fact.kind === 'at' ? [] : [...scopes.entries()].filter(([name]) => name !== fact.name)
      .filter(([namedActor, clausesOfActor]) => {
        const textOfActor = clausesOfActor.join('，');
        if (!factInScope(fact, textOfActor).ok) return false;
        // The named actor also owns this payload: same equal-value ambiguity as
        // the alignment grader; do not force an attribution.
        return !input.facts.some((other) => other.name === namedActor && other.kind === fact.kind
          && factInScope(other, textOfActor).ok);
      }).map(([namedActor]) => namedActor);
    if (verdict.kind === 'missing' && others.length) {
      problems.push({ kind: 'actor', factId: fact.id, detail: `${fact.name} 的事实出现在 ${others.join('/')} 的分句里` });
    } else {
      problems.push({ kind: verdict.kind, factId: fact.id, detail: verdict.detail });
    }
  }
  // Added claims: event verbs, unknown locations, unknown Arabic numbers.
  const allowedNumbers = new Set<number>(input.time ? [input.time.amount] : []);
  for (const [name, ids] of byOwner) {
    for (const id of ids) {
      const fact = input.facts.find((entry) => entry.id === id)!;
      if (fact.kind === 'sanity' || fact.kind === 'sanity_changed') {
        allowedNumbers.add(fact.kind === 'sanity' ? fact.value : fact.from);
        if (fact.kind === 'sanity_changed') allowedNumbers.add(fact.to);
      }
    }
  }
  for (const sentence of sentences(text)) {
    const plain = maskQuotes(sentence);
    const event = EVENT_VERBS.find((verb) => plain.includes(verb));
    if (event) problems.push({ kind: 'added', sentence, detail: `出现没有事实背书的事件动词「${event}」` });
    for (const name of input.roster) {
      for (const location of input.locations) {
        if (!new RegExp(`${name}[^。！？]{0,8}(?:在|位于|站在|待在|停在|到|走到|来到|进入)[^。！？]{0,4}${location}`, 'u').test(plain)) continue;
        const owned = input.facts.some((fact) => fact.name === name
          && ((fact.kind === 'at' && fact.location === location)
            || (fact.kind === 'moved' && (fact.from === location || fact.to === location))));
        if (!owned) problems.push({ kind: 'added', sentence, detail: `${name} 出现在 ${location}，但该点没有这个位置事实` });
      }
    }
    const phrase = UNLICENSED_PHRASES.find((item) => plain.includes(item));
    if (phrase) problems.push({ kind: 'added', sentence, detail: `出现没有事实背书的意图/因果/解释措辞「${phrase}」` });
    if (MOVEMENT_VERBS.some((verb) => plain.includes(verb))
      && !input.facts.some((fact) => fact.kind === 'moved')) {
      problems.push({ kind: 'added', sentence, detail: '出现了移动动词，但本点没有移动事实' });
    }
    for (const match of plain.matchAll(/(?<![0-9])([0-9]+)(?![0-9])/gu)) {
      const value = Number(match[1]);
      if (!allowedNumbers.has(value)) problems.push({ kind: 'number', sentence, detail: `多出未给出的数字 ${value}` });
    }
  }
  if (input.time) {
    const words = UNIT_WORDS[input.time.unit];
    const mentioned = hasValue(text, input.time.amount) && words.some((word) => text.includes(word));
    if (!mentioned) problems.push({ kind: 'time', detail: `时间推进 ${input.time.amount} ${input.time.unit} 未写全` });
  }
  return { ok: problems.length === 0, problems, covered };
}
