/** Contract trace interpreter; no world apply, dice or canonical hashing here. */
import Ajv2020 from 'ajv/dist/2020';
import traceSchema from '../../../../design/world-protocol/v2/trace.schema.json';
import pin from './contract-digest.json';
import { ProtocolError, validateRequest, validateSuccess, validateError, operationRegistry } from './protocol';
import { WorldApiError, type WorldTransport } from './transport';
import type { Json, RequestMap, Scope, WorldOperation } from './types';

export interface TraceVariable { name: string; kind: 'identity' | 'clock' | 'ownership' | 'business'; valueType: 'string' | 'integer' | 'boolean' | 'object' | 'array' | 'null'; origin: 'input' | 'capture'; captureStep: string | null }
export interface TraceAssertion { op: 'eq' | 'ne' | 'type' | 'range' | 'set' | 'ordered' | 'delta' | 'time_window' | 'absent'; path: string; expected?: Json; baseline?: Json; minimum?: number | null; maximum?: number | null }
export interface TraceStep { id: string; operation: WorldOperation; scope: Json; request: Json; response: Json; responseKind: 'success' | 'error'; httpStatus: number; captures: { variable: string; path: string }[]; assertions: TraceAssertion[]; projectionPath: string | null; digestPath: string | null; expectedProjection: Json; nextAction: string }
export interface TraceSample { id: string; values: Record<string, Json>; expectedDigests: Record<string, string> }
export interface TraceDocument { traceFormatVersion: 1; protocolVersion: 2; contractDigest: string; scenario: string; acceptanceLayer: 'contract'; runtimeTarget: 'runtime-A2' | 'runtime-A3'; description: string; preconditions: string[]; variables: TraceVariable[]; steps: TraceStep[]; samples: TraceSample[] }

const ajv = new Ajv2020({ strictSchema: true, strictTypes: false, strictRequired: false, allErrors: true });
const validateTrace = ajv.compile(traceSchema);
const missing = Symbol('missing');
export function at(value: unknown, path: string, allowMissing = false): unknown {
  if (path === '') return value;
  if (!path.startsWith('/')) throw new ProtocolError('Expected JSON pointer');
  for (const segment of path.slice(1).split('/')) {
    const token = segment.replace(/~1/g, '/').replace(/~0/g, '~');
    if (['__proto__', 'constructor', 'prototype'].includes(token)) throw new ProtocolError('Unsafe pointer');
    if (!value || typeof value !== 'object' || !Object.hasOwn(value, token)) {
      if (allowMissing) return missing;
      throw new ProtocolError(`Missing response path: ${path}`);
    }
    value = (value as Record<string, unknown>)[token];
  }
  return value;
}
export function refs(node: unknown): string[] {
  if (Array.isArray(node)) return node.flatMap(refs);
  if (node && typeof node === 'object') {
    const obj = node as Record<string, unknown>;
    if ('$var' in obj) {
      if (Object.keys(obj).length !== 1 || typeof obj.$var !== 'string') throw new ProtocolError('Invalid variable node');
      return [obj.$var];
    }
    if ('$map' in obj) {
      if (Object.keys(obj).length !== 1 || !Array.isArray(obj.$map)) throw new ProtocolError('Invalid keyed map');
      return obj.$map.flatMap((entry) => {
        if (!entry || typeof entry !== 'object' || Object.keys(entry).sort().join() !== 'key,value') throw new ProtocolError('Invalid keyed map entry');
        return [...refs(entry.key), ...refs(entry.value)];
      });
    }
    return Object.values(obj).flatMap(refs);
  }
  return [];
}
export function instantiate(node: unknown, bindings: Record<string, unknown>): unknown {
  if (Array.isArray(node)) return node.map((v) => instantiate(v, bindings));
  if (node && typeof node === 'object') {
    refs(node);
    const obj = node as Record<string, unknown>;
    if ('$var' in obj) {
      const name = obj.$var as string;
      if (!Object.hasOwn(bindings, name)) throw new ProtocolError(`Uncaptured variable: ${name}`);
      return structuredClone(bindings[name]);
    }
    if ('$map' in obj) {
      const result: Record<string, unknown> = Object.create(null);
      for (const entry of obj.$map as { key: unknown; value: unknown }[]) {
        const key = instantiate(entry.key, bindings);
        if (typeof key !== 'string' || Object.hasOwn(result, key)) throw new ProtocolError('Duplicate/invalid instantiated map key');
        result[key] = instantiate(entry.value, bindings);
      }
      return result;
    }
    return Object.fromEntries(Object.entries(obj).map(([key, value]) => [key, instantiate(value, bindings)]));
  }
  return node;
}
// Structural comparison, not a canonical-byte encoder or a digest algorithm.
export function equal(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (!left || !right || typeof left !== 'object' || typeof right !== 'object') return false;
  if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right) && left.length === right.length && left.every((v, i) => equal(v, right[i]));
  const a = left as Record<string, unknown>, b = right as Record<string, unknown>;
  return Object.keys(a).length === Object.keys(b).length && Object.keys(a).every((key) => Object.hasOwn(b, key) && equal(a[key], b[key]));
}
function isType(value: unknown, type: string): boolean {
  if (type === 'integer') return Number.isSafeInteger(value);
  if (type === 'array') return Array.isArray(value);
  if (type === 'object') return value !== null && typeof value === 'object' && !Array.isArray(value);
  if (type === 'null') return value === null;
  return typeof value === type;
}
export function readTrace(value: unknown): TraceDocument {
  if (!validateTrace(value)) throw new ProtocolError(`Trace schema: ${ajv.errorsText(validateTrace.errors)}`);
  const trace = value as unknown as TraceDocument;
  if (trace.contractDigest !== pin.contractDigest) throw new ProtocolError('Trace contract pin mismatch');
  const declarations = new Map(trace.variables.map((v) => [v.name, v]));
  if (declarations.size !== trace.variables.length || new Set(trace.steps.map((s) => s.id)).size !== trace.steps.length) throw new ProtocolError('Duplicate declaration/step');
  for (const variable of trace.variables) if ((variable.origin === 'capture') !== (variable.captureStep !== null)) throw new ProtocolError('Invalid variable origin');
  const available = new Set(trace.variables.filter((v) => v.origin === 'input').map((v) => v.name));
  for (const step of trace.steps) {
    const own = new Set(step.captures.map((c) => c.variable));
    for (const name of [...refs(step.scope), ...refs(step.request)]) if (!available.has(name)) throw new ProtocolError('Request references uncaptured variable');
    for (const name of refs(step.response)) if (!available.has(name) && !own.has(name)) throw new ProtocolError('Response references future variable');
    for (const node of [step.expectedProjection, ...step.assertions.map((a) => a.expected), ...step.assertions.map((a) => a.baseline)]) {
      for (const name of refs(node)) {
        if (!declarations.has(name) || declarations.get(name)!.kind === 'business') throw new ProtocolError('Business variable in independent expectation');
        if (!available.has(name) && !own.has(name)) throw new ProtocolError('Expectation references uncaptured variable');
      }
    }
    if (!step.assertions.some((a) => !['', '/protocolVersion', '/engineVersion', '/schemaVersion', '/canonicalVersion'].includes(a.path))) throw new ProtocolError('Missing semantic assertion');
    for (const assertion of step.assertions) {
      if (['range', 'time_window'].includes(assertion.op) && assertion.minimum == null && assertion.maximum == null) throw new ProtocolError('Range requires bounds');
      if (assertion.minimum != null && assertion.maximum != null && assertion.minimum > assertion.maximum) throw new ProtocolError('Inverted range');
    }
    if (step.responseKind === 'error' && !step.assertions.some((a) => a.op === 'eq' && a.path === '/error/code')) throw new ProtocolError('Missing error code assertion');
    if ((step.expectedProjection == null) !== (step.projectionPath === null) || (step.expectedProjection == null) !== (step.digestPath === null)) throw new ProtocolError('Incomplete projection assertion');
    for (const capture of step.captures) {
      if (available.has(capture.variable) || declarations.get(capture.variable)?.captureStep !== step.id) throw new ProtocolError('Capture overwritten/undeclared');
      available.add(capture.variable);
    }
  }
  if (available.size !== declarations.size) throw new ProtocolError('Variable never captured');
  if (new Set(trace.samples.map((s) => s.id)).size !== trace.samples.length) throw new ProtocolError('Duplicate sample id');
  for (const sample of trace.samples) {
    if (!equal(Object.keys(sample.values).sort(), [...declarations.keys()].sort())) throw new ProtocolError('Sample variable set differs');
    for (const variable of trace.variables) if (!isType(sample.values[variable.name], variable.valueType)) throw new ProtocolError('Sample variable type mismatch');
    const projectionIds = trace.steps.filter((s) => s.expectedProjection != null).map((s) => s.id).sort();
    if (!equal(projectionIds, Object.keys(sample.expectedDigests).sort())) throw new ProtocolError('Expected digest step coverage mismatch');
  }
  return trace;
}
function assertValue(response: unknown, a: TraceAssertion, bindings: Record<string, unknown>): void {
  const value = at(response, a.path, true);
  if (a.op === 'absent') { if (value !== missing) throw new ProtocolError('Path must be absent'); return; }
  if (value === missing) throw new ProtocolError(`Missing assertion path: ${a.path}`);
  const expected = instantiate(a.expected, bindings);
  let ok = false;
  if (a.op === 'eq' || a.op === 'ordered') ok = equal(value, expected);
  else if (a.op === 'ne') ok = !equal(value, expected);
  else if (a.op === 'type') ok = isType(value, String(expected));
  else if (a.op === 'set') ok = Array.isArray(value) && Array.isArray(expected) && value.length === expected.length && value.every((v, i) => !value.slice(0, i).some((w) => equal(v, w)) && expected.some((w) => equal(v, w)));
  else {
    if (!Number.isSafeInteger(value)) throw new ProtocolError('Numeric assertion needs safe integer');
    const baseline = a.op === 'range' ? 0 : instantiate(a.baseline, bindings);
    if (!Number.isSafeInteger(baseline)) throw new ProtocolError('Invalid numeric baseline');
    const number = (value as number) - (baseline as number);
    ok = a.op === 'delta' ? number === expected : (a.minimum == null || number >= a.minimum) && (a.maximum == null || number <= a.maximum);
  }
  if (!ok) throw new ProtocolError(`Trace ${a.op} assertion failed: ${a.path}`);
}

export async function runTrace(raw: unknown, sampleId: string, transport: WorldTransport): Promise<Record<string, unknown>> {
  const trace = readTrace(raw);
  const sample = trace.samples.find((s) => s.id === sampleId);
  if (!sample) throw new ProtocolError('Unknown trace sample');
  const bindings: Record<string, unknown> = Object.fromEntries(trace.variables.filter((v) => v.origin === 'input').map((v) => [v.name, structuredClone(sample.values[v.name])]));
  for (const step of trace.steps) {
    const request = instantiate(step.request, bindings) as RequestMap[typeof step.operation];
    const scope = instantiate(step.scope, bindings) as Scope;
    if (!scope || typeof scope !== 'object' || Object.keys(scope).some((k) => !['worldId', 'pointId'].includes(k))) throw new ProtocolError('Invalid path scope');
    const fields = request as unknown as Record<string, unknown>;
    for (const [, key] of operationRegistry[step.operation].path.matchAll(/\{(worldId|pointId)\}/g)) {
      const value = scope[key as keyof Scope] ?? fields[key];
      if (typeof value !== 'string' || !value || (fields[key] !== undefined && fields[key] !== value)) throw new ProtocolError('Missing/inconsistent path identity');
    }
    validateRequest(step.operation, request);
    let response: unknown;
    try {
      response = await transport.execute(step.operation, request, scope);
      if (step.responseKind !== 'success') throw new ProtocolError('Expected an API error');
      validateSuccess(step.operation, response);
      if (step.httpStatus !== operationRegistry[step.operation].successHttpStatus) throw new ProtocolError('Trace success HTTP mismatch');
    } catch (error) {
      if (!(error instanceof WorldApiError) || step.responseKind !== 'error') throw error;
      response = validateError(error.response);
      if (step.httpStatus !== error.response.error.httpStatus || step.nextAction !== error.response.error.clientAction) throw new ProtocolError('Trace error recovery/HTTP mismatch');
      if (!operationRegistry[step.operation].errorCodes.some((e) => e.code === error.response.error.code)) throw new ProtocolError('Error not registered for operation');
    }
    const envelope = response as Record<string, unknown>;
    if (envelope.operation != null && envelope.operation !== step.operation) throw new ProtocolError('Trace response operation mismatch');
    if (fields.requestId != null && envelope.requestId != null && fields.requestId !== envelope.requestId) throw new ProtocolError('Trace response requestId mismatch');
    const worldId = scope.worldId ?? fields.worldId;
    if (worldId && ((envelope.world as { worldId?: string } | null)?.worldId ?? envelope.worldId) !== worldId) throw new ProtocolError('Trace response worldId mismatch');
    // Validate before capturing or interpreting assertions, including error steps.
    for (const capture of step.captures) {
      const variable = trace.variables.find((v) => v.name === capture.variable)!;
      const value = at(response, capture.path);
      if (Object.hasOwn(bindings, variable.name) || !isType(value, variable.valueType)) throw new ProtocolError('Capture type/reassignment error');
      bindings[variable.name] = structuredClone(value);
    }
    for (const assertion of step.assertions) assertValue(response, assertion, bindings);
    if (step.expectedProjection != null) {
      const expected = instantiate(step.expectedProjection, bindings);
      if (!equal(at(response, step.projectionPath!), expected)) throw new ProtocolError('Independent state projection mismatch');
      // Digests were supplied by the independent Python expectation tool. TS
      // reads them; it does not calculate canonical bytes or derive an answer.
      if (at(response, step.digestPath!) !== sample.expectedDigests[step.id]) throw new ProtocolError('Expected state digest mismatch');
    }
  }
  return bindings;
}
