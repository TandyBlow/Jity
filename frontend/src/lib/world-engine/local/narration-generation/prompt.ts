/** Prompt composition WITHOUT a second fact serializer.
 *
 * The caller/lane-01 serialization (`inputText`) is the model input. This file
 * only inserts an optional task instruction, the previous draft (revise mode)
 * and the grounded repair guidance directly BEFORE the body marker, so the
 * head of the serialized string keeps its trained shape. If the caller wants
 * different placement, `policy.composePrompt` replaces this entirely.
 */
import type { ComposePromptArgs, NarrationPolicy } from './types';

const BODY_MARKERS = ['【正文】', '\n正文：', '\n正文:'] as const;

/** The last body marker wins: a serialized input may contain the word 正文 in
 * an earlier field, and the model continues from the final one. */
function bodyMarkerIndex(inputText: string): number {
  let best = -1;
  for (const marker of BODY_MARKERS) {
    const index = inputText.lastIndexOf(marker);
    if (index > best) best = index;
  }
  return best;
}

export function insertBeforeBody(inputText: string, block: string): string {
  if (!block.trim()) return inputText;
  const index = bodyMarkerIndex(inputText);
  if (index < 0) return `${inputText}\n${block}`;
  const head = inputText.slice(0, index);
  const tail = inputText.slice(index);
  const before = head.length === 0 || head.endsWith('\n') ? '' : '\n';
  const after = tail.startsWith('\n') ? '' : '\n';
  return `${head}${before}${block}${after}${tail}`;
}

export function composeNarrationPrompt(args: ComposePromptArgs, policy: NarrationPolicy): string {
  if (policy.composePrompt) return policy.composePrompt(args);
  const blocks: string[] = [];
  if (args.instruction?.trim()) blocks.push(args.instruction.trim());
  if (args.previousDraft?.trim()) {
    blocks.push(['【上一稿】', args.previousDraft.trim(), '【修订要求】'].join('\n'));
  }
  if (args.guidance.trim()) blocks.push(args.guidance.trim());
  return insertBeforeBody(args.inputText, blocks.join('\n\n'));
}
