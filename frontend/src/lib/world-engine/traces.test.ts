import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, test } from 'vitest';
import { FixtureWorldTransport } from './fixture-transport';
import { HttpWorldTransport } from './http-transport';
import { ProtocolError, operationRegistry, protocolHeader } from './protocol';
import { at, equal, instantiate, readTrace, refs, runTrace, type TraceDocument } from './trace-runner';
import { WorldApiError, type WorldTransport } from './transport';
import type { RequestMap, Scope, WorldOperation } from './types';

const directory = resolve(process.cwd(), '../design/world-protocol/v2/traces');
const documents = readdirSync(directory).filter((n) => /^T.*\.json$/.test(n)).sort().map((name) => ({ name, trace: JSON.parse(readFileSync(resolve(directory, name), 'utf8')) as TraceDocument }));
if (!documents.length) throw new Error('Shared trace set is empty');
const load = (name = 'T01.json'): TraceDocument => structuredClone(documents.find((d) => d.name === name)!.trace);

/** A controlled HTTP endpoint: verify serialization against declared requests,
 * then return only authored responses. No state transition implementation. */
function httpFixture(trace: TraceDocument, sampleId: string) {
  const fixed = new FixtureWorldTransport(trace, sampleId);
  const sample = trace.samples.find((s) => s.id === sampleId)!;
  const bindings: Record<string, unknown> = Object.fromEntries(trace.variables.filter((v) => v.origin === 'input').map((v) => [v.name, sample.values[v.name]]));
  let index = 0;
  const fetcher: typeof fetch = async (input, init) => {
    const step = trace.steps[index];
    if (!step) throw new ProtocolError('Unexpected HTTP request');
    const request = instantiate(step.request, bindings) as RequestMap[WorldOperation];
    const fields = request as unknown as Record<string, unknown>;
    const scope = instantiate(step.scope, bindings) as Scope;
    const spec = operationRegistry[step.operation];
    const path = spec.path.replace(/\{(worldId|pointId)\}/g, (_, key: keyof Scope) => encodeURIComponent(String(scope[key] ?? fields[key])));
    const url = new URL(String(input));
    expect(url.pathname).toBe('/api' + path);
    expect(init?.method).toBe(spec.method);
    expect(new Headers(init?.headers).get(protocolHeader)).toBe('2');
    if (spec.method === 'GET' || spec.method === 'DELETE') {
      expect(init?.body).toBeUndefined();
      const expected = spec.queryBindings.filter((k) => fields[k] != null).map((k) => [k, String(fields[k])]);
      expect([...url.searchParams.entries()]).toEqual(expected);
    } else expect(JSON.parse(String(init?.body))).toEqual(request);
    let response: unknown;
    try { response = await fixed.execute(step.operation, request, scope); }
    catch (error) { if (!(error instanceof WorldApiError)) throw error; response = error.response; }
    for (const capture of step.captures) bindings[capture.variable] = structuredClone(at(response, capture.path));
    index++;
    return Response.json(response, { status: step.httpStatus });
  };
  return { transport: new HttpWorldTransport('https://contract.invalid/api', fetcher), complete: () => { fixed.assertComplete(); expect(index).toBe(trace.steps.length); } };
}

describe('shared Python expectations consumed in TS', () => {
  for (const { name, trace } of documents) for (const sample of trace.samples) {
    test(`${name} ${sample.id} fixed transport`, async () => {
      const transport = new FixtureWorldTransport(trace, sample.id);
      const bindings = await runTrace(trace, sample.id, transport);
      expect(Object.keys(bindings).sort()).toEqual(trace.variables.map((v) => v.name).sort());
      transport.assertComplete();
    });
    test(`${name} ${sample.id} controlled HTTP`, async () => {
      const http = httpFixture(trace, sample.id);
      await runTrace(trace, sample.id, http.transport);
      http.complete();
    });
  }
});

test.each(['business', 'future', 'duplicate', 'missingAssertion', 'missingCapture', 'pin', 'unknown', 'range', 'duplicateSample'])( 'reject unsafe trace: %s', async (kind) => {
  const trace = load();
  if (kind === 'business') {
    const name = trace.steps.flatMap((s) => refs(s.expectedProjection))[0];
    trace.variables.find((v) => v.name === name)!.kind = 'business';
  } else if (kind === 'future') trace.steps[0].request = { $var: trace.variables.at(-1)!.name };
  else if (kind === 'duplicate') trace.steps[1].captures.push(...trace.steps[0].captures);
  else if (kind === 'missingAssertion') trace.steps[0].assertions = [];
  else if (kind === 'missingCapture') trace.steps[0].captures[0].path = '/nonexistent';
  else if (kind === 'pin') trace.contractDigest = '0'.repeat(64);
  else if (kind === 'unknown') (trace as unknown as Record<string, unknown>).unknown = true;
  else if (kind === 'range') trace.steps[0].assertions.push({ op: 'range', path: '/control/revision' });
  else trace.samples[1].id = trace.samples[0].id;
  await expect(runTrace(trace, trace.samples[0].id, new FixtureWorldTransport(load(), 'sample_1'))).rejects.toThrow();
});

test.each(['digest', 'identity', 'business', 'order', 'epoch'])( 'reject altered expectation: %s', async (kind) => {
  const trace = load(kind === 'epoch' ? 'T07.json' : 'T01.json');
  const projection = trace.steps.find((s) => s.expectedProjection != null)!;
  if (kind === 'digest') trace.samples[0].expectedDigests[projection.id] = '0'.repeat(64);
  else if (kind === 'identity') (projection.expectedProjection as Record<string, unknown>).worldId = 'another_world';
  else if (kind === 'business') (projection.expectedProjection as unknown as { characters: { person_c: { sanity: number } } }).characters.person_c.sanity = 1;
  else if (kind === 'order') {
    const step = trace.steps.find((s) => s.operation === 'checkpoint_start_advance')!;
    step.assertions.find((a) => a.op === 'ordered')!.expected = ['person_f', 'person_e', 'person_d', 'person_c', 'person_b', 'person_a'];
  } else trace.steps[0].assertions.find((a) => a.op === 'delta')!.expected = 0;
  const fixed = new FixtureWorldTransport(load(kind === 'epoch' ? 'T07.json' : 'T01.json'), 'sample_1');
  await expect(runTrace(trace, 'sample_1', fixed)).rejects.toThrow();
});

test('validate success and error schemas before capture or business assertions', async () => {
  for (const errorResponse of [false, true]) {
    const trace = load(errorResponse ? 'T09.json' : 'T01.json');
    const fixed = new FixtureWorldTransport(trace, 'sample_1');
    const transport: WorldTransport = { async execute(operation, request, scope) {
      try {
        const response = await fixed.execute(operation, request, scope);
        if (!errorResponse) delete (response as unknown as Record<string, unknown>).control;
        return response;
      } catch (error) {
        if (!(error instanceof WorldApiError)) throw error;
        delete (error.response.error as unknown as Record<string, unknown>).code;
        throw error;
      }
    } };
    await expect(runTrace(trace, 'sample_1', transport)).rejects.toThrow(/(?:required|property)/i);
  }
});

test.each(['operation', 'token', 'order', 'scope'])('fixed transport rejects unexpected %s', async (kind) => {
  const trace = load('T07.json'), sample = trace.samples[0];
  const first = trace.steps[0], bindings = sample.values;
  let operation = first.operation;
  const request = instantiate(first.request, bindings) as Record<string, unknown>;
  const scope = instantiate(first.scope, bindings) as Scope;
  if (kind === 'operation') operation = 'get_context';
  else if (kind === 'token') request.leaseToken = 'stale_lease';
  else if (kind === 'order') operation = trace.steps[1].operation;
  else scope.worldId = 'wrong_world';
  const fixed = new FixtureWorldTransport(trace, sample.id);
  await expect(fixed.execute(operation, request as RequestMap[typeof operation], scope)).rejects.toThrow('Unexpected fixture');
  expect(() => fixed.assertComplete()).toThrow('not fully consumed');
});

test('failed response cannot provide a missing capture', async () => {
  const trace = load('T09.json'), step = trace.steps.find((s) => s.responseKind === 'error')!;
  trace.variables.push({ name: 'missing', kind: 'identity', valueType: 'string', origin: 'capture', captureStep: step.id });
  step.captures.push({ variable: 'missing', path: '/data/pointId' });
  trace.samples.forEach((s) => { s.values.missing = 'p'; });
  await expect(runTrace(trace, 'sample_1', new FixtureWorldTransport(trace, 'sample_1'))).rejects.toThrow('Missing response path');
});

test('structured references cannot execute code or collide map keys; absent differs from null', () => {
  expect(() => instantiate({ $var: 'missing' }, {})).toThrow('Uncaptured');
  expect(() => instantiate({ $var: 'x', extra: true }, { x: 'value' })).toThrow('Invalid variable');
  expect(() => instantiate({ $map: [{ key: 'a', value: 1 }, { key: 'a', value: 2 }] }, {})).toThrow('Duplicate');
  expect(() => at({}, '/__proto__')).toThrow('Unsafe');
  expect(at({ n: null }, '/n', true)).not.toBe(at({}, '/n', true));
  expect(equal([1, 2], [2, 1])).toBe(false);
  expect(() => readTrace({})).toThrow('Trace schema');
});
