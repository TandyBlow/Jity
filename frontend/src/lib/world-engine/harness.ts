/** B1 scenario harness. Executes controller segments with the real
 * ControllerDriver against declared corpora: shared-trace steps instantiate
 * their request/response/scope per sample (input-origin variables preloaded
 * exactly like the shared interpreter), B-authored preview specimens are
 * inserted at declared positions and marked as such. Every served response
 * is held to the corpus' runtime identity: the declared digest chain between
 * capture and reference positions, the shared independent expectations —
 * at serve time, not only on harness-issued inspects — scenario-declared
 * alignments that bind a final preview's served body and digest to a later
 * independent expectation, and scenario-declared independent digest pins for
 * fields no later reference consumes. Error steps are consumed linearly like
 * any recorded HTTP exchange: served once, captures and chain applied from
 * the error body, then the segment continues at the next declared step —
 * the driver's reaction must match that step. The transport never hands
 * expected requests to the driver and reads nothing from driver memory:
 * requestId lifecycle is enforced independently (a fresh id per id-bearing
 * operation, a recorded reuse declared as 'continue' and held to the
 * previous served id, none where the operation declares no id, served
 * envelopes echo the id actually sent). Nothing steers driver memory
 * mid-flight. */
import { at, equal, instantiate, readTrace } from './trace-runner';
import { ProtocolError, validateError, validateRequest, validateSuccess } from './protocol';
import { WorldApiError, type WorldTransport } from './transport';
import type { ModelTask } from './schedule';
import type { ControlState, Id, Json, PointWork, Scope, WorldContext, WorldOperation } from './types';

export const PLACEHOLDER_DIGEST = '0'.repeat(64); // schema-valid; never evidence of a real digest

export interface PreviewAlignment {
  previewStepId: string;
  expectationStepId: string;
  workingStatePath: string;
  workingStateDigestPath: string;
}

export interface IndependentDigestPin {
  stepId: string;
  path: string;
  digest: string;
}

/** Explicit retry semantics: a 'continue' step re-sends the previous call's
 * operation, scope and full request under the same requestId; a 'probe'
 * deliberately replays a previously served id with a different payload (the
 * request_id_reused demonstration). Neither is inferred from the recording. */
export interface RetryDeclaration {
  stepId: string;
  kind: 'continue' | 'probe';
}

export interface CorpusStep {
  id: string; // shared step id or B-specimen label
  segment: 'controller' | 'preview' | 'command' | 'probe' | 'inspect' | 'heartbeat';
  sharedStepId: string | null;
  operation: WorldOperation;
  request: Json; // recorded requestId stripped where the operation bears one
  requestIdRequired: boolean;
  /** 'continue' = declared retry: same operation/scope/body as the previous
   * served call under its id. 'probe' = declared deliberate replay of a
   * served id. Default 'fresh' = a never-seen id. */
  requestIdExpectation: 'fresh' | 'continue' | 'probe';
  scope: Scope;
  response: Json; // recorded echo, rewritten to the served request id at serve time
  responseKind: 'success' | 'error';
  placeholderDigests?: boolean;
  captures: { variable: string; path: string }[];
  digestChain: { variable: string; captureStepId: string; path: string }[];
  digestPin?: { path: string; digest: string };
  /** Independent scenario rules checked on this response before the
   * driver can consume it; later fixed responses cannot repair a violation. */
  businessAssertions?: { path: string; expected: Json }[];
  expectation?: {
    projectionPath: string; digestPath: string; expectedProjection: Json; expectedDigest: string;
    alignsWith?: { previewStepId: string; workingStatePath: string; workingStateDigestPath: string };
  };
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
  build: (served: ServedSnapshot) => { workingState: Json; pointProjection: Json; mergedEntityDeltas: Json; settlementGroups?: Json[] };
}

/** Collects the JSON pointers where a response template references trace
 * variables, walking template and instantiated response in lockstep so
 * $map keys resolve to their runtime positions. */
function collectVariablePositions(template: unknown, value: unknown, pointer: string, bindings: Record<string, unknown>, out: { variable: string; path: string }[]): void {
  const escape = (token: string) => token.replace(/~/g, '~0').replace(/\//g, '~1');
  if (Array.isArray(template)) {
    template.forEach((entry, index) => collectVariablePositions(entry, (value as unknown[])[index], `${pointer}/${index}`, bindings, out));
    return;
  }
  if (template && typeof template === 'object') {
    const node = template as Record<string, unknown>;
    if ('$var' in node) {
      out.push({ variable: node.$var as string, path: pointer });
      return;
    }
    if ('$map' in node) {
      const record = (value ?? {}) as Record<string, unknown>;
      for (const entry of node.$map as { key: unknown; value: unknown }[]) {
        const key = instantiate(entry.key, bindings);
        collectVariablePositions(entry.value, record[String(key)], `${pointer}/${escape(String(key))}`, bindings, out);
      }
      return;
    }
    for (const [key, child] of Object.entries(node)) collectVariablePositions(child, (value as Record<string, unknown>)[key], `${pointer}/${escape(key)}`, bindings, out);
  }
}

/** Instantiates every shared step for one sample (request/scope/response via
 * the trace's own capture discipline), tracks the served state, and inserts
 * B-authored preview specimens at their declared positions. Preview
 * alignments and independent digest pins are scenario-declared expectations
 * the trace itself does not carry: an alignment binds a final preview's
 * served body and digest to a later step's independent expectation, a pin
 * holds a served field to an externally precomputed digest. Retry
 * declarations are equally explicit — a recorded requestId reuse is never
 * inferred to be a retry. */
/** B-authored get_state read inserted into the controller flow at a declared
 * position (after a trace step OR another read specimen). `data` is the FULL
 * GetStateData the specimen serves — recorded material or a marked B
 * construction; the envelope mirrors the served fixture shape exactly. */
export interface ReadStateSpecimenSpec { label: string; afterStepId: string; data: Json }

/** Frozen group action as the driver retains it for the §7.1 results input. */
export interface FrozenGroupAction {
  memberId: Id;
  actionText: string;
  rollRefs: { targetId: Id; rollId: Id; result: number; eligible: boolean; admitted: boolean }[];
}

/** Mirrors the driver's retained frozen group actions from the recording:
 * discover resets the group, an admitted extend unshifts the reacting member,
 * create_rolls appends EVERY outcome (inadmissible included), and staging or
 * committing settles the batch (reset). Returns each stage unit's snapshot
 * taken BEFORE it is consumed — what that group's results call must declare. */
export function frozenGroupActionsAtStage(
  steps: { id: string; operation: string }[],
  requestOf: Map<string, Record<string, unknown>>,
  responseOf: Map<string, Record<string, unknown>>,
): Map<string, FrozenGroupAction[]> {
  const snapshots = new Map<string, FrozenGroupAction[]>();
  let current: FrozenGroupAction[] = [];
  for (const step of steps) {
    const request = requestOf.get(step.id)!;
    if (step.operation === 'checkpoint_discover_group') {
      current = [{ memberId: request.initiatorId as Id, actionText: request.actionText as string, rollRefs: [] }];
    } else if (step.operation === 'checkpoint_extend_group') {
      const admit = request.admittedMember as { memberId: Id; actionText?: string | null } | null | undefined;
      if (admit?.memberId) current = [{ memberId: admit.memberId, actionText: admit.actionText ?? '', rollRefs: [] }, ...current];
    } else if (step.operation === 'create_rolls') {
      const spec = (request.rolls as { sourceId: Id; targetId: Id }[])[0];
      const outcome = (responseOf.get(step.id) as { data: { rolls: { rollId: Id; result: number; eligible: boolean; admitted: boolean }[] } }).data.rolls[0];
      current.find((member) => member.memberId === spec.sourceId)?.rollRefs.push({ targetId: spec.targetId, rollId: outcome.rollId, result: outcome.result, eligible: outcome.eligible, admitted: outcome.admitted });
    } else if (step.operation === 'checkpoint_stage_unit') {
      snapshots.set(step.id, structuredClone(current));
      current = [];
    } else if (step.operation === 'checkpoint_stage_time_scan' || step.operation === 'commit_point') {
      current = [];
    }
  }
  return snapshots;
}

/** State the driver holds when the model call declared at a step runs: the
 * world served by the last response the driver actually adopted, and the last
 * adopted get_context's activeInput (other envelopes omit the field, so the
 * driver retains it). Harness-issued inspect steps never reach the driver, so
 * the caller lists them as never-adopted (the seeded bootstrap context is the
 * exception — scenarios seed it and pass only the later inspects). */
export interface ServedBefore { world: WorldContext | null; activeInput: { advanceId: Id; inputId: Id; text: string } | null }

export function servedBeforeSteps(
  steps: { id: string; operation: string }[],
  responseOf: Map<string, Record<string, unknown>>,
  notAdoptedStepIds: Iterable<string> = [],
): Map<string, ServedBefore> {
  const notAdopted = new Set(notAdoptedStepIds);
  const before = new Map<string, ServedBefore>();
  let world: WorldContext | null = null;
  let activeInput: ServedBefore['activeInput'] = null;
  for (const step of steps) {
    before.set(step.id, { world, activeInput });
    if (notAdopted.has(step.id)) continue;
    const response = responseOf.get(step.id) as { world?: WorldContext | null; activeInput?: ServedBefore['activeInput'] } | undefined;
    if (response?.world !== undefined) world = response.world;
    if (response?.activeInput !== undefined) activeInput = response.activeInput;
  }
  return before;
}

export function buildCorpus(rawTrace: unknown, sampleId: string, specimens: PreviewSpecimenSpec[], inspectStepIds: string[], previewAlignments: PreviewAlignment[] = [], digestPins: IndependentDigestPin[] = [], retries: RetryDeclaration[] = [], readSpecimens: ReadStateSpecimenSpec[] = []): Corpus {
  const trace = readTrace(rawTrace);
  const sample = trace.samples.find((s) => s.id === sampleId);
  if (!sample) throw new ProtocolError(`Unknown sample ${sampleId}`);
  // Input-origin variables start bound, exactly like the shared interpreter.
  const bindings: Record<string, unknown> = Object.fromEntries(trace.variables.filter((v) => v.origin === 'input').map((v) => [v.name, structuredClone(sample.values[v.name])]));
  const steps: CorpusStep[] = [];
  const servedAfter: Record<string, ServedSnapshot> = {};
  const requests: Record<string, Json> = {};
  const capturedAt = new Map<string, { stepId: string; path: string }>();
  let lastRecorded: { requestId: string; operation: WorldOperation; scope: Scope; body: Record<string, unknown> } | null = null;
  for (const step of trace.steps) {
    const request = instantiate(step.request, bindings) as Json;
    const scope = instantiate(step.scope, bindings) as Scope;
    const own = Object.fromEntries(step.captures.map((c) => [c.variable, sample.values[c.variable]]));
    const response = instantiate(step.response, { ...bindings, ...own }) as Json;
    // Recorded request identity: the echo must match, then the lifecycle
    // leaves the corpus — the transport enforces it against the driver. A
    // recorded requestId reuse is NEVER inferred: it must be declared as a
    // retry (same payload resent) or a probe (deliberate replay), and the
    // declaration is validated against the recording.
    const requestIdRequired = Object.hasOwn(request as Record<string, unknown>, 'requestId');
    let requestIdExpectation: 'fresh' | 'continue' | 'probe' = 'fresh';
    if (requestIdRequired) {
      const declared = (request as Record<string, unknown>).requestId;
      const echo = (response as Record<string, unknown>).requestId;
      if (typeof declared !== 'string' || echo !== declared) throw new ProtocolError(`[${step.id}] recorded response requestId ${String(echo)} does not echo the request ${String(declared)}`);
      const { requestId: _recordedId, ...recordedBody } = request as Record<string, unknown>;
      const declaration = retries.find((r) => r.stepId === step.id);
      if (declaration) {
        if (!lastRecorded || declared !== lastRecorded.requestId) throw new ProtocolError(`[${step.id}] declared ${declaration.kind} does not replay the recorded predecessor's requestId`);
        if (declaration.kind === 'continue') {
          if (step.operation !== lastRecorded.operation || !equal(scope, lastRecorded.scope) || !equal(recordedBody, lastRecorded.body)) throw new ProtocolError(`[${step.id}] declared retry diverges from the recorded predecessor's payload — declare a probe instead if the replay is deliberate`);
          requestIdExpectation = 'continue';
        } else {
          if (step.operation === lastRecorded.operation && equal(scope, lastRecorded.scope) && equal(recordedBody, lastRecorded.body)) throw new ProtocolError(`[${step.id}] declared probe re-sends the recorded payload verbatim — declare a retry instead`);
          requestIdExpectation = 'probe';
        }
      } else if (lastRecorded && declared === lastRecorded.requestId) {
        throw new ProtocolError(`[${step.id}] recorded requestId reuse must be declared explicitly as a retry ('continue') or a probe ('probe')`);
      }
      lastRecorded = { requestId: declared, operation: step.operation, scope: structuredClone(scope), body: recordedBody };
      delete (request as Record<string, unknown>).requestId;
    }
    for (const capture of step.captures) capturedAt.set(capture.variable, { stepId: step.id, path: capture.path });
    const positions: { variable: string; path: string }[] = [];
    collectVariablePositions(step.response, response, '', bindings, positions);
    const digestChain = positions.flatMap((p) => {
      const capture = capturedAt.get(p.variable);
      return capture ? [{ variable: p.variable, captureStepId: capture.stepId, path: p.path }] : [];
    });
    const segment = inspectStepIds.includes(step.id) ? 'inspect' as const : 'controller' as const;
    const digest = sample.expectedDigests[step.id];
    steps.push({
      id: step.id, segment, sharedStepId: step.id, operation: step.operation, request, requestIdRequired, requestIdExpectation, scope, response,
      responseKind: step.responseKind,
      captures: step.captures.map((c) => ({ ...c })), digestChain,
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
      // Each served specimen owns its body, even if an author reuses an
      // object also used to declare model expectations or another preview.
      const built = structuredClone(specimen.build(served));
      steps.push({
        id: specimen.label, segment: 'preview', sharedStepId: null, operation: 'preview_point',
        request: {
          protocolVersion: 2, worldId: world.worldId,
          advanceId: world.advance.advanceId!, roundId: world.activeRoundId ?? world.round?.roundId ?? '',
          pointId: work.pointId, expectedPointId: world.head.pointId, expectedVersion: world.head.version,
          expectedCheckpointRevision: control.revision, timeAdvance: work.timeAdvance,
          settlementGroups: built.settlementGroups ?? [],
        } as unknown as Json,
        requestIdRequired: false, requestIdExpectation: 'fresh',
        scope: { worldId: world.worldId },
        response: {
          protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 2, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
          operation: 'preview_point', world, control, work,
          data: { pointId: work.pointId, pointProjection: built.pointProjection, mergedEntityDeltas: built.mergedEntityDeltas, workingStateDigest: PLACEHOLDER_DIGEST, pointProjectionDigest: PLACEHOLDER_DIGEST, workingState: built.workingState },
        } as unknown as Json,
        responseKind: 'success', placeholderDigests: true, captures: [], digestChain: [],
      });
    }
    // Read specimens chain on trace steps or on previously inserted reads:
    // drain every spec whose anchor is the step just pushed, in declaration
    // order, so a target read can be followed by its predecessor read.
    let lastPushedId: string = step.id;
    for (let drain = true; drain;) {
      drain = false;
      for (let k = 0; k < readSpecimens.length; k++) {
        if (readSpecimens[k].afterStepId !== lastPushedId) continue;
        const spec = readSpecimens.splice(k, 1)[0];
        const served = servedAfter[step.id];
        const world = served.world;
        if (!world) throw new ProtocolError(`[${spec.label}] read specimen needs a served world after ${step.id}`);
        const data = structuredClone(spec.data) as Record<string, unknown>;
        steps.push({
          id: spec.label, segment: 'controller', sharedStepId: null, operation: 'get_state',
          request: { point: data.pointId ?? null } as unknown as Json,
          requestIdRequired: false, requestIdExpectation: 'fresh',
          scope: { worldId: world.worldId },
          response: {
            protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 2, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1,
            world,
            data,
          } as unknown as Json,
          responseKind: 'success', captures: [], digestChain: [],
        });
        lastPushedId = spec.label;
        drain = true;
        break;
      }
    }
  }
  for (const alignment of previewAlignments) {
    const step = steps.find((s) => s.id === alignment.expectationStepId);
    if (!step?.expectation) throw new ProtocolError(`[${alignment.expectationStepId}] preview alignment needs an expectation-bearing step`);
    if (!steps.some((s) => s.id === alignment.previewStepId)) throw new ProtocolError(`[${alignment.previewStepId}] preview alignment references an unknown preview step`);
    step.expectation.alignsWith = { previewStepId: alignment.previewStepId, workingStatePath: alignment.workingStatePath, workingStateDigestPath: alignment.workingStateDigestPath };
  }
  for (const pin of digestPins) {
    const step = steps.find((s) => s.id === pin.stepId);
    if (!step) throw new ProtocolError(`[${pin.stepId}] digest pin references an unknown step`);
    if (step.digestPin) throw new ProtocolError(`[${pin.stepId}] duplicate digest pin for ${step.digestPin.path}`);
    step.digestPin = { path: pin.path, digest: pin.digest };
  }
  return { steps, servedAfter, requests, sampleId };
}

/** Verifies driver-derived calls against the declared corpus: operation,
 * full request (recorded requestId stripped; lifecycle enforced
 * independently below), scope and global order; responses are
 * schema-validated corpus instances held to the runtime digest chain and
 * the shared independent expectations. */
export class ScenarioTransport implements WorldTransport {
  private index = 0;
  private readonly seenRequestIds = new Set<Id>();
  private frontRequestId: Id | null = null; // id accepted at the current front: a retry_same_request re-sends it
  private lastServedRequestId: Id | null = null; // previous served id-bearing call: 'continue' expectations hold against it
  private lastServedRequest: { operation: WorldOperation; scope: Scope; body: Record<string, unknown> } | null = null;
  private harnessRequestCounter = 0;
  private readonly captured = new Map<string, unknown>();
  private readonly servedResponses = new Map<string, Json>();
  readonly ops: WorldOperation[] = [];
  readonly requests: Json[] = [];
  constructor(private readonly steps: CorpusStep[], private readonly label: string) {}
  get exhausted(): boolean { return this.index >= this.steps.length; }
  get nextStepId(): string | null { return this.steps[this.index]?.id ?? null; }
  /** True at a harness boundary (inspect/probe/command/heartbeat), or the end. */
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
    // Request identity lifecycle, enforced without reading driver memory:
    // an id-bearing operation must carry a fresh requestId, operations that
    // declare none must not leak one, and the served envelope echoes the id
    // actually sent.
    let requestId: Id | null = null;
    if (step.requestIdRequired) {
      requestId = sent.requestId as Id;
      if (typeof requestId !== 'string' || requestId === '') throw new ProtocolError(`[${this.label}] step ${step.id}: requestId must be a non-empty string, got ${String(sent.requestId)}`);
      if (step.requestIdExpectation === 'continue') {
        const last = this.lastServedRequest;
        if (requestId !== this.lastServedRequestId || !last) throw new ProtocolError(`[${this.label}] step ${step.id}: requestId ${requestId} must reuse the previous operation's id ${String(this.lastServedRequestId)} (declared retry)`);
        const { requestId: _sentId, ...retryBody } = sent;
        if (operation !== last.operation || !equal(scope as unknown as Scope, last.scope) || !equal(retryBody, last.body)) throw new ProtocolError(`[${this.label}] step ${step.id}: retry payload drift — a declared retry must repeat the original operation, scope and request body`);
      } else if (step.requestIdExpectation === 'probe') {
        if (!this.seenRequestIds.has(requestId)) throw new ProtocolError(`[${this.label}] step ${step.id}: declared probe replays ${requestId} which was never served`);
      } else if (this.seenRequestIds.has(requestId) && requestId !== this.frontRequestId) {
        throw new ProtocolError(`[${this.label}] step ${step.id}: requestId ${requestId} already used — the factory must mint a fresh id per id-bearing operation`);
      }
      this.seenRequestIds.add(requestId);
      this.frontRequestId = requestId;
      this.lastServedRequestId = requestId;
      const { requestId: _servedId, ...servedBody } = sent;
      this.lastServedRequest = { operation, scope: structuredClone(scope as unknown as Scope), body: servedBody };
    } else if (sent.requestId !== undefined) {
      throw new ProtocolError(`[${this.label}] step ${step.id}: declared request carries no requestId but controller sent ${String(sent.requestId)}`);
    }
    let body: Record<string, unknown> = sent;
    if (step.requestIdRequired) {
      const { requestId: _sentId, ...withoutId } = sent;
      body = withoutId;
    }
    if (!equal(step.request, body)) throw new ProtocolError(`[${this.label}] step ${step.id} request mismatch:\n  declared ${JSON.stringify(step.request)}\n  driver   ${JSON.stringify(sent)}`);
    if (!equal(step.scope, scope as unknown as Scope)) throw new ProtocolError(`[${this.label}] step ${step.id} scope mismatch: declared ${JSON.stringify(step.scope)}, driver ${JSON.stringify(scope)}`);
    validateRequest(operation, request);
    const response = structuredClone(step.response) as Json;
    if (requestId !== null) (response as Record<string, unknown>).requestId = requestId;
    if (step.responseKind === 'error') {
      // Error steps are recorded HTTP exchanges: serve once with the same
      // runtime identity checks (captures and chain from the error body),
      // advance, and let the driver's reaction land on the next declared
      // step. A retry_same_request therefore re-sends its payload as the
      // NEXT declared step — the one carrying the 'continue' expectation.
      const validatedError = validateError(response);
      this.assertBusiness(step, validatedError);
      this.servedResponses.set(step.id, validatedError as unknown as Json);
      for (const capture of step.captures) this.captured.set(capture.variable, at(validatedError, capture.path));
      for (const link of step.digestChain) {
        if (!equal(at(validatedError, link.path), this.captured.get(link.variable))) throw new ProtocolError(`[${this.label}] step ${step.id}: digest chain broken at ${link.path} (${link.variable}, captured at ${link.captureStepId}): served value diverges from the recorded capture`);
      }
      if (step.digestPin && at(validatedError, step.digestPin.path) !== step.digestPin.digest) throw new ProtocolError(`[${this.label}] step ${step.id}: independent digest pin broken at ${step.digestPin.path}`);
      this.index++;
      this.frontRequestId = null;
      this.ops.push(operation);
      this.requests.push(structuredClone(sent) as Json);
      throw new WorldApiError(validatedError);
    }
    // Runtime corpus identity: captures feed the declared digest chain — a
    // served response may not diverge from the earlier-served capture it
    // references — every declared independent expectation holds at serve
    // time, not only on harness-issued inspects, scenario-declared
    // alignments bind a final preview's served body and digest to a later
    // independent expectation, and pins hold fields no reference consumes to
    // externally precomputed digests.
    const validated = validateSuccess(operation, response) as unknown as Json;
    this.assertBusiness(step, validated);
    this.servedResponses.set(step.id, validated);
    for (const capture of step.captures) this.captured.set(capture.variable, at(validated, capture.path));
    for (const link of step.digestChain) {
      if (!equal(at(validated, link.path), this.captured.get(link.variable))) throw new ProtocolError(`[${this.label}] step ${step.id}: digest chain broken at ${link.path} (${link.variable}, captured at ${link.captureStepId}): served value diverges from the recorded capture`);
    }
    if (step.digestPin && at(validated, step.digestPin.path) !== step.digestPin.digest) throw new ProtocolError(`[${this.label}] step ${step.id}: independent digest pin broken at ${step.digestPin.path}: served ${String(at(validated, step.digestPin.path))}, pinned ${step.digestPin.digest}`);
    if (step.expectation) {
      assertSharedExpectation(step, validated);
      const alignment = step.expectation.alignsWith;
      if (alignment) {
        const previewStep = this.steps.find((s) => s.id === alignment.previewStepId);
        const preview = this.servedResponses.get(alignment.previewStepId);
        if (!previewStep || !preview) throw new ProtocolError(`[${this.label}] step ${step.id}: alignment preview ${alignment.previewStepId} has not been served`);
        if (!equal(at(preview, alignment.workingStatePath), step.expectation.expectedProjection)) throw new ProtocolError(`[${this.label}] step ${step.id}: preview alignment broken — ${alignment.previewStepId}${alignment.workingStatePath} diverges from the independent projection of ${step.id}`);
        // A placeholder-bearing B specimen never claims digests, so only its
        // body leg is bindable; recorded previews bind both legs.
        if (!previewStep.placeholderDigests && at(preview, alignment.workingStateDigestPath) !== step.expectation.expectedDigest) throw new ProtocolError(`[${this.label}] step ${step.id}: preview alignment broken — ${alignment.previewStepId}${alignment.workingStateDigestPath} diverges from the independent digest of ${step.id}`);
      }
    }
    this.index++;
    this.frontRequestId = null;
    this.ops.push(operation);
    this.requests.push(structuredClone(sent) as Json);
    return validated as never;
  }
  private assertBusiness(step: CorpusStep, response: unknown): void {
    for (const assertion of step.businessAssertions ?? []) {
      const actual = at(response, assertion.path);
      if (!equal(actual, assertion.expected)) throw new ProtocolError(`[${this.label}] step ${step.id}: business assertion failed at ${assertion.path}: expected ${JSON.stringify(assertion.expected)}, got ${JSON.stringify(actual)}`);
    }
  }
  /** Explicit harness reads/replays. A declared retry reuses the prior
   * served write's identity and is held to its original complete payload. */
  async runInspect(stepId: string): Promise<{ step: CorpusStep; response: Json }> {
    return this.runDeclared(stepId, 'inspect');
  }
  /** Deliberately invalid exchanges are marked probes, never attributed to
   * scheduler decisions. Expected WorldApiError still consumes the step. */
  async runProbe(stepId: string): Promise<{ step: CorpusStep; response: Json }> {
    return this.runDeclared(stepId, 'probe');
  }
  /** B1 explicitly injects heartbeat exchanges. Scheduling timers and
   * maintaining live runtime TTLs remain B2 responsibilities. */
  async runHeartbeat(stepId: string): Promise<{ step: CorpusStep; response: Json }> {
    const step = this.steps[this.index];
    if (!step || !['lease_renew', 'narration_claim_renew'].includes(step.operation)) throw new ProtocolError(`[${this.label}] ${stepId} is not a heartbeat operation`);
    return this.runDeclared(stepId, 'heartbeat');
  }
  private async runDeclared(stepId: string, segment: 'inspect' | 'probe' | 'heartbeat'): Promise<{ step: CorpusStep; response: Json }> {
    const step = this.steps[this.index];
    if (!step || step.id !== stepId || step.segment !== segment) throw new ProtocolError(`[${this.label}] ${segment} ${stepId} is not at the execution front (next: ${step?.id ?? 'none'})`);
    const request: Record<string, unknown> = { ...(step.request as Record<string, unknown>) };
    if (step.requestIdRequired && request.requestId === undefined) {
      if (step.requestIdExpectation === 'continue') {
        if (!this.lastServedRequestId) throw new ProtocolError(`[${this.label}] no served request to replay at ${stepId}`);
        request.requestId = this.lastServedRequestId;
      } else {
        let harnessId: Id;
        do {
          harnessId = `${this.label}_harness_${++this.harnessRequestCounter}`;
        } while (this.seenRequestIds.has(harnessId));
        request.requestId = harnessId;
      }
    }
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

/** Drives the controller segment until every controller/preview step and
 * model call is consumed; any early terminal status fails the run. Inspect
 * steps stay for the harness to issue afterwards. */
export async function driveControllerSegment<H extends { driver: { step(): Promise<{ kind: string; reason?: string; detail?: string } | undefined> }; transport: { controllerDrained: boolean }; model: { exhausted: boolean } }>(scenario: H, label = 'segment'): Promise<void> {
  await driveControllerSlice(scenario, label);
  if (!scenario.model.exhausted) throw new ProtocolError(`[${label}] model calls remain at the declared boundary`);
}

/** Runs to the next explicit harness boundary. Later slices may still own
 * model calls; no fixture request or memory is fed into the driver here. */
export async function driveControllerSlice<H extends { driver: { step(): Promise<{ kind: string; reason?: string; detail?: string } | undefined> }; transport: { controllerDrained: boolean } }>(scenario: H, label = 'slice'): Promise<void> {
  for (let i = 0; i < 500; i++) {
    if (scenario.transport.controllerDrained) return;
    const terminal = await scenario.driver.step();
    if (terminal) throw new ProtocolError(`[${label}] controller segment ended early: ${terminal.kind}/${terminal.reason ?? terminal.detail}`);
  }
  throw new ProtocolError(`[${label}] controller step limit exceeded`);
}
