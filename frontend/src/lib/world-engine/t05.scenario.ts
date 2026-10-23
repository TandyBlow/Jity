/** T05 pause/narration acceptance. Commands are delivered to the real
 * driver; heartbeat exchanges and the context/final read belong to the
 * harness. All shared responses carry explicit, independent lifecycle
 * assertions before consumption. No preview, apply or digest is invented. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { ControllerDriver, initialMemory } from './controller';
import { buildCorpus, ScenarioModelPort, ScenarioTransport } from './harness';
import { instantiate, readTrace } from './trace-runner';
import type { HarnessCommand } from './schedule';
import type { ControlState, CurrentClaim, Id, Json, WorldContext } from './types';

export type T05PauseOrigin = 'external' | 'budget';

export function buildT05Scenario(sampleId: string, pauseOrigin: T05PauseOrigin = 'external', budgetMax: number | null = 0) {
  const raw = JSON.parse(readFileSync(resolve(process.cwd(), '../design/world-protocol/v2/traces/T05.json'), 'utf8'));
  const trace = readTrace(raw);
  const sample = trace.samples.find((entry) => entry.id === sampleId);
  if (!sample) throw new Error(`Unknown T05 sample ${sampleId}`);
  const requests = new Map(trace.steps.map((step) => [step.id, instantiate(step.request, sample.values) as Record<string, unknown>]));
  const context = instantiate(trace.steps[0].response, sample.values) as unknown as { world: WorldContext; control: ControlState };
  const corpus = buildCorpus(raw, sampleId, [], ['s1', 's9']);
  for (const step of corpus.steps) {
    if (['s2', 's5', 's6'].includes(step.id)) step.segment = 'command';
    if (['s3', 's4'].includes(step.id)) step.segment = 'heartbeat';
  }

  // These rules come from T05's intended lifecycle, not its response
  // bodies: later fixed snapshots may never hide a broken earlier one.
  const lifecycle: [string, boolean, 'pending' | 'none', 'pending' | 'ready', string[]][] = [
    ['s1', false, 'pending', 'pending', ['narration_pending']],
    ['s2', true, 'pending', 'pending', ['narration_pending', 'paused']],
    ['s3', true, 'pending', 'pending', ['narration_pending', 'paused']],
    ['s4', true, 'pending', 'pending', ['narration_pending', 'paused']],
    ['s5', false, 'none', 'pending', ['claim_expired']],
    ['s6', true, 'none', 'pending', ['narration_pending', 'paused']],
    ['s7', true, 'pending', 'pending', ['narration_pending', 'paused']],
    ['s8', true, 'none', 'ready', ['paused']],
  ];
  for (const [stepId, paused, gate, narrationStatus, blockedReasons] of lifecycle) {
    const step = corpus.steps.find((entry) => entry.id === stepId)!;
    step.businessAssertions = [
      { path: '/control/phase', expected: 'select_actor' },
      { path: '/control/paused', expected: paused },
      { path: '/control/canCompute', expected: false },
      { path: '/control/gate/status', expected: gate },
      { path: '/control/blockedReasons', expected: blockedReasons },
      { path: '/world/head/narrationStatus', expected: narrationStatus },
      { path: '/world/head/version', expected: 0 },
      { path: '/world/advance/intentStatus', expected: 'pending' },
      { path: '/world/advance/inputAvailable', expected: true },
      { path: '/world/round/cursor', expected: 0 },
      { path: '/world/round/actedIds', expected: [] },
      { path: '/world/round/visitedIds', expected: [] },
    ];
    if (step.segment === 'command') step.businessAssertions.push({ path: '/data/paused', expected: paused });
  }
  corpus.steps.find((step) => step.id === 's7')!.businessAssertions!.push({ path: '/data/generation', expected: 2 });
  corpus.steps.find((step) => step.id === 's8')!.businessAssertions!.push(
    { path: '/data/generation', expected: 2 },
    { path: '/data/narrationStatus', expected: 'ready' },
  );

  const memory = initialMemory('req_T05', 'browser');
  memory.leaseToken = requests.get('s2')!.leaseToken as Id;
  memory.budget.max = budgetMax;
  // The initial claim is client-held ownership, independently supplied by
  // the renewal request. Resume must retire this expired generation.
  const renewal = requests.get('s4')!;
  memory.narration = {
    pointId: context.world.head.pointId,
    claim: { claimToken: renewal.claimToken, generation: renewal.generation, issuedAtEpochMilli: renewal.issuedAtEpochMilli } as CurrentClaim,
    input: { pointId: context.world.head.pointId, stateDigest: context.world.head.stateDigest },
  };
  const model = new ScenarioModelPort([
    { task: 'narration', key: context.world.head.pointId, input: structuredClone(memory.narration.input), output: requests.get('s8')!.text as Json },
  ], 'T05');
  const transport = new ScenarioTransport(corpus.steps, 'T05');
  const driver = new ControllerDriver({ transport, model }, memory, { world: context.world, control: context.control });
  const pauseCommand: HarnessCommand = { kind: pauseOrigin === 'budget' ? 'budget_exhausted' : 'pause' };
  return { driver, transport, model, corpus, pauseCommand, pauseOrigin };
}
