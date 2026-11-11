"use client";

import type { CSSProperties } from "react";

import type { GateChip, GatePhase } from "@/lib/game/actionGate";

const PASSED_PHASES: GatePhase[] = ["closing", "waiting", "done", "leaving"];

function gateLabel(phase: GatePhase, active: GateChip | null): string {
  if (phase === "running") return active ? `${active.label} 行动中` : "行动中";
  if (phase === "closing") return "行动结束";
  if (phase === "waiting") return "行动中";
  if (phase === "leaving") return "检查完毕";
  if (phase === "done") return "检查完毕";
  return "行动中";
}

/**
 * Display-only rail: the cast stands to the right of the door, walks through
 * one body per second, and ends dimmed on the left. No focus targets and no
 * pointer events; the live region announces the queue once instead of every
 * animation frame.
 */
export function ActionGateTrack({
  chips,
  phase,
  activeIndex,
  revealedCount,
}: {
  chips: GateChip[];
  phase: GatePhase;
  activeIndex: number;
  revealedCount: number;
}) {
  // Preserve timeline indices when removing chips from the visual layout.
  const visible = chips.map((chip, timelineIndex) => ({ chip, timelineIndex }))
    .filter(({ chip }) => !chip.dropped);
  const candidate = activeIndex >= 0 ? chips[activeIndex] ?? null : null;
  const active = candidate?.dropped ? null : candidate;
  const allPassed = PASSED_PHASES.includes(phase);

  return (
    <section
      aria-label={`行动检查：${visible.map(({ chip }) => chip.label).join(" → ")}`}
      aria-live="polite"
      className={`action-gate is-${phase}`}
      data-testid="action-gate"
      role="status"
    >
      <div aria-hidden="true" className="gate-baseline" />
      <div aria-hidden="true" className="gate-door" />
      <div className="gate-label" data-testid="gate-label">{gateLabel(phase, active)}</div>
      <ol className="gate-chips">
        {visible.map(({ chip, timelineIndex }, index) => {
          const passed = allPassed || (phase === "running" && timelineIndex < activeIndex);
          const passing = phase === "running" && timelineIndex === activeIndex;
          const revealed = allPassed || timelineIndex < revealedCount;
          const className = [
            "gate-chip",
            revealed ? "is-revealed" : "",
            passed ? "is-passed" : passing ? "is-passing" : "is-pending",
            phase === "leaving" ? "is-leaving" : "",
          ]
            .filter(Boolean)
            .join(" ");
          const style = {
            "--gate-i": index,
            "--gate-n": visible.length,
          } as CSSProperties;
          return (
            <li className={className} data-testid="gate-chip" key={chip.id} style={style}>
              <span aria-hidden="true" className="gate-chip-initial">{chip.label.slice(0, 1)}</span>
              <span className="gate-chip-name">{chip.label}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
