// 冻结前诊断：把候选程序句送进冻结判分器，看必述是否通过、残差是否被标记。
// 用法（仓库根）：
//   OUT=%TEMP%/c6-eval-build; node ../../world-components-worktree/frontend/node_modules/typescript/bin/tsc \
//     frontend/src/lib/world-engine/runtime/narration-split-eval.ts \
//     --target es2022 --module commonjs --moduleResolution node --skipLibCheck --outDir "$(cygpath -w "$OUT")"
//   node experiments/world-components/parallel/scene_expression/probe_sentences.mjs
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const build = join(process.env.TEMP, 'c6-eval-build', 'runtime');
const evalMod = await import(pathToFileURL(join(build, 'narration-split-eval.js')).href);
const samplesMod = await import(pathToFileURL(join(build, 'narration-split-samples.js')).href);
const by = new Map(samplesMod.NARRATION_SPLIT_SAMPLES.map((s) => [s.id, s]));

const cases = [
  ['ns-task-time-1', '时间已到中午。'],
  ['ns-task-time-1', '约一分钟过去了。时间已到中午。学生A完成了任务「坚持到中午」。'],
  ['ns-pers-1', '约一分钟过去了。学生B的理智值升为12。学生B完成了任务「帮主角熟悉校园」。'],
  ['ns-task-1', '约两分钟过去了。主角完成了任务「取回柜子里的东西」。'],
  ['ns-empty-1', '约两分钟过去了。'],
  ['ns-cont-1', '约两秒过去了。学生A从走廊来到了大厅。'],
];

for (const [id, text] of cases) {
  const r = evalMod.evaluateNarration(by.get(id), text);
  console.log('==', id, JSON.stringify(text));
  console.log('   missing:', JSON.stringify(r.omissions));
  console.log('   residue:', JSON.stringify(r.fabricationFlags));
}
