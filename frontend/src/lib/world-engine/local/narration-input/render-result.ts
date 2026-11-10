/** Result-block serializer `yuyan-prose-result-v2`.
 *
 * The previous state and the delta are byte-identical to the legacy
 * serializer. The only addition is an explicit 本回合状态 block between the
 * delta and 正文. That block is a result of the round, not a full snapshot:
 *
 *   名称（类型）：位置…；精神值0；外貌[…、…]；个性[…]；任务大任务《…》（…）；
 *   小任务《…》（…，属于《…》）。
 *
 * Fields that are absent mean "this result does not carry the field". They
 * never mean zero or deletion. Zero and empty lists are written explicitly.
 */
import type {
  NarrationProjection, RenderedNarrationInput, RowResultEntity, RowResultPerson,
  RowResultTaskGroup,
} from './types';
import { NarrationInputError } from './types';
import { compareCodePoints } from './code-points';
import { assertNoUnsafeWhitespace, renderLegacyInput } from './render-legacy';
import { finalizeRenderedInput, type RenderOptions } from './render-common';

const TYPE_LABEL = { location: '地点', character: '人物', item: '物品' } as const;

function listField(label: string, values: string[]): string {
  for (const value of values) {
    if (typeof value !== 'string') throw new NarrationInputError('invalid_projection', `result ${label} contains a non-string value`);
  }
  return `${label}[${values.join('、')}]`;
}

function assertOnlyKeys(view: object, allowed: readonly string[]): void {
  for (const key of Object.keys(view)) {
    if (!allowed.includes(key)) {
      throw new NarrationInputError('invalid_projection', `result field ${key} is not allowed here`, { field: key });
    }
  }
}

function taskGroup(group: RowResultTaskGroup): string {
  const parts: string[] = [];
  if (group.大任务) parts.push(`大任务《${group.大任务.目标}》（${group.大任务.状态}）`);
  for (const task of group.小任务 ?? []) {
    const parent = task.属于大任务 ? `，属于《${task.属于大任务}》` : '';
    parts.push(`小任务《${task.目标}》（${task.状态}${parent}）`);
  }
  return parts.join('；');
}

function personFields(view: RowResultPerson): string[] {
  assertOnlyKeys(view, ['位置', '精神值', '外貌', '个性', '任务']);
  const fields: string[] = [];
  if (view.位置 !== undefined) {
    if (typeof view.位置 !== 'string' || view.位置.length === 0) {
      throw new NarrationInputError('invalid_projection', 'result 位置 must be a non-empty string');
    }
    fields.push(`位置${view.位置}`);
  }
  if (view.精神值 !== undefined) {
    if (typeof view.精神值 !== 'number' || !Number.isFinite(view.精神值)) {
      throw new NarrationInputError('invalid_projection', 'result 精神值 must be a finite number');
    }
    fields.push(`精神值${view.精神值}`);
  }
  if (view.外貌 !== undefined) {
    if (!Array.isArray(view.外貌)) throw new NarrationInputError('invalid_projection', 'result 外貌 must be an array');
    fields.push(listField('外貌', view.外貌));
  }
  if (view.个性 !== undefined) {
    if (!Array.isArray(view.个性)) throw new NarrationInputError('invalid_projection', 'result 个性 must be an array');
    fields.push(listField('个性', view.个性));
  }
  if (view.任务 !== undefined) {
    const text = taskGroup(view.任务);
    if (text.length > 0) fields.push(`任务${text}`);
  }
  return fields;
}

function itemFields(view: RowResultEntity & { 位置?: string; 外貌?: string[] }): string[] {
  assertOnlyKeys(view, ['位置', '外貌']);
  const fields: string[] = [];
  if (view.位置 !== undefined) {
    if (typeof view.位置 !== 'string' || view.位置.length === 0) {
      throw new NarrationInputError('invalid_projection', 'result 位置 must be a non-empty string');
    }
    fields.push(`位置${view.位置}`);
  }
  if (view.外貌 !== undefined) {
    if (!Array.isArray(view.外貌)) throw new NarrationInputError('invalid_projection', 'result 外貌 must be an array');
    fields.push(listField('外貌', view.外貌));
  }
  return fields;
}

function locationFields(view: RowResultEntity & { 外貌?: string[] }): string[] {
  assertOnlyKeys(view, ['外貌']);
  if (view.外貌 === undefined) return [];
  if (!Array.isArray(view.外貌)) throw new NarrationInputError('invalid_projection', 'result 外貌 must be an array');
  return [listField('外貌', view.外貌)];
}

/** Render the 本回合状态 block, or an empty string when the result is empty. */
export function renderResultBlock(projection: NarrationProjection): string {
  assertNoUnsafeWhitespace(projection);
  const result = projection.resultState ?? {};
  const byType: Record<keyof typeof TYPE_LABEL, string[]> = { location: [], character: [], item: [] };
  for (const name of Object.keys(result)) {
    const matches = [
      projection.beforeState.地点[name] ? 'location' as const : null,
      projection.beforeState.人物[name] ? 'character' as const : null,
      projection.beforeState.物品[name] ? 'item' as const : null,
    ].filter((value): value is keyof typeof TYPE_LABEL => value !== null);
    if (matches.length === 0) {
      throw new NarrationInputError('invalid_projection', `result entity ${name} has no type in the before state`, { name });
    }
    if (matches.length > 1) {
      throw new NarrationInputError('duplicate_name', `result entity ${name} matches more than one type`, { name });
    }
    byType[matches[0]].push(name);
  }
  const lines: string[] = [];
  for (const type of ['location', 'character', 'item'] as const) {
    const names = byType[type].sort(compareCodePoints);
    for (const name of names) {
      const view = result[name];
      const fields = type === 'character'
        ? personFields(view as RowResultPerson)
        : type === 'item'
          ? itemFields(view as RowResultEntity & { 位置?: string; 外貌?: string[] })
          : locationFields(view as RowResultEntity & { 外貌?: string[] });
      if (fields.length === 0) continue;
      lines.push(`${name}（${TYPE_LABEL[type]}）：${fields.join('；')}。`);
    }
  }
  return lines.length > 0 ? `【本回合状态】${lines.join('')}` : '';
}

export function renderResultInput(
  projection: NarrationProjection,
  options: RenderOptions = {},
): RenderedNarrationInput {
  const legacy = renderLegacyInput(projection, { ...options, enforceLength: false });
  const block = renderResultBlock(projection);
  if (block.length === 0) {
    return finalizeRenderedInput(legacy.text, projection, 'yuyan-prose-result-v2', options);
  }
  const marker = '【正文】';
  const index = legacy.text.lastIndexOf(marker);
  if (index < 0) throw new NarrationInputError('invalid_projection', 'legacy body has no 正文 marker');
  const text = legacy.text.slice(0, index) + block + legacy.text.slice(index);
  return finalizeRenderedInput(text, projection, 'yuyan-prose-result-v2', options);
}
