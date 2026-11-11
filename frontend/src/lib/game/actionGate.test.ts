import { describe, expect, it } from "vitest";

import {
  GATE_MAX_CHIPS,
  GATE_SLOT_MS,
  buildGateChips,
  gatePassDurationMs,
  selectGateCast,
} from "./actionGate";

describe("buildGateChips", () => {
  it("keeps every name up to the cap", () => {
    expect(buildGateChips(["你", "诺诺"]).map((chip) => chip.label)).toEqual(["你", "诺诺"]);
  });

  it("folds the overflow into one aggregate chip so the track still fits", () => {
    const chips = buildGateChips(["你", "甲", "乙", "丙", "丁", "戊"]);
    expect(chips).toHaveLength(GATE_MAX_CHIPS);
    expect(chips.at(-1)).toMatchObject({ label: "+2", aggregate: 2 });
  });

  it("drops duplicates and blank names", () => {
    expect(buildGateChips(["你", "你", " ", "诺诺"])).toHaveLength(2);
  });

  it("returns an empty track for an empty cast", () => {
    expect(buildGateChips([])).toEqual([]);
  });
});

describe("gatePassDurationMs", () => {
  it("is one second per chip", () => {
    expect(gatePassDurationMs(3)).toBe(3 * GATE_SLOT_MS);
    expect(gatePassDurationMs(0)).toBe(0);
  });
});

describe("selectGateCast", () => {
  const npcs = [
    { name: "诺诺", status: "已接触" },
    { name: "古德里安教授", status: "仅提及" },
    { name: "芬格尔", status: "在场" },
  ];

  it("puts the player first and orders speakers by their first line", () => {
    const cast = selectGateCast(npcs, {
      dialogue: [{ speaker: "芬格尔" }, { speaker: "诺诺" }, { speaker: "芬格尔" }],
    });
    expect(cast).toEqual(["你", "芬格尔", "诺诺"]);
  });

  it("appends present NPCs that did not speak, in state order", () => {
    const cast = selectGateCast(npcs, { dialogue: [{ speaker: "诺诺" }] });
    expect(cast).toEqual(["你", "诺诺", "芬格尔"]);
  });

  it("excludes NPCs that are not in the scene", () => {
    const cast = selectGateCast(npcs, { dialogue: [{ speaker: "古德里安教授" }] });
    expect(cast).not.toContain("古德里安教授");
  });

  it("still produces the player alone when nobody is present", () => {
    expect(selectGateCast([], null)).toEqual(["你"]);
    expect(selectGateCast(undefined, undefined)).toEqual(["你"]);
  });
});
