// H1 browser adapter, owned by A. Imports B's actual controller and HTTP
// transport from a read-only checkout; never substitutes a response transport.
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const [browserRoot, configFile, resultFile, cacheDir] = process.argv.slice(2);
const config = JSON.parse(readFileSync(configFile, 'utf8'));
const requireBrowser = createRequire(resolve(browserRoot, 'frontend/package.json'));
const { createServer } = await import(pathToFileURL(requireBrowser.resolve('vite')).href);
const { chromium } = requireBrowser('@playwright/test');
const server = await createServer({
  root: resolve(browserRoot, 'frontend'), configFile: false, cacheDir,
  server: { host: '127.0.0.1', port: config.browserPort, strictPort: true, hmr: false,
    fs: { allow: [browserRoot] } },
  plugins: [{ name: 'world-h1-page', configureServer(vite) {
    vite.middlewares.use((req, res, next) => {
      if (req.url !== '/__h1') return next();
      res.setHeader('Content-Type', 'text/html');
      res.end('<!doctype html><title>Jity H1 HTTP acceptance</title>');
    });
  } }],
});
let browser;
try {
  await server.listen();
  browser = await chromium.launch({ headless: true, channel: config.browserChannel });
  const page = await browser.newPage();
  await page.goto(`http://127.0.0.1:${config.browserPort}/__h1`);
  const results = await page.evaluate(async ({ apiUrl, samples, timeSamples }) => {
    const { ControllerDriver, initialMemory } = await import('/src/lib/world-engine/controller.ts');
    const { HttpWorldTransport } = await import('/src/lib/world-engine/http-transport.ts');
    const { WorldApiError } = await import('/src/lib/world-engine/transport.ts');
    const check = (condition, message) => { if (!condition) throw new Error(message); };
    const all = [];
    for (const sample of samples) {
      const req = sample.requests;
      const exchanges = [];
      const modelCalls = [];
      const errorChecks = [];
      // Default fetcher path: B's constructor now binds the platform fetch
      // to the global object, so the default receiver is legal in Chromium
      // (83dbe3b). No injection, no mock — the page's own window.fetch.
      const http = new HttpWorldTransport(apiUrl);
      const expectApiError = async (operation, payload, scope, code) => {
        try {
          await http.execute(operation, payload, scope);
        } catch (error) {
          check(error instanceof WorldApiError, `${operation}: error was not consumable by B transport: ${error}`);
          check(error.response.error.code === code, `${operation}: wrong error code`);
          errorChecks.push({ operation, code, clientAction: error.response.error.clientAction });
          return;
        }
        throw new Error(`${operation}: expected refusal`);
      };
      const transport = { async execute(operation, request, scope) {
        const response = await http.execute(operation, request, scope);
        exchanges.push({ operation, request: structuredClone(request), scope, response });
        if (operation === 'checkpoint_begin_point') {
          await expectApiError('checkpoint_restore_group_work', {
            protocolVersion: 2, requestId: `req_H1_restore_${sample.id}`,
            worldId: request.worldId, operation: 'restore_group_work', pointId: request.pointId,
            groupId: driver.getMemory().ids.group, leaseToken: request.leaseToken,
            fenceEpoch: request.fenceEpoch, expectedPointId: request.expectedPointId,
            expectedVersion: request.expectedVersion,
            expectedCheckpointRevision: response.control.revision,
            sourceEpoch: request.fenceEpoch, sourceAttempt: 1,
            manifest: [{ memberId: req.s7.initiatorId, actionContentHash: '0'.repeat(64),
              targetsContentHash: null, resultContentHash: null, candidatesContentHash: null }],
          }, scope, 'frozen_work_missing');
          const after = await http.execute('get_context', {}, scope);
          for (const key of ['world', 'control', 'work']) {
            check(JSON.stringify(after[key]) === JSON.stringify(response[key]), `restore refusal changed ${key}`);
          }
        }
        if (operation === 'preview_point') {
          const repeated = await http.execute(operation, request, scope);
          check(JSON.stringify(response.data) === JSON.stringify(repeated.data), 'repeated preview changed');
          check(response.control.revision === repeated.control.revision, 'preview changed revision');
          exchanges.push({ operation, request: structuredClone(request), scope,
            response: repeated, repeat: true });
        }
        return response;
      } };
      const expectedTasks = ['initial', 'narration', 'pointPlan', 'action', 'targets', 'results', 'updates', 'narration'];
      let driver;
      const model = { async generate(task, key, input) {
        check(task === expectedTasks[modelCalls.length], `unexpected model task ${task}`);
        modelCalls.push({ task, key, input: structuredClone(input) });
        const ids = driver.getMemory().ids;
        switch (task) {
          case 'initial': return structuredClone(req.s1.initial);
          case 'narration': return modelCalls.length === 2 ? req.s3.text : req.s20.text;
          case 'pointPlan': return [{ pointId: ids.point, kind: req.s6.kind,
            timeAdvance: req.s6.timeAdvance, actorIds: req.s10.candidates.actorIds }];
          case 'action': return { kind: 'act', text: req.s7.actionText };
          case 'targets': return { targets: [] };
          case 'results': return structuredClone(req.s10.results);
          case 'updates': return [{ stage: 'position', changes: Object.fromEntries(
            Object.entries(req.s10.candidates.positions).map(([id, position]) => [id, { positionSet: position }])) }];
          default: throw new Error(`unhandled task ${task}`);
        }
      } };
      const memory = initialMemory(`req_H1_${sample.id}`, 'h1_browser');
      memory.playerInput = { text: req.s5.inputText, order: req.s5.order };
      memory.allocPlan = { allocationKey: req.s4.allocationKey, slots: req.s4.slots };
      driver = new ControllerDriver({ transport, model }, memory, { world: null },
        { identityAliases: { 'group:person_a': 'group' } });
      let complete = false;
      for (let step = 0; step < 200; step++) {
        const decision = driver.pendingDecision();
        if (decision.kind === 'model' && decision.task === 'continuation') {
          complete = true;
          break;
        }
        const terminal = await driver.step();
        check(!terminal, `controller stopped: ${JSON.stringify(terminal)}`);
      }
      check(complete && modelCalls.length === expectedTasks.length, 'H1 stop boundary not reached');
      const create = exchanges.find((e) => e.operation === 'create_world').response;
      const commit = exchanges.find((e) => e.operation === 'commit_point').response;
      const worldId = create.data.worldId;
      const pointId = commit.data.pointId;
      await transport.execute('get_state', {}, { worldId });
      await transport.execute('list_points', {}, { worldId });
      await transport.execute('narration_get', {}, { worldId, pointId });
      const context = await http.execute('get_context', {}, { worldId });
      check(context.control.canCompute && context.control.gate.status === 'none', 'head gate not cleared');
      check(context.world.head.narrationStatus === 'ready', 'head narration not ready');
      await expectApiError('narration_get', {}, { worldId, pointId: 'invalid id' }, 'version_mismatch');
      // Actual Fetch from a different origin exercised Chromium CORS/preflight.
      all.push({ id: sample.id, exchanges, modelCalls, errorChecks, context, memory: driver.getMemory() });
    }
    const times = [];
    for (const sample of timeSamples) {
      const http = new HttpWorldTransport(apiUrl);
      let counter = 0;
      const requestId = () => `req_H1_time_${sample.id}_${counter++}`;
      const create = await http.execute('create_world', {
        ...samples.find((entry) => entry.id === sample.id).requests.s1,
        requestId: requestId(),
      }, {});
      const worldId = create.data.worldId;
      const root = create.data.rootPointId;
      const lease = create.data.lease;
      const scope = { worldId };
      const leaseBind = { worldId, leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch };
      const ready = async (pointId, text) => {
        const claim = await http.execute('narration_claim', {
          protocolVersion: 2, requestId: requestId(), ...leaseBind,
          pointId, mode: 'head', currentClaim: null,
        }, { worldId, pointId });
        const response = await http.execute('narration_submit', {
          protocolVersion: 2, requestId: requestId(), ...leaseBind, pointId, mode: 'head',
          claimToken: claim.data.claimToken, generation: claim.data.generation,
          issuedAtEpochMilli: claim.data.issuedAtEpochMilli,
          outcome: 'ready', text, failureReason: null,
        }, { worldId, pointId });
        return { claim, response };
      };
      await ready(root, '纯时间场景的根点。');
      const slots = ['advance', 'input', 'round', 'point', 'change'].map((kind) => ({
        slotKey: kind, kind, scope: null,
      }));
      const allocation = await http.execute('allocate_ids', {
        protocolVersion: 2, requestId: requestId(), ...leaseBind,
        allocationKey: 'h1_time_slots', slots,
      }, scope);
      const ids = Object.fromEntries(allocation.data.allocations.map((entry) => [entry.slotKey, entry.id]));
      const req = sample.requests;
      const oldChange = Object.values(req.s3.candidates.personalities)[0][0].id;
      const replacements = new Map([
        [req.s2.worldId, worldId], [req.s2.expectedPointId, root],
        [req.s2.pointId, ids.point], [req.s5.advanceId, ids.advance],
        [req.s5.roundId, ids.round], [oldChange, ids.change],
      ]);
      const rebind = (value) => {
        if (Array.isArray(value)) return value.map(rebind);
        if (value && typeof value === 'object') return Object.fromEntries(
          Object.entries(value).map(([key, item]) => [replacements.get(key) ?? key, rebind(item)]));
        return replacements.get(value) ?? value;
      };
      await http.execute('checkpoint_start_advance', {
        protocolVersion: 2, requestId: requestId(), ...leaseBind, operation: 'start_advance',
        expectedPointId: root, expectedVersion: 0, expectedCheckpointRevision: 0,
        advanceId: ids.advance, inputId: ids.input, roundId: ids.round,
        inputText: '等待到中午。', order: samples.find((entry) => entry.id === sample.id).requests.s5.order,
      }, scope);
      const served = { s1: await http.execute('get_context', {}, scope) };
      let revision = served.s1.control.revision;
      for (const [step, operation] of [['s2', 'checkpoint_begin_point'], ['s3', 'checkpoint_stage_time_scan'],
        ['s4', 'checkpoint_seal_point'], ['s5', 'commit_point']]) {
        served[step] = await http.execute(operation, {
          ...rebind(req[step]), requestId: requestId(), ...leaseBind,
          expectedPointId: root, expectedVersion: 0, expectedCheckpointRevision: revision,
        }, scope);
        revision = served[step].control.revision;
        if (step === 's3') {
          const previewRequest = { protocolVersion: 2, worldId,
            advanceId: ids.advance, roundId: ids.round, pointId: ids.point,
            expectedPointId: root, expectedVersion: 0, expectedCheckpointRevision: revision,
            timeAdvance: req.s2.timeAdvance, settlementGroups: [rebind(req.s3.candidates)] };
          served.preview = await http.execute('preview_point', previewRequest, scope);
          const repeat = await http.execute('preview_point', previewRequest, scope);
          check(JSON.stringify(served.preview.data) === JSON.stringify(repeat.data), 'time preview changed');
        }
      }
      const narration = await ready(ids.point, req.s7.text);
      served.s6 = narration.claim;
      served.s7 = narration.response;
      served.s8 = await http.execute('get_state', {}, scope);
      times.push({ id: sample.id, served, identityBindings: [...replacements] });
    }
    return { normal: all, time: times };
  }, config);
  writeFileSync(resultFile, JSON.stringify({ browser: browser.version(), results }, null, 2));
  process.stdout.write(`Browser H1: ${results.normal.length} T01 controller flows and ${results.time.length} time-scan HTTP flows completed\n`);
} finally {
  if (browser) await browser.close();
  await server.close();
}
