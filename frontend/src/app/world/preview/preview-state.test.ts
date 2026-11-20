import { describe, expect, it } from 'vitest';
import { describePreview } from './preview-state';

describe('describePreview', () => {
  it('shows the sentences when the adapter produced facts', () => {
    const view = describePreview({ facts: [{ kind: 'moved', sentence: '林川从走廊到门厅。' }], gaps: [], notDisplayed: [], delta: {} });
    expect(view.band).toBe('facts');
    expect(view.sentences).toEqual(['林川从走廊到门厅。']);
    expect(view.quietPoint).toBe(false);
  });

  it('refuses to read a failed recovery as a quiet point', () => {
    const view = describePreview({ facts: [], gaps: [{ gap: 'state not recoverable', replayFailure: 'unavailable' }], notDisplayed: [], delta: {} });
    expect(view.band).toBe('gap');
    expect(view.quietPoint).toBe(false);
    expect(view.gapMessages).toEqual(['state not recoverable']);
  });

  it('names the withheld checkpoint when the replay found an inconsistency', () => {
    const view = describePreview({
      facts: [], gaps: [{ gap: 'replay found an inconsistency; the checkpoint is not used to mask it', replayFailure: 'ledger' }],
      notDisplayed: [], delta: { person_a: { sanitySet: 2 } },
    });
    expect(view.band).toBe('gap');
    expect(view.gapMessages[0]).toContain('未用检查点兜底');
  });

  it('keeps an unshown task distinct from a quiet point', () => {
    const view = describePreview({
      facts: [], gaps: [], notDisplayed: [{ reason: 'task delta has no display shape yet, so it is not shown' }],
      delta: { person_a: { tasksAchieved: ['task_watch'] } },
    });
    expect(view.band).toBe('unshown');
    expect(view.quietPoint).toBe(false);
    expect(view.unshownReason).toContain('task delta');
  });

  it('only calls a point quiet when the delta is genuinely empty', () => {
    const quiet = describePreview({ facts: [], gaps: [], notDisplayed: [], delta: {} });
    expect(quiet.band).toBe('empty');
    expect(quiet.quietPoint).toBe(true);
    const notQuiet = describePreview({ facts: [], gaps: [], notDisplayed: [], delta: { person_a: { sanitySet: 3 } } });
    expect(notQuiet.quietPoint).toBe(false);
  });
});
