// B-side S1 review. This consumes the shared artifacts without importing Python.
// It is a review gate, not the IF-05 production transport or IF-04 trace runner.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import Ajv2020 from 'ajv/dist/2020.js';

const root = new URL('../../design/world-protocol/v2/', import.meta.url);
const load = (name) => JSON.parse(readFileSync(new URL(name, root), 'utf8'));
const contract = load('api-contract.json');
const schema = load('world-protocol.schema.json');
const ajv = new Ajv2020({ strictSchema: true, strictTypes: false,
  strictRequired: false, allErrors: true, coerceTypes: false,
  useDefaults: false, removeAdditional: false });
// Pydantic's OpenAPI discriminator mapping is an annotation here. JSON Schema
// oneOf/const enforce the unions; Ajv's optional discriminator optimizer does
// not support these mappings. Unknown *other* keywords still fail compilation.
ajv.addKeyword({ keyword: 'discriminator', schemaType: 'object', valid: true });
ajv.addSchema(schema);
for (const name of Object.keys(schema.$defs)) ajv.getSchema(`${schema.$id}#/$defs/${name}`);

let checks = 0;
const failures = [];
function check(label, run) {
  try { run(); checks++; }
  catch (error) { failures.push({ label, message: error.message }); }
}
function validate(name, value) {
  const fn = ajv.getSchema(`${schema.$id}#/$defs/${name}`);
  assert(fn, `unresolved schema: ${name}`);
  const before = JSON.stringify(value);
  assert(fn(value), `${name}: ${ajv.errorsText(fn.errors, { separator: '; ' })}`);
  assert.equal(JSON.stringify(value), before, 'validator changed the payload');
}
const roundTrip = (value) => assert.deepEqual(JSON.parse(JSON.stringify(value)), value);

// Authored from workflow §9.2: neither the keyset nor the fields are copied
// dynamically from the operation registry being reviewed.
const calls = {
  create_world: ['initial', 'worldId rootPointId lease'],
  get_context: ['', ''],
  checkpoint_start_advance: ['advanceId inputId roundId inputText order', 'advanceId inputId roundId'],
  checkpoint_begin_point: ['pointId kind timeAdvance', 'pointId'],
  checkpoint_set_point_time: ['pointId timeAdvance', 'pointId timeAdvance'],
  checkpoint_discover_group: ['pointId groupId initiatorId actionText', 'groupId targetIds'],
  checkpoint_extend_group: ['pointId groupId sourceId', 'groupId memberIds frontierIds'],
  checkpoint_close_group: ['pointId groupId', 'groupId closed'],
  checkpoint_stage_unit: ['pointId groupId candidates results', 'groupId unitId working'],
  checkpoint_record_skip: ['pointId slotActorId', 'pointId working'],
  checkpoint_stage_time_scan: ['pointId candidates', 'pointId working'],
  checkpoint_seal_point: ['pointId', 'pointId prefixDigest'],
  checkpoint_prepare_successor: ['pointId successorPointId timeAdvance', 'pointId successorPointId prefixDigest successor'],
  checkpoint_restore_group_work: ['pointId groupId sourceEpoch sourceAttempt manifest', 'pointId groupId fenceEpoch attempt sourceEpoch sourceAttempt restoredMemberIds'],
  checkpoint_pause: ['', 'paused'],
  checkpoint_resume: ['', 'paused'],
  round_conclusion_conclude: ['advanceId roundId conclusion', 'kind roundId nextRoundId'],
  round_conclusion_cancel: ['advanceId roundId cancelReason', 'roundId abandonedGroupIds'],
  lease_acquire: ['holderId', 'holderId leaseToken fenceEpoch expiresAtEpochMilli'],
  lease_renew: ['leaseToken fenceEpoch', 'leaseToken fenceEpoch expiresAtEpochMilli'],
  lease_release: ['leaseToken fenceEpoch', 'released'],
  allocate_ids: ['allocationKey slots', 'allocations'],
  preview_point: ['advanceId roundId pointId timeAdvance settlementGroups', 'pointId workingState pointProjection mergedEntityDeltas workingStateDigest pointProjectionDigest'],
  create_rolls: ['rolls', 'rolls'],
  commit_point: ['advanceId roundId pointId point settlementGroups', 'pointId version stateDigest'],
  list_points: ['', 'points'],
  get_state: ['', 'pointId version state stateDigest'],
  narration_claim: ['pointId mode', 'pointId mode generation claimToken fenceEpoch issuedAtEpochMilli expiresAtEpochMilli'],
  narration_claim_renew: ['pointId mode claimToken generation issuedAtEpochMilli', 'pointId mode generation fenceEpoch issuedAtEpochMilli expiresAtEpochMilli'],
  narration_submit: ['pointId mode claimToken generation issuedAtEpochMilli outcome', 'pointId narrationStatus generation'],
  narration_get: ['', 'pointId narrationStatus generation text'],
  narration_delete: ['mode claimToken generation issuedAtEpochMilli', 'pointId narrationStatus invalidatedGeneration'],
};
const operations = new Map(contract.operations.map((entry) => [entry.operation, entry]));
const fixtures = new Map();
const words = (text) => text.split(' ').filter(Boolean);
const hasFields = (value, fields) => words(fields).forEach((key) => assert(key in value, `missing ${key}`));
const preconditions = (name) => Object.fromEntries(operations.get(name).preconditions.map((p) => [p.kind, p.value]));
check('32 operation keyset', () => assert.deepEqual([...operations.keys()].sort(), Object.keys(calls).sort()));

const clientActions = {
  retry_same_request: 'keep_request_id_and_body',
  reacquire_lease: 'stop_writes_and_acquire_lease',
  refresh_context: 'reload_server_context',
  wait_narration: 'stop_computation_and_wait',
  regenerate_narration: 'obtain_fresh_narration_claim',
  resolve_gate: 'inspect_control_before_scheduling',
  pause: 'pause_and_preserve_frozen_work',
  fix_request: 'stop_automatic_retry_and_fix_input',
  none: 'stop_and_show_error',
};
check('client action vocabulary', () => assert.deepEqual(Object.keys(clientActions).sort(), [...contract.clientActions].sort()));

for (const [name, [requestFields, resultFields]] of Object.entries(calls)) {
  check(`operation ${name}`, () => {
    const spec = operations.get(name);
    const request = load(`fixtures/api/${name}/request.json`);
    const success = load(`fixtures/api/${name}/success.json`);
    const error = load(`fixtures/api/${name}/error.json`);
    fixtures.set(name, { request, success, error });
    if (spec.requestSchema) validate(spec.requestSchema, request);
    else assert.deepEqual(request, {});
    validate(spec.successSchema, success);
    validate('ErrorResponse', error);
    [request, success, error].forEach(roundTrip);
    hasFields(request, requestFields);
    hasFields(success.data ?? {}, resultFields);
    if (request.requestId) assert.equal(success.requestId, request.requestId);
    if (success.operation) assert.equal(success.operation, name);
    if (request.worldId) assert.equal(success.world.worldId, request.worldId);
    assert(spec.errorCodes.some((entry) => entry.code === error.error.code));
    assert(clientActions[error.error.clientAction]);
    const code = contract.errorCodes[error.error.code];
    assert.equal(error.error.httpStatus, code.httpStatus);
    assert.equal(error.error.clientAction, code.clientAction);
    if (code.controlRequired) assert(error.control);
    if (spec.idempotency.scope !== 'none') assert.equal(spec.idempotency.key, 'requestId');
    // Exercise an HTTP serialization plan using only schema-declared query
    // fields, path bindings and the protocol header. No credentials in GET body.
    const pathBindings = { worldId: success.world.worldId,
      pointId: request.pointId ?? success.data?.pointId ?? success.world.head.pointId };
    const url = new URL(spec.path.replace(/\{(\w+)\}/g, (_, key) => encodeURIComponent(pathBindings[key])), 'https://world.invalid');
    const headers = new Headers({ [contract.protocolHeader]: String(request.protocolVersion ?? contract.protocolVersion) });
    assert.equal(headers.get('X-World-Protocol-Version'), '2');
    if (spec.method === 'GET' || spec.method === 'DELETE') {
      for (const key of spec.queryBindings) {
        if (request[key] != null) url.searchParams.set(key, String(request[key]));
      }
      for (const key of spec.queryBindings) {
        if (request[key] != null) assert.equal(url.searchParams.get(key), String(request[key]));
      }
    } else roundTrip(JSON.parse(JSON.stringify(request)));
    assert(!url.pathname.includes('undefined'));
    assert.equal(success.protocolVersion, 2);
  });
}
for (const [code, spec] of Object.entries(contract.errorCodes)) {
  check(`error ${code}`, () => {
    const value = load(`fixtures/errors/${code}.json`);
    validate('ErrorResponse', value);
    assert.equal(value.error.code, code);
    assert.equal(value.error.httpStatus, spec.httpStatus);
    assert.equal(value.error.retryable, spec.retryable);
    assert.equal(value.error.clientAction, spec.clientAction);
    assert(clientActions[value.error.clientAction]);
  });
}

const compute = ['checkpoint_start_advance', 'checkpoint_begin_point', 'checkpoint_set_point_time',
  'checkpoint_discover_group', 'checkpoint_extend_group', 'checkpoint_close_group',
  'checkpoint_stage_unit', 'checkpoint_record_skip', 'checkpoint_stage_time_scan',
  'checkpoint_seal_point', 'checkpoint_prepare_successor', 'preview_point',
  'create_rolls', 'commit_point', 'round_conclusion_conclude'];
check('computation permissions', () => {
  for (const name of compute) {
    const p = preconditions(name);
    assert.equal(p.headNarration, 'ready', name);
    assert.equal(p.gate, 'cleared', name);
    assert.equal(p.paused, false, name);
  }
});
check('pause/resume/restore permissions', () => {
  for (const name of ['checkpoint_pause', 'checkpoint_resume', 'checkpoint_restore_group_work']) {
    const p = preconditions(name);
    for (const key of ['gate', 'headNarration', 'paused']) assert(!(key in p), `${name}: ${key}`);
  }
  assert.deepEqual(preconditions('checkpoint_restore_group_work').pointWork, ['open', 'sealed']);
  assert.equal(preconditions('checkpoint_restore_group_work').frozenSource, 'active_reference');
  assert.equal(operations.get('checkpoint_restore_group_work').mutatesRevision, false);
  assert(!('paused' in preconditions('round_conclusion_cancel')));
  assert.equal(preconditions('round_conclusion_cancel').headNarration, 'ready');
});
check('resume does not authorize computation', () => {
  const { success } = fixtures.get('checkpoint_resume');
  assert.equal(success.data.paused, false);
  assert.equal(success.control.canCompute, false);
  assert(success.control.blockedReasons.length > 0);
});
check('root claims and credential replay', () => {
  const root = fixtures.get('create_world').success;
  assert.equal(root.world.round, null);
  assert.equal(root.control.gate.generation, 1);
  assert(root.data.lease.leaseToken);
  const replay = load('fixtures/branches/claim-replay.success.json');
  validate('NarrationClaimSuccess', replay);
  assert.equal(replay.replayed, true);
  assert(!('claimToken' in replay.data));
  assert(!('claimToken' in fixtures.get('narration_claim_renew').success.data));
});
check('preview to point commit and normal handback', () => {
  const preview = fixtures.get('preview_point').success;
  const commit = structuredClone(fixtures.get('commit_point').request);
  for (const key of ['requestId', 'requestHash', 'replayed']) assert(!(key in preview));
  commit.point = preview.data.pointProjection;
  validate('CommitPointRequest', commit);
  assert.deepEqual(commit.point.entityDeltas, preview.data.mergedEntityDeltas);
  validate('ConcludeRoundRequest', load('fixtures/branches/handback.request.json'));
  const handback = load('fixtures/branches/handback.success.json');
  validate('ConcludeRoundSuccess', handback);
  assert.equal(handback.data.nextRoundId, null);
});

const takeover = load('fixtures/branches/takeover.json');
check('takeover wire frames and preserved frozen work', () => {
  for (const step of takeover.steps) {
    validate(step.requestSchema, step.request);
    validate(step.successSchema, step.success);
  }
  const [grant, readBefore, , , readAfter] = takeover.steps;
  assert.equal(grant.success.data.fenceEpoch, 8);
  assert.equal(readBefore.request.leaseToken, grant.success.data.leaseToken);
  for (const role of ['current', 'successor']) {
    const before = readBefore.success.recovery[role];
    const after = readAfter.success.recovery[role];
    assert.equal(before.payloadStatus, 'restore_required');
    assert.deepEqual(before.groups, []);
    assert.equal(before.timeScanCandidates, null);
    assert.equal(after.payloadStatus, 'available');
    assert.deepEqual(before.work, after.work);
    assert.deepEqual(before.restoreSources, after.restoreSources);
  }
  assert.deepEqual(readBefore.success.control, readAfter.success.control);
  for (const entry of takeover.failures) {
    validate(entry.requestSchema, entry.request);
    validate(entry.errorSchema, entry.error);
    assert.deepEqual(entry.error.control, readBefore.success.control);
    assert(clientActions[entry.error.error.clientAction]);
  }
});
for (const [role, index] of [['current', 2], ['successor', 3]]) {
  check(`takeover ${role}: construct restore from server-owned values`, () => {
    const grant = takeover.steps[0].success;
    const snapshot = takeover.steps[1].success;
    const source = snapshot.recovery[role].restoreSources[0];
    const request = { ...source, protocolVersion: 2, operation: 'restore_group_work',
      requestId: `b_review_restore_${role}`, worldId: snapshot.world.worldId,
      leaseToken: grant.data.leaseToken, fenceEpoch: grant.data.fenceEpoch,
      expectedPointId: snapshot.world.head.pointId, expectedVersion: snapshot.world.head.version,
      expectedCheckpointRevision: snapshot.control.revision };
    // Source epoch/attempt come from the read. Only the restore transaction
    // allocates the destination attempt and returns its accepted copy identity.
    validate('RestoreGroupWorkRequest', request);
    assert(!('attempt' in request));
    const expected = takeover.steps[index].request;
    for (const key of Object.keys(source)) assert.deepEqual(request[key], expected[key]);
    const result = takeover.steps[index].success;
    validate('RestoreGroupWorkSuccess', result);
    assert.equal(result.data.pointId, request.pointId);
    assert.equal(result.data.groupId, request.groupId);
    assert.equal(result.data.fenceEpoch, grant.data.fenceEpoch);
    assert(Number.isSafeInteger(result.data.attempt) && result.data.attempt > source.sourceAttempt);
  });
}

console.log(`S1 B consumer review: ${checks} passed, ${failures.length} failed; ` +
  `${Object.keys(schema.$defs).length} definitions, ${operations.size} operations, ` +
  `${Object.keys(contract.errorCodes).length} error codes; ${fileURLToPath(root)}`);
for (const failure of failures) console.error(`FAIL ${failure.label}: ${failure.message}`);
if (failures.length) process.exitCode = 1;
