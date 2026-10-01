import { describe, expect, it } from "vitest";

import { diffMemory } from "./memoryDiff";

const card = (name: string, description = "旧卡", location = "口袋") => ({ name, description, location, status: "owned" });

describe("diffMemory", () => {
  it("reports names that only the later state holds", () => {
    const diff = diffMemory([card("旧卡")], [card("旧卡"), card("新卡")]);

    expect(diff.added).toEqual(["新卡"]);
    expect(diff.removed).toEqual([]);
    expect(diff.changed).toEqual([]);
  });

  it("reports names that only the earlier state held", () => {
    const diff = diffMemory([card("旧卡"), card("被丢的卡")], [card("旧卡")]);

    expect(diff.removed).toEqual(["被丢的卡"]);
    expect(diff.added).toEqual([]);
  });

  it("names the fields that changed, key order aside", () => {
    const diff = diffMemory(
      [card("旧卡", "铁盒")],
      [{ status: "owned", location: "口袋", description: "火漆", name: "旧卡" }],
    );

    expect(diff.changed).toEqual([{ name: "旧卡", fields: ["description"] }]);
  });

  it("treats a missing field and an empty one as the same", () => {
    // Both sides came through the server's normalization, so this is the
    // shape a comparison actually sees.
    const diff = diffMemory([{ name: "旧卡", notes: "" }], [{ name: "旧卡" }]);

    expect(diff.changed).toEqual([]);
  });

  it("ignores entries with no name", () => {
    const diff = diffMemory([{ description: "无名字" }], []);

    expect(diff.removed).toEqual([]);
  });

  it("returns empty lists when nothing moved", () => {
    const diff = diffMemory([card("旧卡")], [card("旧卡")]);

    expect(diff).toEqual({ added: [], removed: [], changed: [] });
  });
});
