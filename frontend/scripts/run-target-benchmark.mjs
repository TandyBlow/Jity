// Programmatic target-benchmark run: real Chromium (multi-threaded WASM),
// full suite on Qwen3-0.6B, raw JSON export captured from the page.
//
// Usage:
//   node scripts/run-target-benchmark.mjs [baseUrl] [threads]
// Defaults: baseUrl http://localhost:3100, threads 4.
// Output: artifacts/benchmark/target-retest-<timestamp>.json (+ stdout log).
// The dev server must be running; do NOT run `next build` while it is.

import { mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const frontendRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const baseUrl = process.argv[2] ?? "http://localhost:3100";
const threads = process.argv[3] ?? "4";
const MODEL_URL = "/models/Qwen3-0.6B-Q4_K_M.gguf";

const log = (...parts) => console.log(new Date().toISOString().slice(11, 19), ...parts);

async function setPageValue(page, selector, value) {
  await page.$eval(
    selector,
    (element, text) => {
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        "value",
      ).set;
      setter.call(element, text);
      element.dispatchEvent(new Event("input", { bubbles: true }));
    },
    value,
  );
}

function selectorForPlaceholder(fragment) {
  return `input[placeholder*="${fragment}"]`;
}

async function lastStatus(page) {
  return page.evaluate(() => {
    const paragraphs = [...document.querySelectorAll("p")].map((p) => p.textContent ?? "");
    return paragraphs[paragraphs.length - 1] ?? "";
  });
}

async function readTable(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll("tbody tr")].map((row) =>
      [...row.querySelectorAll("td")].map((cell) => cell.textContent?.trim()),
    ),
  );
}

async function launchBrowser() {
  // Prefer the system Edge (real Chromium, no download); fall back to the
  // Playwright-bundled Chromium when the channel is unavailable.
  try {
    return await chromium.launch({ channel: "msedge", headless: true });
  } catch (error) {
    log(`msedge channel unavailable (${error.message.split("\n")[0]}); using bundled chromium`);
    return chromium.launch({ headless: true });
  }
}

async function main() {
  const cpu = os.cpus()[0]?.model ?? "unknown";
  log(`host CPU: ${cpu}`);
  const browser = await launchBrowser();
  const page = await browser.newPage();
  await page.goto(`${baseUrl}/benchmark`);
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(1500);

  const environment = await page.evaluate(() => {
    const sections = [...document.querySelectorAll("section")];
    const lines = (sections[0]?.textContent ?? "").split("\n").map((line) => line.trim());
    return {
      crossOriginIsolated: window.crossOriginIsolated === true,
      panelLines: lines.filter(Boolean),
    };
  });
  log(`crossOriginIsolated: ${environment.crossOriginIsolated}`);
  if (!environment.crossOriginIsolated) {
    console.error("FATAL: page is not cross-origin isolated; multi-thread WASM unavailable.");
    await browser.close();
    process.exit(2);
  }

  // Configure the suite before loading: n_ctx/threads only apply at load time.
  const configRow = page.locator(".bench-config-row");
  const inputs = configRow.locator("input:not([type=checkbox])");
  // Order: 总输入 / 记忆注入 / 生成长度 / prefill 遍数 / n_ctx / 线程 / 4s 生成
  await inputs.nth(0).fill("512,1024,2048");
  await inputs.nth(1).fill("256,512,1024");
  await inputs.nth(2).fill("128");
  await inputs.nth(3).fill("1");
  await inputs.nth(4).fill("4096");
  await inputs.nth(5).fill(threads);
  await inputs.nth(6).fill("512");
  await page.locator("input[type=checkbox]").evaluateAll((boxes) => {
    for (const box of boxes) {
      const label = box.parentElement?.textContent ?? "";
      const want = label.includes("4 秒实测") || label.includes("chat 模板对照");
      if (box.checked !== want) box.click();
    }
  });
  log("config set; loading model…");

  await setPageValue(page, selectorForPlaceholder("模型 URL"), `${baseUrl}${MODEL_URL}`);
  await page.getByRole("button", { name: "从 URL 加载" }).click();
  await page.waitForFunction(
    () =>
      [...document.querySelectorAll("p")]
        .some((p) => (p.textContent ?? "").includes("模型已加载")),
    null,
    { timeout: 180_000 },
  );
  const runtimeText = await page.evaluate(() => {
    const sections = [...document.querySelectorAll("section")];
    return (sections[1]?.textContent ?? "").split("\n").map((line) => line.trim()).filter(Boolean);
  });
  log("model loaded:");
  for (const line of runtimeText.slice(2, 5)) log(`  ${line}`);

  await page.getByRole("button", { name: "运行基准套件" }).click();
  log("suite started; polling…");

  const deadline = Date.now() + 90 * 60_000;
  let finalStatus = "";
  while (Date.now() < deadline) {
    await page.waitForTimeout(15_000);
    finalStatus = await lastStatus(page);
    log(`  ${finalStatus}`);
    if (/套件完成|套件被手动停止|套件中断/.test(finalStatus)) break;
  }
  if (!/套件完成|套件被手动停止|套件中断/.test(finalStatus)) {
    // Stop the suite so whatever it collected can still be exported.
    log("deadline reached; stopping the suite and exporting partial data");
    await page.getByRole("button", { name: "停止" }).click();
    await page
      .waitForFunction(
        () =>
          [...document.querySelectorAll("p")]
            .some((p) => /套件被手动停止|套件完成|套件中断/.test(p.textContent ?? "")),
        null,
        { timeout: 180_000 },
      )
      .catch(() => undefined);
    finalStatus = await lastStatus(page);
  }

  // The exported JSON is the raw report (React state), not the DOM table.
  const downloadPromise = page.waitForEvent("download", { timeout: 30_000 });
  await page.getByRole("button", { name: "导出 JSON 报告" }).click();
  const download = await downloadPromise;
  const outDir = path.join(frontendRoot, "..", "artifacts", "benchmark");
  await mkdir(outDir, { recursive: true });
  const outPath = path.join(outDir, `target-retest-${Date.now()}.json`);
  await download.saveAs(outPath);

  const table = await readTable(page);
  const environmentAfter = await page.evaluate(() => {
    const sections = [...document.querySelectorAll("section")];
    return (sections[0]?.textContent ?? "").split("\n").map((line) => line.trim()).filter(Boolean);
  });

  await writeFile(
    outPath.replace(/\.json$/, ".context.json"),
    JSON.stringify({ hostCpu: cpu, baseUrl, threads, environmentAfter, runtimeText }, null, 2),
  );

  log(`raw JSON saved: ${outPath}`);
  log("results table:");
  for (const row of table) log(`  ${row.join(" | ")}`);

  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
