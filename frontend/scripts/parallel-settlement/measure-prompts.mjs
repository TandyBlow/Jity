import { createServer } from 'vite';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
const root = process.cwd();
const vite = await createServer({ root, configFile: false, logLevel: 'warn', cacheDir: '../.local/vite-measure', server: { middlewareMode: true, hmr: false }, appType: 'custom' });
try {
  const { buildInitialState } = await vite.ssrLoadModule('/src/lib/world-engine/local/state.ts');
  const { createSettlementHandlers } = await vite.ssrLoadModule('/src/lib/world-engine/local/semantics/settlement/index.ts');
  const world = JSON.parse(await readFile(join(root, 'public/worlds/dragon-raja-free-day.world.json'), 'utf8'));
  const state = buildInitialState(world.initial);
  const order = ['lu', 'nono'];
  const prompts = [];
  const engine = { info: { backend: 'probe', modelId: 'none' }, async load() {}, async dispose() {}, async complete(prompt) { prompts.push(prompt); throw new Error('probe'); } };
  const handlers = createSettlementHandlers({ engine, options: { maxPromptChars: 1_000_000 } });
  await handlers.updates('group_probe', {
    groupId: 'group_probe', mode: 'group',
    results: { lu: '路明非走到工具箱旁，蹲下把箱盖掀开。', nono: '诺诺蹲下，掀开路明非的袖口查看伤口。' },
    workingState: state,
  });
  const sections = prompts.map((prompt, index) => {
    const lines = prompt.split('\n');
    const catalogStart = lines.findIndex((line) => line.startsWith('地点和容器'));
    const headerEnd = lines.findIndex((line) => line.startsWith('你是中文跑团游戏'));
    const facts = lines.slice(0, headerEnd);
    const catalog = catalogStart >= 0 ? lines.slice(catalogStart) : [];
    const middle = lines.slice(headerEnd, catalogStart >= 0 ? catalogStart : lines.length);
    return { index, chars: prompt.length, factsChars: facts.join('\n').length, middleChars: middle.join('\n').length, catalogChars: catalog.join('\n').length, catalogLines: catalog.length };
  });
  console.log(JSON.stringify(sections, null, 1));
} finally { await vite.close(); }
