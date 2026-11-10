import { describe, expect, it } from 'vitest';

import {
  composeProse, generateCandidate, guardSentence, validateScene,
  type ProseScene,
} from './index';
import {
  CONTINUATION_SCENE, NO_CHANGE_SCENE, SERVICE_LANE_SCENE, SHED_SCENE, SHORT_MOVE_SCENE,
} from './fixtures';

function clone<T>(value: T): T {
  return structuredClone(value);
}

function sentences(text: string): string[] {
  return text.split(/。(?![」』”])/u).map((part) => part.trim()).filter(Boolean);
}

describe('composeProse facts and direction', () => {
  it('renders a move from -> to, keeps the stayer and does not touch the item', () => {
    const result = composeProse(SHORT_MOVE_SCENE);
    expect(result.accepted).toBe(true);
    expect(result.text).toContain('林川');
    expect(result.text).toContain('周宁');
    expect(result.text).toContain('盒子');
    expect(result.text).not.toMatch(/打开|开盖|盒盖打开/u);
    const moveSentence = sentences(result.text).find((sentence) => sentence.includes('林川') && sentence.includes('门厅'));
    expect(moveSentence).toBeTruthy();
    expect(moveSentence!.indexOf('走廊')).toBeLessThan(moveSentence!.indexOf('门厅'));
    expect(result.text).not.toContain('person_a');
    expect(result.text).not.toContain('person_c');
  });

  it('does not reverse a direction even when the move is the first beat', () => {
    const scene = clone(SHORT_MOVE_SCENE);
    scene.beats = [{ kind: 'move', actorId: 'person_a', from: '门厅', to: '走廊' }];
    scene.location.name = '走廊';
    const result = composeProse(scene);
    const moveSentence = sentences(result.text).find((sentence) => sentence.includes('林川') && sentence.includes('门厅'));
    expect(moveSentence).toBeTruthy();
    expect(moveSentence!.indexOf('门厅')).toBeLessThan(moveSentence!.indexOf('走廊'));
    expect(result.issues.filter((issue) => issue.kind === 'direction_reversed')).toHaveLength(0);
  });

  it('weaves the licensed item detail instead of inventing a new object', () => {
    const result = composeProse(SHED_SCENE);
    expect(result.accepted).toBe(true);
    expect(result.text).toContain('电池盒的盖子已经打开，槽里换上了一节新电池');
    expect(result.text).toContain('相机电池');
    expect(result.text).not.toContain('钥匙');
    expect(result.text).not.toContain('雨');
  });

  it('keeps every supplied dialogue line and the answer pause', () => {
    const result = composeProse(SERVICE_LANE_SCENE);
    expect(result.accepted).toBe(true);
    for (const beat of SERVICE_LANE_SCENE.beats) {
      if (beat.kind !== 'line') continue;
      // A long line may be split into two quotes with a tag in between.
      expect(result.text).toContain(beat.text.slice(0, 6));
      expect(result.text).toContain(beat.text.slice(-6));
    }
    expect(result.text).toContain('路明非');
    expect(result.text).toContain('诺诺');
    expect(result.text).toContain('路明非问清了');
  });

  it('is deterministic for the same seed and varies with another seed', () => {
    expect(composeProse(SERVICE_LANE_SCENE).text).toBe(composeProse(SERVICE_LANE_SCENE).text);
    const other = clone(SERVICE_LANE_SCENE);
    other.seed = 999;
    expect(composeProse(other).text).not.toBe(composeProse(SERVICE_LANE_SCENE).text);
  });
});

describe('composeProse references and continuity', () => {
  it('uses names, not guessed pronouns, when gender is unknown', () => {
    const scene = clone(SHORT_MOVE_SCENE);
    scene.cast[0].name = '米拉';
    scene.cast[0].gender = 'unknown';
    scene.cast[1].name = '凯';
    scene.cast[1].gender = 'unknown';
    scene.protagonistId = 'person_c';
    const result = composeProse(scene);
    expect(result.text).toContain('米拉');
    expect(result.text).toContain('凯');
    expect(result.text).not.toMatch(/[他她]/u);
  });

  it('uses a pronoun only when one actor of that gender is visible', () => {
    const result = composeProse(SHORT_MOVE_SCENE);
    expect(result.text).toMatch(/[他她]/u);
    const twoMen = clone(SHORT_MOVE_SCENE);
    twoMen.cast[1].gender = 'male';
    const second = composeProse(twoMen);
    // Both are male: the composer must not use a bare pronoun for them.
    expect(second.text).not.toMatch(/他(从|的)/u);
  });

  it('does not reopen with the previous turn detail or echo its sentences', () => {
    const result = composeProse(CONTINUATION_SCENE);
    expect(result.accepted).toBe(true);
    expect(result.text).not.toContain('推拉门可回服务巷');
    expect(result.text).not.toContain('电池盒的盖子已经打开');
    expect(result.opening.startsWith('器材棚的推拉门')).toBe(false);
    expect(result.issues.filter((issue) => issue.kind === 'echo_prior')).toHaveLength(0);
  });
});

describe('composeProse guards', () => {
  it('refuses unlicensed props, past events, promises and stock gestures', () => {
    const license = {
      text: '走廊 门厅 林川 周宁',
      actorNames: ['林川', '周宁'],
      locationNames: ['走廊', '门厅'],
      itemNames: [],
    };
    expect(guardSentence('外面下起了雨。', license)?.kind).toBe('unlicensed_detail');
    expect(guardSentence('他想起十年前的事。', license)?.kind).toBe('unlicensed_past');
    expect(guardSentence('他答应明天再来。', license)?.kind).toBe('unlicensed_promise');
    expect(guardSentence('他愣住了。', license)?.kind).toBe('stock_phrase');
    expect(guardSentence('林川走到门厅。', license)).toBeNull();
  });

  it('does not add weather or a surprise gesture to the move scene', () => {
    const result = composeProse(SHORT_MOVE_SCENE);
    expect(result.text).not.toMatch(/雨|雪|风|阳光|愣|一惊|不由得/u);
  });

  it('keeps a no-change turn short but accepted', () => {
    const result = composeProse(NO_CHANGE_SCENE);
    expect(result.accepted).toBe(true);
    expect([...result.text].length).toBeLessThan(80);
  });
});

describe('validateScene and generateCandidate', () => {
  it('reports unknown actors instead of silently dropping them', () => {
    const scene = clone(SHORT_MOVE_SCENE);
    scene.beats = [{ kind: 'move', actorId: 'ghost', from: '走廊', to: '门厅' }];
    const issues = validateScene(scene);
    expect(issues.some((issue) => issue.kind === 'unknown_reference')).toBe(true);
    const result = composeProse(scene);
    expect(result.accepted).toBe(false);
    expect(result.issues.some((issue) => issue.kind === 'unknown_reference')).toBe(true);
  });

  it('returns the candidate contract and reports progress once', () => {
    const progress: Array<{ status: string; verified: boolean; text: string }> = [];
    const result = generateCandidate({
      policy: { scene: SERVICE_LANE_SCENE },
      onProgress: (event) => progress.push({ status: event.status, verified: event.verified, text: event.text }),
    });
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts).toHaveLength(1);
    expect(result.rawAttempts[0].accepted).toBe(true);
    expect(result.rawAttempts[0].prompt).toBe('');
    expect(result.attemptIndex).toBe(0);
    expect(result.status).toBe('accepted');
    expect(result.timings.attemptsMs).toBeGreaterThanOrEqual(0);
    expect(result.display.status).toBe('accepted');
    expect(result.strategy).toBe('prose-composer');
    expect(result.text.length).toBeGreaterThan(80);
    expect(progress).toHaveLength(1);
    expect(progress[0].status).toBe('complete');
    expect(progress[0].verified).toBe(true);
    expect(progress[0].text).toBe(result.text);
  });

  it('builds a sparse but truthful scene from committed facts', () => {
    const result = generateCandidate({
      committed: {
        anchor: { worldId: 'w', pointId: 'p' },
        facts: [
          { id: 'a', actorId: 'a', name: '林川', kind: 'moved', from: '走廊', to: '门厅' },
          { id: 'b', actorId: 'a', name: '林川', kind: 'task_achieved', goal: '守住走廊' },
        ],
      },
      policy: { viewpoint: { id: 'a', name: '林川' }, minChars: 20 },
    });
    expect(result.sparse).toBe(true);
    expect(result.issues.some((issue) => issue.kind === 'sparse_skeleton')).toBe(true);
    expect(result.text).toContain('林川');
    expect(result.text).toContain('门厅');
    expect(result.composed.text).toBe(result.text);
  });

  it('accepts the shared browser driver call shape', () => {
    const events: string[] = [];
    const controller = new AbortController();
    // The driver spreads the whole run context: engine, committed, state, before,
    // delta, inputText, priorText, policy, signal, onProgress.
    const result = generateCandidate({
      engine: { info: { backend: 'none', modelId: 'none' } },
      committed: {
        anchor: { worldId: 'w', pointId: 'p', version: 1, stateDigest: 'd', previousPointId: 'root' },
        facts: [{ id: 'm', actorId: 'a', name: '林川', kind: 'moved', from: '走廊', to: '门厅' }],
      },
      state: {}, before: null, delta: { timeAdvance: null, entityDeltas: {} },
      inputText: '林川从走廊走到门厅。',
      priorText: null,
      policy: { scene: SHORT_MOVE_SCENE, minChars: 40 },
      signal: controller.signal,
      onProgress: (event: { status: string }) => events.push(event.status),
    } as never);
    expect(result.text.length).toBeGreaterThan(0);
    expect(result.accepted).toBe(true);
    expect(result.rawAttempts.length).toBe(1);
    expect(result.issues).toEqual([]);
    expect(result.timings.totalMs).toBeGreaterThanOrEqual(0);
    expect(events).toEqual(['complete']);
  });

  it('fails closed when neither a skeleton nor facts are supplied', () => {
    const result = generateCandidate({});
    expect(result.accepted).toBe(false);
    expect(result.text).toBe('');
    expect(result.issues[0].kind).toBe('empty_scene');
  });
});

describe('composeProse style mechanics', () => {
  it('keeps paragraphs short and does not repeat the same opening token', () => {
    const result = composeProse(SHED_SCENE);
    expect(result.paragraphs.length).toBeGreaterThanOrEqual(4);
    for (const paragraph of result.paragraphs) {
      expect([...paragraph].length).toBeLessThanOrEqual(120);
    }
    for (let index = 1; index < result.paragraphs.length; index += 1) {
      const previous = result.paragraphs[index - 1].slice(0, 3);
      expect(result.paragraphs[index].startsWith(previous)).toBe(false);
    }
  });

  it('turns a repeated paragraph-opening name into a pronoun when unambiguous', () => {
    const scene: ProseScene = {
      ...clone(SHORT_MOVE_SCENE),
      beats: [
        { kind: 'action', actorId: 'person_a', text: '林川把袖口卷起来。' },
        { kind: 'action', actorId: 'person_a', text: '林川又看了一眼门口。' },
      ],
    };
    const result = composeProse(scene);
    expect(result.text).toContain('他又看了一眼门口');
  });

  it('keeps the name when two actors share the gender', () => {
    const scene: ProseScene = {
      ...clone(SHORT_MOVE_SCENE),
      cast: [
        { id: 'person_a', name: '林川', gender: 'male' },
        { id: 'person_b', name: '陈默', gender: 'male' },
      ],
      beats: [
        { kind: 'action', actorId: 'person_a', text: '林川把袖口卷起来。' },
        { kind: 'action', actorId: 'person_a', text: '林川又看了一眼门口。' },
      ],
    };
    const result = composeProse(scene);
    expect(result.text).toContain('林川又看了一眼门口');
  });

  it('does not merge a place-stance line into a place-detail line', () => {
    const scene: ProseScene = {
      ...clone(SHORT_MOVE_SCENE),
      location: { name: '西侧服务巷', details: ['巷口的黄黑绳已放下。'] },
      beats: [{ kind: 'stay', actorId: 'person_c', location: '西侧服务巷' }],
    };
    const result = composeProse(scene);
    expect(result.text).not.toMatch(/还在西侧服务巷。\s*西侧服务巷里/u);
  });

  it('places a stay beat after the movement it contrasts with', () => {
    const scene: ProseScene = {
      ...clone(SHORT_MOVE_SCENE),
      cast: [
        ...SHORT_MOVE_SCENE.cast,
        { id: 'person_b', name: '陈默', gender: 'male' },
      ],
      beats: [
        { kind: 'stay', actorId: 'person_c', location: '走廊' },
        { kind: 'move', actorId: 'person_a', from: '走廊', to: '门厅' },
      ],
    };
    const result = composeProse(scene);
    const moveAt = result.text.indexOf('林川从走廊');
    const stayAt = result.text.indexOf('周宁留');
    expect(moveAt).toBeGreaterThanOrEqual(0);
    expect(stayAt).toBeGreaterThan(moveAt);
  });
});
