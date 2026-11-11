/**
 * Pure rules for the action-gate track: who walks through the gate, in what
 * order, and how long the track runs. No React, no DOM — the hook and the
 * component both consume these values, and the tests pin them directly.
 */

/** One second per character: the whole reveal budget is count × this. */
export const GATE_SLOT_MS = 1000;
/** Chips land 70 ms apart (the spec asks for 60–80 ms). */
export const GATE_REVEAL_STAGGER_MS = 70;
/** Beat between the last arrival and the narration hand-off. */
export const GATE_CLOSE_MS = 200;
/** Chips fade out left-to-right after the narration ends. */
export const GATE_LEAVE_MS = 260;
/** More than five bodies and the track stops being readable. */
export const GATE_MAX_CHIPS = 5;
/** The player is always the first check. */
export const GATE_PLAYER_LABEL = "你";

export type GateChip = {
  id: string;
  label: string;
  /** 0 for a named character; N for the "+N" tail that stands for the rest. */
  aggregate: number;
  /** Silently removed after the response (never inserted mid-animation). */
  dropped?: boolean;
};

export type GatePhase =
  | "idle"
  | "running"
  | "closing"
  | "waiting"
  | "done"
  | "leaving";

/** Statuses that mean "this NPC is in the scene right now". */
const PRESENT_STATUSES = new Set(["present", "following", "在场", "同行", "已接触"]);

/**
 * Build the chips. Above the limit the track keeps `limit - 1` named chips and
 * closes with one aggregate chip, so the runtime still fits the 5 second cap.
 */
export function buildGateChips(names: string[], limit: number = GATE_MAX_CHIPS): GateChip[] {
  const unique = [...new Set(names.map((name) => name.trim()).filter(Boolean))];
  if (unique.length <= limit) {
    return unique.map((label, index) => ({ id: `chip-${index}`, label, aggregate: 0 }));
  }
  const kept = unique.slice(0, Math.max(1, limit - 1));
  return [
    ...kept.map((label, index) => ({ id: `chip-${index}`, label, aggregate: 0 })),
    {
      id: "chip-aggregate",
      label: `+${unique.length - kept.length}`,
      aggregate: unique.length - kept.length,
    },
  ];
}

/**
 * Cast approximation: the generation response is all-or-nothing, so the front
 * end cannot know "this turn's" cast up front. Use the NPCs that are present
 * now, ordered by where they first spoke last turn, then the remaining state
 * order. The player always leads.
 */
export function selectGateCast(
  npcs: Array<{ name?: string; status?: string }> | null | undefined,
  previous: { dialogue?: Array<{ speaker?: string }> } | null | undefined,
): string[] {
  const present = (npcs ?? []).filter(
    (npc) => npc?.name && (!npc.status || PRESENT_STATUSES.has(npc.status)),
  );
  const presentNames = new Set(present.map((npc) => npc.name as string));
  const ordered: string[] = [];

  for (const line of previous?.dialogue ?? []) {
    const speaker = (line?.speaker ?? "").trim();
    if (speaker && presentNames.has(speaker) && !ordered.includes(speaker)) ordered.push(speaker);
  }
  for (const npc of present) {
    const name = npc.name as string;
    if (!ordered.includes(name)) ordered.push(name);
  }
  return [GATE_PLAYER_LABEL, ...ordered];
}

/** Animation length for the pass phase only; the 200 ms close beat is extra. */
export function gatePassDurationMs(chipCount: number): number {
  return Math.max(0, chipCount) * GATE_SLOT_MS;
}
