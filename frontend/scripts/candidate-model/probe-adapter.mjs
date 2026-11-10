// Which GPU actually backs WebGPU in this browser?
//
// `n_gpu_layers` is a request, not evidence. This script asks the browser for
// an adapter under both Chromium GPU-preference switches and prints the
// adapter identity plus the limits that determine whether a 4B Q4 model fits.
// It loads no model and runs no inference, so it is cheap enough to run at the
// start of a lease window.
//
//   python ../../.local/parallel-local-game/resource_lease.py acquire --lane 08-runtime --purpose "adapter probe"
//   node scripts/candidate-model/probe-adapter.mjs --out ../.local/candidate-model/adapter.json
//   python ../../.local/parallel-local-game/resource_lease.py release --lane 08-runtime
import { mkdirSync, renameSync, writeFileSync } from 'node:fs';
import { cpus } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const frontend = fileURLToPath(new URL('../../', import.meta.url));
const option = (flag, fallback) => (process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback);
const out = resolve(frontend, option('--out', '../.local/candidate-model/adapter.json'));
const channel = option('--channel', 'msedge');
const headed = process.argv.includes('--headed');

const report = {
  status: 'IN_PROGRESS',
  recordedAt: new Date().toISOString(),
  device: { cpu: cpus()[0]?.model, logicalCpus: cpus().length, platform: process.platform },
  probes: [],
};

const describe = async (page) => page.evaluate(async () => {
  const info = (adapter) => (adapter?.info
    ? { vendor: adapter.info.vendor, architecture: adapter.info.architecture, device: adapter.info.device, description: adapter.info.description }
    : null);
  const limits = (adapter) => (adapter?.limits
    ? {
      maxBufferSize: adapter.limits.maxBufferSize,
      maxStorageBufferBindingSize: adapter.limits.maxStorageBufferBindingSize,
      maxComputeWorkgroupStorageSize: adapter.limits.maxComputeWorkgroupStorageSize,
      maxComputeInvocationsPerWorkgroup: adapter.limits.maxComputeInvocationsPerWorkgroup,
      maxComputeWorkgroupsPerDimension: adapter.limits.maxComputeWorkgroupsPerDimension,
    }
    : null);
  const features = (adapter) => (adapter?.features ? [...adapter.features] : []);
  const result = {
    crossOriginIsolated: globalThis.crossOriginIsolated === true,
    webgpuAvailable: Boolean(navigator.gpu),
    defaultAdapter: null,
    highPerformanceAdapter: null,
    error: null,
  };
  if (!navigator.gpu) return result;
  try {
    const fallback = await navigator.gpu.requestAdapter();
    result.defaultAdapter = fallback ? { info: info(fallback), limits: limits(fallback), features: features(fallback) } : null;
    const fast = await navigator.gpu.requestAdapter({ powerPreference: 'high-performance' });
    result.highPerformanceAdapter = fast ? { info: info(fast), limits: limits(fast), features: features(fast) } : null;
  } catch (error) {
    result.error = String(error?.message ?? error);
  }
  return result;
});

const save = () => {
  mkdirSync(dirname(out), { recursive: true });
  const temp = `${out}.tmp`;
  writeFileSync(temp, `${JSON.stringify(report, null, 2)}\n`);
  renameSync(temp, out);
};

for (const [mode, args] of [
  ['forced-high-performance', ['--force_high_performance_gpu']],
  ['forced-low-power', ['--force_low_power_gpu']],
]) {
  let browser;
  try {
    browser = await chromium.launch({ headless: !headed, channel, args: ['--enable-unsafe-webgpu', ...args] });
    const page = await browser.newPage();
    const blank = await page.evaluate(() => 'ok');
    const probe = await describe(page);
    report.probes.push({ mode, args, browser: browser.version(), blank, ...probe });
    console.log(`[adapter] ${mode}: default=${JSON.stringify(probe.defaultAdapter?.info ?? null)} high=${JSON.stringify(probe.highPerformanceAdapter?.info ?? null)}`);
  } catch (error) {
    report.probes.push({ mode, args, error: String(error?.message ?? error) });
    console.log(`[adapter] ${mode}: FAILED ${error?.message ?? error}`);
  } finally {
    if (browser) await browser.close();
  }
  save();
}

report.status = 'COMPLETED';
report.finishedAt = new Date().toISOString();
save();
console.log(`[adapter] wrote ${out}`);
