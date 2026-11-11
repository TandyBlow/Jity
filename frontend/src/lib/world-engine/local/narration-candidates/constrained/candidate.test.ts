/** Constrained route tests: real kernel points -> scene skeleton -> beats ->
 * prose -> verification, with a program realizer and a scripted model engine.
 *
 * The point lineage is built with the same browser kernel the product uses
 * (`buildInitialState` + `applyPoint`), so these tests exercise saved-state
 * reads rather than hand-written packets.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { applyPoint, buildInitialState, stateDigest } from '../../state';
import type { InitialState, TimelinePoint } from '../../../types';
import { createRealizerContext, generateCandidate, planBeats, projectConstrainedScene, realizeBeat, sanitizeBeat, verifyText } from './index';
import type { BeatDirective, CommittedScenePacket } from './types';

const initial = (): InitialState => ({
  engineVersion: 'world-engine-v1',
  schemaVersion: 1,
  worldId: 'world_test',
  protagonistId: 'lu',
  initialTime: { calendar: 'gregorian', dateTime: '2026-03-01T10:00:00', instantOrdinal: 0 },
  locations: {
    room: {
      id: 'room', name: '值班室', parentLocationId: null,
      initialAppearance: '桌上摊着登记簿，窗子朝东，窗台上落了一层灰。',
      slots: [{ id: 'slot_desk', label: '桌边' }, { id: 'slot_window', label: '窗边' }],
    },
    yard: {
      id: 'yard', name: '后院', parentLocationId: null,
      initialAppearance: '院墙下堆着两只空木箱，门口的路灯还没亮。',
      slots: [{ id: 'slot_gate', label: '门口' }, { id: 'slot_wall', label: '墙根' }],
    },
    rest: {
      id: 'rest', name: '休息室', parentLocationId: null,
      initialAppearance: '长椅上搭着一条毯子。', slots: [],
    },
  },
  items: {
    mug: {
      id: 'mug', name: '白瓷杯', initialPosition: { containerId: 'room', slotId: 'slot_desk', relativeTo: null },
      initialAppearance: '杯口有一圈干掉的茶渍。', slots: [],
    },
    ledger: {
      id: 'ledger', name: '登记簿', initialPosition: { containerId: 'room', slotId: 'slot_desk', relativeTo: null },
      initialAppearance: '最后一页夹着一张复写纸。', slots: [],
    },
    crate: {
      id: 'crate', name: '木箱', initialPosition: { containerId: 'yard', slotId: 'slot_wall', relativeTo: null },
      initialAppearance: '箱盖裂了一道缝。', slots: [],
    },
  },
  characters: {
    lu: {
      id: 'lu', name: '路明非',
      initialPosition: { containerId: 'room', slotId: 'slot_desk', relativeTo: null },
      initialAppearance: '外套搭在椅背上，鞋边沾着灰。',
      initialPersonality: '先用一句玩笑替自己解围，再认真把手上的事做完。',
      initialSanity: 50,
      tasks: {
        t1: { id: 't1', ownerId: 'lu', parentTaskId: null, goal: '把登记簿翻到最后一页', status: 'pending' },
      },
      slots: [],
    },
    nono: {
      id: 'nono', name: '诺诺',
      initialPosition: { containerId: 'room', slotId: 'slot_window', relativeTo: null },
      initialAppearance: '袖口卷到手肘，手里转着一支笔。',
      initialPersonality: '看人比听解释更有耐心。',
      initialSanity: 62,
      tasks: {},
      slots: [],
    },
    shen: {
      id: 'shen', name: '沈澄',
      initialPosition: { containerId: 'rest', slotId: null, relativeTo: null },
      initialAppearance: '靠在长椅上。',
      initialPersonality: '不太说话。',
      initialSanity: 44,
      tasks: {},
      slots: [],
    },
  },
});

async function productWorldFixture() {
  const file = join(process.cwd(), 'public/worlds/dragon-raja-free-day.world.json');
  const world = JSON.parse(readFileSync(file, 'utf8'));
  const state0 = buildInitialState(world.initial as InitialState);
  // b7cd group_10: lu walks from lane/slot_wall to lane with no slot; one minute
  // passes; no task is achieved by this point.
  const point: TimelinePoint = {
    worldId: world.initial.worldId, id: 'b7cd_p1', sequence: 1, kind: 'normal', previousPointId: 'root',
    roundId: 'r1', advanceId: 'a1', trigger: 'player', linkedFromPointId: null,
    timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
    entityDeltas: {
      lu: { entityId: 'lu', positionSet: { containerId: 'lane', slotId: null, relativeTo: null } },
    },
  };
  const state1 = applyPoint(state0, point);
  const digest = await stateDigest(state1);
  const packet: CommittedScenePacket = {
    anchor: { worldId: world.initial.worldId, pointId: point.id, version: 1, stateDigest: digest, previousPointId: 'root' },
    state: state1,
    beforeState: state0,
    timeAdvance: point.timeAdvance,
    entityDeltas: point.entityDeltas,
    facts: [],
  };
  return { packet };
}

async function e9a5NoMoveFixture() {
  const file = join(process.cwd(), 'public/worlds/dragon-raja-free-day.world.json');
  const world = JSON.parse(readFileSync(file, 'utf8'));
  const state0 = buildInitialState(world.initial as InitialState);
  // 95dc group_10/group_12: lu stays in lane, no entity is moved; only a
  // minute passes. The bad page program treated the goggles as the mover.
  const point: TimelinePoint = {
    worldId: world.initial.worldId, id: 'e9a5_no_move', sequence: 1, kind: 'normal', previousPointId: 'root',
    roundId: 'r1', advanceId: 'a1', trigger: 'player', linkedFromPointId: null,
    timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
    entityDeltas: {},
  };
  const state1 = applyPoint(state0, point);
  const digest = await stateDigest(state1);
  const packet: CommittedScenePacket = {
    anchor: { worldId: world.initial.worldId, pointId: point.id, version: 1, stateDigest: digest, previousPointId: 'root' },
    state: state1,
    beforeState: state0,
    timeAdvance: point.timeAdvance,
    entityDeltas: point.entityDeltas,
    facts: [],
  };
  return { packet };
}

async function fixture() {
  const state0 = buildInitialState(initial());
  const point1: TimelinePoint = {
    worldId: 'world_test', id: 'p1', sequence: 1, kind: 'normal', previousPointId: 'root',
    roundId: 'r1', advanceId: 'a1', trigger: 'player', linkedFromPointId: null,
    timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } },
    entityDeltas: {
      lu: {
        entityId: 'lu',
        positionSet: { containerId: 'yard', slotId: 'slot_gate', relativeTo: null },
        appearanceChanges: [{ id: 'a1', text: '袖口沾了雨水，右手一直按着口袋。', supersedes: [] }],
        personalityChanges: [{ id: 'p1', text: '说话前先看一眼对方的鞋，再决定要不要开玩笑。', supersedes: [] }],
        sanitySet: 46,
        tasksAchieved: ['t1'],
        subtasksAdded: [{
          id: 't2', ownerId: 'lu', parentTaskId: 't1',
          goal: '把登记簿最后一页的数字抄给门口的人', status: 'pending',
        }],
      },
      nono: {
        entityId: 'nono',
        positionSet: { containerId: 'yard', slotId: 'slot_wall', relativeTo: null },
        sanitySet: 58,
      },
      mug: { entityId: 'mug', positionSet: { containerId: 'yard', slotId: 'slot_wall', relativeTo: null } },
      // Hidden: the viewpoint cannot see the rest room this point.
      shen: { entityId: 'shen', sanitySet: 30 },
    },
  };
  const state1 = applyPoint(state0, point1);
  const digest = await stateDigest(state1);
  const packet: CommittedScenePacket = {
    anchor: {
      worldId: 'world_test', pointId: 'p1', version: 1, stateDigest: digest, previousPointId: 'root',
    },
    state: state1,
    beforeState: state0,
    timeAdvance: point1.timeAdvance,
    entityDeltas: point1.entityDeltas,
    facts: [],
  };
  return { packet, state0, state1, digest };
}

type ScriptedEngine = Parameters<typeof generateCandidate>[0]['engine'];

function scriptedEngine(reply: (prompt: string) => string, progress = true): { engine: ScriptedEngine; prompts: string[] } {
  const prompts: string[] = [];
  const engine: ScriptedEngine = {
    info: { backend: 'scripted', modelId: 'scripted-1' },
    async load() {},
    async dispose() {},
    async complete(prompt, options) {
      prompts.push(prompt);
      // One scripted reply per call: evaluating the script three times made
      // attempt-sensitive scripts advance on every progress event.
      const text = reply(prompt);
      if (progress) {
        options?.onProgress?.({ raw: text.slice(0, 6), elapsedMs: 1 });
        options?.onProgress?.({ raw: text, elapsedMs: 2 });
      }
      return text;
    },
  };
  return { engine, prompts };
}

function factLine(prompt: string, needle: string): string | null {
  return prompt.split('\n').find((line) => line.includes(needle)) ?? null;
}

function modelReplyForPrompt(prompt: string): string {
  const lines: string[] = [];
  if (factLine(prompt, '时间过去 2分钟')) lines.push('两分钟过去了。');
  if (factLine(prompt, '路明非从值班室到后院')) lines.push('路明非离开值班室，走进后院。');
  if (factLine(prompt, '诺诺从值班室到后院')) lines.push('诺诺从值班室走进后院。');
  if (factLine(prompt, '白瓷杯从值班室到后院')) lines.push('白瓷杯从值班室被移到后院。');
  if (factLine(prompt, '把登记簿翻到最后一页')) lines.push('路明非完成了「把登记簿翻到最后一页」。');
  if (factLine(prompt, '路明非接下来还有一件事')) lines.push('接下来，路明非还要把登记簿最后一页的数字抄给门口的人。');
  if (factLine(prompt, '路明非现在说话前先看一眼对方的鞋')) lines.push('路明非现在说话前先看一眼对方的鞋，再决定要不要开玩笑。');
  if (factLine(prompt, '路明非的精神状态下降')) lines.push('路明非的喉咙紧了一下。');
  if (factLine(prompt, '诺诺的精神状态下降')) lines.push('诺诺的肩膀往下收了收。');
  if (factLine(prompt, '路明非现在袖口沾了雨水')) lines.push('路明非现在袖口沾了雨水，右手一直按着口袋。');
  if (factLine(prompt, '白瓷杯现在在后院')) lines.push('白瓷杯就在后院。');
  if (factLine(prompt, '木箱现在在后院')) lines.push('木箱就在后院。箱盖裂了一道缝。');
  if (factLine(prompt, '本段只做场景过渡')) lines.push('路明非没有马上再动。');
  return lines.join('\n\n');
}

describe('projectConstrainedScene', () => {
  it('derives facts from the saved point pair and keeps out-of-view changes hidden', async () => {
    const { packet } = await fixture();
    const { scene } = projectConstrainedScene(
      {
        pointId: packet.anchor.pointId, version: 1, state: packet.state!,
        stateDigest: packet.anchor.stateDigest, previousPointId: 'root',
        timeAdvance: packet.timeAdvance!, entityDeltas: packet.entityDeltas!,
      },
      {
        pointId: 'root', version: 0, state: packet.beforeState!, stateDigest: 'root',
        previousPointId: null, timeAdvance: null, entityDeltas: {},
      },
      { knowledge: { discoveredItemIds: ['mug'] } },
    );
    const kinds = scene.facts.map((fact) => fact.kind);
    expect(kinds).toContain('time');
    expect(kinds).toContain('task_achieved');
    expect(kinds).toContain('subtask_added');
    expect(kinds).toContain('personality_changed');
    expect(kinds).toContain('sanity_changed');
    expect(kinds).toContain('appearance_changed');
    const hidden = scene.facts.filter((fact) => fact.visibility === 'hidden');
    expect(hidden.map((fact) => fact.kind)).toContain('sanity_changed');
    expect(hidden.every((fact) => 'name' in fact && fact.name === '沈澄')).toBe(true);
    expect(scene.present.map((person) => person.name)).toContain('诺诺');
    expect(scene.place.name).toBe('后院');
  });

  it('refuses a mismatched lineage instead of guessing', async () => {
    const { packet } = await fixture();
    expect(() => projectConstrainedScene(
      {
        pointId: 'p1', version: 1, state: packet.state!,
        stateDigest: packet.anchor.stateDigest, previousPointId: 'other',
        timeAdvance: packet.timeAdvance!, entityDeltas: packet.entityDeltas!,
      },
      {
        pointId: 'root', version: 0, state: packet.beforeState!, stateDigest: 'root',
        previousPointId: null, timeAdvance: null, entityDeltas: {},
      },
    )).toThrow(/lineage_mismatch/);
  });

  it('refuses a delta that disagrees with the saved state', async () => {
    const { packet } = await fixture();
    const broken = structuredClone(packet.entityDeltas!);
    broken.lu.sanitySet = 99;
    expect(() => projectConstrainedScene(
      {
        pointId: 'p1', version: 1, state: packet.state!,
        stateDigest: packet.anchor.stateDigest, previousPointId: 'root',
        timeAdvance: packet.timeAdvance!, entityDeltas: broken,
      },
      {
        pointId: 'root', version: 0, state: packet.beforeState!, stateDigest: 'root',
        previousPointId: null, timeAdvance: null, entityDeltas: {},
      },
    )).toThrow(/delta_sanity_disagrees/);
  });
});

describe('planBeats', () => {
  it('orders the viewpoint move before other actors and keeps hidden facts out', async () => {
    const { packet } = await fixture();
    const { scene } = projectConstrainedScene(
      {
        pointId: 'p1', version: 1, state: packet.state!,
        stateDigest: packet.anchor.stateDigest, previousPointId: 'root',
        timeAdvance: packet.timeAdvance!, entityDeltas: packet.entityDeltas!,
      },
      {
        pointId: 'root', version: 0, state: packet.beforeState!, stateDigest: 'root',
        previousPointId: null, timeAdvance: null, entityDeltas: {},
      },
    );
    const plan = planBeats(scene, {});
    const moveBeat = plan.beats.find((beat) => beat.kind === 'move');
    expect(moveBeat?.factIds[0]).toContain('move:lu');
    expect(plan.hiddenFactIds.length).toBeGreaterThan(0);
    const planned = plan.beats.flatMap((beat) => beat.factIds);
    expect(planned).not.toContain(plan.hiddenFactIds[0]);
  });
});

describe('generateCandidate program mode', () => {
  it('writes an accepted scene with every mandatory visible fact', async () => {
    const { packet } = await fixture();
    const result = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '我拿着杯子去后院。',
      policy: { mode: 'program', knowledge: { discoveredItemIds: ['mug', 'crate'] } },
    });
    expect(result.accepted).toBe(true);
    expect(result.status).toBe('accepted');
    expect(result.text).toContain('两分钟');
    expect(result.text).toContain('后院');
    expect(result.text).toContain('把登记簿翻到最后一页');
    expect(result.text).toContain('说话前先看一眼对方的鞋');
    expect(result.text).toContain('袖口沾了雨水');
    expect(result.text).toMatch(/呼吸沉|喉咙紧|肩膀往下/);
    expect(result.text).not.toContain('沈澄');
    expect(result.composers.every((name) => name === 'program')).toBe(true);
    expect(result.verification.coverage.every((entry) => !entry.mandatory || entry.expressed)).toBe(true);
    expect(result.verification.hiddenFactIds.length).toBeGreaterThan(0);
  });

  it('expresses sanity as a number on request (legacy gate compatibility)', async () => {
    const { packet } = await fixture();
    const result = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '',
      policy: { mode: 'program', sanityStyle: 'number' },
    });
    expect(result.accepted).toBe(true);
    expect(result.text).toMatch(/精神值从五十落到四十六|数值从五十落到四十六/);
  });

  it('expresses the b7cd real-world move and minute without inventing a task', async () => {
    const { packet } = await productWorldFixture();
    const result = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '我沿着服务巷往里走，先看清墙上的演习规则牌。',
      policy: { mode: 'program' },
    });
    expect(result.accepted).toBe(true);
    expect(result.text).toContain('西侧服务巷');
    expect(result.text).toMatch(/一分钟/);
    expect(result.text).not.toContain('任务完成');
    expect(result.text).not.toContain('行动成功完成');
    expect(result.segments.every((segment) => segment.source === 'program')).toBe(true);
  });

  it('writes a readable no-move 95dc point without making the goggles an actor', async () => {
    const { packet } = await e9a5NoMoveFixture();
    const result = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '我沿着服务巷往里走，先看清墙上的演习规则牌。',
      policy: { mode: 'program' },
    });
    expect(result.accepted).toBe(true);
    expect(result.text).toContain('西侧服务巷');
    expect(result.text).toMatch(/一分钟/);
    expect(result.text).not.toContain('护目镜还在');
    expect(result.text).not.toContain('护目镜在原地');
    expect(result.text).not.toContain('资格为false');
    expect(result.text).not.toContain('任务完成');
    expect(result.segments.every((segment) => segment.source === 'program')).toBe(true);
  });

  it('does not repeat the e9a5 player ending in the next constrained point', async () => {
    const { packet } = await productWorldFixture();
    const priorText = '路明非站在西侧服务巷口，看着黄黑绳缓缓放下。风掠过巷口，带起一阵潮湿的泥土味，他忽然想起什么，却只在心里嘀咕了一句。他望着诺诺站在不远处，红发用发圈束在脑后，目光平静。他注意到她手中的演习短枪，枪上有黄色演习标记。一分钟过去，他依旧站在原地，呼吸平稳，目光落在路明非的护目镜和演习背心上，没有动弹。';
    const result = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: { ...packet, priorText },
      inputText: '',
      policy: { mode: 'program' },
    });
    expect(result.accepted).toBe(true);
    const closing = result.text.split(String.fromCharCode(10, 10)).filter(Boolean).slice(-1)[0] ?? '';
    expect(closing).not.toContain('没有动弹');
    expect(result.text).not.toContain('目光落在路明非的护目镜和演习背心上，没有动弹。');
  });

  it('works from a facts-only packet with no full state', async () => {
    const { packet } = await fixture();
    const full = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '',
      policy: { mode: 'program' },
    });
    expect(full.basePacket).not.toBeNull();
    const factsOnly = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: { ...full.basePacket!, inputText: '', priorText: null },
      policy: { mode: 'program' },
    });
    expect(factsOnly.accepted).toBe(true);
    expect(factsOnly.text).toContain('后院');
    expect(factsOnly.skeleton?.hasSceneMaterial).toBe(false);
  });
});

describe('beat provenance and cross-turn phrasing', () => {
  it('labels every paragraph with the writer that produced it', async () => {
    const { packet } = await fixture();
    const result = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '我拿着杯子去后院。',
      policy: { mode: 'program', knowledge: { discoveredItemIds: ['mug', 'crate'] } },
    });
    expect(result.accepted).toBe(true);
    expect(result.segments.length).toBeGreaterThan(0);
    expect(result.segments.every((segment) => segment.text.trim().length > 0)).toBe(true);
    expect(result.segments.every((segment) => ['program', 'model', 'external', 'fallback'].includes(segment.source))).toBe(true);
    expect(result.beatCounts.program).toBe(result.segments.length);
    expect(result.mixed).toBe(false);
  });

  it('writes task and personality facts as narration, not change reports', async () => {
    const { packet } = await fixture();
    const result = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '我拿着杯子去后院。',
      policy: { mode: 'program', knowledge: { discoveredItemIds: ['mug', 'crate'] } },
    });
    expect(result.accepted).toBe(true);
    expect(result.text).toContain('把登记簿翻到最后一页');
    expect(result.text).toMatch(/(办完|做完|完成|了结)/u);
    expect(result.text).toContain('说话前先看一眼对方的鞋');
    // The meta frames read like a state change log, not a scene.
    expect(result.text).not.toContain('性子变了一点');
    expect(result.text).not.toContain('身上多了一点变化');
    expect(result.text).not.toContain('给自己记下一条');
  });

  it('does not close a turn with the same line the player just read', async () => {
    const { packet } = await fixture();
    const first = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '我拿着杯子去后院。',
      policy: { mode: 'program', knowledge: { discoveredItemIds: ['mug', 'crate'] } },
    });
    const closing = first.text.split(String.fromCharCode(10, 10)).filter(Boolean).slice(-1)[0];
    const priorText = `${closing}。`;
    const second = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: { ...packet, inputText: '', priorText },
      inputText: '',
      priorText,
      policy: { mode: 'program', knowledge: { discoveredItemIds: ['mug', 'crate'] } },
    });
    expect(second.accepted).toBe(true);
    expect(second.text.split(String.fromCharCode(10, 10)).filter(Boolean).slice(-1)[0]).not.toBe(closing);
  });

  it('does not reopen a turn with the same sentence the player just read', async () => {
    const { packet } = await fixture();
    const first = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '我拿着杯子去后院。',
      policy: { mode: 'program', knowledge: { discoveredItemIds: ['mug', 'crate'] } },
    });
    const opening = first.text.split(String.fromCharCode(10, 10))[0];
    // Only the previous opening is given as history: repeating it is exactly
    // the failure this rule targets, while the rest of the point stays the same.
    const priorText = `${opening}。`;
    const second = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: { ...packet, inputText: '', priorText },
      inputText: '',
      priorText,
      policy: { mode: 'program', knowledge: { discoveredItemIds: ['mug', 'crate'] } },
    });
    expect(second.accepted).toBe(true);
    expect(second.text.split(String.fromCharCode(10, 10))[0]).not.toBe(opening);
  });
});

describe('generateCandidate model mode', () => {
  it('writes the time and declared action in one scene instead of three empty beats', async () => {
    const { packet } = await productWorldFixture();
    const action = '我沿着服务巷往里走，先看清墙上的演习规则牌。';
    const text = '一分钟过去，路明非沿着服务巷往里走，在墙上的演习规则牌前停下，仔细读过上面的字。诺诺还在巷口，路明非没有继续往交火区走。';
    const { engine, prompts } = scriptedEngine(() => text);
    const result = await generateCandidate({
      engine, committed: packet, inputText: '',
      policy: { mode: 'model', scene: { previousAction: action } },
    });
    expect(result.accepted).toBe(true);
    expect(result.plan?.beats).toHaveLength(1);
    expect(prompts).toHaveLength(1);
    expect(prompts[0]).toContain(action.replace(/^我/u, '路明非'));
    expect(result.text).toBe(text);
    expect(result.rawAttempts[0].source).toBe('model');
    expect(result.plan?.beats[0].maxChars).toBe(150);
  });

  it('keeps rejected model drafts when a missing-time beat uses the program fallback', async () => {
    const { packet } = await productWorldFixture();
    const rejectedText = '路明非低头检查胸前的护目镜，目光仍停在镜片上。';
    const { engine } = scriptedEngine(() => rejectedText);
    const result = await generateCandidate({
      engine, committed: packet, inputText: '', policy: { mode: 'model' },
    });
    const open = result.rawAttempts.find((beat) => beat.beatId === 'open');
    expect(open?.source).toBe('program');
    expect(open?.rejected).toHaveLength(2);
    expect(open?.rejected?.every((draft) => draft.text === rejectedText)).toBe(true);
    expect(open?.rejected?.every((draft) => draft.issues.some((issue) => issue.kind === 'fact_missing'))).toBe(true);
    expect(result.verification.coverage.find((fact) => fact.kind === 'time')?.expressed).toBe(true);
  });

  it('accepts per-beat model prose and reports real streaming progress', async () => {
    const { packet } = await fixture();
    const { engine, prompts } = scriptedEngine(modelReplyForPrompt);
    const progress: string[] = [];
    const result = await generateCandidate({
      engine,
      committed: packet,
      inputText: '我拿着杯子去后院。',
      policy: { mode: 'model', knowledge: { discoveredItemIds: ['mug'] } },
      onProgress: (entry) => { if (entry.text) progress.push(entry.text); },
    });
    expect(result.accepted).toBe(true);
    expect(result.composers.every((name) => name === 'model')).toBe(true);
    expect(result.rawAttempts.every((beat) => beat.source === 'model')).toBe(true);
    expect(prompts.length).toBe(result.rawAttempts.length);
    expect(prompts[0]).toContain('本段必须写出的事实');
    expect(prompts.some((prompt) => prompt.includes('不要新增人物、地点、物品'))).toBe(true);
    expect(progress.length).toBeGreaterThan(0);
    expect(result.text).toContain('路明非离开值班室，走进后院');
  });

  it('rejects an action the model invented and tells it not to add one', async () => {
    const { packet } = await fixture();
    let moveCalls = 0;
    const { engine, prompts } = scriptedEngine((prompt) => {
      if (!factLine(prompt, '路明非从值班室到后院')) return modelReplyForPrompt(prompt);
      moveCalls += 1;
      // First draft invents an action that no settled fact contains.
      return moveCalls === 1
        ? '路明非离开值班室，走进后院。诺诺推开门，先一步跳下台阶。'
        : modelReplyForPrompt(prompt);
    });
    const result = await generateCandidate({
      engine, committed: packet, inputText: '', policy: { mode: 'model' },
    });
    expect(result.accepted).toBe(true);
    const moveBeat = result.rawAttempts.find((beat) => beat.beatId.startsWith('move:lu'));
    expect(moveBeat?.rejected?.some((draft) => draft.issues.some((issue) => issue.kind === 'unlicensed_event'))).toBe(true);
    expect(prompts.some((prompt) => prompt.includes('不要补写没有结算的新动作'))).toBe(true);
    expect(moveBeat?.source).toBe('model');
    expect(result.text).not.toContain('跳下台阶');
  });

  it('names the missing time when a model draft skips it, then accepts the rewrite', async () => {
    const { packet } = await fixture();
    let openCalls = 0;
    const { engine, prompts } = scriptedEngine((prompt) => {
      if (!factLine(prompt, '时间过去 2分钟')) return modelReplyForPrompt(prompt);
      openCalls += 1;
      return openCalls === 1 ? '值班室的门半开着。' : modelReplyForPrompt(prompt);
    });
    const result = await generateCandidate({
      engine, committed: packet, inputText: '', policy: { mode: 'model' },
    });
    expect(result.accepted).toBe(true);
    expect(prompts.some((prompt) => prompt.includes('必须写出已经过去的时间'))).toBe(true);
    expect(result.text).toContain('两分钟');
  });

  it('asks for a different opening frame when the draft repeats the last one', async () => {
    const { packet } = await fixture();
    const repeated = '两分钟过去了。值班室的窗帘没有动。';
    const { engine, prompts } = scriptedEngine((prompt) => {
      if (!factLine(prompt, '时间过去 2分钟')) return modelReplyForPrompt(prompt);
      // Both drafts reuse the previous turn's opening; the second is accepted
      // because a repeated opening is a soft style issue, not a fact error.
      return repeated;
    });
    const result = await generateCandidate({
      engine, committed: packet, inputText: '',
      priorText: '两分钟过去了。走廊里没有人。',
      policy: { mode: 'model' },
    });
    expect(result.accepted).toBe(true);
    expect(prompts.some((prompt) => prompt.includes('换一个开头'))).toBe(true);
  });

  it('rejects reversed direction, retries with feedback, then falls back to the program', async () => {
    const { packet } = await fixture();
    const { engine, prompts } = scriptedEngine((prompt) => (
      factLine(prompt, '路明非从值班室到后院') ? '路明非从后院走进值班室。' : modelReplyForPrompt(prompt)
    ));
    const result = await generateCandidate({
      engine,
      committed: packet,
      inputText: '',
      policy: { mode: 'model' },
    });
    expect(result.accepted).toBe(true);
    const moveBeat = result.rawAttempts.find((beat) => beat.beatId.startsWith('move:lu'));
    expect(moveBeat?.source).toBe('program');
    expect(moveBeat?.issues.some((issue) => issue.kind === 'fact_direction_reversed')).toBe(true);
    expect(moveBeat?.issues.some((issue) => issue.kind === 'beat_fallback')).toBe(true);
    expect(result.composers.some((name) => name.includes('model-failed'))).toBe(true);
    // Two attempts (initial + one feedback retry) on the move beat only.
    expect(prompts.filter((prompt) => prompt.includes('路明非从值班室到后院')).length).toBe(2);
    expect(prompts.some((prompt) => prompt.includes('上一稿没有写清'))).toBe(true);
  });
});

describe('small-model output handling', () => {
  it('unwraps a JSON answer and still checks the facts', () => {
    const nl = String.fromCharCode(10, 10);
    expect(sanitizeBeat('{"text":"两分钟过去了。"}')).toBe('两分钟过去了。');
    const fenced = `\`\`\`json${String.fromCharCode(10)}{"narration":"路明非走进后院。"}${String.fromCharCode(10)}\`\`\``;
    expect(sanitizeBeat(fenced)).toContain('路明非走进后院');
    expect(sanitizeBeat(JSON.stringify(['第一段。', '第二段。']))).toBe(`第一段。${nl}第二段。`);
  });

  it('rejects a heading/annotation answer for the beat and writes that beat with the program', async () => {
    const { packet } = await fixture();
    const { engine, prompts } = scriptedEngine((prompt) => (
      factLine(prompt, '路明非从值班室到后院')
        ? ['【正文】', '事实：路明非移动到后院', '正文：他走了。'].join(String.fromCharCode(10))
        : modelReplyForPrompt(prompt)
    ));
    const result = await generateCandidate({ engine, committed: packet, inputText: '', policy: { mode: 'model' } });
    expect(result.accepted).toBe(true);
    const moveBeat = result.rawAttempts.find((beat) => beat.beatId.startsWith('move:lu'));
    expect(moveBeat?.source).toBe('program');
    expect(moveBeat?.issues.some((issue) => ['prompt_echo', 'fact_list', 'fact_missing'].includes(issue.kind))).toBe(true);
    expect(prompts.filter((prompt) => prompt.includes('路明非从值班室到后院')).length).toBe(2);
    expect(result.text).not.toContain('事实：');
  });

  it.each([
    ['empty reply', () => ''],
    ['fact-list reply', () => ['- 时间：2分钟', '- 路明非移动到后院', '- 人格变化'].join(String.fromCharCode(10))],
    ['english reply', () => 'Lu Mingfei walked into the yard after two minutes.'],
    ['prompt echo', (prompt: string) => prompt],
  ])('never lets a %s become the player text', async (_label, reply: (prompt: string) => string) => {
    const { packet } = await fixture();
    const { engine } = scriptedEngine(reply, false);
    const result = await generateCandidate({ engine, committed: packet, inputText: '', policy: { mode: 'model' } });
    expect(result.accepted).toBe(true);
    expect(result.text).toContain('后院');
    expect(result.text).not.toContain('- 时间');
    expect(result.text).not.toContain('after two minutes');
    expect(result.rawAttempts.some((beat) => beat.source === 'program' || beat.source === 'fallback')).toBe(true);
  });

  it('spends the turn budget on the program instead of overrunning the wait', async () => {
    const { packet } = await fixture();
    let calls = 0;
    const engine: ScriptedEngine = {
      info: { backend: 'slow', modelId: 'slow-1' },
      async load() {},
      async dispose() {},
      async complete(prompt) {
        calls += 1;
        await new Promise((done) => setTimeout(done, 40));
        return modelReplyForPrompt(prompt);
      },
    };
    const started = performance.now();
    const result = await generateCandidate({
      engine, committed: packet, inputText: '',
      policy: { mode: 'model', turnTimeoutMs: 60, model: { timeoutMs: 5000 } },
    });
    const wall = performance.now() - started;
    expect(result.accepted).toBe(true);
    expect(calls).toBeLessThan(6);
    expect(result.rawAttempts.some((beat) => beat.issues.some((issue) => issue.detail.includes('turn budget')))).toBe(true);
    expect(wall).toBeLessThan(4000);
  });
});

describe('injected composer (lane 07 contract)', () => {
  it('uses the injected composer and falls back when its text breaks licensing', async () => {
    const { packet } = await fixture();
    const composer = async () => ({ text: '沈澄走进后院。', source: 'external' as const });
    const result = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '',
      policy: { mode: 'program', composer },
    });
    expect(result.accepted).toBe(true);
    expect(result.composers.some((name) => name.startsWith('external'))).toBe(false);
    expect(result.rawAttempts.some((beat) => beat.issues.some((issue) => issue.kind === 'unlicensed_entity'))).toBe(true);
    expect(result.text).not.toContain('沈澄');
  });

  it('accepts composer text that passes the beat gate', async () => {
    const { packet } = await fixture();
    const composer = async ({ beat, scene }: { beat: BeatDirective; scene: Parameters<typeof createRealizerContext>[0] }) => ({
      text: realizeBeat(beat, createRealizerContext(scene, null, 'direction')),
      source: 'external' as const,
    });
    const result = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '',
      policy: { mode: 'program', composer },
    });
    expect(result.accepted).toBe(true);
    expect(result.composers.every((name) => name.startsWith('external'))).toBe(true);
    expect(result.rawAttempts.every((beat) => beat.source === 'external')).toBe(true);
  });
});

describe('facts-only packets (09 driver shape)', () => {
  it('accepts a presence sentence next to the viewpoint at-fact', async () => {
    const packet = {
      anchor: { worldId: 'world_test', pointId: 'p_facts', version: 1, stateDigest: 'digest', previousPointId: 'root' },
      facts: [
        { id: 'f:at:lu', actorId: 'lu', name: '路明非', kind: 'at' as const, locationId: 'room', location: '值班室' },
        { id: 'f:at:nono', actorId: 'nono', name: '诺诺', kind: 'at' as const, locationId: 'room', location: '值班室' },
        { id: 'f:task', actorId: 'lu', name: '路明非', kind: 'task_achieved' as const, taskId: 't1', goal: '把登记簿翻到最后一页' },
      ],
    };
    const result = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '',
      priorText: null,
      policy: { mode: 'program' },
    });
    expect(result.accepted).toBe(true);
    expect(result.text).toContain('诺诺');
    expect(result.text).toContain('把登记簿翻到最后一页');
  });
});

describe('scene hints on a facts-only packet (06 adapter shape)', () => {
  it('uses the settled place note and object notes', async () => {
    const packet = {
      anchor: { worldId: 'world_test', pointId: 'p_hints', version: 2, stateDigest: 'digest', previousPointId: 'p1' },
      facts: [
        { id: 'h:at:lu', actorId: 'lu', name: '路明非', kind: 'at' as const, locationId: 'shed', location: '器材棚' },
        { id: 'h:at:fingel', actorId: 'fingel', name: '芬格尔', kind: 'at' as const, locationId: 'shed', location: '器材棚' },
      ],
    };
    const result = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '',
      priorText: null,
      policy: {
        mode: 'program',
        scene: {
          placeNote: '器材棚：推拉门可回服务巷，领用台在门内右侧。',
          presentNotes: { 芬格尔: '头发乱着，手指在机身上敲了两下。' },
          objectNotes: { 折叠担架: '帆布与锁脚完好，展开后需两名搬运者。' },
        },
      },
    });
    if (!result.accepted) console.log(JSON.stringify({ text: result.text, issues: result.issues, plan: result.plan?.beats.map((b) => b.id), objects: result.skeleton?.objects, notes: result.skeleton?.place, beats: result.rawAttempts.map((b) => ({ id: b.beatId, text: b.text })) }, null, 2));
    expect(result.accepted).toBe(true);
    expect(result.text).toContain('推拉门可回服务巷');
    expect(result.text).toContain('头发乱着');
    expect(result.text).toContain('帆布与锁脚完好');
    expect(result.text).not.toMatch(/器材棚：/u);
  });
});

describe('06 adapter call shape, end to end', () => {
  it('takes facts + hints + results and keeps every settled change', async () => {
    const packet = {
      anchor: { worldId: 'world_test', pointId: 'p06', version: 2, stateDigest: 'digest', previousPointId: 'p05' },
      facts: [
        { id: 'a:move', actorId: 'lu', name: '路明非', kind: 'moved' as const, fromId: 'corridor', from: '走廊', toId: 'shed', to: '器材棚' },
        { id: 'a:task', actorId: 'lu', name: '路明非', kind: 'task_achieved' as const, taskId: 't1', goal: '把护目镜领到手' },
        { id: 'a:sanity', actorId: 'lu', name: '路明非', kind: 'sanity_changed' as const, from: 70, to: 74 },
        { id: 'a:at:fingel', actorId: 'fingel', name: '芬格尔', kind: 'at' as const, locationId: 'shed', location: '器材棚' },
      ],
    };
    const result = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: { ...packet, timeAdvance: { boundary: 'elapsed' as const, duration: { amount: 1, unit: 'minute' as const } } },
      inputText: '我领了护目镜',
      priorText: null,
      policy: {
        mode: 'program', viewpointId: 'lu', minChars: 40, maxChars: 500,
        resultsText: '秦越说担架在器材笼门口。',
        scene: { placeNote: '器材棚：领用台在门内右侧。', presentNotes: { 芬格尔: '手指在机身上敲了两下。' } },
      },
    });
    expect(result.accepted).toBe(true);
    expect(result.composers.every((composer) => composer === 'program')).toBe(true);
    for (const text of ['器材棚', '把护目镜领到手', '秦越说担架在器材笼门口', '芬格尔']) {
      expect(result.text).toContain(text);
    }
    expect(result.text).toMatch(/好了一些|稳了|松|舒展|缓/u);
  });
});

describe('settled descriptions', () => {
  it('keeps a semicolon rule list whole instead of cutting it at the first rule', async () => {
    const { packet } = await fixture();
    const broken = structuredClone(packet);
    const rules = '墙上贴着值班规定：来人先登记；离场要关灯；钥匙放回抽屉；夜间不得留宿。';
    broken.state!.initial.locations.yard.initialAppearance = rules;
    broken.beforeState!.initial.locations.yard.initialAppearance = rules;
    const result = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: broken,
      inputText: '',
      priorText: null,
      policy: { mode: 'program', viewpointId: 'lu' },
    });
    expect(result.accepted).toBe(true);
    expect(result.text).toContain('离场要关灯');
  });
});

describe('settled result line', () => {
  it('narrates the settlement result wording without inventing events', async () => {
    const { packet } = await fixture();
    const resultsText = '路明非问诺诺后院还有没有别人；诺诺说只剩木箱那边没人看。';
    const result = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '',
      policy: { mode: 'program', resultsText, knowledge: { discoveredItemIds: ['crate'] } },
    });
    expect(result.accepted).toBe(true);
    expect(result.text).toContain(resultsText);
    expect(result.composers).toContain('program');
  });
});

describe('verifyText', () => {
  it('flags an unregistered name and a rediscovery claim', async () => {
    const { packet } = await fixture();
    const full = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '',
      policy: { mode: 'program', knowledge: { discoveredItemIds: ['mug', 'crate'] } },
    });
    const result = verifyText(`${full.text}\n沈澄第一次看见木箱。`, {
      scene: full.skeleton!,
      base: full.basePacket!,
      priorText: null,
      minChars: 0,
    });
    expect(result.ok).toBe(false);
    expect(result.issues.some((issue) => issue.kind === 'unlicensed_entity')).toBe(true);
    expect(result.issues.some((issue) => issue.kind === 'rediscovery_claim')).toBe(true);
  });

  it('rejects a text that never states the elapsed time', async () => {
    const { packet } = await fixture();
    const full = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: packet,
      inputText: '',
      policy: { mode: 'program' },
    });
    const result = verifyText('路明非走进后院，把杯子放在墙根。', {
      scene: full.skeleton!,
      base: full.basePacket!,
      requireTime: true,
      minChars: 0,
    });
    expect(result.issues.some((issue) => issue.kind === 'fact_missing' && issue.detail.includes('time'))).toBe(true);
  });
});

describe('error reporting', () => {
  it('returns an honest error result when projection fails', async () => {
    const { packet } = await fixture();
    const result = await generateCandidate({
      engine: scriptedEngine(() => '').engine,
      committed: { ...packet, beforeState: undefined },
      inputText: '',
      policy: { mode: 'program' },
    });
    expect(result.accepted).toBe(false);
    expect(result.status).toBe('error');
    expect(result.issues[0].detail).toContain('before_missing');
  });
});
