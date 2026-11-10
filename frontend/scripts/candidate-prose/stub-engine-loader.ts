/** Model-loader stub for the program-only prose candidate.
 *
 * The prose composer never calls an inference engine: every sentence is
 * written from settled facts by deterministic code. The shared browser driver
 * still insists on a loaded engine before it will run any candidate, so this
 * loader satisfies that slot without downloading or loading a model. Evidence
 * must label it as a stub; it is not a model-quality run.
 */
export function loadCandidateModel() {
  const engine = {
    info: { backend: 'program-only (stub loader, no model)', modelId: 'none' },
    async load() {
      /* no-op: nothing to load */
    },
    async complete(): Promise<string> {
      throw new Error('program_composer_does_not_infer');
    },
    async dispose() {
      /* no-op */
    },
  };
  return { engine, backend: 'program-only stub (no model)', loadMs: 0 };
}

export const modelSpec = () => ({ id: 'none' });
