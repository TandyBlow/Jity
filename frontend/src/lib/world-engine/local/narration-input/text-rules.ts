/** Text rules shared by both serializers, ported from `v2_render.py`.
 * Whitespace the format cannot represent is refused, never rewritten. */
import { NarrationInputError } from './types';
import { isPythonSpace, SQUASH_WHITESPACE } from './normalize';

export function cleanText(value: unknown, path: string): string {
  if (typeof value !== 'string') {
    throw new NarrationInputError('expected_string', `${path} must be a string`, path);
  }
  if (value.includes('\r') || value.includes('\n')) {
    throw new NarrationInputError('newline_not_allowed', `${path} contains a newline`, path);
  }
  for (const char of value) {
    if ((SQUASH_WHITESPACE as readonly string[]).includes(char)) {
      throw new NarrationInputError('whitespace_not_allowed', `${path} contains whitespace ${JSON.stringify(char)}; normalize it before serializing`, path);
    }
    if (isPythonSpace(char)) {
      throw new NarrationInputError('unsupported_whitespace', `${path} contains unsupported whitespace U+${char.codePointAt(0)!.toString(16).toUpperCase().padStart(4, '0')}`, path);
    }
  }
  return value;
}

export function cleanIdentifier(value: unknown, path: string): string {
  const text = cleanText(value, path);
  if (!text) throw new NarrationInputError('empty_identifier', `${path} is empty`, path);
  return text;
}

export function stripTrailingPunctuation(text: string): string {
  return text.replace(/[。；，]+$/u, '');
}

export function joinItems(value: unknown, path: string): string {
  if (!Array.isArray(value)) {
    throw new NarrationInputError('expected_array', `${path} must be an array, got ${typeof value}`, path);
  }
  const parts: string[] = [];
  for (const [index, item] of value.entries()) {
    const text = stripTrailingPunctuation(cleanText(item, `${path}[${index}]`));
    if (text) parts.push(text);
  }
  return parts.join('、');
}

interface TaskLike {
  目标?: unknown;
  状态?: unknown;
}

function taskStatus(value: unknown, path: string): string {
  // Python `str(value)`; normalization already guarantees a string.
  return cleanIdentifier(value === undefined ? '' : String(value), path);
}

/** `大任务` then the flat `小任务` list. The text carries goal + status only;
 * the parent link and depth live in the structured metadata. */
export function taskLine(value: unknown, path: string): string {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new NarrationInputError('expected_object', `${path} must be an object`, path);
  }
  const tasks = value as { 大任务?: TaskLike | null; 小任务?: unknown };
  const parts: string[] = [];
  const big = tasks.大任务;
  if (big !== undefined && big !== null) {
    if (typeof big !== 'object' || Array.isArray(big)) {
      throw new NarrationInputError('expected_object', `${path}/大任务 must be an object`, `${path}/大任务`);
    }
    const goal = cleanText(big.目标, `${path}/大任务/目标`);
    const status = taskStatus(big.状态, `${path}/大任务/状态`);
    parts.push(`${goal}（${status}）`);
  }
  const small = tasks.小任务 ?? [];
  if (!Array.isArray(small)) {
    throw new NarrationInputError('expected_array', `${path}/小任务 must be an array`, `${path}/小任务`);
  }
  for (const [index, task] of small.entries()) {
    const taskPath = `${path}/小任务[${index}]`;
    if (!task || typeof task !== 'object' || Array.isArray(task)) {
      throw new NarrationInputError('expected_object', `${taskPath} must be an object`, taskPath);
    }
    const entry = task as TaskLike;
    const goal = cleanText(entry.目标, `${taskPath}/目标`);
    const status = taskStatus(entry.状态, `${taskPath}/状态`);
    parts.push(`${goal}（${status}）`);
  }
  if (parts.length === 0) {
    throw new NarrationInputError('empty_tasks', `${path} contains no task entries`, path);
  }
  return parts.join('；');
}
