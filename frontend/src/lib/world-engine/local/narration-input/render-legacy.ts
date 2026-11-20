/** Byte-compatible port of `yuyan/convert_yuyan.py::render_row` for the
 * existing YuYan checkpoint (`yuyan-prose-legacy-v1`).
 *
 * The old format has no result block, and its item line reads `位于` (not
 * `位置`), so item positions are lost. That loss is reproduced on purpose:
 * the old weights were trained on those bytes. Use `render-result`/the v2
 * pipeline when the result block and item position are required.
 */
import type {
  NarrationProjection, ProjectionDelta, RowItem, RowPerson, RowPlace, RowTasks,
} from './types';
import { compareCodePoints } from './code-points';

const SPACES = /[ \t\u3000]+/gu;
const TRAILING = /[。；，]+$/u;

/** Python `re.sub(r"[ \t\u3000]+", "", text)`. */
export function squashLegacy(text: string): string {
  return text.replace(SPACES, '');
}

function joinItems(items: readonly string[]): string {
  return items.map((item) => squashLegacy(item).replace(TRAILING, ''))
    .filter((item) => item.length > 0)
    .join('、');
}

function taskLine(tasks: RowTasks): string {
  const parts: string[] = [];
  if (tasks.大任务) parts.push(`${squashLegacy(tasks.大任务.目标)}（${tasks.大任务.状态}）`);
  for (const task of tasks.小任务 ?? []) parts.push(`${squashLegacy(task.目标)}（${task.状态}）`);
  return parts.join('；');
}

function personLine(name: string, entry: RowPerson): string {
  const pieces: string[] = [];
  if (entry.位置) pieces.push(`在${entry.位置}`);
  if ('精神值' in entry) pieces.push(`精神值${entry.精神值}`);
  if (entry.外貌?.length) pieces.push(`外貌${joinItems(entry.外貌)}`);
  if (entry.个性?.length) pieces.push(`个性${joinItems(entry.个性)}`);
  if (entry.任务) pieces.push(`任务${taskLine(entry.任务)}`);
  return `${name}：${pieces.join('，')}。`;
}

/** Legacy place/item line. The parent comes from `位于` only; an item's
 * `位置` is intentionally ignored to keep the old bytes. */
function placeLine(name: string, entry: RowPlace | RowItem): string {
  const looks = joinItems(entry.外貌 ?? []);
  let body = name;
  const parent = (entry as RowPlace).位于;
  if (parent) body += `（在${parent}里）`;
  if (looks) body += `：${looks}`;
  return `${body}。`;
}

function renderState(state: NarrationProjection['上回合状态']): string {
  const lines: string[] = [];
  const places = Object.keys(state.地点).sort(compareCodePoints);
  if (places.length > 0) lines.push(`【地点】${places.map((name) => placeLine(name, state.地点[name])).join('')}`);
  const people = Object.keys(state.人物).sort(compareCodePoints);
  if (people.length > 0) lines.push(`【人物】${people.map((name) => personLine(name, state.人物[name])).join('')}`);
  const items = Object.keys(state.物品).sort(compareCodePoints);
  if (items.length > 0) lines.push(`【物品】${items.map((name) => placeLine(name, state.物品[name])).join('')}`);
  return lines.join('');
}

function describeChange(name: string, ops: ProjectionDelta['变化'][string], state: NarrationProjection['上回合状态']): string {
  const pieces: string[] = [];
  if ('位置' in ops) pieces.push(`移动到${ops.位置}`);
  if ('精神值' in ops) pieces.push(`精神值变成${ops.精神值}`);
  if (ops.解除外貌?.length) pieces.push(`去掉外貌${joinItems(ops.解除外貌)}`);
  if (ops.新增外貌?.length) pieces.push(`多出外貌${joinItems(ops.新增外貌)}`);
  if (ops.解除个性?.length) pieces.push(`去掉个性${joinItems(ops.解除个性)}`);
  if (ops.新增个性?.length) pieces.push(`多出个性${joinItems(ops.新增个性)}`);
  if (ops.完成任务?.length) pieces.push(`完成${joinItems(ops.完成任务)}`);
  if (ops.新增小任务?.length) pieces.push(`新任务${joinItems(ops.新增小任务.map((task) => task.目标))}`);
  if (pieces.length === 0) return '';
  const kind = state.地点[name] ? '地点' : (state.物品[name] ? '物品' : '人物');
  return `${name}（${kind}）：${pieces.join('，')}。`;
}

type LegacyProjectionFields = Pick<NarrationProjection, '视角' | '上回合状态' | '本回合变化'>;

export function renderLegacyDelta(delta: ProjectionDelta, beforeState: LegacyProjectionFields['上回合状态']): string {
  const timeLine = `时间推进${squashLegacy(delta.时间推进 ?? '')}。`;
  const changes = delta.变化 ?? {};
  const names = Object.keys(changes).sort(compareCodePoints);
  const body = names.map((name) => describeChange(name, changes[name], beforeState)).filter(Boolean).join('');
  if (!body) return `【变化】${timeLine}这一回合没有结算出变化。`;
  return `【变化】${timeLine}${body}`;
}

export function renderLegacyInput(projection: LegacyProjectionFields): string {
  const viewpoint = squashLegacy(projection.视角).split('；')[0] ?? '';
  return [
    `【视角】${viewpoint}`,
    renderState(projection.上回合状态),
    renderLegacyDelta(projection.本回合变化, projection.上回合状态),
    '【正文】',
  ].filter((part) => part.length > 0).join('');
}

export { renderState as renderLegacyState };
