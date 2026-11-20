import { createServer } from 'vite';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
const root = process.cwd();
const vite = await createServer({ root, configFile: false, logLevel: 'warn', cacheDir: '../.local/vite-cat', server: { middlewareMode: true, hmr: false }, appType: 'custom' });
try {
  const { buildInitialState } = await vite.ssrLoadModule('/src/lib/world-engine/local/state.ts');
  const world = JSON.parse(await readFile(join(root, 'public/worlds/dragon-raja-free-day.world.json'), 'utf8'));
  const state = buildInitialState(world.initial);
  const lines = [];
  for (const id of Object.keys(state.initial.locations)) {
    const e = state.initial.locations[id];
    lines.push({ kind: 'loc', id, line: `${id}=${e.name}[${(e.slots ?? []).map((s) => s.id).join(',')}]` });
  }
  for (const id of Object.keys(state.initial.items)) {
    const e = state.initial.items[id];
    lines.push({ kind: 'item', id, line: `${id}=${e.name}[${(e.slots ?? []).map((s) => s.id).join(',')}]` });
  }
  for (const id of Object.keys(state.initial.characters)) {
    const e = state.initial.characters[id];
    lines.push({ kind: 'char', id, line: `${id}=${e.name}[${(e.slots ?? []).map((s) => s.id).join(',')}]` });
  }
  const by = {};
  for (const row of lines) {
    by[row.kind] = by[row.kind] ?? { n: 0, chars: 0 };
    by[row.kind].n += 1;
    by[row.kind].chars += row.line.length + 1;
  }
  console.log('total', lines.reduce((s, r) => s + r.line.length + 1, 0));
  console.log(JSON.stringify(by));
  console.log(lines.filter((r) => r.kind === 'char').slice(0, 3).map((r) => r.line).join('\n'));
  console.log(lines.filter((r) => r.kind === 'item').slice(0, 3).map((r) => r.line).join('\n'));
} finally { await vite.close(); }
