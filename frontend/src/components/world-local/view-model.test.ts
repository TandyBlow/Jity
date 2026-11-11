import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import type { WorldState } from '@/lib/world-engine/types';

import {
  controlAvailability,
  formatElapsed,
  formatWorldTime,
  historyEntriesFromPoints,
  isSubmitShortcut,
  narrationAccepted,
  narrationFailed,
  narrationStatusLabel,
  roomOf,
  splitNarration,
  worldStatusFromState,
  type ControlAvailabilityInput,
} from './view-model';

const fixturePath = fileURLToPath(new URL('../../../public/worlds/dragon-raja-free-day.world.json', import.meta.url));
const state = JSON.parse(readFileSync(fixturePath, 'utf8')) as WorldState;

const baseControlInput: ControlAvailabilityInput = {
  value: '我贴着墙往西走',
  phase: 'ready',
  busy: false,
  paused: false,
  disabled: false,
  disabledReason: null,
  submitDisabledReason: null,
  pauseDisabledReason: null,
  resumeDisabledReason: null,
  cancelDisabledReason: null,
  hasPause: true,
  hasResume: true,
  hasCancel: true,
};

describe('worldStatusFromState', () => {
  it('summarises the committed protagonist, room, tasks and nearby people', () => {
    const status = worldStatusFromState(state);
    expect(status.name).toBe('路明非');
    expect(status.locationLabel).toBe('西侧服务巷');
    expect(status.timeLabel).toBe('2009-10-17 15:20');
    expect(status.sanity).toBe(43);
    expect(status.nearby.map((person) => person.name)).toContain('诺诺');
    expect(status.nearby.map((person) => person.name)).not.toContain('芬格尔');
    expect(status.tasks.some((task) => task.id === 'task_lu_match' && !task.done)).toBe(true);
    expect(status.personality).toContain('玩笑');
    expect(status.items?.map((item) => item.name) ?? []).toContain('演习规则牌');
  });

  it('keeps achieved tasks but orders them after pending ones', () => {
    const changed = structuredClone(state);
    changed.characters.lu.tasks.task_lu_choice.status = 'achieved';
    const status = worldStatusFromState(changed);
    const achieved = status.tasks.findIndex((task) => task.done);
    const pending = status.tasks.findIndex((task) => !task.done);
    expect(status.tasks.some((task) => task.id === 'task_lu_choice' && task.done)).toBe(true);
    expect(pending).toBeGreaterThanOrEqual(0);
    expect(achieved).toBeGreaterThan(pending);
  });

  it('follows container ids to the innermost room like the kernel', () => {
    const nested = structuredClone(state);
    nested.characters.lu.position = { containerId: 'rules' };
    expect(roomOf(nested, 'lu')).toBe('lane');
    expect(worldStatusFromState(nested).locationLabel).toBe('西侧服务巷');
  });
});

describe('presentation helpers', () => {
  it('formats world time without pretending an empty value is a date', () => {
    expect(formatWorldTime('2009-10-17T15:20:00')).toBe('2009-10-17 15:20');
    expect(formatWorldTime('')).toBe('—');
    expect(formatWorldTime(null)).toBe('—');
  });

  it('formats elapsed time in a human unit', () => {
    expect(formatElapsed(null)).toBe('');
    expect(formatElapsed(420)).toBe('420 毫秒');
    expect(formatElapsed(6900)).toBe('6.9 秒');
  });

  it('splits model paragraph markers without changing the words', () => {
    expect(splitNarration('第一段※第二段')).toEqual(['第一段', '第二段']);
    expect(splitNarration('a\n\nb\nc')).toEqual(['a', 'b\nc']);
    expect(splitNarration('a\nb')).toEqual(['a', 'b']);
    expect(splitNarration('')).toEqual([]);
  });

  it('labels an unread narration status instead of guessing a cache state', () => {
    expect(narrationStatusLabel(null)).toBe('正文状态未读取');
    expect(narrationStatusLabel('missing')).toBe('正文缓存缺失');
  });
});

describe('historyEntriesFromPoints', () => {
  it('keeps newest first and leaves unread status/null fields explicit', () => {
    const entries = historyEntriesFromPoints(
      [
        { pointId: 'p1', sequence: 1, kind: 'root', stateDigest: 'd1' },
        { pointId: 'p2', sequence: 2, kind: 'normal', stateDigest: 'd2' },
      ],
      {
        narrationStatusById: { p2: 'missing' },
        advanceIdByPointId: { p2: 'a1' },
        commandByAdvanceId: { a1: '我往前走' },
      },
    );
    expect(entries.map((entry) => entry.pointId)).toEqual(['p2', 'p1']);
    expect(entries[0]).toMatchObject({ status: 'missing', command: '我往前走', stateDigest: 'd2' });
    expect(entries[1]).toMatchObject({ status: null, command: null, stateDigest: 'd1' });

    const direct = historyEntriesFromPoints(
      [{ pointId: 'p3', sequence: 3, kind: 'normal', advanceId: 'a2' }],
      { commandByAdvanceId: { a2: '我从后门绕出去' } },
    );
    expect(direct[0].command).toBe('我从后门绕出去');
  });
});

describe('controlAvailability', () => {
  it('allows submitting a non-empty draft when idle', () => {
    const result = controlAvailability(baseControlInput);
    expect(result.canSubmit).toBe(true);
    expect(result.submitReason).toBeNull();
    expect(result.canPause).toBe(false);
    expect(result.pauseReason).toBe('只有本轮回合进行中才能暂停');
    expect(result.canCancel).toBe(false);
  });

  it('blocks submit and allows pause/cancel while a round is running', () => {
    const result = controlAvailability({ ...baseControlInput, busy: true, phase: 'streaming' });
    expect(result.canSubmit).toBe(false);
    expect(result.submitReason).toBe('本轮回合尚未交还');
    expect(result.canPause).toBe(true);
    expect(result.canCancel).toBe(true);
  });

  it('offers resume and still allows cancel while paused', () => {
    const result = controlAvailability({ ...baseControlInput, paused: true, phase: 'paused' });
    expect(result.canSubmit).toBe(false);
    expect(result.submitReason).toBe('当前已暂停，继续后才能提交行动');
    expect(result.canPause).toBe(false);
    expect(result.canResume).toBe(true);
    expect(result.canCancel).toBe(true);
  });

  it('reports missing callbacks as wiring reasons, never as success', () => {
    const result = controlAvailability({
      ...baseControlInput,
      hasPause: false,
      hasResume: false,
      hasCancel: false,
    });
    expect(result.canPause).toBe(false);
    expect(result.pauseReason).toBe('当前会话尚未接入暂停');
    expect(result.canResume).toBe(false);
    expect(result.resumeReason).toBe('当前会话尚未接入继续');
    expect(result.canCancel).toBe(false);
    expect(result.cancelReason).toBe('当前会话尚未接入取消');
  });

  it('keeps empty input disabled without inventing a defect reason', () => {
    const result = controlAvailability({ ...baseControlInput, value: '   ' });
    expect(result.canSubmit).toBe(false);
    expect(result.submitReason).toBeNull();
  });

  it('surfaces the loading and explicit submit reasons', () => {
    expect(controlAvailability({ ...baseControlInput, phase: 'loading' }).submitReason).toBe('模型仍在载入');
    const blocked = controlAvailability({ ...baseControlInput, submitDisabledReason: '等待存档写入完成' });
    expect(blocked.canSubmit).toBe(false);
    expect(blocked.submitReason).toBe('等待存档写入完成');
  });
});

describe('narration state constructors', () => {
  it('keeps accepted text and warnings separate from failure', () => {
    const accepted = narrationAccepted('p1', '正文', { elapsedMs: 1200, alignmentNote: 'align:actor_swap' });
    expect(accepted).toMatchObject({ phase: 'accepted', text: '正文', alignmentNote: 'align:actor_swap' });
    expect(accepted.failureReason).toBeUndefined();
  });

  it('carries the last accepted text into a failure state', () => {
    const failed = narrationFailed('超时', { previousText: '上一轮', pointId: 'p1' });
    expect(failed).toMatchObject({ phase: 'failed', text: '', failureReason: '超时', previousText: '上一轮', pointId: 'p1' });
  });
});

describe('isSubmitShortcut', () => {
  it('accepts Ctrl+Enter and ⌘+Enter only', () => {
    expect(isSubmitShortcut({ key: 'Enter', ctrlKey: true, metaKey: false })).toBe(true);
    expect(isSubmitShortcut({ key: 'Enter', ctrlKey: false, metaKey: true })).toBe(true);
    expect(isSubmitShortcut({ key: 'Enter', ctrlKey: false, metaKey: false })).toBe(false);
    expect(isSubmitShortcut({ key: 'Enter', ctrlKey: false, metaKey: true, altKey: true })).toBe(false);
    expect(isSubmitShortcut({ key: 'a', ctrlKey: true, metaKey: false })).toBe(false);
  });
});
