// A-owned fixed-trace prerequisite, using B's real default HTTP transport.
// It is not a substitute for B's refresh/takeover controller integration.
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

const [browserRoot, configFile, resultFile, cacheDir] = process.argv.slice(2);
const config = JSON.parse(readFileSync(configFile, 'utf8'));
const requireBrowser = createRequire(resolve(browserRoot, 'frontend/package.json'));
const { createServer } = await import(pathToFileURL(requireBrowser.resolve('vite')).href);
const { chromium } = requireBrowser('@playwright/test');
const server = await createServer({
  root: resolve(browserRoot, 'frontend'), configFile: false, cacheDir,
  server: { host: '127.0.0.1', port: config.browserPort, strictPort: true, hmr: false,
    fs: { allow: [browserRoot, resolve(browserRoot, 'frontend/node_modules')] } },
  plugins: [{ name: 'world-h2-page', configureServer(vite) {
    vite.middlewares.use((req, res, next) => {
      if (req.url !== '/__h2') return next();
      res.setHeader('Content-Type', 'text/html');
      res.end('<!doctype html><title>Jity H2 transport prerequisite</title>');
    });
  } }],
});

// This setup runs afresh after page.reload(). No controller/model memory is
// injected; the fixed-trace harness only retains declared test identities.
async function install(page) {
  await page.evaluate(async ({ apiUrl, steps }) => {
    const { HttpWorldTransport } = await import('/src/lib/world-engine/http-transport.ts');
    const { WorldApiError } = await import('/src/lib/world-engine/transport.ts');
    const check = (ok, reason) => { if (!ok) throw new Error(reason); };
    const pointer = (value, path) => path.split('/').slice(1).reduce(
      (node, key) => node[key.replaceAll('~1', '/').replaceAll('~0', '~')], value);
    const instantiate = (value, bindings) => {
      if (Array.isArray(value)) return value.map((item) => instantiate(item, bindings));
      if (value && typeof value === 'object') {
        if ('$var' in value) {
          check(value.$var in bindings, `missing binding ${value.$var}`);
          return structuredClone(bindings[value.$var]);
        }
        if ('$map' in value) return Object.fromEntries(value.$map.map(({ key, value: item }) =>
          [instantiate(key, bindings), instantiate(item, bindings)]));
        return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, instantiate(item, bindings)]));
      }
      return value;
    };
    // Native page fetch, including browser CORS/preflight. No fetch injection.
    const http = new HttpWorldTransport(apiUrl);
    const call = async (state, operation, request, scope) => {
      const response = await http.execute(operation, request, scope);
      state.exchanges.push({ operation, request: structuredClone(request), scope, response });
      if (response.control) state.revision = response.control.revision;
      return response;
    };
    const run = async (state, id) => {
      const step = steps.find((item) => item.id === id);
      const request = instantiate(step.request, state.bindings);
      if (request.requestId) request.requestId = `${request.requestId}_${state.id}`;
      if ('expectedCheckpointRevision' in request) request.expectedCheckpointRevision = state.revision;
      if (step.operation === 'narration_submit') Object.assign(request, {
        claimToken: state.claim.claimToken, generation: state.claim.generation,
        issuedAtEpochMilli: state.claim.issuedAtEpochMilli,
      });
      const scope = instantiate(step.scope, state.bindings);
      const response = await call(state, step.operation, request, scope);
      state.served[id] = response;
      for (const capture of step.captures) state.bindings[capture.variable] = pointer(response, capture.path);
      if (step.operation === 'narration_claim') state.claim = response.data;
      return response;
    };
    const expectOldWrite = async (state, request, scope) => {
      try { await http.execute('checkpoint_record_skip', request, scope); }
      catch (error) {
        check(error instanceof WorldApiError, `old write was not a B-consumable API error: ${error}`);
        check(['stale_epoch', 'lease_invalid'].includes(error.response.error.code), 'old authority was not fenced');
        state.oldWriteError = error.response.error.code;
        return;
      }
      throw new Error('old authority wrote after takeover');
    };
    window.h2 = { check, pointer, instantiate, http, call, run, expectOldWrite };
  }, config);
}

let browser;
try {
  await server.listen();
  browser = await chromium.launch({ headless: true, channel: config.browserChannel });
  const page = await browser.newPage();
  const samples = [];
  for (const [index, sample] of config.samples.entries()) {
    await page.goto(`http://127.0.0.1:${config.browserPort}/__h2`);
    await install(page);
    const checkpoint = await page.evaluate(async (sample) => {
      const state = { id: sample.id, bindings: sample.values, served: {}, exchanges: [], revision: 0 };
      const { call, run, check } = window.h2;
      for (let i = 1; i <= 10; i++) await run(state, `s${i}`);
      const scope = { worldId: state.served.s1.data.worldId };
      const lease = state.served.s1.data.lease;
      const current = await call(state, 'get_context', {
        includeRecovery: true, leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch,
      }, scope);
      check(current.recovery?.current?.payloadStatus === 'available', 'current-epoch frozen recovery is unavailable');
      check(current.recovery.current.groups.length === 1, 'staged frozen group is missing');
      state.frozenBefore = current.recovery.current.groups[0];
      state.beforeReload = current;
      state.scope = scope;
      state.oldLease = lease;
      // A fresh operation under the old credentials, never an idempotent retry.
      state.oldWrite = { protocolVersion: 2, requestId: `req_h2_old_${state.id}`,
        worldId: scope.worldId, ...lease, operation: 'record_skip',
        expectedPointId: current.world.head.pointId, expectedVersion: current.world.head.version,
        expectedCheckpointRevision: current.control.revision, pointId: current.work.pointId,
        slotActorId: 'person_b' };
      delete state.oldWrite.expiresAtEpochMilli;
      window.h2HeapSentinel = true;
      return state;
    }, sample);
    // Python stops and starts the real service process with the same SQLite
    // file. The handshake is outside the API and cannot fake service replies.
    writeFileSync(resolve(config.runtime, `restart-${index}.request`), 'restart');
    const deadline = Date.now() + 45000;
    while (!existsSync(resolve(config.runtime, `restart-${index}.ready`))) {
      if (Date.now() > deadline) throw new Error('service restart handshake timed out');
      await delay(50);
    }
    await page.reload();
    const reloadLostJavascriptHeap = await page.evaluate(() => window.h2 === undefined && window.h2HeapSentinel === undefined);
    if (!reloadLostJavascriptHeap) throw new Error('reload did not clear the page JavaScript heap');
    await install(page);
    const actual = await page.evaluate(async (state) => {
      const { call, run, check, http, expectOldWrite } = window.h2;
      const old = state.oldLease;
      const current = await call(state, 'get_context', {
        includeRecovery: true, leaseToken: old.leaseToken, fenceEpoch: old.fenceEpoch,
      }, state.scope);
      for (const field of ['work', 'recovery', 'activeInput'])
        check(JSON.stringify(current[field]) === JSON.stringify(state.beforeReload[field]), `${field} changed across reload/restart`);
      const originalStage = state.exchanges.find((entry) => entry.operation === 'checkpoint_stage_unit');
      const replay = await http.execute(originalStage.operation, originalStage.request, state.scope);
      check(replay.replayed && JSON.stringify(replay.data) === JSON.stringify(originalStage.response.data), 'restart lost idempotency');
      state.replayAfterRestart = true;
      await call(state, 'lease_release', { protocolVersion: 2, requestId: `req_h2_release_${state.id}`,
        leaseToken: old.leaseToken, fenceEpoch: old.fenceEpoch }, state.scope);
      const acquired = await call(state, 'lease_acquire', { protocolVersion: 2,
        requestId: `req_h2_acquire_${state.id}`, worldId: state.scope.worldId,
        holderId: `h2_new_${state.id}` }, state.scope);
      state.oldFenceEpoch = old.fenceEpoch;
      state.newFenceEpoch = acquired.data.fenceEpoch;
      check(state.newFenceEpoch > state.oldFenceEpoch, 'takeover did not advance fence epoch');
      state.bindings.v5 = acquired.data.fenceEpoch;
      state.bindings.v8 = acquired.data.leaseToken;
      const beforeRefusal = await call(state, 'get_context', {}, state.scope);
      await expectOldWrite(state, state.oldWrite, state.scope);
      const afterRefusal = await call(state, 'get_context', {}, state.scope);
      for (const field of ['world', 'work', 'control'])
        check(JSON.stringify(beforeRefusal[field]) === JSON.stringify(afterRefusal[field]), `old refusal changed ${field}`);
      const protection = { includeRecovery: true, leaseToken: acquired.data.leaseToken,
        fenceEpoch: acquired.data.fenceEpoch };
      const hidden = await call(state, 'get_context', protection, state.scope);
      check(hidden.recovery?.current?.payloadStatus === 'restore_required', 'old-epoch payload was not hidden before copy');
      check(hidden.recovery.current.groups.length === 0, 'old-epoch group bytes leaked before copy');
      const sources = hidden.recovery.current.restoreSources;
      check(sources.length > 0, 'accepted restore source metadata is missing');
      for (const [index, source] of sources.entries()) {
        await call(state, 'checkpoint_restore_group_work', { protocolVersion: 2,
          requestId: `req_h2_restore_${state.id}_${index}`, worldId: state.scope.worldId,
          leaseToken: acquired.data.leaseToken, fenceEpoch: acquired.data.fenceEpoch,
          expectedPointId: hidden.world.head.pointId, expectedVersion: hidden.world.head.version,
          expectedCheckpointRevision: state.revision, operation: 'restore_group_work', ...source,
        }, state.scope);
      }
      const recovered = await call(state, 'get_context', protection, state.scope);
      check(recovered.recovery.current.payloadStatus === 'available', 'copy did not make the current epoch payload available');
      state.restoredSourceCount = sources.length;
      state.frozenAfter = recovered.recovery.current.groups[0];
      for (const field of ['members', 'candidates', 'inputProjectionHash'])
        check(JSON.stringify(state.frozenBefore[field]) === JSON.stringify(state.frozenAfter[field]), `copy changed ${field}`);
      // Remaining operations come from the frozen trace, not model sampling.
      // This proves the service can continue using accepted candidates; B's
      // actual controller must separately learn to choose this resume path.
      state.generationCallsAfterRecovery = 0;
      for (let i = 11; i <= 23; i++) await run(state, `s${i}`);
      state.finalContext = await call(state, 'get_context', {}, state.scope);
      return state;
    }, checkpoint);
    actual.reloadLostJavascriptHeap = reloadLostJavascriptHeap;
    samples.push(actual);
  }
  writeFileSync(resultFile, JSON.stringify({ browser: browser.version(), samples }, null, 2));
  process.stdout.write(`Browser transport prerequisite: ${samples.length} refresh/restart/takeover flows completed\n`);
} finally {
  if (browser) await browser.close();
  await server.close();
}
