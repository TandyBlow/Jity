"use client";

import { X } from "lucide-react";

import { MemoryPanelBody } from "@/components/game/MemoryPanel";
import type { GameSession } from "@/components/game/useGameSession";
import { useModalFocus } from "@/components/game/useModalFocus";

/**
 * The memory panel below 1100px, where the docked column is hidden.
 *
 * Modal on purpose: a fixed overlay that a keyboard user cannot leave is the
 * defect the check overlay already has, and repeating it here would be worse
 * than the missing panel.
 */
export function MemoryDrawer({
  open,
  onClose,
  session,
}: {
  open: boolean;
  onClose: () => void;
  session: GameSession;
}) {
  const panelRef = useModalFocus(open, onClose);

  if (!open) return null;

  return (
    <div className="memory-drawer">
      <div aria-hidden="true" className="memory-drawer-backdrop" onClick={onClose} />
      <div
        aria-label="记忆面板"
        aria-modal="true"
        className="memory-drawer-panel"
        ref={panelRef}
        role="dialog"
        tabIndex={-1}
      >
        <div className="memory-drawer-head">
          <span>Context Memory</span>
          <button aria-label="关闭记忆面板" onClick={onClose} type="button">
            <X size={16} />
          </button>
        </div>
        <MemoryPanelBody session={session} />
      </div>
    </div>
  );
}
