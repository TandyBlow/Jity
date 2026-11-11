// @vitest-environment jsdom
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CLAUSE_PAUSE_BOUNDS,
  SENTENCE_PAUSE_BOUNDS,
  clausePause,
  jitteredPause,
  sentencePause,
} from "@/lib/game/typewriter";
import { useTypewriter, type TypewriterState } from "@/lib/game/useTypewriter";

/**
 * The hook is driven by requestAnimationFrame. The tests fake the clock and
 * replace rAF with a 16 ms setTimeout, so `vi.advanceTimersByTime` walks the
 * reveal at a deterministic pace instead of racing a real browser.
 *
 * createElement is used instead of JSX so this file stays a plain .ts module;
 * the project's vitest pipeline does not transform JSX.
 */

type HookResult = { current: TypewriterState };

/** Neutral draw: jitter factor is exactly 1.0, so beats equal their base. */
const NEUTRAL = () => 0.5;

function installMatchMedia(matches: boolean): void {
  const stub = (query: string) => ({
    matches,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  });
  (window as unknown as { matchMedia: typeof stub }).matchMedia = stub;
}

function installFrames(): void {
  // Return the real timeout id: cancelAnimationFrame must be able to stop the
  // pending frame, otherwise a reset() would still be overwritten by a stale
  // tick and the cancellation test would silently pass.
  vi.stubGlobal("requestAnimationFrame", (callback: (time: number) => void) =>
    setTimeout(() => callback(Date.now()), 16) as unknown as number,
  );
  vi.stubGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id));
}

function renderTypewriter(text: string, options?: Parameters<typeof useTypewriter>[1]) {
  const result: HookResult = { current: { text: "", isTyping: false, done: false } };
  function Probe() {
    result.current = useTypewriter(text, options);
    return null;
  }
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(createElement(Probe));
  });
  return {
    result,
    unmount: () => {
      act(() => {
        root.unmount();
      });
      container.remove();
    },
  };
}

beforeEach(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  vi.setSystemTime(0);
  installFrames();
  installMatchMedia(false);
  window.localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  delete (window as unknown as { matchMedia?: unknown }).matchMedia;
  window.localStorage.clear();
});

describe("useTypewriter", () => {
  it("reveals characters over time instead of rendering the whole text at once", () => {
    const { result, unmount } = renderTypewriter("你好世界", {
      charsPerSecond: 40,
      random: NEUTRAL,
    });

    expect(result.current.text).toBe("");
    expect(result.current.isTyping).toBe(true);

    act(() => {
      vi.advanceTimersByTime(60);
    });
    expect(result.current.text.length).toBeGreaterThan(0);
    expect(result.current.text.length).toBeLessThan(4);

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.text).toBe("你好世界");
    expect(result.current.isTyping).toBe(false);
    expect(result.current.done).toBe(true);

    unmount();
  });

  it("adds the sentence pause after a full stop", () => {
    const { result, unmount } = renderTypewriter("好。好", {
      charsPerSecond: 40,
      random: NEUTRAL,
    });

    act(() => {
      // The first frame lands at 16 ms; two characters at 25 ms each need ~41 ms.
      vi.advanceTimersByTime(50);
    });
    expect(result.current.text).toBe("好。");

    // Inside the 200 ms beat: still the same two characters.
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(result.current.text).toBe("好。");

    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current.text).toBe("好。好");

    unmount();
  });

  it("adds the shorter clause pause after a comma", () => {
    const { result, unmount } = renderTypewriter("好，好", {
      charsPerSecond: 40,
      random: NEUTRAL,
    });

    act(() => {
      vi.advanceTimersByTime(50);
    });
    expect(result.current.text).toBe("好，");

    // The 90 ms clause beat is shorter than the sentence beat: 100 ms is past
    // it, whereas the same wait would still be inside a sentence pause.
    act(() => {
      vi.advanceTimersByTime(60);
    });
    expect(result.current.text).toBe("好，");

    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(result.current.text).toBe("好，好");

    unmount();
  });

  it("treats a run of ellipses as one pause", () => {
    const { result, unmount } = renderTypewriter("等等……走", {
      charsPerSecond: 100,
      random: NEUTRAL,
    });

    act(() => {
      vi.advanceTimersByTime(60);
    });
    expect(result.current.text).toBe("等等……");

    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(result.current.text).toBe("等等……");

    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current.text).toBe("等等……走");

    unmount();
  });

  it("counts an emoji as a single character", () => {
    const { result, unmount } = renderTypewriter("你好🐉", {
      charsPerSecond: 1000,
      random: NEUTRAL,
    });

    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(result.current.text).toBe("你好🐉");
    expect(Array.from(result.current.text)).toHaveLength(3);
    expect(result.current.done).toBe(true);

    unmount();
  });

  it("renders the full text at once when reduced motion is requested", () => {
    installMatchMedia(true);
    const { result, unmount } = renderTypewriter("你好世界");

    expect(result.current.text).toBe("你好世界");
    expect(result.current.isTyping).toBe(false);
    expect(result.current.done).toBe(true);

    unmount();
  });

  it("honours the automation opt-out stored by the e2e fixtures", () => {
    window.localStorage.setItem("jity_typewriter", "off");
    const { result, unmount } = renderTypewriter("你好世界");

    expect(result.current.text).toBe("你好世界");
    expect(result.current.done).toBe(true);

    unmount();
  });
});

describe("punctuation jitter", () => {
  it("uses the documented base beats at a neutral draw", () => {
    expect(sentencePause(NEUTRAL)).toBe(200);
    expect(clausePause(NEUTRAL)).toBe(90);
  });

  it("keeps both ends of the ±30% draw inside the hard bounds", () => {
    expect(sentencePause(() => 0)).toBe(140); // 200 × 0.7
    expect(sentencePause(() => 1)).toBe(260); // 200 × 1.3
    expect(clausePause(() => 0)).toBe(63); // 90 × 0.7
    expect(clausePause(() => 1)).toBe(117); // 90 × 1.3

    for (let step = 0; step <= 100; step += 1) {
      const draw = step / 100;
      expect(sentencePause(() => draw)).toBeGreaterThanOrEqual(SENTENCE_PAUSE_BOUNDS.min);
      expect(sentencePause(() => draw)).toBeLessThanOrEqual(SENTENCE_PAUSE_BOUNDS.max);
      expect(clausePause(() => draw)).toBeGreaterThanOrEqual(CLAUSE_PAUSE_BOUNDS.min);
      expect(clausePause(() => draw)).toBeLessThanOrEqual(CLAUSE_PAUSE_BOUNDS.max);
    }
  });

  it("clamps hostile bases so one character can never stall the scene", () => {
    expect(jitteredPause(10_000, () => 1, SENTENCE_PAUSE_BOUNDS)).toBe(SENTENCE_PAUSE_BOUNDS.max);
    expect(jitteredPause(-5_000, () => 1, SENTENCE_PAUSE_BOUNDS)).toBe(SENTENCE_PAUSE_BOUNDS.min);
  });

  it("falls back to the neutral beat when the source is not a number", () => {
    expect(jitteredPause(200, () => Number.NaN, SENTENCE_PAUSE_BOUNDS)).toBe(200);
  });
});
