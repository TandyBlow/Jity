/** Field-aware normalization ported from `projection_v2.py`.
 *
 * Free text may contain ordinary space, tab or U+3000; those are removed and
 * each removal is recorded. CR/LF and every other whitespace are refused.
 * Entity names, positions and statuses are identifiers: whitespace is an
 * error, not something to rewrite. Numbers are integers; booleans are not.
 */
import type {
  DeltaNewTask, DeltaOps, NarrationProjection, NormalizationEntry, ProjectionState,
  ResultState, RowPlace, RowPerson, RowTasks,
} from './types';
import { NarrationInputError } from './types';

export const SQUASH_WHITESPACE = [' ', '\t', '\u3000'] as const;

/** Python `str.isspace()`: whitespace includes the C0 separators and NEL,
 * which JavaScript's `\s` does not. Reproduce the full set so a NBSP or
 * U+001C is refused rather than treated as ordinary text. */
export function isPythonSpace(char: string): boolean {
  return /[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/u.test(char);
}

function fail(code: string, message: string, path: string): never {
  throw new NarrationInputError(code, message, path);
}

export function expectObject(value: unknown, path: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    fail('expected_object', `${path} must be an object, got ${typeName(value)}`, path);
  }
  return value as Record<string, unknown>;
}

export function expectArray(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) {
    fail('expected_array', `${path} must be an array, got ${typeName(value)}`, path);
  }
  return value;
}

export function expectString(value: unknown, path: string): string {
  if (typeof value !== 'string') {
    fail('expected_string', `${path} must be a string, got ${typeName(value)}`, path);
  }
  return value;
}

export function expectInt(value: unknown, path: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    fail('expected_integer', `${path} must be an integer, got ${typeName(value)}`, path);
  }
  return value;
}

function typeName(value: unknown): string {
  if (value === null) return 'NoneType';
  if (Array.isArray(value)) return 'list';
  if (typeof value === 'boolean') return 'bool';
  if (typeof value === 'number') return Number.isInteger(value) ? 'int' : 'float';
  return typeof value;
}

function checkNoOtherWhitespace(text: string, path: string): void {
  if (text.includes('\r') || text.includes('\n')) {
    fail('newline_not_allowed', `${path} contains a newline`, path);
  }
  for (const char of text) {
    if (isPythonSpace(char) && !(SQUASH_WHITESPACE as readonly string[]).includes(char)) {
      fail('unsupported_whitespace', `${path} contains unsupported whitespace U+${char.codePointAt(0)!.toString(16).toUpperCase().padStart(4, '0')}`, path);
    }
  }
}

export function normalizeFreeText(value: unknown, path: string, ledger: NormalizationEntry[]): string {
  const text = expectString(value, path);
  checkNoOtherWhitespace(text, path);
  const removed: string[] = [];
  let normalized = '';
  for (const char of text) {
    if ((SQUASH_WHITESPACE as readonly string[]).includes(char)) removed.push(char);
    else normalized += char;
  }
  if (removed.length > 0) {
    ledger.push({ path, action: 'remove_whitespace', removed, before: text, after: normalized });
  }
  return normalized;
}

export function normalizeIdentifier(value: unknown, path: string): string {
  const text = expectString(value, path);
  checkNoOtherWhitespace(text, path);
  for (const char of text) {
    if ((SQUASH_WHITESPACE as readonly string[]).includes(char)) {
      fail('whitespace_in_identifier', `${path} contains whitespace ${JSON.stringify(char)}; identifiers are not normalized`, path);
    }
  }
  if (!text) fail('empty_identifier', `${path} is empty`, path);
  return text;
}

function normalizeList(value: unknown, path: string, ledger: NormalizationEntry[]): string[] {
  return expectArray(value, path).map((item, index) => normalizeFreeText(item, `${path}[${index}]`, ledger));
}

function normalizeTasks(value: unknown, path: string, ledger: NormalizationEntry[]): RowTasks {
  const tasks = expectObject(value, path);
  const out: RowTasks = { 小任务: [] };
  const big = tasks['大任务'];
  if (big !== undefined && big !== null) {
    const bigObject = expectObject(big, `${path}/大任务`);
    out.大任务 = {
      目标: normalizeFreeText(bigObject['目标'], `${path}/大任务/目标`, ledger),
      状态: normalizeIdentifier(bigObject['状态'], `${path}/大任务/状态`),
    };
  }
  const small = expectArray(tasks['小任务'] ?? [], `${path}/小任务`);
  for (const [index, task] of small.entries()) {
    const taskPath = `${path}/小任务[${index}]`;
    const taskObject = expectObject(task, taskPath);
    out.小任务.push({
      目标: normalizeFreeText(taskObject['目标'], `${taskPath}/目标`, ledger),
      状态: normalizeIdentifier(taskObject['状态'], `${taskPath}/状态`),
    });
  }
  return out;
}

function normalizePlaces(value: unknown, path: string, ledger: NormalizationEntry[]): Record<string, RowPlace> {
  const entries = expectObject(value, path);
  const out: Record<string, RowPlace> = {};
  for (const [name, raw] of Object.entries(entries)) {
    const safeName = normalizeIdentifier(name, `${path}/键`);
    const entryPath = `${path}/${safeName}`;
    const entry = expectObject(raw, entryPath);
    const place: RowPlace = {
      位于: entry['位于'] === undefined || entry['位于'] === null
        ? null
        : normalizeIdentifier(entry['位于'], `${entryPath}/位于`),
      外貌: normalizeList(entry['外貌'] ?? [], `${entryPath}/外貌`, ledger),
    };
    unknownFields(entry, ['位于', '外貌'], entryPath, 'unknown_state_field');
    out[safeName] = place;
  }
  return out;
}

function normalizePeople(value: unknown, path: string, ledger: NormalizationEntry[]): Record<string, RowPerson> {
  const entries = expectObject(value, path);
  const out: Record<string, RowPerson> = {};
  for (const [name, raw] of Object.entries(entries)) {
    const safeName = normalizeIdentifier(name, `${path}/键`);
    const entryPath = `${path}/${safeName}`;
    const entry = expectObject(raw, entryPath);
    const person: RowPerson = {
      位置: normalizeIdentifier(entry['位置'], `${entryPath}/位置`),
      精神值: expectInt(entry['精神值'], `${entryPath}/精神值`),
      外貌: normalizeList(entry['外貌'] ?? [], `${entryPath}/外貌`, ledger),
      个性: normalizeList(entry['个性'] ?? [], `${entryPath}/个性`, ledger),
      任务: normalizeTasks(entry['任务'], `${entryPath}/任务`, ledger),
    };
    unknownFields(entry, ['位置', '精神值', '外貌', '个性', '任务'], entryPath, 'unknown_state_field');
    out[safeName] = person;
  }
  return out;
}

function normalizeThings(value: unknown, path: string, ledger: NormalizationEntry[]): Record<string, RowItemLike> {
  const entries = expectObject(value, path);
  const out: Record<string, RowItemLike> = {};
  for (const [name, raw] of Object.entries(entries)) {
    const safeName = normalizeIdentifier(name, `${path}/键`);
    const entryPath = `${path}/${safeName}`;
    const entry = expectObject(raw, entryPath);
    const item: RowItemLike = {
      位置: normalizeIdentifier(entry['位置'], `${entryPath}/位置`),
      外貌: normalizeList(entry['外貌'] ?? [], `${entryPath}/外貌`, ledger),
    };
    unknownFields(entry, ['位置', '外貌'], entryPath, 'unknown_state_field');
    out[safeName] = item;
  }
  return out;
}

interface RowItemLike {
  位置: string;
  外貌: string[];
}

function unknownFields(
  entry: Record<string, unknown>, allowed: string[], path: string, code: string,
): void {
  const unknown = Object.keys(entry).filter((key) => !allowed.includes(key)).sort();
  if (unknown.length > 0) {
    fail(code, `${path} has unsupported field(s): ${unknown.join(', ')}`, path);
  }
}

export function normalizeState(value: unknown, path: string, ledger: NormalizationEntry[]): ProjectionState {
  const state = expectObject(value, path);
  const unknown = Object.keys(state).filter((key) => !['地点', '人物', '物品'].includes(key)).sort();
  if (unknown.length > 0) {
    fail('unknown_state_block', `${path} has unsupported block(s): ${unknown.join(', ')}`, path);
  }
  return {
    地点: normalizePlaces(state['地点'] ?? {}, `${path}/地点`, ledger),
    人物: normalizePeople(state['人物'] ?? {}, `${path}/人物`, ledger),
    物品: normalizeThings(state['物品'] ?? {}, `${path}/物品`, ledger),
  } as ProjectionState;
}

function normalizeDelta(value: unknown, path: string, ledger: NormalizationEntry[]): NarrationProjection['本回合变化'] {
  const delta = expectObject(value, path);
  const unknown = Object.keys(delta).filter((key) => !['时间推进', '变化'].includes(key)).sort();
  if (unknown.length > 0) {
    fail('unknown_delta_field', `${path} has unsupported field(s): ${unknown.join(', ')}`, path);
  }
  const changes = expectObject(delta['变化'] ?? {}, `${path}/变化`);
  const outChanges: Record<string, DeltaOps> = {};
  for (const [name, raw] of Object.entries(changes)) {
    const safeName = normalizeIdentifier(name, `${path}/变化/键`);
    const opsPath = `${path}/变化/${safeName}`;
    const ops = expectObject(raw, opsPath);
    const allowed = ['位置', '精神值', '解除外貌', '新增外貌', '解除个性', '新增个性', '完成任务', '新增小任务'];
    const unknownOps = Object.keys(ops).filter((key) => !allowed.includes(key)).sort();
    if (unknownOps.length > 0) {
      fail('unknown_change_field', `${opsPath} has unsupported operation(s): ${unknownOps.join(', ')}`, opsPath);
    }
    const out: DeltaOps = {};
    if ('位置' in ops) out.位置 = normalizeIdentifier(ops['位置'], `${opsPath}/位置`);
    if ('精神值' in ops) out.精神值 = expectInt(ops['精神值'], `${opsPath}/精神值`);
    for (const field of ['解除外貌', '新增外貌', '解除个性', '新增个性', '完成任务'] as const) {
      if (field in ops) {
        out[field] = normalizeList(ops[field], `${opsPath}/${field}`, ledger);
      }
    }
    if ('新增小任务' in ops) {
      const tasks = expectArray(ops['新增小任务'], `${opsPath}/新增小任务`);
      out.新增小任务 = tasks.map((task, index) => {
        const taskPath = `${opsPath}/新增小任务[${index}]`;
        const taskObject = expectObject(task, taskPath);
        const normalized: DeltaNewTask = {
          目标: normalizeFreeText(taskObject['目标'], `${taskPath}/目标`, ledger),
          属于大任务: normalizeFreeText(taskObject['属于大任务'], `${taskPath}/属于大任务`, ledger),
          状态: normalizeIdentifier(taskObject['状态'] ?? '未完成', `${taskPath}/状态`),
        };
        unknownFields(taskObject, ['目标', '属于大任务', '状态'], taskPath, 'unknown_task_field');
        return normalized;
      });
    }
    if (Object.keys(out).length === 0) {
      fail('empty_change_entity', `${opsPath} has no operations`, opsPath);
    }
    outChanges[safeName] = out;
  }
  return {
    时间推进: normalizeFreeText(delta['时间推进'], `${path}/时间推进`, ledger),
    变化: outChanges,
  };
}

function normalizeResult(value: unknown, path: string, ledger: NormalizationEntry[]): ResultState {
  const result = expectObject(value, path);
  const out: ResultState = {};
  for (const [name, raw] of Object.entries(result)) {
    const safeName = normalizeIdentifier(name, `${path}/键`);
    const viewPath = `${path}/${safeName}`;
    const view = expectObject(raw, viewPath);
    const normalized: Record<string, unknown> = {};
    for (const [field, fieldValue] of Object.entries(view)) {
      const fieldPath = `${viewPath}/${field}`;
      if (field === '位置' || field === '位于') {
        normalized[field] = normalizeIdentifier(fieldValue, fieldPath);
      } else if (field === '精神值') {
        normalized[field] = expectInt(fieldValue, fieldPath);
      } else if (field === '外貌' || field === '个性') {
        normalized[field] = normalizeList(fieldValue, fieldPath, ledger);
      } else if (field === '任务') {
        normalized[field] = normalizeTasks(fieldValue, fieldPath, ledger);
      } else {
        fail('unknown_result_field', `${viewPath} has unsupported result field ${JSON.stringify(field)}`, fieldPath);
      }
    }
    out[safeName] = normalized as ResultState[string];
  }
  return out;
}

export interface NormalizedProjection {
  projection: NarrationProjection;
  ledger: NormalizationEntry[];
}

export function normalizeProjection(raw: unknown): NormalizedProjection {
  const projection = expectObject(raw, 'projection');
  const unknown = Object.keys(projection).filter((key) => !['视角', '上回合状态', '本回合变化', '本回合状态'].includes(key)).sort();
  if (unknown.length > 0) {
    fail('unknown_projection_field', `projection has unsupported field(s): ${unknown.join(', ')}`, 'projection');
  }
  const ledger: NormalizationEntry[] = [];
  return {
    projection: {
      视角: normalizeFreeText(projection['视角'], '视角', ledger),
      上回合状态: normalizeState(projection['上回合状态'], '上回合状态', ledger),
      本回合变化: normalizeDelta(projection['本回合变化'], '本回合变化', ledger),
      本回合状态: normalizeResult(projection['本回合状态'], '本回合状态', ledger),
    },
    ledger,
  };
}
