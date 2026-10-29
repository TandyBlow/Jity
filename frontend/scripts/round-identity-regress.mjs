// 复核 20 ①b 三项的机械回归（对照 .local/review-b673574.cjs 的复现脚本，
// 断言已翻转为修复后行为）。走真实 ControllerDriver + 真实 bootstrapRecovery，
// transport/recovery 读边界打桩——不启动服务、不调模型。
//
//   cd frontend && node scripts/round-identity-regress.mjs
//
// 三项：
//   1. recover 后的 sink 补丁按增量折入：从 recover 前内存整包构造的补丁
//      不得擦掉恢复出的 point/group 身份与既有 allocation key。
//   2. 只有确认结论为 continue 才通知 sink：automatic 轮的 handback（服务端
//      保留已结束轮摘要）不得再分配。
//   3. 未注册 sink 记录 lastRoundIdentityError；预置分配路径合法、不记错。
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const root = resolve(frontend, '..');
const require = createRequire(import.meta.url);
const ts = require(resolve(frontend, 'node_modules/typescript'));
// 与 .local 复现脚本同一加载方式：TS 直译为 CJS，桩可以真的打进去。
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText, filename);
const recovery = require(resolve(frontend, 'src/lib/world-engine/recovery.ts'));
const { ControllerDriver, initialMemory } = require(resolve(frontend, 'src/lib/world-engine/controller.ts'));

const control = (phase = 'select_actor') => ({ phase, paused: false, revision: 0, gate: { status: 'none' }, blockedReasons: [], canCompute: true });
const player = {
  worldId: 'w1', head: { pointId: 'root', version: 0, stateDigest: 'd0', narrationStatus: 'ready' },
  advance: { advanceId: 'adv1', inputId: 'in1', intentStatus: 'consumed', inputAvailable: true },
  round: { roundId: 'r1', trigger: 'player', order: ['a'], cursor: 1, actedIds: ['a'], visitedIds: ['a'], conclusion: null },
  lease: { fenceEpoch: 1 }, successor: null, activePointId: null, activeRoundId: 'r1',
};
const automatic = { ...player, activeRoundId: 'r2', round: { ...player.round, roundId: 'r2', trigger: 'automatic', cursor: 0, actedIds: [], visitedIds: [] } };
const conclusion = { kind: 'continue', closedBy: 'model', cancelReason: null, candidateCharacterIds: ['a'], nextRoundId: 'r2' };
const model = { generate: async () => { throw new Error('unexpected model'); } };
const transport = { execute: async () => ({ world: automatic, control: control(), work: null, data: { kind: 'continue', roundId: 'r1', nextRoundId: 'r2' } }) };

// 1) recover 替换内存后，旧快照式的 sink 补丁只按 key 合并。
recovery.readControllerRecovery = async () => ({
  context: { world: player, control: control('assess_continuation'), work: null, activeInput: null },
  leaseToken: 'lease1', ids: { point: 'recovered_point', 'group:a': 'recovered_group' },
  plan: null, workingState: null, roundChanges: null, point: null, successor: null,
});
const memory = initialMemory('review', 'holder');
const driver = new ControllerDriver({ transport, model }, memory);
assert.equal(await driver.recover('w1'), undefined);
driver.memory.continuation = conclusion;
driver.memory.allocatedKeys.push('existing_key');
// 复核复现的写法：补丁从 recover 前的 memory 对象整包复制。
driver.setRoundIdentitySink(async (roundId) => ({
  ids: { ...memory.ids, 'group:a': 'new_group' },
  roundAllocations: { ...memory.roundAllocations, [roundId]: { allocationKey: 'new_key', slots: [] } },
  allocatedKeys: [...memory.allocatedKeys, 'new_key'],
}));
await driver.step();
assert.equal(driver.getMemory().ids.point, 'recovered_point');
assert.equal(driver.getMemory().ids['group:a'], 'new_group');
assert.deepEqual(driver.getMemory().allocatedKeys, ['existing_key', 'new_key']);
assert.deepEqual(driver.getMemory().roundAllocations, { r2: { allocationKey: 'new_key', slots: [] } });
console.log('PASS 1 recovered ids / existing keys survive a stale whole-memory sink patch');

// 2) 未注册 sink：记录；预置分配路径不记录。
const missing = initialMemory('missing', 'holder');
missing.leaseToken = 'lease1'; missing.continuation = conclusion;
const noSink = new ControllerDriver({ transport, model }, missing, { world: player, control: control('assess_continuation') });
await noSink.step();
assert.equal(noSink.getMemory().lastRoundIdentityError, 'round_identity_sink_missing:r2');
const seeded = initialMemory('seeded', 'holder');
seeded.leaseToken = 'lease1'; seeded.continuation = conclusion;
seeded.roundAllocations = { r2: { allocationKey: 'r2_slots', slots: [] } };
const seededDriver = new ControllerDriver({ transport, model }, seeded, { world: player, control: control('assess_continuation') });
await seededDriver.step();
assert.equal(seededDriver.getMemory().lastRoundIdentityError, null);
console.log('PASS 2 missing sink recorded, pre-seeded allocation path clean');

// 3) automatic 轮的 handback 不再触发 sink。
const handMemory = initialMemory('handback', 'holder');
handMemory.leaseToken = 'lease1'; handMemory.continuation = { kind: 'handback', closedBy: 'model', cancelReason: null };
const handWorld = { ...automatic, round: { ...automatic.round, conclusion: handMemory.continuation } };
let calls = 0;
const handDriver = new ControllerDriver({ transport: { execute: async () => ({ world: handWorld, control: control('complete'), work: null, data: { kind: 'handback', roundId: 'r2', nextRoundId: null } }) }, model }, handMemory, { world: automatic, control: control('assess_continuation') });
handDriver.setRoundIdentitySink(() => { calls++; });
await handDriver.step();
assert.equal(calls, 0);
console.log('PASS 3 handback over the finished automatic round calls the sink 0 times');
