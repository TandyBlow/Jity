/** Player-visible history rebuilt from a saved snapshot.
 *
 * The entries are not a second source of truth: each one pairs a stored player
 * command with the narration text the transport committed for that point. A
 * point whose narration never became ready is shown as an unfinished turn, not
 * as an empty or fabricated paragraph.
 */
import type { LocalGameSnapshot, NarrationSourceNote } from './session';

export interface RestoredTurn {
  key: number;
  input: string;
  text: string;
  note: string | null;
  /** How the committed text was produced; a draft is never accepted prose. */
  source?: NarrationSourceNote['source'];
  /** A turn that was submitted but never committed (the page was reloaded or
   * the settlement failed). It is shown as an unfinished entry, never as prose. */
  unfinished?: boolean;
  ms: number | null;
  draftMs: number | null;
  acceptedMs: number | null;
  programMs: number | null;
  mixedMs: number | null;
  restored: true;
}

export function restoredEntries(snapshot: LocalGameSnapshot): RestoredTurn[] {
  const record = snapshot.transport as unknown as {
    points?: Record<string, { id: string; sequence: number; trigger: string }>;
    narrations?: Record<string, { status: string; text: string | null }>;
    advance?: { inputText?: string | null; intentStatus?: string } | null;
  };
  const points = Object.values(record.points ?? {})
    .filter((point) => point.trigger === 'player')
    .sort((a, b) => a.sequence - b.sequence);
  const entries: RestoredTurn[] = points.map((point, index) => {
    const narration = record.narrations?.[point.id];
    const ready = narration?.status === 'ready' && Boolean(narration.text);
    const provenance = snapshot.narrationSources?.[point.id];
    const source = provenance?.source;
    const note = !ready
      ? '这一回合的正文没有保存成功，刷新后无法显示原文。'
      : source === 'draft'
        ? '这一回合的正文没有通过事实自检，保存下来的只是按已结算事实列出的草稿。'
        : source === 'program'
          ? '这一回合的正文由程序按已结算事实成文（降级，不是模型正文）。'
          : source === 'mixed'
            ? '这一回合的正文混有程序按已结算事实写出的句子。'
            : null;
    return {
      key: -1 - point.sequence,
      input: snapshot.commands[index] ?? '',
      text: ready ? (narration?.text ?? '') : '',
      note,
      source,
      ms: null, draftMs: null, acceptedMs: null, programMs: null, mixedMs: null,
      restored: true as const,
    };
  });
  // A submitted command with no committed point is an unfinished turn. It must
  // still be visible after a reload (and must never be shown as prose): the
  // player can see that the sentence was not lost, and retry it.
  const extra = snapshot.commands.length - points.length;
  if (extra > 0) {
    const lastInputs = snapshot.commands.slice(points.length);
    for (const [index, input] of lastInputs.entries()) {
      entries.push({
        key: -1000 - index,
        input,
        text: '',
        note: '上一回合没有完成，已结算的内容仍然保留；可以重新提交这一句。',
        unfinished: true,
        ms: null, draftMs: null, acceptedMs: null, programMs: null, mixedMs: null,
        restored: true as const,
      });
    }
  }
  return entries;
}
