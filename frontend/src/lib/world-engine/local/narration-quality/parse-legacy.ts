/** Parse the legacy narration input string back into the dataset row.
 *
 * Some real-output records (browser-09, navigation probes) store only the
 * prompt string the model saw, not the structured row. The string is produced
 * by `renderLegacyInput`, so a strict reader can recover the settled state and
 * let the independent checker review those runs instead of discarding them.
 *
 * The reader is validated by round-trip: `parseLegacyInput(s)` then
 * `renderLegacyInput(parsed)` must reproduce `s` byte for byte. A string that
 * does not round-trip is rejected rather than guessed at.
 */
import type { DatasetInput } from './scene';

const SECTION = /【(视角|地点|人物|物品|变化|正文)】/gu;

type PersonBlock = NonNullable<NonNullable<DatasetInput['上回合状态']>['人物']>[string];
type PlaceBlock = NonNullable<NonNullable<DatasetInput['上回合状态']>['地点']>[string];
type ItemBlock = NonNullable<NonNullable<DatasetInput['上回合状态']>['物品']>[string];

/** Cut `name（在parent里）：looks。` into its three parts. */
function readPlaceLine(line: string): { name: string; parent: string | null; looks: string[] } | null {
  const match = /^([^（：]+?)(?:（在(.+?)里）)?(?:\uFF1A(.*))?。$/u.exec(line);
  if (!match) return null;
  const [, name, parent, looks] = match;
  return {
    name,
    parent: parent ?? null,
    looks: looks ? looks.split('、').map((part) => part.trim()).filter((part) => part.length > 0) : [],
  };
}

/** `name：在place，精神值N，外貌…，个性…，任务…。` (pieces optional).
 *
 * Values can contain `，` (a look or a goal written as a clause), so the reader
 * splits on the field markers, never on commas. */
function readPersonLine(line: string): { name: string; block: PersonBlock } | null {
  const match = /^([^：]+?)：(.*)。$/u.exec(line);
  if (!match) return null;
  const [, name, body] = match;
  const block: PersonBlock = {};
  const sanity = /精神值(\d+)/u.exec(body);
  const lookAt = body.indexOf('外貌');
  const traitAt = body.indexOf('个性');
  const taskAt = body.indexOf('任务');
  const headEnd = [sanity?.index, lookAt, traitAt, taskAt].filter((index): index is number => index !== undefined && index >= 0)
    .reduce((min, index) => Math.min(min, index), body.length);
  const head = body.slice(0, headEnd).replace(/，$/u, '');
  if (head.startsWith('在')) block.位置 = head.slice(1);
  else if (head.length > 0) return null;
  if (sanity) block.精神值 = Number(sanity[1]);
  const take = (from: number, keywords: string[]): string => {
    let end = body.length;
    for (const keyword of keywords) {
      const at = body.indexOf(keyword, from);
      if (at >= 0 && at < end) end = at;
    }
    return body.slice(from, end).replace(/，$/u, '');
  };
  if (lookAt >= 0) block.外貌 = take(lookAt + 2, ['个性', '任务']).split('、').map((part) => part.trim()).filter(Boolean);
  if (traitAt >= 0) block.个性 = take(traitAt + 2, ['任务']).split('、').map((part) => part.trim()).filter(Boolean);
  if (taskAt >= 0) {
    const text = body.slice(taskAt + 2);
    if (text !== '无') {
      const parsed = text.split('；').map((part) => {
        const task = /^(.*?)（(未完成|已完成)）$/u.exec(part);
        return task ? { 目标: task[1], 状态: task[2] } : null;
      });
      if (parsed.some((task) => task === null)) return null;
      const list = parsed as { 目标: string; 状态: string }[];
      if (list.length > 0) block.任务 = { 大任务: list[0], 小任务: list.slice(1) };
    }
  }
  return { name, block };
}

/** `name（人物|地点|物品）：移动到X，精神值变成N，…。` */
function readChangeLine(line: string): { name: string; kind: string; block: Record<string, unknown> } | null {
  const match = /^([^（]+?)（(人物|地点|物品)）：(.*)。$/u.exec(line);
  if (!match) return null;
  const [, name, kind, body] = match;
  const markers = [...body.matchAll(/(移动到|精神值变成|去掉外貌|多出外貌|去掉个性|多出个性|完成|新任务)/gu)];
  if (markers.length === 0) return null;
  const block: Record<string, unknown> = {};
  markers.forEach((marker, index) => {
    const start = (marker.index ?? 0) + marker[0].length;
    const end = index + 1 < markers.length ? (markers[index + 1].index ?? body.length) : body.length;
    const value = body.slice(start, end).replace(/，$/u, '');
    const list = (key: string): void => {
      const current = (block[key] as string[] | undefined) ?? [];
      current.push(...value.split('、'));
      block[key] = current;
    };
    switch (marker[1]) {
      case '移动到': block.位置 = value; break;
      case '精神值变成': block.精神值 = Number(value); break;
      case '去掉外貌': list('解除外貌'); break;
      case '多出外貌': list('新增外貌'); break;
      case '去掉个性': list('解除个性'); break;
      case '多出个性': list('新增个性'); break;
      case '完成': list('完成任务'); break;
      case '新任务': {
        const current = (block.新增小任务 as { 目标: string }[] | undefined) ?? [];
        current.push({ 目标: value });
        block.新增小任务 = current;
        break;
      }
      default: return null;
    }
  });
  return { name, kind, block };
}

/** Split a section into entries. Field values may contain `。`, so a full stop
 * only ends an entry when the next text starts a new `name：` line. */
function splitEntries(section: string, nextEntry: RegExp): string[] {
  const parts: string[] = [];
  let start = 0;
  for (let index = 0; index < section.length; index += 1) {
    if (section[index] !== '。') continue;
    const rest = section.slice(index + 1);
    if (rest.length === 0) { parts.push(section.slice(start)); start = section.length; break; }
    if (nextEntry.test(rest.slice(0, 40))) { parts.push(section.slice(start, index + 1)); start = index + 1; }
  }
  if (start < section.length) parts.push(section.slice(start));
  return parts;
}

function stage(name: string): null {
  (globalThis as { __parseStage?: string }).__parseStage = name;
  return null;
}

export function parseLegacyInput(text: string): DatasetInput | null {
  const markers = [...text.matchAll(SECTION)];
  if (markers.length === 0) return stage('no-markers');
  const sections = new Map<string, string>();
  markers.forEach((marker, index) => {
    const start = (marker.index ?? 0) + marker[0].length;
    const end = index + 1 < markers.length ? (markers[index + 1].index ?? text.length) : text.length;
    sections.set(marker[1], text.slice(start, end));
  });
  const viewpoint = sections.get('视角');
  if (viewpoint === undefined) return stage('no-viewpoint');

  const state: NonNullable<DatasetInput['上回合状态']> = { 人物: {}, 地点: {}, 物品: {} };
  for (const line of splitEntries(sections.get('地点') ?? '', /^[^：。\s]{1,10}(（在[^）]{1,20}里）)?：/u)) {
    const place = readPlaceLine(line);
    if (!place) return stage('place:'+line);
    const block: PlaceBlock = { 位于: place.parent, 外貌: place.looks };
    state.地点![place.name] = block;
  }
  for (const line of splitEntries(sections.get('人物') ?? '', /^[^：。\s]{1,6}：(?=[^【]{0,80}精神值)/u)) {
    const person = readPersonLine(line);
    if (!person) return stage('person:'+line);
    state.人物![person.name] = person.block;
  }
  for (const line of splitEntries(sections.get('物品') ?? '', /^[^：。\s]{1,10}(（在[^）]{1,20}里）)?：/u)) {
    const item = readPlaceLine(line);
    if (!item) return stage('item:'+line);
    const block: ItemBlock = { 位置: item.parent ?? undefined, 外貌: item.looks };
    state.物品![item.name] = block;
  }

  const delta: NonNullable<DatasetInput['本回合变化']> = { 变化: {} };
  const changeText = sections.get('变化') ?? '';
  const time = /^时间推进([^。]*)。/u.exec(changeText);
  if (time) delta.时间推进 = time[1];
  const rest = time ? changeText.slice(time[0].length) : changeText;
  if (rest !== '这一回合没有结算出变化。') {
    for (const line of rest.split(/(?<=。)/u).filter(Boolean)) {
      const change = readChangeLine(line);
      if (!change) return stage('change:'+line);
      delta.变化![change.name] = change.block as never;
    }
  }

  const input: DatasetInput = { 视角: viewpoint, 上回合状态: state, 本回合变化: delta };
  if (!roundTrips(input, text)) {
    (globalThis as { __parseDebug?: string }).__parseDebug = JSON.stringify({
      rendered: renderParsed(input), original: text,
    });
    return null;
  }
  return input;
}

/** Re-render with the same grammar the product page emits. Unlike the legacy
 * trainer renderer this keeps insertion order, prints `任务无`, and keeps an
 * item's parent, so a byte comparison proves the reader consumed every field. */
export function renderParsed(input: DatasetInput): string {
  const joined = (items: readonly string[]): string => items.join('、');
  const place = (name: string, block: { 位于?: string | null; 位置?: string; 外貌?: string[] }): string => {
    const parent = block.位于 ?? block.位置 ?? null;
    const looks = block.外貌?.length ? `：${joined(block.外貌)}` : '';
    return `${name}${parent ? `（在${parent}里）` : ''}${looks}。`;
  };
  const task = (tasks: { 大任务?: { 目标: string; 状态: string }; 小任务?: { 目标: string; 状态: string }[] }): string => {
    const list = [...(tasks.大任务 ? [tasks.大任务] : []), ...(tasks.小任务 ?? [])];
    return list.length ? list.map((entry) => `${entry.目标}（${entry.状态}）`).join('；') : '无';
  };
  const person = (name: string, block: Record<string, unknown>): string => {
    const pieces: string[] = [];
    if (block.位置) pieces.push(`在${String(block.位置)}`);
    if ('精神值' in block) pieces.push(`精神值${String(block.精神值)}`);
    if ((block.外貌 as string[] | undefined)?.length) pieces.push(`外貌${joined(block.外貌 as string[])}`);
    if ((block.个性 as string[] | undefined)?.length) pieces.push(`个性${joined(block.个性 as string[])}`);
    pieces.push(`任务${task((block.任务 as never) ?? {})}`);
    return `${name}：${pieces.join('，')}。`;
  };
  const state = input.上回合状态 ?? {};
  const delta = input['本回合变化'] ?? {};
  const change = (name: string, kind: string, block: Record<string, unknown>): string => {
    const pieces: string[] = [];
    if (block.位置) pieces.push(`移动到${String(block.位置)}`);
    if ('精神值' in block) pieces.push(`精神值变成${String(block.精神值)}`);
    if ((block.解除外貌 as string[] | undefined)?.length) pieces.push(`去掉外貌${joined(block.解除外貌 as string[])}`);
    if ((block.新增外貌 as string[] | undefined)?.length) pieces.push(`多出外貌${joined(block.新增外貌 as string[])}`);
    if ((block.解除个性 as string[] | undefined)?.length) pieces.push(`去掉个性${joined(block.解除个性 as string[])}`);
    if ((block.新增个性 as string[] | undefined)?.length) pieces.push(`多出个性${joined(block.新增个性 as string[])}`);
    if ((block.完成任务 as string[] | undefined)?.length) pieces.push(`完成${joined(block.完成任务 as string[])}`);
    if ((block.新增小任务 as { 目标: string }[] | undefined)?.length) pieces.push(`新任务${joined((block.新增小任务 as { 目标: string }[]).map((entry) => entry.目标))}`);
    return pieces.length ? `${name}（${kind}）：${pieces.join('，')}。` : '';
  };
  const parts: string[] = [`【视角】${input.视角 ?? ''}`];
  const places = Object.entries(state.地点 ?? {});
  if (places.length) parts.push(`【地点】${places.map(([name, block]) => place(name, block)).join('')}`);
  const people = Object.entries(state.人物 ?? {});
  if (people.length) parts.push(`【人物】${people.map(([name, block]) => person(name, block as Record<string, unknown>)).join('')}`);
  const items = Object.entries(state.物品 ?? {});
  if (items.length) parts.push(`【物品】${items.map(([name, block]) => place(name, block)).join('')}`);
  const kinds = new Map<string, string>();
  for (const [name] of places) kinds.set(name, '地点');
  for (const [name] of people) kinds.set(name, '人物');
  for (const [name] of items) kinds.set(name, '物品');
  const body = Object.entries(delta.变化 ?? {}).map(([name, block]) => change(name, kinds.get(name) ?? '人物', block as Record<string, unknown>)).join('');
  const timeLine = delta.时间推进 ? `时间推进${delta.时间推进}。` : '';
  parts.push(`【变化】${timeLine}${body || '这一回合没有结算出变化。'}`);
  parts.push('【正文】');
  return parts.join('');
}

function roundTrips(input: DatasetInput, original: string): boolean {
  try {
    return renderParsed(input) === original;
  } catch {
    return false;
  }
}
