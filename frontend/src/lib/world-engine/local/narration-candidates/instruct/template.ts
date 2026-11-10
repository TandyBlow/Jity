/** Chat templates for the native instruct weights.
 *
 * Qwen2.5-Instruct and Qwen3 both use ChatML, but Qwen3's template adds an
 * explicit empty ` thinking` block when thinking is disabled. Getting this
 * wrong is not cosmetic: a raw ChatML prompt without the empty block makes
 * Qwen3 write a long reasoning trace before the prose. The player only ever
 * sees the stripped prose; the raw output stays in the evidence.
 *
 * The template is selected from the engine's model id by default and may be
 * overridden by the caller. An unknown model is a hard error: guessing a
 * template is exactly the failure lane 02 documented.
 */
import type { EngineInfo } from '../../../runtime/engine';
import type { InstructTemplate } from './types';

export type ResolvedTemplate = Exclude<InstructTemplate, 'auto'>;

export interface ChatTurn { system: string; user: string }

/** `allowUnknown` is for chat mode: the engine's own template renders the
 * turns, so the name is evidence only. Hand-written ChatML (raw mode) must
 * never guess, because a wrong header is exactly the template-mismatch failure
 * lane 02 documented. */
export function resolveTemplate(
  template: InstructTemplate | undefined,
  info: EngineInfo,
  allowUnknown = false,
): ResolvedTemplate | null {
  if (template && template !== 'auto') return template;
  const id = (info.modelId ?? '').toLowerCase();
  if (id.includes('qwen3')) return 'qwen3-instruct';
  if (id.includes('qwen2.5') || id.includes('qwen2_5') || id.includes('qwen25')) return 'qwen2.5-instruct';
  if (allowUnknown) return null;
  throw new Error(`unknown_instruct_template:${info.modelId ?? 'null'}`);
}

const IM_END = '<|im_end|>';

export type PromptMode = 'chat' | 'raw';

/** The engine's own chat template already wraps `complete()` as one user turn
 * (wllama's createChatCompletion with enable_thinking=false), so a raw ChatML
 * render would be double-templated. In chat mode the system text becomes the
 * head of that user turn; in raw mode it is a real system turn. */
export function resolvePromptMode(mode: 'chat' | 'raw' | 'auto' | undefined, info: EngineInfo): PromptMode {
  if (mode === 'chat' || mode === 'raw') return mode;
  return info.backend === 'wllama' ? 'chat' : 'raw';
}

export function renderPrompt(turn: ChatTurn, template: ResolvedTemplate, mode: PromptMode): string {
  if (mode === 'chat') return `${turn.system}

${turn.user}`;
  return renderChatML(turn, template);
}

/** Render one system + one user turn and leave the assistant header open. */
export function renderChatML(turn: ChatTurn, template: ResolvedTemplate): string {
  const open = `<|im_start|>system\n${turn.system}${IM_END}\n<|im_start|>user\n${turn.user}${IM_END}\n<|im_start|>assistant\n`;
  // Qwen3: `enable_thinking=false` in the official template is this empty
  // think block; both weights emit ` thinking` when the header is bare.
  return template === 'qwen3-instruct' ? `${open}<think>\n\n</think>\n\n` : open;
}

/** Stop sequences per template family. `<|im_end|>` is the real EOS; the
 * extra markers catch a model that starts a new fake turn. */
export function stopSequences(template: ResolvedTemplate): string[] {
  return template === 'qwen3-instruct'
    ? [IM_END, '<|endoftext|>', '<|im_start|>']
    : [IM_END, '<|endoftext|>'];
}

const THINK_BLOCK = /<think>[\s\S]*?<\/think>/gi;
const THINK_OPEN = /<think>[\s\S]*$/i;

/** Remove reasoning traces and template artifacts before the player sees text.
 * A partially emitted ` thinking` without a close marker is dropped entirely:
 * showing half a reasoning trace as narration is worse than an empty draft. */
export function stripThinking(raw: string): string {
  let text = raw.replace(THINK_BLOCK, '');
  text = text.replace(THINK_OPEN, '');
  text = text.split(IM_END)[0].replace(/<\|im_start\|>[\s\S]*/g, '');
  text = text.replace(/<\|endoftext\|>/g, '');
  return text;
}

/** Long reasoning traces without the marker (some Qwen3 quants drop it). Only
 * removed when the draft clearly starts with a plan heading. */
const REASONING_HEAD = /^\s*(?:Thinking Process|思考过程|推理过程|分析)[:：]?/i;
export function stripBareReasoning(text: string): { text: string; stripped: boolean } {
  if (!REASONING_HEAD.test(text)) return { text, stripped: false };
  let rest = text.replace(REASONING_HEAD, '').trimStart();
  // Cut at the last explicit prose marker if the trace ends with one.
  const marker = rest.match(/(?:^|\n)\s*(?:正文|叙事正文|场景正文|小说正文)\s*[:：]\s*/);
  if (marker && marker.index !== undefined) rest = rest.slice(marker.index + marker[0].length);
  return { text: rest, stripped: true };
}
