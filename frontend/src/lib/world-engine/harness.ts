/** B1 scenario harness. Executes controller segments with the real
 * ControllerDriver against declared corpora: shared-trace steps instantiate
 * their request/response/scope per sample, B-authored preview specimens are
 * inserted at declared positions and marked as such, and harness-issued
 * inspect reads verify the shared independent expectations (projection +
 * digest). The transport never hands expected requests to the driver — it
 * only verifies what the driver derives — and nothing steers driver memory
 * mid-flight. */
import { at, equal, instantiate, readTrace } from './trace-runner';
import { ProtocolError, validateError, validateRequest, validateSuccess } from './protocol';
import { WorldApiError, type WorldTransport } from './transport';
import type { ModelTask } from './schedule';
import type { ControlState, Id, Json, PointWork, Scope, WorldContext, WorldOperation } from './types';

export const PLACEHOLDER_DIGEST = '0'.repeat(64); // schema-valid; never evidence of a real digest

export interface CorpusStep {
  id: string; // shared step id or B-specimen label
  segment: 'controller' | 'preview' | 'command' | 'probe' | 'inspect';
  sharedStepId: string | null;
  operation: WorldOperation;
  request: Json;
  scope: Scope;
  response: Json;
  responseKind: 'success' | 'error';
  placeholderDigests?: boolean;
  expectation?: { projectionPath: string; digestPath: string; expectedProjection: Json; expectedDigest: string };
}

export interface ServedSnapshot { world: WorldContext | null; control: ControlState | null; work: PointWork | null }

export interface Corpus {
  steps: CorpusStep[];
  servedAfter: Record<string, ServedSnapshot>;
  requests: Record<string, Json>;
  sampleId: string;
}

export interface PreviewSpecimenSpec {
  afterStepId: string;
  label: string;
  build: (served: ServedSnapshot) => { workingState: Json; pointProjection: Json; mergedEntityDeltas: Json };
}

/** Instantiates every shared step for one sample (request/scope/response via
 * the trace's own capture discipline), tracks the served state, and inserts
 * B-authored preview specimens at their declared positions. */
export function buildCorpus(rawTrace: unknown, sampleId: string, specimens: PreviewSpecimenSpec[], inspectStepIds: string[]): Corpus {
  const trace = readTrace(rawTrace);
  const sample = trace.samples.find((s) => s.id === sampleId);
  if (!sample) throw new ProtocolError(`Unknown sample ${sampleId}`);
  const bindings: Record<string, unknown> = {};
  const steps: CorpusStep[] = [];
  const servedAfter: Record<string, ServedSnapshot> = {};
  const requests: Record<string, Json> = {};
  for (const step of trace.steps) {
    const request = instantiate(step.request, bindings) as Json;
    const scope = instantiate(step.scope, bindings) as Scope;
    const own = Object.fromEntries(step.captures.map((c) => [c.variable, sample.values[c.variable]]));
    const response = instantiate(step.response, { ...bindings, ...own }) as Json;
    const segment = inspectStepIds.includes(step.id) ? 'inspect' as const : 'controller' as const;
    const digest = sample.expectedDigests[step.id];
    steps.push({
      id: step.id, segment, sharedStepId: step.id, operation: step.operation, request, scope, response,
      responseKind: step.responseKind,
      expectation: digest == null || step.projectionPath == null || step.digestPath == null ? undefined : {
        projectionPath: step.projectionPath, digestPath: step.digestPath,
        expectedProjection: instantiate(step.expectedProjection, sample.values) as Json, expectedDigest: digest,
      },
    });
    requests[step.id] = request;
    const envelope = response as { world?: WorldContext | null; control?: ControlState | null; work?: PointWork | null };
    servedAfter[step.id] = { world: envelope.world ?? null, control: envelope.control ?? null, work: envelope.work ?? null };
    for (const capture of step.captures) bindings[capture.variable] = at(response, capture.path);
    for (const specimen of specimens.filter((p) => p.afterStepId === step.id)) {
      const served = servedAfter[step.id];
      const world = served.world;
      const work = served.work;
      const control = served.control;
      if (!world || !work || !control) throw new ProtocolError(`[${specimen.label}] preview specimen needs served world/control/work after ${step.id}`);
      const built = specimen.build(served);
      steps.push({
        id: specimen.label, segment: 'preview', sharedStepId: null, operation: 'preview_point',
        request: {
          protocolVersion: 2, worldId: world.worldId,
          advanceId: world.advance.advanceId!, roundId: world.activeRoundId ?? world.round?.roundId ?? '',
          pointId: work.pointId, expectedPointId: world.head.pointId, expectedVersion: world.head.version,
          expectedCheckpointRevision: control.revision, timeAdvance: work.timeAdvance,
          settlementGroups: [],
        } as unknown as Json,
        scope: { worldId: world.worldId },
        response: {
          protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
          operation: 'preview_point', world, control, work,
          data: { pointId: work.pointId, pointProjection: built.pointProjection, mergedEntityDeltas: built.mergedEntityDeltas, workingStateDigest: PLACEHOLDER_DIGEST, pointProjectionDigest: PLACEHOLDER_DIGEST, workingState: built.workingState },
        } as unknown as Json,
        responseKind: 'success', placeholderDigests: true,
      });
    }
  }
  return { steps, servedAfter, requests, sampleId };
}

/** Verifies driver-derived calls against the declared corpus: operation,
 * full request (requestId pinned to the factory's current value), scope and
 * global order; responses are schema-validated corpus instances. */
export class ScenarioTransport implements WorldTransport {
  private index = 0;
  readonly ops: WorldOperation[] = [];
  readonly requests: Json[] = [];
  constructor(private readonly steps: CorpusStep[], private readonly currentRequestId: () => Id, private readonly label: string) {}
  get exhausted(): boolean { return this.index >= this.steps.length; }
  /** True once every controller/preview step is consumed and only inspect
   * (harness-issued) steps remain. */
  get controllerDrained(): boolean {
    const next = this.steps[this.index];
    return next == null || (next.segment !== 'controller' && next.segment !== 'preview');
  }
  get consumed(): number { return this.index; }
  async execute(operation: WorldOperation, request: never, scope: never): Promise<never> {
    const step = this.steps[this.index];
    if (!step) throw new ProtocolError(`[${this.label}] call #${this.index + 1} (${operation}) is undeclared: all ${this.steps.length} steps consumed`);
    if (step.operation !== operation) throw new ProtocolError(`[${this.label}] step ${step.id}: declared ${step.operation}, controller sent ${operation}`);
    const sent = request as unknown as Record<string, unknown>;
    const expected: Record<string, unknown> = { ...(step.request as Record<string, unknown>) };
    if (Object.hasOwn(expected, 'requestId')) {
      const current = this.currentRequestId();
      if (sent.requestId !== current) throw new ProtocolError(`[${this.label}] step ${step.id}: requestId ${String(sent.requestId)} is not the factory value ${current}`);
      expected.requestId = current;
    }
    if (!equal(expected, sent)) throw new ProtocolError(`[${this.label}] step ${step.id} request mismatch:\n  declared ${JSON.stringify(expected)}\n  driver   ${JSON.stringify(sent)}`);
    if (!equal(step.scope, scope as unknown as Scope)) throw new ProtocolError(`[${this.label}] step ${step.id} scope mismatch: declared ${JSON.stringify(step.scope)}, driver ${JSON.stringify(scope)}`);
    validateRequest(operation, request);
    const response = structuredClone(step.response);
    if (step.responseKind === 'error') throw new WorldApiError(validateError(response));
    this.index++;
    this.ops.push(operation);
    this.requests.push(structuredClone(sent) as Json);
    return validateSuccess(operation, response) as never;
  }
  /** Harness-issued inspect read: the request IS the declared template; the
   * call still passes through the same order/scope/schema verification. */
  async runInspect(stepId: string): Promise<{ step: CorpusStep; response: Json }> {
    const step = this.steps[this.index];
    if (!step || step.id !== stepId || step.segment !== 'inspect') throw new ProtocolError(`[${this.label}] inspect ${stepId} is not at the execution front (next: ${step?.id ?? 'none'})`);
    const request = { ...(step.request as Record<string, unknown>) };
    if (Object.hasOwn(request, 'requestId')) request.requestId = this.currentRequestId();
    const response = (await this.execute(step.operation, request as never, step.scope as never)) as unknown as Json;
    return { step, response };
  }
  assertConsumed(): void {
    if (this.index !== this.steps.length) throw new ProtocolError(`[${this.label}] declared steps not fully consumed: ${this.steps.length - this.index} left (next: ${this.steps[this.index]?.id ?? 'none'})`);
  }
}

export interface DeclaredModelCall { task: ModelTask; key: string; input: Json; output: Json }

/** Strict model port: task, key, full input and order must match the
 * declared calls; outputs are declared scenario values. */
export class ScenarioModelPort {
  private index = 0;
  readonly calls: { task: ModelTask; key: string; input: Json }[] = [];
  constructor(public readonly declared: DeclaredModelCall[], private readonly label: string) {}
  get exhausted(): boolean { return this.index >= this.declared.length; }
  async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
    const call = this.declared[this.index];
    if (!call) throw new ProtocolError(`[${this.label}] model call #${this.index + 1} (${task}/${key}) is undeclared: all ${this.declared.length} consumed`);
    if (call.task !== task || call.key !== key) throw new ProtocolError(`[${this.label}] model call #${this.index + 1}: declared ${call.task}/${call.key}, controller sent ${task}/${key}`);
    if (!equal(call.input, input)) throw new ProtocolError(`[${this.label}] model call ${call.task}/${call.key} input mismatch:\n  declared ${JSON.stringify(call.input)}\n  controller ${JSON.stringify(input)}`);
    this.index++;
    this.calls.push({ task, key, input: structuredClone(input) });
    return structuredClone(call.output);
  }
  assertConsumed(): void {
    if (this.index !== this.declared.length) throw new ProtocolError(`[${this.label}] declared model calls not fully consumed (next: ${this.declared[this.index]?.task}/${this.declared[this.index]?.key})`);
  }
}

/** Shared independent expectation: digest equality plus the projected state
 * against the trace's expectedProjection — never derived from any actual
 * response body. */
export function assertSharedExpectation(step: CorpusStep, response: Json): void {
  if (!step.expectation) return;
  const digest = at(response, step.expectation.digestPath);
  if (digest !== step.expectation.expectedDigest) throw new ProtocolError(`[${step.id}] shared digest mismatch at ${step.expectation.digestPath}: expected ${step.expectation.expectedDigest}, got ${String(digest)}`);
  const projection = at(response, step.expectation.projectionPath);
  if (!equal(projection, step.expectation.expectedProjection)) throw new ProtocolError(`[${step.id}] shared projection mismatch at ${step.expectation.projectionPath}`);
}
