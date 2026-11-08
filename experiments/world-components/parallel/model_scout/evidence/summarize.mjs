// Turn the raw probe files into one table, so every number quoted in the
// report can be re-derived instead of typed by hand.
//
//   node evidence/summarize.mjs
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const FILES = [
  ['MNN-Pocket-0.3B Q4_1 (QAT, recommended)', 'probe-Q4_1-ctx2048-r2.json'],
  ['MNN-Pocket-0.3B Q4_1, world-page settings (ctx 2048, enable_thinking kwarg)', 'probe-Q4_1-ctx2048-pagekw.json'],
  ['MNN-Pocket-0.3B Q4_1, narration-eval settings (ctx 4096, enable_thinking kwarg)', 'probe-Q4_1-ctx4096-pagekw.json'],
  ['MNN-Pocket-0.3B Q8_0', 'probe-Q8_0-ctx2048.json'],
  ['control: Qwen3-0.6B Q4_K_M (existing baseline)', 'control-qwen3-0.6b.json'],
];
const median = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};

const rows = FILES.map(([label, file]) => {
  const report = JSON.parse(readFileSync(resolve(here, file), 'utf8'));
  const runs = report.runs ?? [];
  const totalMemoryMB = report.memorySamples?.afterLoad?.wall?.totalMB ?? null;
  return {
    label, file, status: report.status,
    model: report.config.model, modelBytes: report.config.modelBytes, modelSha256: report.config.modelSha256,
    generalName: report.modelMetadata?.meta?.['general.name'] ?? null,
    architecture: report.modelMetadata?.meta?.['general.architecture'] ?? null,
    fileType: report.modelMetadata?.meta?.['general.file_type'] ?? null,
    libllama: report.libllamaVersion, wllama: report.assets.wllamaVersion, browser: report.browser?.version,
    threads: report.topology?.numThreads ?? null, multithread: report.topology?.multithread ?? null,
    webgpuVisible: report.environment?.webgpuVisible ?? null,
    webgpuSupported: report.webgpuSupported,
    crossOriginIsolated: report.environment?.crossOriginIsolated ?? null,
    loadMs: report.loadMs, memoryAfterLoadMB: totalMemoryMB,
    cpuLoadPercent: report.device?.cpuLoadPercentAtStart ?? null,
    pageErrors: report.pageErrors?.length ?? 0, requestFailures: report.requestFailures?.length ?? 0,
    calls: runs.length,
    promptTokens: runs.map((run) => run.promptTokens),
    prefillTokensPerSec: runs.map((run) => run.prefillTokensPerSec),
    predictedTokens: runs.map((run) => run.predictedTokens),
    decodeTokensPerSec: runs.map((run) => run.decodeTokensPerSec),
    wallMs: runs.map((run) => run.wallMs),
    finishReasons: runs.map((run) => run.finishReason),
    medianWallMs: runs.length ? median(runs.map((run) => run.wallMs)) : null,
    medianPrefillTps: runs.length ? +median(runs.map((run) => run.prefillTokensPerSec)).toFixed(2) : null,
    medianDecodeTps: runs.length ? +median(runs.map((run) => run.decodeTokensPerSec)).toFixed(2) : null,
    outputSha256: runs.map((run) => ({ sha256: null, note: 'raw text kept in the probe file' })),
    outputs: runs.map((run) => run.text),
  };
});

const summary = {
  generatedAt: new Date().toISOString(),
  generator: 'evidence/summarize.mjs',
  prompt: JSON.parse(readFileSync(resolve(here, 'probe-Q4_1-ctx2048-r2.json'), 'utf8')).prompt,
  rows,
};
writeFileSync(resolve(here, 'summary.json'), JSON.stringify(summary, null, 2) + '\n');

const md = ['| run | load s | mem MB | prefill tok/s | decode tok/s | wall s | finish |',
  '|---|---|---|---|---|---|---|'];
for (const row of rows) {
  md.push(`| ${row.label} | ${(row.loadMs / 1000).toFixed(1)} | ${row.memoryAfterLoadMB ?? '-'} | `
    + `${row.prefillTokensPerSec.join(' / ')} | ${row.decodeTokensPerSec.join(' / ')} | `
    + `${(row.wallMs.map((ms) => ms / 1000).join(' / '))} | ${row.finishReasons.join(' / ')} |`);
}
writeFileSync(resolve(here, 'summary.md'), md.join('\n') + '\n');

const outputs = [summary.prompt.text, ''];
for (const row of rows) {
  outputs.push(`=== ${row.label} ===`, `file: ${row.file}`, `model: ${row.model}`,
    `model sha256: ${row.modelSha256}`, `finish: ${row.finishReasons.join(' / ')}`, '');
  row.outputs.forEach((text, index) => outputs.push(`-- call ${index + 1} --`, text, ''));
}
writeFileSync(resolve(here, 'outputs.txt'), outputs.join('\n'));
console.log(md.join('\n'));
