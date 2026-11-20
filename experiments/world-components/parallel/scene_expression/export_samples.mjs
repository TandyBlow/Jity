// 把冻结样本从 TS 抽出为 JSON（只读源文件，只写本目录 step1/）。
// 用法（仓库根）：
//   node ../../world-components-worktree/frontend/node_modules/typescript/bin/tsc \
//     frontend/src/lib/world-engine/runtime/narration-split-samples.ts \
//     --target es2022 --module commonjs --moduleResolution node --skipLibCheck \
//     --outDir "%TEMP%/c6-samples-build"
//   node experiments/world-components/parallel/scene_expression/export_samples.mjs
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const SOURCE = 'frontend/src/lib/world-engine/runtime/narration-split-samples.ts';
const BUILD = join(process.env.TEMP, 'c6-samples-build', 'runtime', 'narration-split-samples.js');
const OUT = 'experiments/world-components/parallel/scene_expression/step1/narration-split-samples.export.json';

const mod = await import(pathToFileURL(BUILD).href);
const samples = mod.NARRATION_SPLIT_SAMPLES ?? mod.default?.NARRATION_SPLIT_SAMPLES;
if (!samples) throw new Error(`样本未导出: ${BUILD}`);

const doc = {
  source: SOURCE,
  sourceSha256: createHash('sha256').update(readFileSync(SOURCE)).digest('hex'),
  extractedBy: 'tsc --target es2022 --module commonjs（typescript 取自 .local/world-components-worktree/frontend/node_modules）',
  extractedAt: new Date().toISOString(),
  samples,
};
writeFileSync(OUT, JSON.stringify(doc, null, 1), 'utf8');
console.log(`samples=${samples.length} sha256=${doc.sourceSha256} out=${OUT}`);
