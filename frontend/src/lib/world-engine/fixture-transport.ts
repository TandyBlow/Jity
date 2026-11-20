import { equal, instantiate, at, readTrace, type TraceDocument, type TraceSample } from './trace-runner';
import { ProtocolError, validateSuccess, validateError, validateRequest } from './protocol';
import { WorldApiError, type WorldTransport } from './transport';
import type { RequestMap, Scope, Success, WorldOperation } from './types';

/** Returns only declared responses. Never computes or fills in world state. */
export class FixtureWorldTransport implements WorldTransport {
  private index = 0;
  private readonly trace: TraceDocument;
  private readonly sample: TraceSample;
  private readonly bindings: Record<string, unknown>;
  constructor(value: unknown, sampleId: string) {
    this.trace = readTrace(value);
    const sample = this.trace.samples.find((s) => s.id === sampleId);
    if (!sample) throw new ProtocolError('Unknown fixture sample');
    this.sample = sample;
    this.bindings = Object.fromEntries(this.trace.variables.filter((v) => v.origin === 'input').map((v) => [v.name, structuredClone(sample.values[v.name])]));
  }
  async execute<K extends WorldOperation>(operation: K, request: RequestMap[K], scope: Scope): Promise<Success<K>> {
    const step = this.trace.steps[this.index];
    if (!step || operation !== step.operation || !equal(request, instantiate(step.request, this.bindings)) || !equal(scope, instantiate(step.scope, this.bindings))) throw new ProtocolError('Unexpected fixture request, scope or ordering');
    validateRequest(operation, request);
    const own = Object.fromEntries(step.captures.map((c) => [c.variable, this.sample.values[c.variable]]));
    const response = instantiate(step.response, { ...this.bindings, ...own });
    if (step.responseKind === 'error') validateError(response);
    else validateSuccess(operation, response);
    this.index++;
    for (const capture of step.captures) this.bindings[capture.variable] = structuredClone(at(response, capture.path));
    if (step.responseKind === 'error') throw new WorldApiError(validateError(response));
    return validateSuccess<K>(operation, response);
  }
  assertComplete(): void { if (this.index !== this.trace.steps.length) throw new ProtocolError('Fixture trace not fully consumed'); }
}
