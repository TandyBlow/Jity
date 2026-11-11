"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  GATE_CLOSE_MS,
  GATE_LEAVE_MS,
  GATE_MAX_CHIPS,
  GATE_REVEAL_STAGGER_MS,
  GATE_SLOT_MS,
  buildGateChips,
  type GateChip,
  type GatePhase,
} from "@/lib/game/actionGate";
import { automationSuppressed, prefersReducedMotion } from "@/lib/game/motion";

export type ActionGateState = {
  phase: GatePhase;
  chips: GateChip[];
  activeIndex: number;
  revealedCount: number;
  /** True while the gate still holds the narration back. */
  blocking: boolean;
};

export type ActionGate = ActionGateState & {
  /**
   * Start the track for a cast list. Returns true when a timed track actually
   * runs; false for an empty cast, automation-off, or reduced motion (the
   * caller should commit the new narration immediately in that case).
   */
  begin: (names: string[], options?: { waitForOutput?: boolean }) => boolean;
  /** The turn's output arrived; release the hold once the track is done. */
  noteOutput: (keep?: string[]) => void;
  /** Narration finished: fade the chips out and go idle. */
  finishNarration: () => void;
  reset: () => void;
};

const IDLE: ActionGateState = {
  phase: "idle",
  chips: [],
  activeIndex: -1,
  revealedCount: 0,
  blocking: false,
};

/**
 * Timeline for the action-gate track: n slots of one second, a 200 ms closing
 * beat, then either the narration or a breathing "waiting" state.
 *
 * One requestAnimationFrame loop drives everything — no per-chip timers — and
 * every callback checks the refs, so reset()/unmount cannot be resurrected by
 * a stale frame.
 */
export function useActionGate(
  options: { enabled?: boolean; maxChips?: number } = {},
): ActionGate {
  const { enabled = true, maxChips = GATE_MAX_CHIPS } = options;

  const [state, setState] = useState<ActionGateState>(IDLE);
  const frameRef = useRef<number | null>(null);
  const leaveRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startedRef = useRef<number | null>(null);
  const elapsedRef = useRef(0);
  const chipsRef = useRef<GateChip[]>([]);
  const awaitingRef = useRef(false);
  const phaseRef = useRef<GatePhase>("idle");

  const cancelFrame = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
  }, []);

  const cancelLeave = useCallback(() => {
    if (leaveRef.current !== null) {
      clearTimeout(leaveRef.current);
      leaveRef.current = null;
    }
  }, []);

  const apply = useCallback((next: ActionGateState) => {
    // Returning the previous object skips a render when nothing changed.
    setState((previous) =>
      previous.phase === next.phase &&
      previous.activeIndex === next.activeIndex &&
      previous.revealedCount === next.revealedCount &&
      previous.blocking === next.blocking &&
      previous.chips === next.chips
        ? previous
        : next,
    );
  }, []);

  const reset = useCallback(() => {
    cancelFrame();
    cancelLeave();
    startedRef.current = null;
    elapsedRef.current = 0;
    awaitingRef.current = false;
    phaseRef.current = "idle";
    chipsRef.current = [];
    setState(IDLE);
  }, [cancelFrame, cancelLeave]);

  const begin = useCallback(
    (names: string[], beginOptions: { waitForOutput?: boolean } = {}) => {
      cancelFrame();
      cancelLeave();
      const chips = buildGateChips(names, maxChips);
      // Automation/tests and an empty cast both mean "no track at all".
      if (!enabled || chips.length === 0 || automationSuppressed()) {
        reset();
        return false;
      }
      chipsRef.current = chips;
      // The app starts the track after the turn already exists, so there is
      // nothing to wait for. waitForOutput stays available for callers that
      // genuinely stream a later response.
      awaitingRef.current = beginOptions.waitForOutput === true;
      startedRef.current = null;
      elapsedRef.current = 0;

      // Reduced motion still shows the cast, but as the finished state.
      if (prefersReducedMotion()) {
        phaseRef.current = "done";
        apply({ phase: "done", chips, activeIndex: -1, revealedCount: chips.length, blocking: false });
        return false;
      }

      phaseRef.current = "running";
      apply({ phase: "running", chips, activeIndex: 0, revealedCount: 1, blocking: true });

      const tick = (now: number) => {
        if (startedRef.current === null) startedRef.current = now;
        const elapsed = Math.max(0, now - startedRef.current);
        elapsedRef.current = elapsed;
        const slots = chipsRef.current.length;
        const passEnd = slots * GATE_SLOT_MS;
        const closeEnd = passEnd + GATE_CLOSE_MS;
        const revealedCount = Math.min(
          slots,
          Math.floor(elapsed / GATE_REVEAL_STAGGER_MS) + 1,
        );

        let phase: GatePhase;
        let activeIndex = -1;
        if (elapsed < passEnd) {
          phase = "running";
          activeIndex = Math.min(slots - 1, Math.floor(elapsed / GATE_SLOT_MS));
        } else if (elapsed < closeEnd) {
          phase = "closing";
        } else {
          // The animation is over; the gate only keeps breathing if the
          // response has not landed yet.
          phase = awaitingRef.current ? "waiting" : "done";
        }

        phaseRef.current = phase;
        apply({
          phase,
          chips: chipsRef.current,
          activeIndex,
          revealedCount,
          blocking: phase === "running" || phase === "closing" || phase === "waiting",
        });

        if (phase === "running" || phase === "closing") {
          frameRef.current = requestAnimationFrame(tick);
        } else {
          frameRef.current = null;
        }
      };
      frameRef.current = requestAnimationFrame(tick);
      return true;
    },
    [apply, cancelFrame, cancelLeave, enabled, maxChips, reset],
  );

  const noteOutput = useCallback(
    (keep?: string[]) => {
      awaitingRef.current = false;
      if (keep && keep.length) {
        const allowed = new Set(keep);
        chipsRef.current = chipsRef.current.map((chip, index) => {
          if (chip.aggregate > 0 || chip.dropped || allowed.has(chip.label)) return chip;
          // Only trim bodies that have not started their pass yet; removing a
          // chip mid-walk would leave a hole in the track.
          if (index * GATE_SLOT_MS < elapsedRef.current) return chip;
          return { ...chip, dropped: true };
        });
      }
      if (phaseRef.current === "waiting") {
        phaseRef.current = "done";
        apply({
          phase: "done",
          chips: chipsRef.current,
          activeIndex: -1,
          revealedCount: chipsRef.current.length,
          blocking: false,
        });
      }
    },
    [apply],
  );

  const finishNarration = useCallback(() => {
    if (phaseRef.current !== "done") return;
    phaseRef.current = "leaving";
    apply({
      phase: "leaving",
      chips: chipsRef.current,
      activeIndex: -1,
      revealedCount: chipsRef.current.length,
      blocking: false,
    });
    leaveRef.current = setTimeout(() => {
      leaveRef.current = null;
      phaseRef.current = "idle";
      chipsRef.current = [];
      setState(IDLE);
    }, GATE_LEAVE_MS);
  }, [apply]);

  useEffect(
    () => () => {
      cancelFrame();
      cancelLeave();
    },
    [cancelFrame, cancelLeave],
  );

  return { ...state, begin, noteOutput, finishNarration, reset };
}
