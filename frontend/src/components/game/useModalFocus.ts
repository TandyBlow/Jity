"use client";

import { useCallback, useEffect, useRef } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

/**
 * Modal behaviour for a fixed overlay: Tab stays inside, Escape closes, and
 * focus goes back to whatever opened it.
 *
 * A full-screen overlay without these is a keyboard trap that only mouse users
 * can leave — which is the state the check overlay is already in.
 */
export function useModalFocus(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  const restoreTo = useRef<HTMLElement | null>(null);
  const close = useCallback(() => onClose(), [onClose]);

  useEffect(() => {
    if (!open) return;
    restoreTo.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const panel = ref.current;
    // Focus the panel, not its first control: opening a drawer must not arm
    // whatever button happens to be first.
    panel?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const items = [...panel.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (element) => element.getClientRects().length > 0,
      );
      if (items.length === 0) {
        event.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || active === panel || active === document.body)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      restoreTo.current?.focus();
    };
  }, [open, close]);

  return ref;
}
