// G6 1.2: the runtime narration path must not call the development quality
// gate. The gate exists for offline review; importing it at runtime would
// change what the player reads (D-004 keeps the raw model text).
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const localRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');

function walk(path: string, out: string[] = []): string[] {
  for (const entry of readdirSync(path)) {
    const full = join(path, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.(ts|tsx)$/.test(full) && !/\.test\.ts$/.test(full)) out.push(full);
  }
  return out;
}

const runtimeFiles = [
  ...walk(join(localRoot, 'narration-generation')),
  ...walk(join(localRoot, 'point-narration')),
  join(localRoot, 'game-model.ts'),
  join(localRoot, 'session.ts'),
  resolve(localRoot, '../../../app/world-local/page.tsx'),
];

describe('runtime narration boundary', () => {
  it('never imports the development quality gate from the runtime path', () => {
    const offenders = runtimeFiles.filter((file) => {
      const source = readFileSync(file, 'utf8');
      return /from\s+['"][^'"]*narration-quality[^'"]*['"]/u.test(source)
        || /from\s+['"][^'"]*\/gate['"]/u.test(source);
    }).map((file) => file.replaceAll('\\', '/').split('/').pop());
    expect(offenders).toEqual([]);
  });

  it('finds the runtime files it is supposed to scan', () => {
    expect(runtimeFiles.length).toBeGreaterThanOrEqual(6);
  });
});
