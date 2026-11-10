/** Byte-compatible port of `yuyan/convert_yuyan.py::render_row` for the
 * existing YuYan checkpoint (`yuyan-prose-legacy-v1`).
 *
 * The old format has no result block. It contains the viewpoint, the scoped
 * BEFORE state, the delta and the 正文 marker. `render_result.ts` adds the
 * new block under a separate serializer version; the two are never mixed.
 */
import type {
  NarrationProjection, RenderedNarrationInput, RowDelta, RowDeltaOps, RowPerson,
  RowState, RowTasks,
} from './types';
import { NarrationInputError } from './types';
import { compareCodePoints } from './code-points';
import { finalizeRenderedInput, type RenderOptions } from './render-common';

const TRAILING_PUNCTUATION = /[。；，]+$/u;
const SPACES = /[ \t\u3000]+/gu;

/** Python `re.sub(r"[ \t\u3000]+", "", text)`: delete only these three
 * whitespace kinds. Other whitespace is rejected later, never silently
 * removed. */
export function squashLegacy(text: string): string {
  return text.replace(SPACES, '');
}

function joinItems(items: readonly string[]): string {
  const clean = items.map((item) => squashLegacy(item).replace(TRAILING_PUNCTUATION, ''));
  return clean.filter((item) => item.length > 0).join('、');
}

function taskLine(tasks: RowTasks): string {
  const parts: string[] = [];
  if (tasks.大任务) parts.push(`${squashLegacy(tasks.大任务.目标)}（${tasks.大任务.状态}）`);
  for (const task of tasks.小任务 ?? []) {
    parts.push(`${squashLegacy(task.目标)}（${task.状态}）`);
  }
  return parts.join('；');
}

function personLine(name: string, entry: RowPerson): string {
  const pieces: string[] = [];
  if (entry.位置) pieces.push(`在${entry.位置}`);
  if (Object.prototype.hasOwnProperty.call(entry, '精神值')) pieces.push(`精神值${entry.精神值}`);
  if (entry.外貌 && entry.外貌.length > 0) pieces.push(`外貌${joinItems(entry.外貌)}`);
  if (entry.个性 && entry.个性.length > 0) pieces.push(`个性${joinItems(entry.个性)}`);
  if (entry.任务) pieces.push(`任务${taskLine(entry.任务)}`);
  return `${name}：${pieces.join('，')}。`;
}

function placeLine(name: string, entry: { 位于?: string | null; 外貌?: string[] }): string {
  const looks = joinItems(entry.外貌 ?? []);
  let body = name;
  if (entry.位于) body += `（在${entry.位于}里）`;
  if (looks) body += `：${looks}`;
  return `${body}。`;
}

function renderState(state: RowState): string {
  const lines: string[] = [];
  const places = state.地点 ?? {};
  const placeNames = Object.keys(places).sort(compareCodePoints);
  if (placeNames.length > 0) lines.push(`【地点】${placeNames.map((name) => placeLine(name, places[name])).join('')}`);
  const people = state.人物 ?? {};
  const personNames = Object.keys(people).sort(compareCodePoints);
  if (personNames.length > 0) lines.push(`【人物】${personNames.map((name) => personLine(name, people[name])).join('')}`);
  const things = state.物品 ?? {};
  const itemNames = Object.keys(things).sort(compareCodePoints);
  if (itemNames.length > 0) lines.push(`【物品】${itemNames.map((name) => placeLine(name, things[name])).join('')}`);
  return lines.join('');
}

function describeChange(entity: string, ops: RowDeltaOps, state: RowState): string {
  const pieces: string[] = [];
  if ('位置' in ops) pieces.push(`移动到${ops.位置}`);
  if ('精神值' in ops) pieces.push(`精神值变成${ops.精神值}`);
  if (ops.解除外貌 && ops.解除外貌.length > 0) pieces.push(`去掉外貌${joinItems(ops.解除外貌)}`);
  if (ops.新增外貌 && ops.新增外貌.length > 0) pieces.push(`多出外貌${joinItems(ops.新增外貌)}`);
  if (ops.解除个性 && ops.解除个性.length > 0) pieces.push(`去掉个性${joinItems(ops.解除个性)}`);
  if (ops.新增个性 && ops.新增个性.length > 0) pieces.push(`多出个性${joinItems(ops.新增个性)}`);
  if (ops.完成任务 && ops.完成任务.length > 0) pieces.push(`完成${joinItems(ops.完成任务)}`);
  if (ops.新增小任务 && ops.新增小任务.length > 0) {
    pieces.push(`新任务${joinItems(ops.新增小任务.map((task) => task.目标))}`);
  }
  if (pieces.length === 0) return '';
  const kind = state.地点[entity] ? '地点' : (state.物品[entity] ? '物品' : '人物');
  return `${entity}（${kind}）：${pieces.join('，')}。`;
}

function renderDelta(delta: RowDelta, beforeState: RowState): string {
  const timeLine = `时间推进${squashLegacy(delta.时间推进 ?? '')}。`;
  const changes = delta.变化 ?? {};
  const names = Object.keys(changes).sort(compareCodePoints);
  const body = names.map((name) => describeChange(name, changes[name], beforeState)).filter(Boolean).join('');
  if (body.length === 0) return `【变化】${timeLine}这一回合没有结算出变化。`;
  return `【变化】${timeLine}${body}`;
}

function rejectWhitespace(value: string, path: string): void {
  if (/\s/u.test(value)) {
    throw new NarrationInputError('whitespace', `projection field ${path} contains whitespace`, { path });
  }
}

export function assertNoUnsafeWhitespace(projection: NarrationProjection): void {
  const state = projection.beforeState;
  for (const [name, entry] of Object.entries(state.地点)) {
    if (entry.位于) rejectWhitespace(entry.位于, `beforeState.地点.${name}.位于`);
    entry.外貌.forEach((text, index) => rejectWhitespace(text, `beforeState.地点.${name}.外貌[${index}]`));
  }
  for (const [name, entry] of Object.entries(state.人物)) {
    rejectWhitespace(entry.位置, `beforeState.人物.${name}.位置`);
    entry.外貌.forEach((text, index) => rejectWhitespace(text, `beforeState.人物.${name}.外貌[${index}]`));
    entry.个性.forEach((text, index) => rejectWhitespace(text, `beforeState.人物.${name}.个性[${index}]`));
    if (entry.任务?.大任务) rejectWhitespace(entry.任务.大任务.目标, `beforeState.人物.${name}.任务.大任务.目标`);
    (entry.任务?.小任务 ?? []).forEach((task, index) => rejectWhitespace(task.目标, `beforeState.人物.${name}.任务.小任务[${index}].目标`));
  }
  for (const [name, entry] of Object.entries(state.物品)) {
    rejectWhitespace(entry.位置, `beforeState.物品.${name}.位置`);
    entry.外貌.forEach((text, index) => rejectWhitespace(text, `beforeState.物品.${name}.外貌[${index}]`));
  }
  // 时间推进 is the one field the old converter deliberately squashes.
  for (const [name, ops] of Object.entries(projection.delta.变化)) {
    if (ops.位置) rejectWhitespace(ops.位置, `delta.${name}.位置`);
    for (const field of ['解除外貌', '新增外貌', '解除个性', '新增个性', '完成任务'] as const) {
      (ops[field] ?? []).forEach((text, index) => rejectWhitespace(text, `delta.${name}.${field}[${index}]`));
    }
    (ops.新增小任务 ?? []).forEach((task, index) => rejectWhitespace(task.目标, `delta.${name}.新增小任务[${index}].目标`));
  }
  rejectWhitespace(projection.viewpoint.text, 'viewpoint.text');
}

export function assertNarrationProjection(projection: NarrationProjection): void {
  if (projection.projectionVersion !== 'narration-projection-v1') {
    throw new NarrationInputError('invalid_projection', `unknown projection version ${String(projection.projectionVersion)}`);
  }
  if (!projection.beforeState || !projection.beforeState.地点 || !projection.beforeState.人物 || !projection.beforeState.物品) {
    throw new NarrationInputError('invalid_projection', 'beforeState must contain 地点/人物/物品 maps');
  }
  if (!projection.delta || !projection.delta.变化) {
    throw new NarrationInputError('invalid_projection', 'delta must contain a 变化 map');
  }
  if (!projection.viewpoint || typeof projection.viewpoint.text !== 'string') {
    throw new NarrationInputError('invalid_projection', 'viewpoint.text must be a string');
  }
  assertNoUnsafeWhitespace(projection);
}

export function renderLegacyInput(
  projection: NarrationProjection,
  options: RenderOptions = {},
): RenderedNarrationInput {
  assertNarrationProjection(projection);
  const viewpoint = squashLegacy(projection.viewpoint.text).split('；')[0] ?? '';
  const parts = [
    `【视角】${viewpoint}`,
    renderState(projection.beforeState),
    renderDelta(projection.delta, projection.beforeState),
    '【正文】',
  ];
  const text = parts.filter((part) => part.length > 0).join('');
  return finalizeRenderedInput(text, projection, 'yuyan-prose-legacy-v1', options);
}

export { renderState as renderLegacyState, renderDelta as renderLegacyDelta };
