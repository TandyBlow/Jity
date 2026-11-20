// Deterministic prompt dump: no model, no GPU. Renders the exact prompt each
// arm would send for a scenario file so the text can be inspected (and diffed)
// before spending a browser run on it.
//
//   npx tsx scripts/parallel-narration/dump-scene-prompt.mjs \
//     --scenario-file ../../../results/quality/free-day-root-scenario.json \
//     --modes scene,prose,beats
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = fileURLToPath(new URL('../..', import.meta.url));
const option = (flag, fallback) => (process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback);
const scenarioFile = option('--scenario-file', '');
const modes = option('--modes', 'scene,prose,beats').split(',').map((value) => value.trim()).filter(Boolean);
if (!scenarioFile) {
  console.error('usage: --scenario-file <fixture.json> [--modes scene,prose,beats]');
  process.exit(2);
}
const scenario = JSON.parse(readFileSync(resolve(frontend, scenarioFile), 'utf8'));

const { buildLedger } = await import('../../src/lib/world-engine/local/narration-generation/ledger.ts');
const { buildBeatPrompt, planBeats } = await import('../../src/lib/world-engine/local/narration-generation/beats.ts');
const { composeNarrationPrompt } = await import('../../src/lib/world-engine/local/narration-generation/prompt.ts');
const { renderProseFactsPrompt } = await import('../../src/lib/world-engine/local/narration-generation/scene-prompt.ts');

const policy = {
  ...scenario.policy,
  scene: scenario.scene ?? null,
  time: scenario.time ?? null,
  promptShape: undefined,
};
const ledger = buildLedger(scenario.committed, scenario.inputText, null, policy);

for (const mode of modes) {
  if (mode === 'scene') {
    const prompt = composeNarrationPrompt({
      inputText: scenario.inputText, attempt: 0, guidance: '', previousDraft: null, instruction: null,
    }, { ...policy, mode: 'scene' });
    console.log(`\n===== scene (${[...prompt].length} chars) =====\n${prompt}`);
  } else if (mode === 'prose') {
    const prompt = renderProseFactsPrompt({ committed: scenario.committed, policy, scene: policy.scene, priorTail: null });
    console.log(`\n===== prose (${[...prompt].length} chars) =====\n${prompt}`);
  } else if (mode === 'beats') {
    const beats = planBeats({ committed: scenario.committed, ledger, policy, scene: policy.scene });
    console.log(`\n===== beats: ${beats.length} beat(s) =====`);
    for (const beat of beats) {
      const prompt = buildBeatPrompt({ beat, ledger, policy, scene: policy.scene, written: [] });
      console.log(`\n--- ${beat.id} (${beat.kind}, ${[...prompt].length} chars)\n${prompt}`);
    }
  }
}
