import { describe, expect, it } from "vitest";

import { formatEndingTitle } from "./format";

describe("formatEndingTitle", () => {
  it("shows the title without duplicating a saved epilogue", () => {
    expect(formatEndingTitle("钟楼守望者：诺诺仍会给钟楼留一杯热咖啡。"))
      .toBe("钟楼守望者");
    expect(formatEndingTitle("破晓共犯:众人带着原始档案离开钟楼。"))
      .toBe("破晓共犯");
  });

  it("presents legacy budget endings with story titles", () => {
    expect(formatEndingTitle("回合预算耗尽·未完成的调查：这一局到此结束。"))
      .toBe("未竟的追寻");
    expect(formatEndingTitle("回合预算耗尽·失败的调查：这一局到此结束。"))
      .toBe("无声的终章");
  });

  it("accepts current title-only endings and an empty legacy reason", () => {
    expect(formatEndingTitle("未竟的追寻")).toBe("未竟的追寻");
    expect(formatEndingTitle("钟楼守望者")).toBe("钟楼守望者");
    expect(formatEndingTitle("")).toBe("故事落幕");
  });
});
