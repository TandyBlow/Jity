// @vitest-environment jsdom
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ActionGateTrack } from "./ActionGateTrack";
import { buildGateChips } from "@/lib/game/actionGate";

function renderTrack(activeIndex: number, revealedCount: number) {
  const chips = buildGateChips(["你", "离场人物", "留场人物"]);
  chips[1].dropped = true;
  const container = document.createElement("div");
  container.innerHTML = renderToStaticMarkup(createElement(ActionGateTrack, {
    chips, phase: "running", activeIndex, revealedCount,
  }));
  return container;
}

describe("gate chips after a character leaves", () => {
  it("keeps the active label and moving chip on the same character", () => {
    const view = renderTrack(2, 3);
    expect(view.querySelector('[data-testid="gate-label"]')?.textContent).toBe("留场人物 行动中");
    expect(view.querySelectorAll(".is-passing")).toHaveLength(1);
    expect(view.querySelector(".is-passing .gate-chip-name")?.textContent).toBe("留场人物");
    expect(view.querySelectorAll('[data-testid="gate-chip"]')).toHaveLength(2);
    expect(view.textContent).not.toContain("离场人物");
  });

  it("does not move the next character during a dropped character's slot", () => {
    const view = renderTrack(1, 3);
    expect(view.querySelector('[data-testid="gate-label"]')?.textContent).toBe("行动中");
    expect(view.querySelectorAll(".is-passing")).toHaveLength(0);
    expect(view.querySelector(".is-pending .gate-chip-name")?.textContent).toBe("留场人物");
  });

  it("uses timeline positions for reveal timing and compact positions for layout", () => {
    const view = renderTrack(0, 2);
    const last = view.querySelectorAll('[data-testid="gate-chip"]')[1];
    expect(last.classList.contains("is-revealed")).toBe(false);
    expect(last.getAttribute("style")).toContain("--gate-i:1");
    expect(last.getAttribute("style")).toContain("--gate-n:2");
  });
});
