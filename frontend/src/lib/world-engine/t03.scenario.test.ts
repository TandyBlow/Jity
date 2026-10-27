/** T03 time-scan and collapse acceptance: non-empty scan deltas reach the
 * later previews through the same settlement list (A §7), the seal preview
 * aligns with the final independent expectation, and the collapse group's
 * candidates carry the ruled world-roster coverage. #5 场景级多阶段（2026-10-26
 * 验收）：updates 按规范阶段拆分阶梯——①前序变化进入后序输入（部分应用正
 * 文）、②完整候选只暂存一次且等于从声明输出独立重建的合并期望、③最终 Δ 与
 * 独立期望一致、④时间不重复累加；崩溃组的 tasks 边界镜像前向引用拆分。 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, test } from 'vitest';
import { assertSharedExpectation, driveControllerSegment } from './harness';
import { buildT03Scenario, openT03Session, type T03TraceName } from './t03.scenario';
import { instantiate, readTrace } from './trace-runner';
import type { Json, SettlementGroup } from './types';

const ROSTER = ['person_a', 'person_b', 'person_c', 'person_d', 'person_e', 'person_f'];

interface PreviewData {
  workingState: {
    time: Json;
    characters: Record<string, {
      sanity: number;
      tasks: Record<string, { status: string; parentTaskId: string | null }>;
      appearanceChanges: { id: string; sourcePointId: string; active: boolean }[];
      personalityChanges: { id: string; sourcePointId: string; active: boolean }[];
    }>;
  };
  pointProjection: { entityDeltas: Record<string, Json> };
  mergedEntityDeltas: Record<string, Json>;
}

const EXPECTED_TIMES: Record<T03TraceName, { dateTime: string; instantOrdinal: number }> = {
  'T03': { dateTime: '2026-01-01T12:00:00', instantOrdinal: 0 },
  'T03-collapse': { dateTime: '2026-01-01T11:59:07', instantOrdinal: 0 },
};

async function runT03Acceptance(traceName: T03TraceName, sampleId: string) {
  const scenario = buildT03Scenario(traceName, sampleId);
  await openT03Session(scenario);
  await driveControllerSegment(scenario, traceName);
  const { step, response } = await scenario.transport.runInspect(scenario.finalStepId);
  assertSharedExpectation(step, response);
  expect(scenario.driver.pendingDecision()).toMatchObject({ kind: 'model', task: 'continuation', key: scenario.roundId });
  scenario.transport.assertConsumed();
  scenario.model.assertConsumed();
  return scenario;
}

describe.each([
  ['T03', 'sample_1'],
  ['T03', 'sample_2'],
  ['T03-collapse', 'sample_1'],
  ['T03-collapse', 'sample_2'],
] as [T03TraceName, string][])('%s %s: scan/collapse segment, previews, inspect, stop boundary', (traceName, sampleId) => {
  test('opens the session, drives the scan point, ends at the continuation boundary', async () => {
    const scenario = await runT03Acceptance(traceName, sampleId);

    // Context bootstrap, then controller-issued allocation for collapse.
    expect(scenario.transport.ops[0]).toBe('get_context');
    expect(scenario.transport.ops).not.toContain('create_world');
    expect(scenario.transport.ops).toContain(traceName === 'T03' ? 'checkpoint_stage_time_scan' : 'checkpoint_stage_unit');

    // Preview specimens: begin + two split-ladder boundaries + the stage
    // anchor, placeholder digests.
    const previews = scenario.corpus.steps.filter((s) => s.segment === 'preview');
    expect(previews).toHaveLength(4);
    expect(previews.every((s) => s.placeholderDigests === true)).toBe(true);
    const [beginPreview, boundary1, boundary2, sealPreview] = previews;
    const suffix = sampleId === 'sample_2' ? '_sampleB' : '';
    const pointId = `${traceName === 'T03' ? 'time_only' : 'p4'}${suffix}`;
    const groupId = `group_task${suffix}`;
    const child = `task_new_child${suffix}`;

    // —— #5 场景级多阶段验收（2026-10-26）——
    // ① 前序变化进入后序输入：边界预览只携带已声明的可达部分（部分阶段
    //    预览），后序阶段的模型输入=已应用前序候选的部分应用正文。
    const boundary1Groups = (boundary1.request as unknown as { settlementGroups: SettlementGroup[] }).settlementGroups;
    if (traceName === 'T03') {
      expect(boundary1Groups).toHaveLength(1);
      expect(boundary1Groups[0]).toMatchObject({ groupId: null, tasksAchieved: { person_c: ['task_wait_noon'] }, personalities: {} });
    } else {
      expect(boundary1Groups).toHaveLength(1);
      expect(boundary1Groups[0]).toMatchObject({ groupId, appearances: { person_c: [expect.objectContaining({ id: `change_final${suffix}` })] }, tasksAchieved: {} });
      // 拆分边界：tasks 阶段的 child 达成是前向引用——被延后，绝不入预览。
      const boundary2Groups = (boundary2.request as unknown as { settlementGroups: SettlementGroup[] }).settlementGroups;
      expect(boundary2Groups).toHaveLength(1);
      expect(boundary2Groups[0].tasksAchieved).toEqual({});
      expect(boundary2Groups[0].appearances.person_c).toHaveLength(1);
    }
    // ④ 时间没有重复累加：全部边界/锚点正文同点同刻，时间推进只在点位。
    const previewTimes = previews.map((s) => (s.response as unknown as { data: PreviewData }).data.workingState.time);
    expect(new Set(previewTimes.map((t) => JSON.stringify(t)))).toHaveLength(1);
    expect(previewTimes[0]).toMatchObject(EXPECTED_TIMES[traceName]);
    for (const preview of previews) {
      expect((preview.request as { timeAdvance: Json }).timeAdvance).toEqual((scenario.corpus.steps.find((step) => step.operation === 'checkpoint_begin_point')!.request as { timeAdvance: Json }).timeAdvance);
    }

    // THE A §7 point: the stage anchor's preview carries the staged unit in
    // its settlement list — T03's scan candidate (groupId null, non-empty
    // sections), T03-collapse's group candidates under the ruled coverage.
    const sealGroups = (sealPreview.request as unknown as { settlementGroups: SettlementGroup[] }).settlementGroups;
    expect(sealGroups).toHaveLength(1);
    if (traceName === 'T03') {
      expect(sealGroups[0]).toMatchObject({ groupId: null, sanities: { person_c: 35 } });
    } else {
      expect(sealGroups[0]).toMatchObject({ groupId });
    }
    expect(sealGroups[0].taskCoverageIds).toEqual(ROSTER);
    expect(sealGroups[0].personalityCoverageIds).toEqual(ROSTER);

    // Bodies: the begin preview is the inherited base state under the staged
    // time; the seal preview is the committed final state (serve-time
    // alignment binds it to the independent expectation); the split-boundary
    // bodies are the partial-application ladder states.
    const begin = (beginPreview.response as unknown as { data: PreviewData }).data;
    const seal = (sealPreview.response as unknown as { data: PreviewData }).data;
    expect(begin.workingState.time).toMatchObject(EXPECTED_TIMES[traceName]);
    expect(seal.workingState.time).toEqual(begin.workingState.time);
    expect(begin.pointProjection.entityDeltas).toEqual({});
    expect(begin.mergedEntityDeltas).toEqual({});
    expect((beginPreview.request as { settlementGroups: unknown[] }).settlementGroups).toEqual([]);
    expect(seal.mergedEntityDeltas).toEqual(seal.pointProjection.entityDeltas);
    expect(Object.keys(seal.mergedEntityDeltas)).toEqual(['person_c']);
    const before = begin.workingState.characters.person_c;
    const after = seal.workingState.characters.person_c;
    expect(before.sanity).toBe(30);
    expect(before.tasks.task_wait_noon.status).toBe('pending');
    expect(before.appearanceChanges).toEqual([]);
    expect(before.personalityChanges).toEqual([]);
    if (traceName === 'T03') {
      const body1 = (boundary1.response as unknown as { data: PreviewData }).data.workingState.characters.person_c;
      const body2 = (boundary2.response as unknown as { data: PreviewData }).data.workingState.characters.person_c;
      expect(body1.tasks.task_wait_noon.status).toBe('achieved'); // tasks 已应用
      expect(body1.sanity).toBe(30); // sanity 未应用
      expect(body1.personalityChanges).toEqual([]); // personality 未应用
      expect(body2.tasks.task_wait_noon.status).toBe('achieved');
      expect(body2.personalityChanges).toEqual([expect.objectContaining({ sourcePointId: pointId, active: true })]); // personality 已应用
      expect(body2.sanity).toBe(30);
      expect(after.sanity).toBe(35);
      expect(after.tasks.task_wait_noon.status).toBe('achieved');
      expect(after.personalityChanges).toEqual([expect.objectContaining({ sourcePointId: pointId, active: true })]);
    } else {
      const parent = `task_new_parent${suffix}`;
      const body1 = (boundary1.response as unknown as { data: PreviewData }).data.workingState.characters.person_c;
      expect(body1.appearanceChanges).toEqual([expect.objectContaining({ id: `change_final${suffix}`, sourcePointId: pointId, active: true })]); // appearance 已应用
      expect(body1.tasks[parent]).toBeUndefined();
      expect(body1.tasks[child]).toBeUndefined(); // 前向引用未应用——subtasks 阶段据此声明
      expect(body1.sanity).toBe(after.sanity);
      expect(after.tasks[parent]).toMatchObject({ status: 'pending', parentTaskId: 'task_c_root' });
      expect(after.tasks[child]).toMatchObject({ status: 'achieved', parentTaskId: parent });
      expect(after.appearanceChanges).toEqual([expect.objectContaining({ id: `change_final${suffix}`, sourcePointId: pointId, active: true })]);
      // The candidate adds a pending child and achieves it in the same unit;
      // the server projection collapses that into one achieved addition.
      const added = sealGroups[0].subtasksAdded.person_c;
      const parentTask = added.find((task) => task.parentTaskId === 'task_c_root');
      const childTask = added.find((task) => task.parentTaskId === parentTask?.id);
      expect(parentTask).toBeDefined();
      expect(childTask).toBeDefined();
      expect(sealGroups[0].tasksAchieved.person_c).toEqual([childTask!.id]);
      // 子任务 id 已按 §9.3 派生为分配身份；同一映射也改写 parentTaskId 与
      // tasksAchieved 引用，预览折入已暂存候选时保持与 stage/commit 一致。
      expect(sealGroups[0].subtasksAdded.person_c.find((task) => task.parentTaskId === 'task_c_root')?.status).toBe('pending');
      expect(seal.pointProjection.entityDeltas.person_c).toMatchObject({
        subtasksAdded: [expect.objectContaining({ id: parent, status: 'pending' }), expect.objectContaining({ id: child, status: 'achieved' })],
      });
      expect(seal.pointProjection.entityDeltas.person_c).not.toHaveProperty('tasksAchieved');
    }

    // Roster legality of the collapse group: what the DRIVER sent.
    const sentStage = scenario.transport.requests.map((r) => r as { candidates?: SettlementGroup }).find((r) => r.candidates?.groupId === groupId);
    if (traceName === 'T03-collapse') {
      expect(sentStage).toBeDefined();
      expect(sentStage!.candidates!.taskCoverageIds).toEqual(ROSTER);
      expect(sentStage!.candidates!.personalityCoverageIds).toEqual(ROSTER);
    }

    // Model calls: generated from the recording, updates split per stage.
    const calls = scenario.model.calls.map((c) => `${c.task}:${c.key}`);
    expect(calls[0]).toBe(`pointPlan:${scenario.roundId}`);
    if (traceName === 'T03') {
      // #7：零覆盖计划 + 六个未处理槽位 → 逐人判断（固定输出=skip），再扫时间。
      expect(calls).toEqual([
        `pointPlan:${scenario.roundId}`,
        ...ROSTER.map((actor) => `action:${actor}`),
        `updates:time_scan:${pointId}#tasks`, `updates:time_scan:${pointId}#personality`, `updates:time_scan:${pointId}#sanity`, `narration:${pointId}`,
      ]);
      // 补的跳过交换必须与真实 A 服务同语义（定向复核实测）：首次 skip 即
      // 锁定时间、本点输入机会标为已处理；stage/seal 保持该工作态；提交时
      // world.advance 随点位结算翻为 consumed（后续叙事/读取视图一致）。
      type WorkView = { timeLocked: boolean; working: { intentStatus: string } };
      const skipWork = (scenario.corpus.steps.find((step) => step.id === 'b-skip-person_a')!.response as unknown as { work: WorkView }).work;
      expect(skipWork.timeLocked).toBe(true);
      expect(skipWork.working.intentStatus).toBe('consumed');
      for (const operation of ['checkpoint_stage_time_scan', 'checkpoint_seal_point']) {
        const stageWork = (scenario.corpus.steps.find((step) => step.operation === operation)!.response as unknown as { work: WorkView }).work;
        expect(stageWork.timeLocked).toBe(true);
        expect(stageWork.working.intentStatus).toBe('consumed');
      }
      const commitIndex = scenario.corpus.steps.findIndex((step) => step.operation === 'commit_point');
      for (const step of scenario.corpus.steps.slice(commitIndex)) {
        const view = step.response as unknown as { world?: { advance: { intentStatus: string } } };
        if (view.world) expect(view.world.advance.intentStatus).toBe('consumed');
      }
    } else {
      expect(calls).toEqual([`pointPlan:${scenario.roundId}`, 'action:person_c', 'targets:person_c', `results:${groupId}`, `updates:${groupId}#appearance`, `updates:${groupId}#tasks`, `updates:${groupId}#subtasks`, `narration:${pointId}`]);
    }
    // ①（续）：后序阶段输入必须已含前序候选；首阶段读阶梯前状态。
    const stageInputs = scenario.model.calls.filter((call) => call.task === 'updates').map((call) => (call.input as { workingState: PreviewData['workingState'] }).workingState);
    expect(stageInputs[0]).toEqual(begin.workingState);
    expect(stageInputs[1]).not.toEqual(stageInputs[0]);
    if (traceName === 'T03') {
      expect(stageInputs[1].characters.person_c.tasks.task_wait_noon.status).toBe('achieved');
      expect(stageInputs[2].characters.person_c.personalityChanges).toHaveLength(1);
      expect(stageInputs[2].characters.person_c.sanity).toBe(30); // sanity 由阶段 3 声明，仍未应用
    } else {
      expect(stageInputs[1].characters.person_c.appearanceChanges).toHaveLength(1);
      expect(stageInputs[1].characters.person_c.tasks[child]).toBeUndefined();
      expect(stageInputs[2]).toEqual(stageInputs[1]); // 拆分边界只再应用可达部分（外貌）——正文不变
    }

    // ② 完整候选只暂存一次，且与独立权威夹具（轨迹录制的 stage 请求候选，
    //    原文件直读＋模板实例化；唯一许可的推导=覆盖率裁定规则）逐字一致
    //    ——期望不经任何生产合并函数（共同出错时不得全绿）。
    const stageOp = traceName === 'T03' ? 'checkpoint_stage_time_scan' : 'checkpoint_stage_unit';
    expect(scenario.transport.ops.filter((operation) => operation === stageOp)).toHaveLength(1);
    const rawTrace = JSON.parse(readFileSync(resolve(process.cwd(), `../design/world-protocol/v2/traces/${traceName}.json`), 'utf8'));
    const traceDoc = readTrace(rawTrace);
    const traceSample = traceDoc.samples.find((entry) => entry.id === sampleId);
    if (!traceSample) throw new Error(`unknown sample ${sampleId}`);
    const recordedStage = traceDoc.steps.find((step) => step.operation === stageOp)!;
    const recordedCandidates = (instantiate(recordedStage.request, traceSample.values) as { candidates: Record<string, unknown> }).candidates;
    const hasAchieved = Object.values((recordedCandidates.tasksAchieved ?? {}) as Record<string, unknown[]>).some((list) => list.length > 0);
    // 已登记覆盖率桥（collapse 的 pre-ruling 形状）按 2026-10-22 裁定修正：
    // 有达成 ⇒ 全角色名册，否则为空。
    recordedCandidates.personalityCoverageIds = hasAchieved ? [...ROSTER] : [];
    const sentStageRequest = scenario.transport.requests[scenario.transport.ops.indexOf(stageOp)] as unknown as { candidates: Record<string, unknown> };
    // §9.3 身份派生：候选里的 change/task id 是程序分配值（发送前改写），
    // 结构/文本/覆盖仍须与独立权威夹具逐字一致——比较剥除定义 id、父引用
    // 与 tasksAchieved 引用值，分配形态另行断言。
    const stripIds = (candidates: Record<string, unknown>): Record<string, unknown> => {
      const clone = structuredClone(candidates) as { appearances?: Record<string, Record<string, unknown>[]>; personalities?: Record<string, Record<string, unknown>[]>; subtasksAdded?: Record<string, Record<string, unknown>[]>; tasksAchieved?: Record<string, string[]> };
      for (const section of [clone.appearances, clone.personalities, clone.subtasksAdded]) {
      for (const [entity, list] of Object.entries(section ?? {})) {
        section![entity] = list.map(({ id: _id, parentTaskId: _parent, supersedes: _supersedes, ...rest }) => rest);
      }
      }
      for (const [entity, list] of Object.entries(clone.tasksAchieved ?? {})) {
        clone.tasksAchieved![entity] = list.map(() => 'task_ref');
      }
      return clone;
    };
    expect(stripIds(sentStageRequest.candidates)).toEqual(stripIds(recordedCandidates));
    for (const section of [sentStageRequest.candidates.appearances, sentStageRequest.candidates.personalities, sentStageRequest.candidates.subtasksAdded] as Record<string, { id: string }[]>[]) {
      for (const list of Object.values(section ?? {})) {
        for (const item of list) expect(item.id).toMatch(/^alloc_(change|task)_\d+$/);
      }
    }
    const sentCandidates = sentStageRequest.candidates as { tasksAchieved?: Record<string, string[]>; subtasksAdded?: Record<string, { id: string; parentTaskId: string | null }[]> };
    for (const list of Object.values(sentCandidates.tasksAchieved ?? {})) {
      for (const reference of list) {
        if (traceName === 'T03-collapse') expect(reference).toMatch(/^alloc_task_\d+$/);
        else expect(reference).toBe('task_wait_noon'); // 已登记的状态任务不是新分配身份
      }
    }
    for (const list of Object.values(sentCandidates.subtasksAdded ?? {})) {
      for (const task of list) if (task.parentTaskId != null && task.parentTaskId.startsWith('task_new')) {
        expect(task.parentTaskId).toMatch(/^alloc_task_\d+$/);
      }
    }

    // ③ 最终 Δ 与独立权威夹具一致：commit 请求的 point.entityDeltas 与录制
    //    commit 请求逐字（collapse 的子任务状态浓缩是录制投影的一部分）。
    const recordedCommit = instantiate(traceDoc.steps.find((step) => step.operation === 'commit_point')!.request, traceSample.values) as { point: { entityDeltas: Record<string, Json>; timeAdvance: Json } };
    const commitRequest = scenario.transport.requests[scenario.transport.ops.indexOf('commit_point')] as { point: { entityDeltas: Record<string, Json>; timeAdvance: Json } };
    expect(commitRequest.point.entityDeltas).toEqual(recordedCommit.point.entityDeltas);
    // ④（续）：commit 的点位时间推进恰好一次。
    const beginRequest = scenario.corpus.steps.find((step) => step.operation === 'checkpoint_begin_point')!.request as { timeAdvance: Json };
    expect(commitRequest.point.timeAdvance).toEqual(beginRequest.timeAdvance);

    // 拆分记账：拆分边界应用了可达部分——不是跳过；未决引用随结算批次落定。
    expect(scenario.driver.getMemory().updatesPreviewSkipped).toBe(0);
    expect(scenario.driver.getMemory().updatesPendingRefs).toEqual([]);
    expect(scenario.driver.getMemory().stagedTimeScan).toBeNull();
    expect(scenario.driver.getMemory().staged).toEqual([]);
    // 组装阶梯：每条叙事链 +2 次读取（目标＋前驱）。
    expect(scenario.transport.ops).toHaveLength(traceName === 'T03' ? 21 : 19);
    if (traceName === 'T03-collapse') {
      expect(scenario.transport.ops[1]).toBe('allocate_ids');
      expect((scenario.transport.requests[1] as { requestId: string }).requestId).toMatch(/^req_T03-collapse_\d+$/);
      expect(scenario.driver.getMemory().ids['group:person_c']).toBe(groupId);
      expect(scenario.driver.getMemory().ids.point).toBe(pointId);
    }
  });

  test('rejects a boundary preview that leaks the deferred forward reference into the fold', async () => {
    // 崩溃组专用：边界 2 的在途组必须只携带可达部分（外貌）——被延后的
    // child 达成入预览即偏离驱动器行为（A 会以状态外引用拒绝）。
    const scenario = buildT03Scenario('T03-collapse', 'sample_1');
    const boundary2 = scenario.corpus.steps.filter((s) => s.segment === 'preview')[2];
    (((boundary2.request as { settlementGroups: { tasksAchieved: Record<string, string[]> }[] }).settlementGroups)[0]).tasksAchieved.person_c = ['task_new_child'];
    await openT03Session(scenario);
    await expect(driveControllerSegment(scenario, 'T03-collapse')).rejects.toThrow(/request mismatch/);
  });

  test('rejects a preview that drops the staged scan/group candidate', async () => {
    const scenario = buildT03Scenario(traceName, sampleId);
    const sealPreview = scenario.corpus.steps.filter((s) => s.segment === 'preview').at(-1)!;
    (sealPreview.request as { settlementGroups: unknown[] }).settlementGroups = []; // the pre-fix driver bug
    await openT03Session(scenario);
    await expect(driveControllerSegment(scenario, traceName)).rejects.toThrow(/request mismatch/);
  });

  test('rejects a begin preview that leaks the later staged state into model input', async () => {
    const scenario = buildT03Scenario(traceName, sampleId);
    const [beginPreview, sealPreview] = scenario.corpus.steps.filter((s) => s.segment === 'preview');
    (beginPreview.response as { data: { workingState: Json } }).data.workingState = structuredClone((sealPreview.response as { data: { workingState: Json } }).data.workingState);
    await openT03Session(scenario);
    await expect(driveControllerSegment(scenario, traceName)).rejects.toThrow(/input mismatch/);
  });
});

describe('T03 harness directed negatives', () => {
  test('round entry allocates even when old slot values remain in memory', async () => {
    const scenario = buildT03Scenario('T03-collapse', 'sample_1');
    scenario.memory.ids['group:person_c'] = 'old_round_group';
    scenario.memory.ids.point = 'old_round_point';
    await openT03Session(scenario);
    await driveControllerSegment(scenario);
    // 组身份分配（round entry）＋候选 change/task 分配（stage 前）各一次。
    expect(scenario.transport.ops.filter((operation) => operation === 'allocate_ids')).toHaveLength(2);
    expect(scenario.driver.getMemory().ids['group:person_c']).toBe('group_task');
    expect(scenario.driver.getMemory().ids.point).toBe('p4');
  });

  test('a mismatched round allocation stops before pointPlan or action generation', async () => {
    const scenario = buildT03Scenario('T03-collapse', 'sample_1');
    const allocate = scenario.corpus.steps.find((step) => step.operation === 'allocate_ids')!;
    (allocate.response as { data: { allocations: { slotKey: string }[] } }).data.allocations.at(-1)!.slotKey = 'unexpected_slot';
    await openT03Session(scenario);
    await expect(driveControllerSegment(scenario)).rejects.toThrow(/Allocation response does not match requested slots/);
    expect(scenario.model.calls).toEqual([]);
  });

  test('rejects a tampered final digest at the inspect read', async () => {
    const scenario = buildT03Scenario('T03', 'sample_1');
    const finalStep = scenario.corpus.steps.find((s) => s.sharedStepId === scenario.finalStepId)!;
    finalStep.expectation!.expectedDigest = 'f'.repeat(64);
    await openT03Session(scenario);
    await driveControllerSegment(scenario, 'T03');
    await expect(scenario.transport.runInspect(scenario.finalStepId)).rejects.toThrow(/shared digest mismatch/);
  });

  test('rejects a tampered seal preview body via the final alignment', async () => {
    const scenario = buildT03Scenario('T03-collapse', 'sample_1');
    const sealPreview = scenario.corpus.steps.filter((s) => s.segment === 'preview').at(-1)!;
    (((sealPreview.response as { data: { workingState: { characters: Record<string, { sanity: number }> } } }).data.workingState).characters).person_c.sanity = 99;
    await openT03Session(scenario);
    await driveControllerSegment(scenario, 'T03-collapse');
    await expect(scenario.transport.runInspect(scenario.finalStepId)).rejects.toThrow(/preview alignment broken/);
  });
});
