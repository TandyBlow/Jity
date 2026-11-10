/** Draft cleanup. The player sees only prose: reasoning traces, template
 * tokens, markdown fences, prompt labels and repeated sentences are removed
 * before verification. A draft that is only labels/JSON is reported as empty,
 * never "fixed" into something that looks like narration. */
import { stripBareReasoning, stripThinking } from './template';

export interface CleanResult {
  text: string;
  /** A ` thinking` block or a bare reasoning preface was removed. */
  removedThinking: boolean;
  /** Lines that looked like prompt labels (`【本次变化】`, `正文：`). */
  echoedLabels: string[];
  /** Sentences dropped because they repeated an earlier sentence verbatim. */
  repeatedSentences: string[];
}

/** A whole line that is only a heading (`【本次变化】`) is dropped; a label
 * prefix with content after it (`正文：……`) keeps the content. */
const PURE_LABEL = /^\s*(?:【[^】]{1,10}】|\[[^\]]{1,10}\])\s*$/;
const LABEL_PREFIX = /^\s*(?:正文|叙事|输出|回答|场景|小说正文|旁白)\s*[:：]\s*/;
const META_TAIL = /[（(]\s*(?:约|共|全文)?\s*\d{2,4}\s*字\s*[)）]\s*$/;
const FENCE = /```[a-zA-Z]*\n?|```/g;

function isProseStart(line: string): boolean {
  return !/^\s*(?:[-*•]|\d+[.、)]|[{}\[\]])/.test(line);
}

export function cleanDraft(raw: string): CleanResult {
  const echoedLabels: string[] = [];
  let text = raw.replace(/\r\n?/g, '\n');
  const beforeThink = text;
  text = stripThinking(text);
  let removedThinking = text !== beforeThink;
  const bare = stripBareReasoning(text);
  text = bare.text;
  removedThinking ||= bare.stripped;

  text = text.replace(FENCE, '');

  const kept: string[] = [];
  for (const line of text.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) { kept.push(''); continue; }
    if (PURE_LABEL.test(trimmed)) { echoedLabels.push(trimmed.slice(0, 24)); continue; }
    if (LABEL_PREFIX.test(trimmed)) {
      echoedLabels.push(trimmed.slice(0, 24));
      const rest = trimmed.replace(LABEL_PREFIX, '').trim();
      if (rest) kept.push(rest);
      continue;
    }
    if (/^(?:以下是|这是|好的|当然)[^。]{0,20}[:：]$/.test(trimmed)) { echoedLabels.push(trimmed.slice(0, 24)); continue; }
    kept.push(trimmed);
  }
  text = kept.join('\n');

  // An opening quote wrapping the whole draft is a quotation, not prose.
  text = text.trim().replace(/^[“"「『]+/, '').replace(/[”"」』]+$/, '');
  text = text.replace(META_TAIL, '').trim();

  const paragraphs = text.split(/\n{2,}/).map((part) => part.replace(/\n+/g, '').trim()).filter(Boolean);
  const seen = new Set<string>();
  const repeatedSentences: string[] = [];
  const seenHeads = new Set<string>();
  const deduped = paragraphs.map((paragraph) => paragraph.split(/(?<=[。！？])/).filter(Boolean).map((sentence) => {
    const key = sentence.trim();
    // Exact repeats and near-repeats (same 12-char opening) are the visible
    // form of a small-model loop; the second copy adds nothing.
    const head = key.slice(0, 12);
    if (seen.has(key) || (key.length > 16 && seenHeads.has(head))) {
      repeatedSentences.push(key.slice(0, 40));
      return '';
    }
    seen.add(key);
    seenHeads.add(head);
    return sentence;
  }).join('')).filter(Boolean);

  text = deduped.join('\n\n').trim();
  // A short leading fragment before the first real sentence ("好。").
  if (deduped.length && deduped[0].length <= 3 && deduped.length > 1) text = deduped.slice(1).join('\n\n');

  return { text, removedThinking, echoedLabels, repeatedSentences };
}

/** Structural checks that do not need the fact packet. */
export function shapeIssues(text: string): { kind: 'not_prose' | 'prompt_echo' | 'thinking_leaked' | 'empty_output'; detail: string }[] {
  const issues: { kind: 'not_prose' | 'prompt_echo' | 'thinking_leaked' | 'empty_output'; detail: string }[] = [];
  if (!text.trim()) { issues.push({ kind: 'empty_output', detail: 'draft has no prose after cleanup' }); return issues; }
  const lines = text.split('\n').filter(Boolean);
  const bullet = lines.filter((line) => /^\s*(?:[-*•]|\d+[.、)])\s/.test(line)).length;
  if (bullet >= 2 || /^[\[{]/.test(text.trim()) || /"kind"\s*:/.test(text)) {
    issues.push({ kind: 'not_prose', detail: 'draft is a list/JSON, not prose' });
  }
  const labels = (text.match(/【[^】]{1,10}】/g) ?? []).length;
  if (labels >= 2 || /(?:写作规则|必须写到|本次变化)[:：]/.test(text)) {
    issues.push({ kind: 'prompt_echo', detail: 'draft repeats the instructions' });
  }
  if (/<think>|Thinking Process|思考过程[:：]/.test(text)) {
    issues.push({ kind: 'thinking_leaked', detail: 'reasoning trace survived cleanup' });
  }
  if (!isProseStart(lines[0] ?? '')) issues.push({ kind: 'not_prose', detail: 'draft does not start with prose' });
  return issues;
}
