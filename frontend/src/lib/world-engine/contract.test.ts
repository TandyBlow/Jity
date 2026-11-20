import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { HttpWorldTransport } from './http-transport';
import { canSchedule, operationRegistry, ProtocolError, recoveryAction, validateError, validateRequest, validateSchema, validateSuccess } from './protocol';
import { WorldApiError, WorldTimeoutError } from './transport';
import { FixtureModelOutputs, type FixedModelCall } from './fixture-model';
import { worldOperations, type RequestMap, type WorldOperation, type Success, type ErrorResponse } from './types';

const root = new URL('../../../../design/world-protocol/v2/', import.meta.url);
const load = <T = unknown>(name: string): T => JSON.parse(readFileSync(new URL(name, root), 'utf8'));
type Specimen<K extends WorldOperation> = { request: RequestMap[K]; success: Success<K>; error: ErrorResponse };
const readCase = <K extends WorldOperation>(op: K): Specimen<K> => ({
  request: load(`fixtures/api/${op}/request.json`), success: load(`fixtures/api/${op}/success.json`), error: load(`fixtures/api/${op}/error.json`),
});
const cases = {
  create_world: readCase('create_world'), get_context: readCase('get_context'),
  checkpoint_start_advance: readCase('checkpoint_start_advance'), checkpoint_begin_point: readCase('checkpoint_begin_point'),
  checkpoint_set_point_time: readCase('checkpoint_set_point_time'), checkpoint_discover_group: readCase('checkpoint_discover_group'),
  checkpoint_extend_group: readCase('checkpoint_extend_group'), checkpoint_close_group: readCase('checkpoint_close_group'),
  checkpoint_stage_unit: readCase('checkpoint_stage_unit'), checkpoint_record_skip: readCase('checkpoint_record_skip'),
  checkpoint_stage_time_scan: readCase('checkpoint_stage_time_scan'), checkpoint_seal_point: readCase('checkpoint_seal_point'),
  checkpoint_prepare_successor: readCase('checkpoint_prepare_successor'), checkpoint_restore_group_work: readCase('checkpoint_restore_group_work'),
  checkpoint_pause: readCase('checkpoint_pause'), checkpoint_resume: readCase('checkpoint_resume'),
  round_conclusion_conclude: readCase('round_conclusion_conclude'), round_conclusion_cancel: readCase('round_conclusion_cancel'),
  lease_acquire: readCase('lease_acquire'), lease_renew: readCase('lease_renew'), lease_release: readCase('lease_release'),
  allocate_ids: readCase('allocate_ids'), preview_point: readCase('preview_point'), create_rolls: readCase('create_rolls'),
  commit_point: readCase('commit_point'), list_points: readCase('list_points'), get_state: readCase('get_state'),
  narration_claim: readCase('narration_claim'), narration_claim_renew: readCase('narration_claim_renew'),
  narration_submit: readCase('narration_submit'), narration_get: readCase('narration_get'), narration_delete: readCase('narration_delete'),
} satisfies Record<WorldOperation, { request: unknown; success: unknown; error: unknown }>;
const fixture = <K extends WorldOperation>(op: K): Specimen<K> => cases[op] as unknown as Specimen<K>;
const scopeFor = (op: WorldOperation) => {
  const { request, success } = fixture(op);
  return { worldId: op === 'create_world' ? undefined : success.world.worldId,
    pointId: (request as { pointId?: string }).pointId ?? ('data' in success ? (success.data as { pointId?: string }).pointId : undefined) ?? success.world.head.pointId };
};

describe('all S1 operations consumed through HTTP transport', () => {
  it.each(worldOperations)('%s request/success/error are consumed without dropping fields', async (op) => {
    const { request, success, error } = fixture(op);
    const spec = operationRegistry[op];
    validateRequest(op, request);
    expect(validateSuccess(op, success)).toEqual(success);
    let calls = 0;
    const transport = new HttpWorldTransport('https://example.invalid/api/', async (url, init) => {
      calls++;
      expect(new URL(String(url)).pathname).toMatch(/^\/api\/worlds/);
      expect(init?.method).toBe(spec.method);
      expect(new Headers(init?.headers).get('X-World-Protocol-Version')).toBe('2');
      if (spec.method === 'GET' || spec.method === 'DELETE') {
        expect(init?.body).toBeUndefined();
        const fields = request as Record<string, unknown>;
        for (const key of spec.queryBindings) if (fields[key] != null) expect(new URL(String(url)).searchParams.get(key)).toBe(String(fields[key]));
      } else expect(JSON.parse(init?.body as string)).toEqual(request);
      return Response.json(success, { status: spec.successHttpStatus });
    });
    expect(await transport.execute(op, request as RequestMap[typeof op], scopeFor(op))).toEqual(success);
    expect(calls).toBe(1);
    const bad = new HttpWorldTransport('https://example.invalid', async () => Response.json(error, { status: error.error.httpStatus }));
    await expect(bad.execute(op, request, scopeFor(op))).rejects.toMatchObject({ name: 'WorldApiError', response: error });
    expect(recoveryAction(validateError(error))).toBeTruthy();
  });
});

it('rejects missing fields, unknown fields, version drift and illegal tagged unions', () => {
  const value: Partial<Success<'checkpoint_resume'>> = structuredClone(fixture('checkpoint_resume').success);
  delete value.control;
  expect(() => validateSuccess('checkpoint_resume', value)).toThrow(ProtocolError);
  for (const key of ['unexpected', 'protocolVersion', 'engineVersion', 'schemaVersion', 'canonicalVersion']) {
    const broken = structuredClone(fixture('checkpoint_resume').success) as unknown as Record<string, unknown>;
    broken[key] = key === 'unexpected' ? true : 'unsupported';
    expect(() => validateSuccess('checkpoint_resume', broken)).toThrow(ProtocolError);
  }
  const request = { ...fixture('checkpoint_pause').request, operation: 'resume' };
  expect(() => validateRequest('checkpoint_pause', request)).toThrow(ProtocolError);
  expect(() => validateSchema('GateView', { status: 'pending' })).toThrow(ProtocolError);
});

it('handles resume-blocked, claim replay, input cleanup and business errors', () => {
  const resumed = validateSuccess('checkpoint_resume', fixture('checkpoint_resume').success);
  expect(resumed.data.paused).toBe(false);
  expect(canSchedule(resumed.control)).toBe(false);
  const replay = validateSuccess('narration_claim', load('fixtures/branches/claim-replay.success.json'));
  expect(replay.replayed).toBe(true);
  expect(replay.data).not.toHaveProperty('claimToken');
  const commit = structuredClone(fixture('commit_point').success);
  const data = structuredClone(commit.data);
  commit.replayed = true;
  commit.control.paused = true;
  commit.control.canCompute = false;
  commit.control.blockedReasons = ['paused'];
  expect(validateSuccess('commit_point', commit).data).toEqual(data);
  expect(JSON.stringify(commit)).not.toContain('inputText');
  const codes = load<{ errorCodes: Record<string, unknown> }>('api-contract.json').errorCodes;
  for (const code of Object.keys(codes)) {
    const error = validateError(load(`fixtures/errors/${code}.json`));
    expect(recoveryAction(error)).toBeTruthy();
    expect(new WorldApiError(error).response.error.code).toBe(code);
  }
});

it('preserves request identity after a timeout and never retries automatically', async () => {
  let count = 0;
  const request = fixture('checkpoint_pause').request;
  const before = JSON.stringify(request);
  const transport = new HttpWorldTransport('https://example.invalid', async () => { count++; return await new Promise<Response>(() => {}); }, 5);
  await expect(transport.execute('checkpoint_pause', request, scopeFor('checkpoint_pause'))).rejects.toBeInstanceOf(WorldTimeoutError);
  expect(count).toBe(1);
  expect(JSON.stringify(request)).toBe(before);
});

it('handles invalid JSON, caller cancellation, HTTP mismatches and wrong identities', async () => {
  const request = fixture('checkpoint_pause').request;
  const scope = scopeFor('checkpoint_pause');
  const raw = new HttpWorldTransport('https://example.invalid', async () => new Response('broken', { status: 200 }));
  await expect(raw.execute('checkpoint_pause', request, scope)).rejects.toThrow('Invalid JSON');
  const abort = new AbortController(); abort.abort();
  await expect(raw.execute('checkpoint_pause', request, scope, abort.signal)).rejects.toMatchObject({ name: 'AbortError' });
  const wrong = structuredClone(fixture('checkpoint_pause').success); wrong.requestId = 'another';
  const mismatch = new HttpWorldTransport('https://example.invalid', async () => Response.json(wrong));
  await expect(mismatch.execute('checkpoint_pause', request, scope)).rejects.toThrow('requestId mismatch');
  const err = fixture('checkpoint_pause').error;
  const wrongStatus = new HttpWorldTransport('https://example.invalid', async () => Response.json(err, { status: 400 }));
  await expect(wrongStatus.execute('checkpoint_pause', request, scope)).rejects.toThrow('HTTP/error contract mismatch');
  await expect(raw.execute('checkpoint_pause', request, { worldId: 'cross_world' })).rejects.toThrow('differs from request');
});

it('constructs both restore requests without a client-owned destination attempt', () => {
  const trace = load<{ steps: { success: unknown }[] }>('fixtures/branches/takeover.json');
  const grant = validateSuccess('lease_acquire', trace.steps[0].success).data;
  const context = validateSuccess('get_context', trace.steps[1].success);
  for (const role of ['current', 'successor'] as const) {
    const point = context.recovery![role]!;
    expect(point.groups).toEqual([]);
    const input = { ...point.restoreSources[0], protocolVersion: 2, requestId: `restore_${role}`,
      operation: 'restore_group_work', worldId: context.world.worldId,
      leaseToken: grant.leaseToken, fenceEpoch: grant.fenceEpoch,
      expectedPointId: context.world.head.pointId, expectedVersion: context.world.head.version,
      expectedCheckpointRevision: context.control.revision };
    validateRequest('checkpoint_restore_group_work', input);
    expect(input).not.toHaveProperty('attempt');
  }
  expect(fileURLToPath(root)).toContain('world-protocol');
});

it('consumes fixed model outputs without allocating IDs or simulating state', async () => {
  const request = fixture('checkpoint_discover_group').request;
  const calls: FixedModelCall[] = [
    { task: 'action' as const, key: 'source', input: { actorId: request.initiatorId }, output: { actionText: request.actionText } },
    { task: 'updates' as const, key: 'new-task', input: {}, output: { localRef: 'local_task', goal: '检查教室', status: 'pending' } },
  ];
  const model = new FixtureModelOutputs(calls);
  await expect(model.generate('targets', 'source', calls[0].input)).rejects.toThrow('Unexpected');
  const output = await model.generate('action', 'source', calls[0].input);
  expect(output).toEqual(calls[0].output);
  (output as Record<string, unknown>).actionText = 'mutated by caller';
  expect(calls[0].output).toHaveProperty('actionText', request.actionText);
  expect(() => model.assertComplete()).toThrow('not fully consumed');
  const task = await model.generate('updates', 'new-task', {});
  expect(task).not.toHaveProperty('id');
  expect(task).toHaveProperty('localRef', 'local_task');
  model.assertComplete();
  await expect(model.generate('updates', 'new-task', {})).rejects.toThrow('Unexpected');
});
