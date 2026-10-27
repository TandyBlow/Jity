// Read-only checks for the archived evidence and its implementation binding.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../../', import.meta.url));
const bytes = (name) => readFileSync(new URL(name, import.meta.url));
const sha = (data) => createHash('sha256').update(data).digest('hex');
const manifest = JSON.parse(bytes('manifest.json'));
const report = JSON.parse(bytes('qwen3-0.6b.json'));
const review = JSON.parse(bytes('review.json'));
for (const [file, digest] of Object.entries(manifest.files)) assert.equal(sha(bytes(file)), digest, file);
assert.equal(sha(bytes('qwen3-0.6b.json')), review.rawReportSha256);
for (const [file, binding] of Object.entries(manifest.sourceBinding)) {
  assert.equal(report.source.sha256[file], binding.recordedWorkingSha256);
  const blob = execFileSync('git', ['-c', `safe.directory=${root.replaceAll('\\', '/')}`, '-C', root,
    'show', `${manifest.implementationCommit}:${file}`]);
  assert.equal(sha(blob), binding.implementationGitBlobSha256, file);
}
assert.equal(report.status, 'COMPLETED');
assert.equal(report.crossOriginIsolated, true);
assert.deepEqual(report.topology, { multithread: true, numThreads: 4 });
assert.equal(report.rows.length, 6);
assert.deepEqual(report.rows.map((row) => row.id), review.rows.map((row) => row.id));
for (const [index, row] of report.rows.entries()) {
  assert.equal(row.completion.raw, review.rows[index].raw);
  assert.equal(row.completion.finishReason, 'stop');
  assert.ok(row.completion.firstTokenMs >= 0 && row.completion.firstTokenMs <= row.completion.wallMs);
  assert.ok(row.completion.timings.prompt_ms >= 0);
  if (row.task !== 'narration') assert.doesNotThrow(() => JSON.parse(row.completion.raw));
}
assert.equal(review.rows.filter((row) => row.semanticCorrect).length, 3);
assert.equal(review.rows.filter((row) => row.automaticJudgeMiss).length, 1);
console.log('PASS: archive hashes, 8 source bindings, 6 real-browser receipts, and explicit 3/6 content review');
