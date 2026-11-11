// @vitest-environment jsdom
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useActionGate, type ActionGate } from "@/components/game/useActionGate";

/**
 * The track is a requestAnimationFrame timeline. Tests fake the clock and
 * replace rAF with a 16 ms setTimeout so `vi.advanceTimersByTime` walks the
 * slots deterministically. Visual movement lives in CSS; this suite pins the
 * state machine: caps, blocking, cancellation and the reduced-motion path.
 */

type HookResult = { current: ActionGate | null };

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

function renderGate(options?: Parameters<typeof useActionGate>[0]) {
  const result: HookResult = { current: null };
  function Probe() {
    result.current = useActionGate(options);
    return null;
  }
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(createElement(Probe));
  });
  return {
    gate: () => result.current as ActionGate,
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

describe("useActionGate", () => {
  it("caps the cast at five chips and folds the rest into one aggregate", () => {
    const { gate, unmount } = renderGate();

    act(() => {
      gate().begin(["你", "甲", "乙", "丙", "丁", "戊", "己"]);
    });

    const chips = gate().chips;
    expect(chips).toHaveLength(5);
    expect(chips.slice(0, 4).map((chip) => chip.label)).toEqual(["你", "甲", "乙", "丙"]);
    expect(chips[4].label).toBe("+3");
    expect(chips[4].aggregate).toBe(3);

    unmount();
  });

  it("runs one second per chip, then finishes on its own", () => {
    const { gate, unmount } = renderGate();

    let animated = false;
    act(() => {
      animated = gate().begin(["你"]);
    });
    expect(animated).toBe(true);
    expect(gate().phase).toBe("running");
    expect(gate().blocking).toBe(true);

    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(gate().activeIndex).toBe(0);

    // 1 s pass + 200 ms close, then the gate releases the narration.
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(gate().phase).toBe("done");
    expect(gate().blocking).toBe(false);

    unmount();
  });

  it("can hold longer when a caller asks it to wait for the response", () => {
    const { gate, unmount } = renderGate();

    act(() => {
      gate().begin(["你"], { waitForOutput: true });
    });
    act(() => {
      vi.advanceTimersByTime(1400);
    });
    expect(gate().phase).toBe("waiting");
    expect(gate().blocking).toBe(true);

    act(() => {
      gate().noteOutput(["你"]);
    });
    expect(gate().phase).toBe("done");

    unmount();
  });

  it("cancels a running track so a stale animation cannot resurrect", () => {
    const { gate, unmount } = renderGate();

    act(() => {
      gate().begin(["你", "甲", "乙"]);
    });
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(gate().phase).toBe("running");

    act(() => {
      gate().reset();
    });
    expect(gate().phase).toBe("idle");
    expect(gate().chips).toHaveLength(0);
    expect(gate().blocking).toBe(false);

    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(gate().phase).toBe("idle");

    unmount();
  });

  it("spends one second per chip on the pass phase", () => {
    const { gate, unmount } = renderGate();

    act(() => {
      gate().begin(["你", "甲", "乙"]);
    });

    act(() => {
      vi.advanceTimersByTime(2900);
    });
    expect(gate().phase).toBe("running");

    // 3 s of passes + 200 ms close: crossing 3.1 s must be past the walk.
    act(() => {
      vi.advanceTimersByTime(250);
    });
    expect(gate().phase).toBe("closing");

    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(gate().phase).toBe("done");

    unmount();
  });

  it("stays idle for an empty cast", () => {
    const { gate, unmount } = renderGate();

    let animated = true;
    act(() => {
      animated = gate().begin([]);
    });
    expect(animated).toBe(false);
    expect(gate().phase).toBe("idle");
    expect(gate().blocking).toBe(false);

    unmount();
  });

  it("shows the finished state immediately under reduced motion", () => {
    installMatchMedia(true);
    const { gate, unmount } = renderGate();

    act(() => {
      gate().begin(["你", "诺诺"]);
    });

    expect(gate().phase).toBe("done");
    expect(gate().blocking).toBe(false);
    expect(gate().revealedCount).toBe(2);

    unmount();
  });

  it("does not render a track when automation turns animation off", () => {
    window.localStorage.setItem("jity_typewriter", "off");
    const { gate, unmount } = renderGate();

    act(() => {
      gate().begin(["你", "诺诺"]);
    });

    expect(gate().phase).toBe("idle");
    expect(gate().chips).toHaveLength(0);
    expect(gate().blocking).toBe(false);

    unmount();
  });

  it("fades the chips out after the narration and returns to idle", () => {
    const { gate, unmount } = renderGate();

    act(() => {
      gate().begin(["你"]);
    });
    act(() => {
      vi.advanceTimersByTime(1300);
    });
    expect(gate().phase).toBe("done");

    act(() => {
      gate().finishNarration();
    });
    expect(gate().phase).toBe("leaving");

    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(gate().phase).toBe("idle");
    expect(gate().chips).toHaveLength(0);

    unmount();
  });
});
