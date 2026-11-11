"use client";

import { useEffect, useRef, useState } from "react";

import {
  DEFAULT_CHARS_PER_SECOND,
  TypewriterEngine,
  type RandomSource,
} from "@/lib/game/typewriter";

export type UseTypewriterOptions = {
  /** Hard off switch. The full text renders at once when false. */
  enabled?: boolean;
  charsPerSecond?: number;
  /** Injectable randomness (tests pin the punctuation jitter). */
  random?: RandomSource;
};

export type TypewriterState = {
  /** The narration that should currently be on screen. */
  text: string;
  /** True while characters are still being revealed. */
  isTyping: boolean;
  /** True once the complete text is visible. */
  done: boolean;
};

/** Automation override used by the e2e fixtures; also reachable via ?typing=off. */
const SUPPRESS_KEY = "jity_typewriter";

function shouldAnimate(enabled: boolean): boolean {
  if (!enabled || typeof window === "undefined") return false;
  // Accessibility: honour the OS "reduce motion" setting.
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches) return false;
  try {
    if (window.localStorage.getItem(SUPPRESS_KEY) === "off") return false;
  } catch {
    // Storage can throw in private modes; animation is still safe there.
  }
  const param = new URLSearchParams(window.location.search).get("typing");
  return param !== "off";
}

const EMPTY: TypewriterState = { text: "", isTyping: false, done: false };

/**
 * Reveals `text` character by character at roughly 40 chars/second.
 *
 * The reveal is driven by requestAnimationFrame and writes to state at most
 * once per frame — never once per character — so a 4000-character scene does
 * not schedule 4000 renders. The starting state is deliberately empty so the
 * first paint is the placeholder instead of the finished text, which is what
 * would otherwise flash before the animation starts.
 */
export function useTypewriter(
  text: string,
  options: UseTypewriterOptions = {},
): TypewriterState {
  const { enabled = true, charsPerSecond = DEFAULT_CHARS_PER_SECOND, random } = options;

  const [state, setState] = useState<TypewriterState>(EMPTY);
  const frameId = useRef<number | null>(null);

  useEffect(() => {
    if (!shouldAnimate(enabled) || text.length === 0) {
      setState({ text, isTyping: false, done: true });
      return;
    }

    const engine = new TypewriterEngine(text, { charsPerSecond, random });
    setState({ text: "", isTyping: true, done: false });

    let startedAt: number | null = null;
    const step = (timestamp: number) => {
      if (startedAt === null) startedAt = timestamp;
      const frame = engine.tick(timestamp - startedAt);
      if (frame.changed) {
        // One state update per animation frame, batched by React.
        setState((previous) => ({ ...previous, text: frame.text }));
      }
      if (frame.done) {
        frameId.current = null;
        setState({ text, isTyping: false, done: true });
        return;
      }
      frameId.current = requestAnimationFrame(step);
    };
    frameId.current = requestAnimationFrame(step);

    return () => {
      if (frameId.current !== null) cancelAnimationFrame(frameId.current);
      frameId.current = null;
    };
  }, [text, enabled, charsPerSecond, random]);

  return state;
}
