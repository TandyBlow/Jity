import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

/** Browser token-by-token measurement for the fixed 96/64 int8 seq2seq pair. */
test("seq2seq encoder plus decoder-step loop", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/micro-seq2seq-probe");
  await page.waitForFunction(
    () => Boolean((window as unknown as { __probeResult?: unknown }).__probeResult),
    null,
    { timeout: 150_000 },
  );
  const result = await page.evaluate(
    () => (window as unknown as { __probeResult?: unknown }).__probeResult,
  );
  const directory = path.join(process.cwd(), ".visual-out");
  fs.mkdirSync(directory, { recursive: true });
  fs.writeFileSync(path.join(directory, "micro-seq2seq-probe.json"), JSON.stringify(result, null, 1));
  await page.screenshot({ path: path.join(directory, "micro-seq2seq-probe.png"), fullPage: true });
  console.log(JSON.stringify(result));
  const probe = result as { ok?: boolean; fullP50Ms?: number; output?: string; error?: string };
  expect(probe.error).toBeUndefined();
  expect(probe.ok).toBe(true);
  expect(probe.fullP50Ms ?? 0).toBeGreaterThan(0);
  expect((probe.output ?? "").length).toBeGreaterThan(0);
});
