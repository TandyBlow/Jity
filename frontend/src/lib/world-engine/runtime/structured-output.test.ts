import { describe, expect, test } from 'vitest';
import { StructuredOutputError, decodeTaskOutput } from './structured-output';

const rejects = (
  task: Parameters<typeof decodeTaskOutput>[0],
  raw: string,
  reason: RegExp = /structured output rejected/,
  constraints?: Parameters<typeof decodeTaskOutput>[2],
) => expect(() => decodeTaskOutput(task, raw, constraints)).toThrow(reason);

const asError = (task: Parameters<typeof decodeTaskOutput>[0], raw: string) => {
  try {
    decodeTaskOutput(task, raw);
  } catch (error) {
    return error as StructuredOutputError;
  }
  throw new Error('expected a rejection');
};

describe('decodeTaskOutput — text tasks', () => {
  test('narration and reaction pass raw prose through, never JSON-parsed', () => {
    const prose = '走廊尽头的门半开着，person_a 听见里面传来翻动声。';
    expect(decodeTaskOutput('narration', prose)).toBe(prose);
    expect(decodeTaskOutput('reaction', `  ${prose}\n`)).toBe(prose);
    const fence = '```json\n{"kind":"act"}\n```'; // a fenced JSON body is still just prose here
    expect(decodeTaskOutput('narration', fence)).toBe(fence);
  });

  test('empty text output is rejected with the raw payload', () => {
    const error = asError('narration', '   \n');
    expect(error.task).toBe('narration');
    expect(error.raw).toBe('   \n');
    rejects('reaction', '');
  });
});

describe('decodeTaskOutput — JSON tasks', () => {
  test('action accepts act and skip exactly', () => {
    expect(decodeTaskOutput('action', '{"kind":"act","text":"推门"}')).toEqual({ kind: 'act', text: '推门' });
    expect(decodeTaskOutput('action', '{"kind":"skip"}')).toEqual({ kind: 'skip' });
    rejects('action', '{"kind":"flee"}');
    rejects('action', '{"kind":"act"}', /text/);
    rejects('action', '{"kind":"skip","text":"多余"}', /only kind/);
  });

  test('targets accepts an empty or id-only list and rejects drift', () => {
    expect(decodeTaskOutput('targets', '{"targets":[]}')).toEqual({ targets: [] });
    expect(decodeTaskOutput('targets', '{"targets":[{"targetId":"person_b"}]}')).toEqual({ targets: [{ targetId: 'person_b' }] });
    // 模型只声明目标：触发键与骰点规则是程序身份，出现在输出里即拒绝。
    rejects('targets', '{"targets":[{"targetId":"x","triggerKey":"y"}]}', /target keys/);
    rejects('targets', '{"targets":[{"targetId":"x","ruleVersion":"reaction-d20-v1"}]}', /target keys/);
  });

  test('results is a non-empty-string record', () => {
    expect(decodeTaskOutput('results', '{"person_a":"门开了"}')).toEqual({ person_a: '门开了' });
    expect(decodeTaskOutput('results', '{}')).toEqual({});
    rejects('results', '{"person_a":42}', /non-empty strings/);
  });

  test('updates accepts batch arrays and split-mode single calls, with typed deltas', () => {
    const batch = [{ stage: 'position', changes: { person_a: { positionSet: { containerId: 'corridor', slotId: null, relativeTo: null } } } }];
    expect(decodeTaskOutput('updates', JSON.stringify(batch))).toEqual(batch);
    const split = { stage: 'sanity', changes: { person_b: { sanitySet: 7 } } };
    expect(decodeTaskOutput('updates', JSON.stringify(split))).toEqual(split); // single call, not an array
    expect(decodeTaskOutput('updates', '[]')).toEqual([]);
    // With the call's mode declared, the wrong shape rejects at the codec.
    expect(decodeTaskOutput('updates', JSON.stringify(split), { updatesSplitMode: true })).toEqual(split);
    rejects('updates', JSON.stringify(batch), /split-mode updates must be a single call/, { updatesSplitMode: true });
    expect(decodeTaskOutput('updates', JSON.stringify(batch), { updatesSplitMode: false })).toEqual(batch);
    rejects('updates', JSON.stringify(split), /batch-mode updates must be an array/, { updatesSplitMode: false });
    // Deltas are validated to their declared fields: mergeUpdatesStages must
    // never meet a shape it cannot consume.
    rejects('updates', '[{"stage":"subtasks","changes":{"person_a":{"subtasksAdded":7}}}]', /subtasksAdded must be an array/);
    rejects('updates', '[{"stage":"position","changes":{"person_a":{"weather":"sunny"}}}]', /unknown entity delta field/);
    rejects('updates', '[{"stage":"sanity","changes":{"person_a":{"sanitySet":"high"}}}]', /number or null/);
    const full = [{
      stage: 'tasks',
      changes: {
        person_a: {
          positionSet: { containerId: 'hall', slotId: 'shelf', relativeTo: { entityId: 'item_lamp', relation: 'above' } },
          appearanceChanges: [{ id: 'c1', text: null, supersedes: ['c0'] }],
          tasksAchieved: ['task_a'],
          subtasksAdded: [{ id: 't9', ownerId: 'person_a', parentTaskId: null, goal: '找灯', status: 'pending' }],
        },
      },
    }];
    expect(decodeTaskOutput('updates', JSON.stringify(full))).toEqual(full);
    rejects('updates', '[{"stage":"tasks","changes":{"person_a":{"positionSet":{"containerId":"hall","relativeTo":{"entityId":"x","relation":"underneath"}}}}}]', /relation/);
    rejects('updates', '[{"stage":"tasks","changes":{"person_a":{"subtasksAdded":[{"id":"t","ownerId":"p","parentTaskId":null,"goal":"g","status":"done"}]}}}]', /status/);
  });

  test('continuation accepts only model-closed variants', () => {
    const proceed = { kind: 'continue', closedBy: 'model', cancelReason: null, candidateCharacterIds: ['person_a', 'person_b'], nextRoundId: 'round_2' };
    expect(decodeTaskOutput('continuation', JSON.stringify(proceed))).toEqual(proceed);
    expect(decodeTaskOutput('continuation', '{"kind":"handback","closedBy":"model","cancelReason":null}'))
      .toEqual({ kind: 'handback', closedBy: 'model', cancelReason: null });
    rejects('continuation', '{"kind":"continue","closedBy":"cancel","cancelReason":"x","candidateCharacterIds":[],"nextRoundId":"r"}', /closedBy/);
    rejects('continuation', '{"kind":"handback","closedBy":"model","cancelReason":null,"nextRoundId":"r"}', /keys/);
  });

  test('initial checks the top-level contract; the wire schema re-checks depth', () => {
    const initial = {
      engineVersion: 'world-engine-v1', schemaVersion: 1, protagonistId: 'person_c',
      initialTime: { calendar: 'gregorian', dateTime: '2026-01-01T08:00:00', instantOrdinal: 0 },
      locations: { hall: {} }, items: {}, characters: { person_c: {} },
    };
    expect(decodeTaskOutput('initial', JSON.stringify(initial))).toEqual(initial);
    rejects('initial', JSON.stringify({ ...initial, engineVersion: 'v9' }), /version constants/);
    rejects('initial', JSON.stringify({ ...initial, locations: [] }), /must be an object/);
  });

  test('time validates the TimeAdvance shape and closed units', () => {
    expect(decodeTaskOutput('time', '{"boundary":"elapsed","duration":{"amount":2,"unit":"second"}}'))
      .toEqual({ boundary: 'elapsed', duration: { amount: 2, unit: 'second' } });
    expect(decodeTaskOutput('time', '{"boundary":"instant","duration":{"amount":0,"unit":"hour"}}'))
      .toEqual({ boundary: 'instant', duration: { amount: 0, unit: 'hour' } });
    rejects('time', '{"boundary":"elapsed","duration":{"amount":1,"unit":"week"}}', /unit/);
    rejects('time', '{"boundary":"elapsed","duration":{"amount":-1,"unit":"second"}}', /amount/);
    rejects('time', '{"boundary":"elapsed","duration":{"amount":1.5,"unit":"second"}}', /amount/);
  });

  test('pointPlan allows actionless points and validates the point shape', () => {
    const plan = [{ pointId: 'p1', kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'second' } }, actorIds: ['person_a'] }];
    expect(decodeTaskOutput('pointPlan', JSON.stringify(plan))).toEqual(plan);
    const scan = [{ pointId: 'p2', kind: 'linked', timeAdvance: { boundary: 'elapsed', duration: { amount: 60, unit: 'second' } }, actorIds: [] }];
    expect(decodeTaskOutput('pointPlan', JSON.stringify(scan))).toEqual(scan); // T03 actionless time-scan point
    rejects('pointPlan', '[]', /not be empty/);
    rejects('pointPlan', JSON.stringify([{ pointId: 'p1', kind: 'weird', timeAdvance: { boundary: 'instant', duration: { amount: 0, unit: 'second' } }, actorIds: ['person_a'] }]), /point kind/);
    rejects('pointPlan', JSON.stringify([{ pointId: 'p1', kind: 'normal', timeAdvance: { boundary: 'instant', duration: { amount: 0, unit: 'second' } }, actorIds: [42] }]), /actor ids/);
  });

  test('json fences are stripped; broken json and emptiness carry the raw payload', () => {
    expect(decodeTaskOutput('action', '```json\n{"kind":"skip"}\n```')).toEqual({ kind: 'skip' });
    rejects('action', '前言无关内容 {"kind":"skip"}', /not valid JSON/); // prose-wrapped json is rejected, not guessed apart
    const broken = asError('results', '{oops');
    expect(broken).toBeInstanceOf(StructuredOutputError);
    expect(broken.reason).toMatch(/not valid JSON/);
    expect(broken.raw).toBe('{oops');
    rejects('action', '```json\n');
  });
});
