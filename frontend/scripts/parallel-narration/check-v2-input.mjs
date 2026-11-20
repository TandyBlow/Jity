// CPU-only check of the v2 input path used by --template v2.
// Loads lane 01's adapter through Vite (type-stripped, no browser, no model)
// and renders the same dev points the real runner uses. This proves the
// runner will not fail on a missing before/root state before spending a
// real-model lease.
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { createServer } from 'vite';

const frontend = fileURLToPath(new URL('../..', import.meta.url));
const inputWorktree = process.env.INPUT_WORKTREE
  ?? 'D:/others/Jity/.local/parallel-local-game/worktrees/01-input';
const server = await createServer({
  root: frontend, configFile: false, logLevel: 'warn',
  server: { middlewareMode: true, fs: { strict: true, allow: [frontend, inputWorktree] } },
  appType: 'custom',
});
try {
  const { SHORT_STATE } = await server.ssrLoadModule('/src/lib/world-engine/runtime/b3-short-samples.ts');
  const input = await server.ssrLoadModule(
    `/@fs/${inputWorktree}/frontend/src/lib/world-engine/local/narration-input/index.ts`,
  );
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const position = (containerId) => ({ containerId, slotId: null, relativeTo: null });
  const after = clone(SHORT_STATE);
  after.characters.person_a.position = position('hall');
  const cases = [
    { id: 'root', before: null, after: clone(SHORT_STATE), delta: {}, time: null },
    {
      id: 'move', before: clone(SHORT_STATE), after,
      delta: { person_a: { entityId: 'person_a', positionSet: position('hall') } },
      time: { boundary: 'instant', duration: { amount: 0, unit: 'second' } },
    },
  ];
  for (const item of cases) {
    const built = input.buildNarrationInput({
      // The v2 adapter requires a previous state even at the root point. For
      // the root, the settled after-state is the only legal snapshot: an
      // empty delta against it means "nothing changed before this scene".
      before: item.before ?? item.after,
      after: item.after,
      delta: item.delta,
      timeAdvance: item.time,
      viewpointId: 'person_c',
    }, { model: 'result-v2', checkTokenizer: false });
    console.log(`[${item.id}] chars=${built.rendered.text.length} sha=${built.rendered.sha256}`);
    console.log(built.rendered.text);
    console.log('---');
  }
} finally {
  await server.close();
}
