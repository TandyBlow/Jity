/** Port of `v2_render.build_result`.
 *
 * The stored result is the settled view of the changed entities (built from
 * the AFTER state by the runtime adapter). This function validates it against
 * the declared delta, fills fields the stored view omitted, and refuses a
 * disagreement instead of silently overwriting it.
 */
import type {
  DeltaOps, ProjectionDelta, ProjectionState, ResultFill, ResultState,
  ResultTaskGroup, ResultPerson, ResultPlace, ResultItem, RowTask,
} from './types';
import { NarrationInputError } from './types';
import { expectArray, expectInt, expectObject, expectString } from './normalize';
import { entityRegistry, resolveType } from './registry';
import { compareCodePoints } from './code-points';

const RESULT_FIELDS: Record<string, readonly string[]> = {
  人物: ['位置', '精神值', '外貌', '个性', '任务'],
  地点: ['位于', '外貌'],
  物品: ['位置', '外貌'],
};

function fail(code: string, message: string, path: string): never {
  throw new NarrationInputError(code, message, path);
}

function taskEntries(beforeEntity: Record<string, unknown>, ops: DeltaOps, path: string): ResultTaskGroup {
  const tasks = expectObject(beforeEntity['任务'], `${path}/任务`);
  const bigObject = expectObject(tasks['大任务'], `${path}/任务/大任务`);
  const bigGoal = expectString(bigObject['目标'], `${path}/任务/大任务/目标`);
  const smallList = expectArray(tasks['小任务'] ?? [], `${path}/任务/小任务`);
  const small = new Map<string, RowTask>();
  for (const [index, task] of smallList.entries()) {
    const entry = expectObject(task, `${path}/任务/小任务[${index}]`);
    small.set(expectString(entry['目标'], `${path}/任务/小任务[${index}]/目标`), entry as unknown as RowTask);
  }
  let outBig: RowTask | undefined;
  const outSmall: RowTask[] = [];
  for (const goal of expectArray(ops.完成任务 ?? [], `${path}/完成任务`)) {
    const target = expectString(goal, `${path}/完成任务`);
    if (bigGoal === target) {
      outBig = { 目标: target, 状态: '已完成' };
    } else if (small.has(target)) {
      outSmall.push({ 目标: target, 状态: '已完成' });
    } else {
      fail('unknown_task', `${path} completes unknown task ${JSON.stringify(target)}`, `${path}/完成任务`);
    }
  }
  for (const [index, added] of expectArray(ops.新增小任务 ?? [], `${path}/新增小任务`).entries()) {
    const entry = expectObject(added, `${path}/新增小任务[${index}]`);
    const goal = expectString(entry['目标'], `${path}/新增小任务[${index}]/目标`);
    outSmall.push({ 目标: goal, 状态: typeof entry['状态'] === 'string' ? entry['状态'] : '未完成' });
  }
  const result: ResultTaskGroup = {};
  if (outBig) result.大任务 = outBig;
  if (outSmall.length > 0) result.小任务 = outSmall;
  return result;
}

function applyListChange(beforeValues: unknown, removed: unknown, added: unknown, path: string): string[] {
  const values = [...expectArray(beforeValues, `${path}/before`)];
  for (const [index, item] of expectArray(removed, `${path}/removed`).entries()) {
    const position = values.indexOf(item);
    if (position < 0) {
      fail('remove_missing_item', `${path} removes missing item ${JSON.stringify(item)}`, `${path}/removed[${index}]`);
    }
    values.splice(position, 1);
  }
  for (const item of expectArray(added, `${path}/added`)) {
    values.push(expectString(item, `${path}/added`));
  }
  return values as string[];
}

function sameStringMultiset(left: unknown, right: unknown): boolean {
  if (!Array.isArray(left) || !Array.isArray(right)) return false;
  if (left.length !== right.length) return false;
  const counts = new Map<unknown, number>();
  for (const value of left) counts.set(value, (counts.get(value) ?? 0) + 1);
  for (const value of right) {
    const count = counts.get(value);
    if (!count) return false;
    counts.set(value, count - 1);
  }
  return true;
}

function canonicalTasks(value: unknown): unknown {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const tasks = value as { 大任务?: RowTask | null; 小任务?: RowTask[] };
  const big = tasks.大任务 == null ? null : [tasks.大任务.目标, tasks.大任务.状态];
  const small = (tasks.小任务 ?? [])
    .map((task) => [task.目标, task.状态])
    .sort((left, right) => {
      const a = `${left[0]}\u0000${left[1]}`;
      const b = `${right[0]}\u0000${right[1]}`;
      return a < b ? -1 : a > b ? 1 : 0;
    });
  return JSON.stringify([big, small]);
}

function sameResultValue(field: string, existing: unknown, computed: unknown): boolean {
  if (field === '外貌' || field === '个性') return sameStringMultiset(existing, computed);
  if (field === '任务') {
    if (!existing || typeof existing !== 'object' || Array.isArray(existing)) return false;
    if (!computed || typeof computed !== 'object' || Array.isArray(computed)) return false;
    return canonicalTasks(existing) === canonicalTasks(computed);
  }
  return existing === computed;
}

function sortedKeys(value: Record<string, unknown>): string[] {
  return Object.keys(value).sort(compareCodePoints);
}

export interface BuildResultOutput {
  result: ResultState;
  fills: ResultFill[];
}

export function buildResult(
  before: ProjectionState,
  delta: ProjectionDelta,
  existing: ResultState = {},
): BuildResultOutput {
  const changes = expectObject(delta.变化, '本回合变化/变化') as Record<string, DeltaOps>;
  const registry = entityRegistry(before, existing);
  const fills: ResultFill[] = [];
  const result: ResultState = {};

  const unknownResult = sortedKeys(existing as Record<string, unknown>)
    .filter((name) => !(name in changes));
  if (unknownResult.length > 0) {
    fail('result_without_change', `result block has unchanged entities: ${unknownResult.join(', ')}`, '本回合状态');
  }

  for (const name of sortedKeys(changes as Record<string, unknown>)) {
    const kind = resolveType(registry, name, `本回合变化/变化/${name}`);
    const ops = expectObject(changes[name], `本回合变化/变化/${name}`) as DeltaOps;
    const beforeBlock = expectObject((before as unknown as Record<string, unknown>)[kind], `上回合状态/${kind}`);
    const beforeEntity = expectObject(beforeBlock[name], `上回合状态/${kind}/${name}`);
    const existingView = existing[name];
    const view: Record<string, unknown> = existingView
      ? { ...(expectObject(existingView, `本回合状态/${name}`)) }
      : {};
    const allowed = RESULT_FIELDS[kind];
    const unknown = sortedKeys(view).filter((field) => !allowed.includes(field));
    if (unknown.length > 0) {
      fail('unknown_result_field', `${name} (${kind}) has unsupported result field(s): ${unknown.join(', ')}`, `本回合状态/${name}`);
    }

    const settle = (field: string, computed: unknown): void => {
      if (field in view) {
        if (!sameResultValue(field, view[field], computed)) {
          fail('result_conflict', `${name}.${field} is ${JSON.stringify(view[field])} but the declared change gives ${JSON.stringify(computed)}`, `本回合状态/${name}/${field}`);
        }
        return;
      }
      view[field] = computed;
      fills.push({ entity: name, type: kind, field, value: computed, source: 'delta' });
    };

    if ('位置' in ops) settle('位置', expectString(ops.位置, `本回合变化/变化/${name}/位置`));
    if ('精神值' in ops) settle('精神值', expectInt(ops.精神值, `本回合变化/变化/${name}/精神值`));
    if ('新增外貌' in ops || '解除外貌' in ops) {
      settle('外貌', applyListChange(beforeEntity['外貌'] ?? [], ops.解除外貌 ?? [], ops.新增外貌 ?? [], `${name}/外貌`));
    }
    if ('新增个性' in ops || '解除个性' in ops) {
      settle('个性', applyListChange(beforeEntity['个性'] ?? [], ops.解除个性 ?? [], ops.新增个性 ?? [], `${name}/个性`));
    }
    if ('完成任务' in ops || '新增小任务' in ops) {
      const computed = taskEntries(beforeEntity, ops, name);
      if (Object.keys(computed).length === 0) {
        fail('empty_tasks', `${name} has task ops but no task result`, `本回合状态/${name}/任务`);
      }
      settle('任务', computed);
    }
    if ('位于' in ops) settle('位于', ops.位于);

    const implied = new Set<string>();
    if ('位置' in ops) implied.add('位置');
    if ('精神值' in ops) implied.add('精神值');
    if ('新增外貌' in ops || '解除外貌' in ops) implied.add('外貌');
    if ('新增个性' in ops || '解除个性' in ops) implied.add('个性');
    if ('完成任务' in ops || '新增小任务' in ops) implied.add('任务');
    if ('位于' in ops) implied.add('位于');
    const extra = sortedKeys(view).filter((field) => !implied.has(field));
    if (extra.length > 0) {
      fail('unchanged_result_field', `${name} repeats unchanged field(s): ${extra.join(', ')}`, `本回合状态/${name}`);
    }
    if (Object.keys(view).length === 0) {
      fail('empty_result_entity', `${name} has changes but no result fields`, `本回合状态/${name}`);
    }
    result[name] = view as ResultPerson | ResultPlace | ResultItem;
  }

  if (Object.keys(changes).length === 0 && Object.keys(existing).length > 0) {
    fail('result_without_change', 'result block is non-empty on a no-change round', '本回合状态');
  }
  return { result, fills };
}

