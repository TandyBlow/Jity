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
  /** Every committed narration in this turn, in point order: the player's
   * point first, then the automatic rounds that continued it. Restoring joins
   * them, so later auto prose never erases the player's paragraph. */
  points?: { pointId: string; text: string; source?: NarrationSourceNote['source'] }[];
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
  const allPoints = Object.values(record.points ?? {}).sort((a, b) => a.sequence - b.sequence);
  const points = allPoints.filter((point) => point.trigger === 'player');

  const entryFor = (point: { id: string; sequence: number }, index: number): RestoredTurn => {
    // A turn owns its player point plus every automatic point up to the next
    // player point. Joining their committed narrations keeps the whole turn.
    const start = allPoints.findIndex((row) => row.id === point.id);
    const end = allPoints.findIndex((row) => row.trigger === 'player' && row.sequence > point.sequence);
    const group = allPoints.slice(start, end < 0 ? allPoints.length : end);
    const parts = group.map((row) => {
      const narration = record.narrations?.[row.id];
      const ready = narration?.status === 'ready' && Boolean(narration.text);
      const provenance = snapshot.narrationSources?.[row.id];
      const source = provenance?.source;
      return { pointId: row.id, text: ready ? (narration?.text ?? '') : '', source };
    }).filter((part) => part.text);
    const text = parts.map((part) => part.text.trim()).filter(Boolean).join('\n\n');
    const sources = parts.map((part) => part.source).filter(Boolean);
    // The entry's own source is the player point's (the first paragraph).
    // Later automatic points are labelled individually in `points`; a draft
    // among them does not relabel the player's accepted prose as a draft.
    const source = parts[0]?.source;
    const note = parts.length === 0
      ? '这一回合的正文没有保存成功，刷新后无法显示原文。'
      : sources.includes('draft')
        ? '这一回合里有旧存档留下的未核对草稿（当前版本不会再产生这种段落）。'
        : sources.includes('program')
          ? '这一回合里有程序按已结算事实成文的段落（降级，不是模型正文）。'
          : sources.includes('mixed')
            ? '这一回合的正文混有程序按已结算事实写出的句子。'
            : null;
    return {
      key: -1 - point.sequence,
      input: snapshot.commands[index] ?? '',
      text,
      points: parts.length ? parts : undefined,
      note,
      source,
      ms: null, draftMs: null, acceptedMs: null, programMs: null, mixedMs: null,
      restored: true as const,
    };
  };

  // When the save has a command->point map, a failed command keeps its own
  // empty slot instead of borrowing the next command's prose.
  const commandPointIds = Array.isArray(snapshot.commandPointIds) && snapshot.commandPointIds.length === snapshot.commands.length
    ? snapshot.commandPointIds : null;
  if (commandPointIds) {
    const byId = new Map(allPoints.map((point) => [point.id, point]));
    return commandPointIds.map((id, index) => {
      const point = id ? byId.get(id) : undefined;
      if (!point) {
        return {
          key: -1 - index, input: snapshot.commands[index] ?? '', text: '',
          note: '这一句没有结算成功；已结算的部分仍然保留，可以重试。', unfinished: true,
          ms: null, draftMs: null, acceptedMs: null, programMs: null, mixedMs: null, restored: true as const,
        };
      }
      return entryFor(point, index);
    });
  }

  const entries: RestoredTurn[] = points.map((point, index) => entryFor(point, index));
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
