/** The page's cancel button must stop device work, not only discard the answer.
 *
 * LocalGameModel hands every engine port (semantic handlers, narration, the
 * movement judge) a per-turn AbortSignal. `abortTurn()` aborts that scope, so an
 * in-flight `complete()` sees `signal.aborted` and the engine can terminate its
 * worker instead of finishing a generation nobody will read.
 */
import { describe, expect, it } from 'vitest';
import type { InferenceEngine } from '../runtime/engine';
import type { Json } from '../types';
import { LocalGameModel } from './game-model';
import { tinyWorld } from './narration-input/test-fixtures';

function capturingEngine() {
  const calls: { prompt: string; signal?: AbortSignal }[] = [];
  const engine: InferenceEngine = {
    info: { backend: 'test', modelId: 'capture' },
    load: async () => undefined,
    dispose: async () => undefined,
    complete: async (prompt: string, options?: { signal?: AbortSignal }) => {
      calls.push({ prompt, signal: options?.signal });
      return '{"kind":"skip"}';
    },
  };
  return { engine, calls };
}

describe('LocalGameModel turn abort scope', () => {
  it('attaches the current turn signal to every semantic engine call', async () => {
    const { engine, calls } = capturingEngine();
    const model = new LocalGameModel(engine, { narrationEngine: engine });
    model.beginTurn();
    await model.generate('targets', 'hero', { sourceId: 'hero', actionText: '我看看门口', workingState: tinyWorld() as unknown as Json });
    expect(calls.length).toBeGreaterThan(0);
    expect(calls[0].signal).toBeInstanceOf(AbortSignal);
    expect(calls[0].signal?.aborted).toBe(false);
  });

  it('abortTurn aborts the in-flight scope and refuses new inference', async () => {
    const { engine, calls } = capturingEngine();
    const model = new LocalGameModel(engine, { narrationEngine: engine });
    model.beginTurn();
    const first = model.generate('targets', 'hero', { sourceId: 'hero', actionText: '我看看门口', workingState: tinyWorld() as unknown as Json });
    model.abortTurn();
    await first;
    expect(calls[0].signal?.aborted).toBe(true);
    const before = calls.length;
    // The action handlers turn an aborted call into their program fallback; the
    // evidence that matters is that no further device work started.
    await model.generate('targets', 'hero', {
      sourceId: 'hero', actionText: '我再看一眼', workingState: tinyWorld() as unknown as Json,
    });
    expect(calls.length).toBe(before);
  });

  it('a fresh beginTurn clears the aborted scope for the next action', async () => {
    const { engine, calls } = capturingEngine();
    const model = new LocalGameModel(engine, { narrationEngine: engine });
    model.beginTurn();
    model.abortTurn();
    model.beginTurn();
    await model.generate('targets', 'hero', { sourceId: 'hero', actionText: '我看看门口', workingState: tinyWorld() as unknown as Json });
    expect(calls.at(-1)?.signal?.aborted).toBe(false);
  });
});
