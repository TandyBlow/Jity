import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

type Probe = { ok?: boolean; fullP50Ms?: number; output?: string; error?: string };
type V3Arm = {
  output?: string;
  tokens?: number;
  pointerSelections?: number;
  encodeMs?: number;
  perTokenMs?: number;
  prefillMs?: number;
  calls?: number;
  decodeP50Ms?: number;
  decodeP95Ms?: number;
  fullP50Ms?: number;
  fullP95Ms?: number;
  runs?: unknown[];
};
type V3Probe = {
  ok?: boolean;
  error?: string;
  loadMs?: number;
  sampleId?: string;
  sampleInput?: string;
  samplePrefix?: string;
  expected?: string;
  vocabSize?: number;
  sameTokens?: boolean;
  sameOutput?: boolean;
  benefit?: { perToken?: number; decode?: number; full?: number };
  fixed?: V3Arm;
  kv?: V3Arm;
};

/** Browser measurement: 5M fixed pair, then v3 candidate pointer fixed vs KV. */
test("seq2seq encoder plus decoder-step loop", async ({ page }) => {
  test.setTimeout(240_000);
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
  const probe = result as Probe;
  expect(probe.error).toBeUndefined();
  expect(probe.ok).toBe(true);
  expect(probe.fullP50Ms ?? 0).toBeGreaterThan(0);
  expect((probe.output ?? "").length).toBeGreaterThan(0);

  await page.waitForFunction(
    () => Boolean((window as unknown as { __v3ProbeResult?: unknown }).__v3ProbeResult),
    null,
    { timeout: 180_000 },
  );
  const v3 = await page.evaluate(
    () => (window as unknown as { __v3ProbeResult?: unknown }).__v3ProbeResult,
  ) as V3Probe;
  console.log(JSON.stringify(v3));
  const evidence = path.resolve(
    process.cwd(),
    "..",
    "artifacts",
    "goal",
    "micro-workflow",
    "micro-generative",
  );
  fs.mkdirSync(evidence, { recursive: true });
  const shared = {
    loadMs: v3.loadMs,
    sampleId: v3.sampleId,
    sampleInput: v3.sampleInput,
    samplePrefix: v3.samplePrefix,
    expected: v3.expected,
    vocabSize: v3.vocabSize,
    sameTokensAcrossDecoders: v3.sameTokens,
    sameOutputAcrossDecoders: v3.sameOutput,
  };
  fs.writeFileSync(
    path.join(evidence, "browser-v3-fixed.json"),
    JSON.stringify({ method: "fixed-prefix", ...shared, ...v3.fixed }, null, 1),
  );
  fs.writeFileSync(
    path.join(evidence, "browser-v3-kv.json"),
    JSON.stringify({ method: "past-kv", ...shared, ...v3.kv, benefit: v3.benefit }, null, 1),
  );
  expect(v3.error).toBeUndefined();
  expect(v3.ok).toBe(true);
  expect((v3.fixed?.output ?? "").length).toBeGreaterThan(0);
  expect((v3.kv?.output ?? "").length).toBeGreaterThan(0);
  expect(v3.sameOutput).toBe(true);
  expect(v3.fixed?.pointerSelections ?? 0).toBeGreaterThan(0);
  expect(v3.kv?.pointerSelections ?? 0).toBeGreaterThan(0);
  expect(v3.fixed?.fullP50Ms ?? 0).toBeGreaterThan(0);
  expect(v3.kv?.fullP50Ms ?? 0).toBeGreaterThan(0);
});
