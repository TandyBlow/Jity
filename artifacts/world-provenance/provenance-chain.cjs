/**
 * Real chain over the world HTTP API: point A (real change) → time advance →
 * point B (real change) → read both back with get_state → derive evidence refs
 * → decide whether `before` is authorized. Same-origin browser fetch when run
 * through provenance-browser-run.cjs.
 */
const fs = require('node:fs');
const path = require('node:path');

const ROSTER = ['person_a', 'person_b', 'person_c', 'person_d', 'person_e', 'person_f'];

function groupOf(groupId, changeId, text, supersedes) {
  return {
    groupId, actorIds: ['person_a'], positions: {},
    appearances: { person_a: [{ id: changeId, text, supersedes }] },
    tasksAchieved: {}, subtasksAdded: {}, personalities: {}, sanities: {},
    taskCoverageIds: [...ROSTER].sort(), personalityCoverageIds: [],
  };
}

function evidenceId(pointId, entityId, kind, key) {
  return `${pointId}/${entityId}/${kind}/${key}`;
}

async function chain(fetcher, base, template) {
  const run = Math.random().toString(36).slice(2, 8);
  let counter = 0;
  const rid = (tag) => `${tag}_${run}_${++counter}`;
  const idsOf = (data) => Object.fromEntries(data.allocations.map((a) => [a.slotKey, a.id]));

  async function send(method, url, body) {
    let queryless = url;
    if (method === 'GET') {
      const params = [];
      if (url.includes('/context')) {
        params.push(['leaseToken', live.leaseToken], ['fenceEpoch', String(live.fenceEpoch)]);
      }
      queryless = `${url}${url.includes('?') ? '&' : '?'}${params
        .map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&')}`;
    }
    const response = await fetcher(queryless, {
      method,
      headers: { 'content-type': 'application/json', 'X-World-Protocol-Version': '2' },
      body: method === 'GET' ? undefined : JSON.stringify(body),
    });
    const text = await response.text();
    if (!response.ok) throw new Error(`${method} ${url} ${response.status}: ${text}`);
    return JSON.parse(text);
  }

  const named = JSON.parse(JSON.stringify(template));
  const NAMES = { person_a: '林川', person_b: '周宁', person_c: '陈默',
                  person_d: '沈禾', person_e: '叶南', person_f: '高岭' };
  for (const [id, name] of Object.entries(NAMES)) {
    if (named.characters[id]) named.characters[id].name = name;
  }
  const created = await send('POST', `${base}/worlds`, {
    protocolVersion: 2, requestId: rid('create'), initial: named });
  const worldId = created.data.worldId;
  const rootId = created.data.rootPointId;
  const lease = created.data.lease;
  const live = { leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch };
  const withLive = (extra) => ({ protocolVersion: 2, requestId: rid('req'), worldId, ...live, ...extra });

  async function narrate(pointId, text) {
    const claim = await send('POST',
      `${base}/worlds/${worldId}/points/${pointId}/narration-jobs`,
      withLive({ pointId, mode: 'head', currentClaim: null }));
    const data = claim.data || claim;
    await send('PUT', `${base}/worlds/${worldId}/points/${pointId}/narration`,
      withLive({ pointId, mode: 'head', claimToken: data.claimToken,
                 generation: data.generation,
                 issuedAtEpochMilli: data.issuedAtEpochMilli,
                 outcome: 'ready', text, failureReason: null }));
  }

  const claim = await send('POST', `${base}/worlds/${worldId}/points/${rootId}/narration-jobs`,
    withLive({ pointId: rootId, mode: 'head', currentClaim: null }));
  const claimData = claim.data || claim;
  const submit = await send('PUT', `${base}/worlds/${worldId}/points/${rootId}/narration`,
    withLive({ pointId: rootId, mode: 'head', claimToken: claimData.claimToken,
               generation: claimData.generation,
               issuedAtEpochMilli: claimData.issuedAtEpochMilli,
               outcome: 'ready', text: '开始。', failureReason: null }));
  if (!(submit.data || submit)) throw new Error('narration submit failed');

  const chain1 = idsOf((await send('POST', `${base}/worlds/${worldId}/ids`, withLive({
    allocationKey: 'chain', slots: ['advance', 'input', 'round'].map((kind) =>
      ({ slotKey: kind, kind, scope: null })) }))).data);
  const slot1 = idsOf((await send('POST', `${base}/worlds/${worldId}/ids`, withLive({
    allocationKey: 'round_1', slots: [
      { slotKey: 'point', kind: 'point', scope: null },
      { slotKey: 'group', kind: 'group', scope: chain1.round },
      { slotKey: 'change', kind: 'change', scope: null }] }))).data);

  const checkpoint = async (body) => send('PUT', `${base}/worlds/${worldId}/checkpoint`,
                                          withLive(body));
  await checkpoint({ operation: 'start_advance', expectedPointId: rootId, expectedVersion: 0,
                     expectedCheckpointRevision: 0, advanceId: chain1.advance,
                     inputId: chain1.input, roundId: chain1.round, inputText: '抬手。',
                     order: ROSTER });
  let revision = 1;
  await checkpoint({ operation: 'begin_point', expectedPointId: rootId, expectedVersion: 0,
                     expectedCheckpointRevision: revision++, pointId: slot1.point,
                     kind: 'normal',
                     timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'second' } } });
  const step1 = async (operation, extra) => checkpoint({
    operation, expectedPointId: rootId, expectedVersion: 0,
    expectedCheckpointRevision: revision++, pointId: slot1.point, ...extra });
  await step1('discover_group', { groupId: slot1.group, initiatorId: 'person_a',
                                  actionText: '抬手。', targetIds: null });
  await step1('extend_group', { groupId: slot1.group, sourceId: 'person_a', targets: [],
                                admittedMember: null });
  await step1('close_group', { groupId: slot1.group });
  await step1('stage_unit', { groupId: slot1.group,
                              candidates: groupOf(slot1.group, slot1.change, '袖口沾了雨', []),
                              results: { person_a: '抬手挡了一下。' } });
  for (const actor of ROSTER.slice(1)) await step1('record_skip', { slotActorId: actor });
  await step1('seal_point', {});

  const pointA = {
    worldId, id: slot1.point, sequence: 1, kind: 'normal', previousPointId: rootId,
    roundId: chain1.round, advanceId: chain1.advance, trigger: 'player',
    linkedFromPointId: null,
    timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'second' } },
    entityDeltas: { person_a: { entityId: 'person_a', appearanceChanges: [
      { id: slot1.change, text: '袖口沾了雨', supersedes: [] }] } } };
  await send('POST', `${base}/worlds/${worldId}/points`, withLive({
    advanceId: chain1.advance, roundId: chain1.round, expectedPointId: rootId,
    expectedVersion: 0, expectedCheckpointRevision: revision, pointId: slot1.point,
    point: pointA,
    settlementGroups: [groupOf(slot1.group, slot1.change, '袖口沾了雨', [])] }));

  await narrate(slot1.point, '抬手挡了一下。');
  const context = await send('GET', `${base}/worlds/${worldId}/context`, withLive({}));
  revision = context.data ? context.data.control.revision : context.control.revision;
  const view1 = context.data ? context.data : context;
  revision = view1.control.revision;

  await send('POST', `${base}/worlds/${worldId}/round-conclusion`, withLive({
    operation: 'conclude', advanceId: chain1.advance, roundId: chain1.round,
    expectedPointId: slot1.point, expectedVersion: 1,
    expectedCheckpointRevision: revision,
    conclusion: { kind: 'handback', closedBy: 'model', cancelReason: null } }));

  const chain2 = idsOf((await send('POST', `${base}/worlds/${worldId}/ids`, withLive({
    allocationKey: `chain2_${run}`,
    slots: ['advance', 'input', 'round'].map((kind) =>
      ({ slotKey: kind, kind, scope: null })) }))).data);

  const context2 = await send('GET', `${base}/worlds/${worldId}/context`, withLive({}));
  const view2 = context2.data ? context2.data : context2;
  revision = view2.control.revision;
  const headVersion = view2.world.head.version;
  await checkpoint({ operation: 'start_advance', expectedPointId: slot1.point,
                     expectedVersion: headVersion, expectedCheckpointRevision: revision,
                     advanceId: chain2.advance, inputId: chain2.input,
                     roundId: chain2.round, inputText: '走进门厅。',
                     order: ROSTER });
  revision += 1;
  const slot2 = idsOf((await send('POST', `${base}/worlds/${worldId}/ids`, withLive({
    allocationKey: `round_2_${run}`, slots: [
      { slotKey: 'point', kind: 'point', scope: null },
      { slotKey: 'group', kind: 'group', scope: chain2.round },
      { slotKey: 'change', kind: 'change', scope: null }] }))).data);
  await checkpoint({ operation: 'begin_point', expectedPointId: slot1.point,
                     expectedVersion: headVersion, expectedCheckpointRevision: revision++,
                     pointId: slot2.point, kind: 'normal',
                     timeAdvance: { boundary: 'elapsed',
                                    duration: { amount: 3, unit: 'second' } } });
  const step2 = async (operation, extra) => checkpoint({
    operation, expectedPointId: slot1.point, expectedVersion: headVersion,
    expectedCheckpointRevision: revision++, pointId: slot2.point, ...extra });
  const group2 = groupOf(slot2.group, slot2.change, '斗篷下摆湿了一片', []);
  group2.actorIds = ['person_a'];
  group2.appearances = { person_b: [{ id: slot2.change, text: '斗篷下摆湿了一片',
                                      supersedes: [] }] };
  await step2('discover_group', { groupId: slot2.group, initiatorId: 'person_a',
                                  actionText: '拉了他一把。', targetIds: null });
  await step2('extend_group', { groupId: slot2.group, sourceId: 'person_a', targets: [],
                                admittedMember: null });
  await step2('close_group', { groupId: slot2.group });
  await step2('stage_unit', { groupId: slot2.group, candidates: group2,
                              results: { person_a: '拉了他一把。' } });
  for (const actor of ROSTER.slice(1)) await step2('record_skip', { slotActorId: actor });
  await step2('seal_point', {});

  const pointB = {
    worldId, id: slot2.point, sequence: 2, kind: 'normal', previousPointId: slot1.point,
    roundId: chain2.round, advanceId: chain2.advance, trigger: 'player',
    linkedFromPointId: null,
    timeAdvance: { boundary: 'elapsed', duration: { amount: 3, unit: 'second' } },
    entityDeltas: { person_b: { entityId: 'person_b', appearanceChanges: [
      { id: slot2.change, text: '斗篷下摆湿了一片', supersedes: [] }] } } };
  await send('POST', `${base}/worlds/${worldId}/points`, withLive({
    advanceId: chain2.advance, roundId: chain2.round, expectedPointId: slot1.point,
    expectedVersion: headVersion, expectedCheckpointRevision: revision, pointId: slot2.point,
    point: pointB, settlementGroups: [group2] }));

  const readA = await send('GET', `${base}/worlds/${worldId}/state?` +
    new URLSearchParams({ point: slot1.point }), withLive({}));
  const readB = await send('GET', `${base}/worlds/${worldId}/state?` +
    new URLSearchParams({ point: slot2.point }), withLive({}));
  const bodyA = readA.data ? readA.data : readA;
  const bodyB = readB.data ? readB.data : readB;

  const refs = [];
  for (const [pointId, view] of [[slot1.point, bodyA], [slot2.point, bodyB]]) {
    for (const [entityId, delta] of Object.entries(view.entityDeltas || {})) {
      for (const change of delta.appearanceChanges || []) {
        refs.push({ pointId, evidenceId: evidenceId(pointId, entityId, 'appearance', change.id),
                    text: change.text });
      }
    }
  }
  const seconds = (view) => {
    const advance = view.timeAdvance;
    return advance && advance.boundary === 'elapsed' ? advance.duration.amount : 0;
  };
  return {
    worldId, rootId,
    pointA: { id: slot1.point, previousPointId: bodyA.previousPointId,
              elapsedSeconds: seconds(bodyA), deltas: Object.keys(bodyA.entityDeltas || {}) },
    pointB: { id: slot2.point, previousPointId: bodyB.previousPointId,
              elapsedSeconds: seconds(bodyB), deltas: Object.keys(bodyB.entityDeltas || {}) },
    evidenceRefs: refs,
    beforeAuthorized: refs.length === 2 && refs[0].pointId !== refs[1].pointId
      && seconds(bodyB) > 0 && bodyB.previousPointId === bodyA.pointId,
  };
}

module.exports = { chain };

function fixtureTemplate() {
  const root = path.join(__dirname, '..', '..');
  const snapshot = JSON.parse(fs.readFileSync(
    path.join(root, 'design/world-protocol/v2/fixtures/projections/normal.expected.json'),
    'utf8'));
  const template = snapshot.initial;
  delete template.worldId;
  return template;
}

if (require.main === module) {
  const base = process.env.BASE || 'http://127.0.0.1:8011';
  chain(fetch, base, fixtureTemplate()).then((result) => {
    const out = path.join(__dirname, 'provenance-chain.json');
    fs.writeFileSync(out, JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  }).catch((error) => { console.error('FAILED', error.message); process.exit(1); });
}
