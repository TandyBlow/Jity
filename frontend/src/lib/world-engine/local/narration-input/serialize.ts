/** Exact port of `v2_render.serialize` (the serializer the v2 arm was trained
 * with). Every byte, block order, field order and segment offset is part of
 * the shared contract with `experiments/narration-runtime-v2`.
 */
import type {
ProjectionDelta, ProjectionState, ResultState,
  SerializedProjection, SerializedSegment,
} from './types';
import { NarrationInputError } from './types';
import { expectArray, expectInt, expectObject, expectString, isPythonSpace } from './normalize';
import { cleanIdentifier, cleanText, joinItems, taskLine } from './text-rules';
import { entityRegistry, resolveType, type EntityType } from './registry';
import { compareCodePoints } from './code-points';

export const HEADERS = {
  视角: '【视角】',
  地点: '【地点】',
  人物: '【人物】',
  物品: '【物品】',
  变化: '【变化】',
  本回合状态: '【本回合状态】',
  正文: '【正文】',
} as const;

const TYPE_ORDER: EntityType[] = ['地点', '人物', '物品'];

const RESULT_FIELDS: Record<EntityType, readonly string[]> = {
  人物: ['位置', '精神值', '外貌', '个性', '任务'],
  地点: ['位于', '外貌'],
  物品: ['位置', '外貌'],
};

const DELTA_FIELDS: readonly string[] = [
  '位置', '精神值', '解除外貌', '新增外貌', '解除个性', '新增个性', '完成任务', '新增小任务',
];

const DELTA_PREFIX: Record<string, string> = {
  解除外貌: '去掉外貌',
  新增外貌: '多出外貌',
  解除个性: '去掉个性',
  新增个性: '多出个性',
};

class Parts {
  readonly parts: string[] = [];
  private current = 0;

  get length(): number {
    return this.current;
  }

  push(value: string): [number, number] {
    const start = this.current;
    const end = start + Array.from(value).length;
    this.parts.push(value);
    this.current = end;
    return [start, end];
  }

  toString(): string {
    return this.parts.join('');
  }
}

function fail(code: string, message: string, path = ''): never {
  throw new NarrationInputError(code, message, path);
}

function sortedNames(record: Record<string, unknown>): string[] {
  return Object.keys(record).sort(compareCodePoints);
}

function pushSegment(
  segments: SerializedSegment[], kind: SerializedSegment['kind'], block: string,
  entity: string, entityType: string, field: string, value: unknown, start: number, end: number,
): void {
  segments.push({ kind, block, entity, entityType, field, value, charStart: start, charEnd: end });
}

// ------------------------------------------------------------- state lines

function statePlaceLine(
  name: string, entry: Record<string, unknown>, path: string,
  parts: Parts, segments: SerializedSegment[],
): void {
  const [start] = parts.push(name);
  const parent = entry['位于'];
  let parentValue: string | null = null;
  if (parent !== undefined && parent !== null && parent !== '') {
    parentValue = cleanIdentifier(expectString(parent, `${path}/位于`), `${path}/位于`);
    parts.push(`（在${parentValue}里）`);
  }
  const looks = joinItems(entry['外貌'] ?? [], `${path}/外貌`);
  if (looks) {
    parts.push('：');
    parts.push(looks);
  }
  parts.push('。');
  pushSegment(segments, 'state', '地点', name, '地点', '位于', parentValue, start, start + Array.from(name).length);
}

function statePersonLine(
  name: string, entry: Record<string, unknown>, path: string,
  parts: Parts, segments: SerializedSegment[],
): void {
  const [start] = parts.push(name);
  parts.push('：');
  const pieces: string[] = [];
  let position: string | null = null;
  const rawPosition = entry['位置'];
  if (rawPosition !== undefined && rawPosition !== null && rawPosition !== '') {
    position = cleanIdentifier(expectString(rawPosition, `${path}/位置`), `${path}/位置`);
    pieces.push(`在${position}`);
  }
  if ('精神值' in entry) {
    pieces.push(`精神值${expectInt(entry['精神值'], `${path}/精神值`)}`);
  }
  const looks = joinItems(entry['外貌'] ?? [], `${path}/外貌`);
  if (looks) pieces.push(`外貌${looks}`);
  const traits = joinItems(entry['个性'] ?? [], `${path}/个性`);
  if (traits) pieces.push(`个性${traits}`);
  const tasks = entry['任务'];
  if (tasks !== undefined && tasks !== null) {
    pieces.push(`任务${taskLine(tasks, `${path}/任务`)}`);
  }
  if (pieces.length === 0) fail('empty_person', `${path} has no fields`, path);
  const [bodyStart, bodyEnd] = parts.push(pieces.join('，'));
  parts.push('。');
  pushSegment(segments, 'state', '人物', name, '人物', '位置', position, start, start + Array.from(name).length);
  pushSegment(segments, 'state', '人物', name, '人物', 'body', pieces, bodyStart, bodyEnd);
}

function stateItemLine(
  name: string, entry: Record<string, unknown>, path: string,
  parts: Parts, segments: SerializedSegment[],
): void {
  const [start] = parts.push(name);
  // v2 fix: item rows carry `位置`; the legacy converter read `位于` and lost it.
  let position = entry['位置'];
  if (position === null || position === undefined) position = entry['位于'];
  let positionValue: string | null = null;
  if (position !== undefined && position !== null && position !== '') {
    positionValue = cleanIdentifier(expectString(position, `${path}/位置`), `${path}/位置`);
    parts.push(`（位于${positionValue}）`);
  }
  const looks = joinItems(entry['外貌'] ?? [], `${path}/外貌`);
  if (looks) {
    parts.push('：');
    parts.push(looks);
  }
  parts.push('。');
  pushSegment(segments, 'state', '物品', name, '物品', '位置', positionValue, start, start + Array.from(name).length);
}

function renderStateBlock(
  kind: EntityType, entries: Record<string, unknown>, path: string, segments: SerializedSegment[],
): string {
  const parts = new Parts();
  for (const name of sortedNames(entries)) {
    const safeName = cleanIdentifier(name, `${path}/键`);
    const entry = expectObject(entries[name], `${path}/${safeName}`);
    if (kind === '地点') statePlaceLine(safeName, entry, `${path}/${safeName}`, parts, segments);
    else if (kind === '人物') statePersonLine(safeName, entry, `${path}/${safeName}`, parts, segments);
    else stateItemLine(safeName, entry, `${path}/${safeName}`, parts, segments);
  }
  return parts.toString();
}

// ------------------------------------------------------------- delta block

function deltaEntitySentence(
  name: string, rawOps: unknown, kind: EntityType, path: string,
  parts: Parts, segments: SerializedSegment[],
): void {
  const ops = expectObject(rawOps, path);
  if (Object.keys(ops).length === 0) fail('empty_change_entity', `${path} has no operations`, path);
  const pieces: string[] = [];
  for (const field of DELTA_FIELDS) {
    if (!(field in ops)) continue;
    const value = ops[field];
    const fieldPath = `${path}/${field}`;
    if (field === '位置') {
      pieces.push(`移动到${cleanIdentifier(expectString(value, fieldPath), fieldPath)}`);
    } else if (field === '精神值') {
      pieces.push(`精神值变成${expectInt(value, fieldPath)}`);
    } else if (field in DELTA_PREFIX) {
      const joined = joinItems(value, fieldPath);
      if (joined) pieces.push(DELTA_PREFIX[field] + joined);
    } else if (field === '完成任务') {
      const joined = joinItems(value, fieldPath);
      if (joined) pieces.push('完成' + joined);
    } else if (field === '新增小任务') {
      const goals: string[] = [];
      for (const [index, task] of expectArray(value, fieldPath).entries()) {
        const taskPath = `${fieldPath}[${index}]`;
        const taskObject = expectObject(task, taskPath);
        goals.push(cleanText(expectString(taskObject['目标'], `${taskPath}/目标`), `${taskPath}/目标`));
      }
      if (goals.length > 0) pieces.push('新任务' + goals.join('、'));
    }
  }
  const unknown = sortedNames(ops).filter((field) => !DELTA_FIELDS.includes(field));
  if (unknown.length > 0) {
    fail('unknown_change_field', `${path} has unsupported operation(s): ${unknown.join(', ')}`, path);
  }
  if (pieces.length === 0) fail('empty_change_sentence', `${path} operations produce no sentence`, path);
  const [start] = parts.push(`${name}（${kind}）：`);
  const [bodyStart, bodyEnd] = parts.push(pieces.join('，'));
  parts.push('。');
  pushSegment(segments, 'delta', '变化', name, kind, 'body', pieces, bodyStart, bodyEnd);
  pushSegment(segments, 'delta', '变化', name, kind, 'entity', name, start, start + Array.from(name).length);
}

export function renderDelta(
  rawDelta: unknown, registry: Map<string, EntityType>, segments: SerializedSegment[],
): string {
  const delta = expectObject(rawDelta, '本回合变化') as unknown as ProjectionDelta;
  const time = cleanText(expectString(delta.时间推进, '本回合变化/时间推进'), '本回合变化/时间推进');
  const changes = expectObject(delta.变化 ?? {}, '本回合变化/变化');
  const parts = new Parts();
  parts.push(`时间推进${time}。`);
  if (Object.keys(changes).length === 0) {
    parts.push('这一回合没有结算出变化。');
    return parts.toString();
  }
  for (const name of sortedNames(changes)) {
    const safeName = cleanIdentifier(name, '本回合变化/变化/键');
    const kind = resolveType(registry, safeName, `本回合变化/变化/${safeName}`);
    deltaEntitySentence(safeName, changes[name], kind, `本回合变化/变化/${safeName}`, parts, segments);
  }
  return parts.toString();
}

// ------------------------------------------------------------ result block

function resultFieldPhrase(field: string, value: unknown, path: string): string {
  if (field === '位置' || field === '位于') {
    if (value === null) return `${field}（无）`;
    return `${field}${cleanIdentifier(expectString(value, path), path)}`;
  }
  if (field === '精神值') return `精神值${expectInt(value, path)}`;
  if (field === '外貌' || field === '个性') {
    if (!Array.isArray(value)) fail('expected_array', `${path} must be an array`, path);
    if (value.length === 0) return `${field}（空）`;
    const joined = joinItems(value, path);
    return joined ? `${field}${joined}` : `${field}（空）`;
  }
  if (field === '任务') return `任务${taskLine(value, path)}`;
  fail('unknown_result_field', `unsupported result field ${JSON.stringify(field)}`, path);
}

export function renderResult(
  rawResult: unknown, registry: Map<string, EntityType>, segments: SerializedSegment[],
): string {
  const result = expectObject(rawResult, '本回合状态');
  if (Object.keys(result).length === 0) return '';
  const byType: Record<EntityType, string[]> = { 地点: [], 人物: [], 物品: [] };
  for (const name of Object.keys(result)) {
    const safeName = cleanIdentifier(name, '本回合状态/键');
    byType[resolveType(registry, safeName, `本回合状态/${safeName}`)].push(safeName);
  }
  const parts = new Parts();
  for (const kind of TYPE_ORDER) {
    for (const name of byType[kind].sort(compareCodePoints)) {
      const path = `本回合状态/${name}`;
      const view = expectObject(result[name], path);
      const allowed = RESULT_FIELDS[kind];
      const unknown = sortedNames(view).filter((field) => !allowed.includes(field));
      if (unknown.length > 0) {
        fail('unknown_result_field', `${name} (${kind}) has unsupported result field(s): ${unknown.join(', ')}`, path);
      }
      const [start] = parts.push(`${name}（${kind}）：`);
      const phrases: { field: string; phrase: string; value: unknown }[] = [];
      for (const field of allowed) {
        if (!(field in view)) continue;
        const value = view[field];
        const phrase = resultFieldPhrase(field, value, `${path}/${field}`);
        phrases.push({ field, phrase, value });
      }
      if (phrases.length === 0) fail('empty_result_entity', `本回合状态/${name} has no fields`, path);
      for (const [index, entry] of phrases.entries()) {
        if (index > 0) parts.push('，');
        const [fieldStart, fieldEnd] = parts.push(entry.phrase);
        pushSegment(segments, 'result', '本回合状态', name, kind, entry.field, entry.value, fieldStart, fieldEnd);
      }
      parts.push('。');
      pushSegment(segments, 'result', '本回合状态', name, kind, 'entity', name, start, start + Array.from(name).length);
    }
  }
  return parts.toString();
}

// ------------------------------------------------------------------ entry

const TOP_LEVEL_FIELDS = ['视角', '上回合状态', '本回合变化', '本回合状态'] as const;

export function serialize(rawProjection: unknown): SerializedProjection {
  const projection = expectObject(rawProjection, 'projection');
  const missing = TOP_LEVEL_FIELDS.filter((field) => !(field in projection));
  if (missing.length > 0) {
    fail('missing_projection_field', `projection lacks ${missing.join(', ')}`, 'projection');
  }
  const unknown = Object.keys(projection).filter((field) => !(TOP_LEVEL_FIELDS as readonly string[]).includes(field)).sort();
  if (unknown.length > 0) {
    fail('unknown_projection_field', `projection has unsupported field(s): ${unknown.join(', ')}`, 'projection');
  }

  const segments: SerializedSegment[] = [];
  const blocks: Record<string, string> = {};

  let viewpoint = cleanText(expectString(projection['视角'], '视角'), '视角');
  viewpoint = viewpoint.split('；')[0];
  if (!viewpoint) fail('empty_viewpoint', '视角 is empty', '视角');
  blocks['视角'] = viewpoint;
  pushSegment(segments, 'state', '视角', '', '', '视角', viewpoint, 0, Array.from(viewpoint).length);

  const before = expectObject(projection['上回合状态'], '上回合状态') as unknown as ProjectionState;
  const result = expectObject(projection['本回合状态'], '本回合状态') as unknown as ResultState;
  const delta = expectObject(projection['本回合变化'], '本回合变化');
  const registry = entityRegistry(before, result);

  const parts = new Parts();
  parts.push(HEADERS['视角'] + viewpoint);
  for (const kind of TYPE_ORDER) {
    const entries = expectObject((before as unknown as Record<string, unknown>)[kind] ?? {}, `上回合状态/${kind}`);
    const blockSegments: SerializedSegment[] = [];
    const text = renderStateBlock(kind, entries, `上回合状态/${kind}`, blockSegments);
    if (text) {
      const offset = parts.length + Array.from(HEADERS[kind]).length;
      for (const segment of blockSegments) {
        segment.charStart += offset;
        segment.charEnd += offset;
      }
      parts.push(HEADERS[kind] + text);
      blocks[kind] = text;
      segments.push(...blockSegments);
    }
  }

  const deltaSegments: SerializedSegment[] = [];
  const deltaText = renderDelta(delta, registry, deltaSegments);
  const deltaOffset = parts.length + Array.from(HEADERS['变化']).length;
  for (const segment of deltaSegments) {
    segment.charStart += deltaOffset;
    segment.charEnd += deltaOffset;
  }
  parts.push(HEADERS['变化'] + deltaText);
  blocks['变化'] = deltaText;
  segments.push(...deltaSegments);

  const resultSegments: SerializedSegment[] = [];
  const resultText = renderResult(result, registry, resultSegments);
  if (resultText) {
    const resultOffset = parts.length + Array.from(HEADERS['本回合状态']).length;
    for (const segment of resultSegments) {
      segment.charStart += resultOffset;
      segment.charEnd += resultOffset;
    }
    parts.push(HEADERS['本回合状态'] + resultText);
    blocks['本回合状态'] = resultText;
    segments.push(...resultSegments);
  }

  const bodyStart = parts.length;
  parts.push(HEADERS['正文']);
  pushSegment(segments, 'state', '正文', '', '', '正文', '', bodyStart, bodyStart + Array.from(HEADERS['正文']).length);

  const text = parts.toString();
  for (const char of text) {
    if (isPythonSpace(char)) fail('serialized_whitespace', 'serialized input contains whitespace');
  }
  return { text, blocks, segments };
}

export function serializeText(projection: unknown): string {
  return serialize(projection).text;
}

export { DELTA_FIELDS, RESULT_FIELDS, TYPE_ORDER };
