import { describe, expect, it } from 'vitest';

import {
  composeConstrainedBeat, createBeatComposer, sceneFromBeatRequest,
  type BeatFactLike, type ComposeBeatRequestLike,
} from './index';

const goal = '把胸前护目镜戴好并确认镜片没有裂纹';

function facts(): BeatFactLike[] {
  return [
    { id: 't1', kind: 'time', mandatory: true, visibility: 'scene', advance: { duration: { amount: 6, unit: 'minute' } } },
    { id: 'm1', kind: 'move', mandatory: true, visibility: 'scene', entityId: 'lu', name: '路明非', entityKind: 'character', from: '西侧服务巷', to: '器材棚', viewpoint: true },
    { id: 'm2', kind: 'move', mandatory: true, visibility: 'scene', entityId: 'nono', name: '诺诺', entityKind: 'character', from: '西侧服务巷', to: '红方集结点', viewpoint: false },
    { id: 'm3', kind: 'move', mandatory: true, visibility: 'scene', entityId: 'camera_battery', name: '相机备用电池', entityKind: 'item', from: '芬格尔', to: '器材领用台', viewpoint: false },
    { id: 'k1', kind: 'task_achieved', mandatory: true, visibility: 'scene', ownerId: 'lu', name: '路明非', goal },
    { id: 'p1', kind: 'personality_changed', mandatory: true, visibility: 'scene', ownerId: 'lu', name: '路明非', text: '说话前先看一眼对方的鞋，再决定要不要开玩笑' },
    { id: 's1', kind: 'sanity_changed', mandatory: true, visibility: 'scene', ownerId: 'lu', name: '路明非', from: 43, to: 39 },
    { id: 'o1', kind: 'item_present', mandatory: false, visibility: 'scene', itemId: 'ammo_box', name: '开盖演习弹药箱', container: '器材棚', note: '箱内还有两只装填好的弹匣。' },
  ];
}

function request(kind: string, factIds: string[], details: string[] = []): ComposeBeatRequestLike {
  return {
    beat: { id: kind, kind, factIds, details, mustMention: [], seed: 73 },
    scene: {
      viewpoint: { id: 'lu', name: '路明非', location: '西侧服务巷', note: '护目镜的带子在手腕上绕了一圈。' },
      place: { id: 'shed', name: '器材棚', parentName: '西侧器材区', note: '推拉门可回服务巷，领用台在门内右侧。' },
      present: [
        { id: 'lu', name: '路明非', note: '护目镜的带子在手腕上绕了一圈。' },
        { id: 'fingel', name: '芬格尔', note: '相机背带往肩上提了提。' },
      ],
      objects: [{ id: 'ammo_box', name: '开盖演习弹药箱', note: '箱内还有两只装填好的弹匣。' }],
      facts: facts(),
      priorText: null,
    },
    prior: null,
  };
}

describe('04 beat adapter', () => {
  it('opens at the origin before the viewpoint move, not at the destination', () => {
    const result = composeConstrainedBeat(request('open', ['t1']));
    expect(result.text).toContain('过了六分钟');
    expect(result.text).toContain('路明非还在西侧服务巷');
    expect(result.text).not.toContain('器材棚');
  });

  it('joins two character moves and keeps both directions', () => {
    const result = composeConstrainedBeat(request('move', ['m1', 'm2']));
    expect(result.text).toMatch(/路明非从西侧服务巷(?:走进|走到|来到)器材棚/u);
    expect(result.text).toMatch(/诺诺从西侧服务巷(?:走进|走到|来到)红方集结点/u);
    expect(result.text.indexOf('西侧服务巷')).toBeLessThan(result.text.indexOf('器材棚'));
  });

  it('does not name the source character of an item move (base-grader actor-swap rule)', () => {
    const result = composeConstrainedBeat(request('move', ['m3']));
    expect(result.text).toContain('相机备用电池被带到了器材领用台');
    expect(result.text).not.toContain('芬格尔');
  });

  it('turns an event turn into clauses, not a stack of fact cards', () => {
    const result = composeConstrainedBeat(request('event', ['k1', 'p1', 's1']));
    expect(result.text).toContain(`「${goal}」`);
    expect(result.text).toContain('说话前先看一眼对方的鞋');
    expect(result.text).toMatch(/紧/u);
    const names = result.text.match(/路明非/gu) ?? [];
    expect(names.length).toBeLessThanOrEqual(3);
    expect(result.text).not.toContain('person_');
  });

  it('keeps the item location and its licensed note in a scene beat', () => {
    const result = composeConstrainedBeat(request('scene', ['o1']));
    expect(result.text).toContain('开盖演习弹药箱');
    expect(result.text).toContain('器材棚');
    expect(result.text).toContain('两只装填好的弹匣');
  });

  it('closes on a grounded micro-action without a new event', () => {
    const result = composeConstrainedBeat(request('close', [], ['芬格尔']));
    expect(result.text).toContain('路明非没有马上再动');
    expect(result.text).toContain('芬格尔也没有动');
    expect(result.text).not.toMatch(/推|拿|走|跑|打开/u);
  });

  it('maps a future action or dialogue fact when lane 04 supplies one', () => {
    const scene = request('event', ['a1', 'l1']);
    scene.scene.facts.push(
      { id: 'a1', kind: 'action', mandatory: true, visibility: 'scene', actorId: 'lu', name: '路明非', text: '把护目镜往手腕上推了推。' },
      { id: 'l1', kind: 'line', mandatory: true, visibility: 'scene', speakerId: 'fingel', name: '芬格尔', text: '别看，机型不一样。' },
    );
    const result = composeConstrainedBeat(scene);
    expect(result.text).toContain('「别看，机型不一样。」');
  });
});

describe("beat text against lane 04's gate vocabulary", () => {
  // Lane 04 verifies a sanity change by direction cues, not by the composer's
  // own claim. The lists are copied from its `verify.ts`; if 04 changes them,
  // this test is the place that fails first instead of a silent beat fallback.
  const DOWN = ['沉', '紧', '往下', '发凉', '收紧', '坠', '缩'];
  const UP = ['松', '顺', '稳', '回暖', '舒', '缓', '放平'];
  const FLAT = ['没有变', '照旧'];

  function sanityScene(from: number, to: number, id: string): ComposeBeatRequestLike {
    const req = request('event', ['s1']);
    req.scene.facts = [{
      id: 's1', kind: 'sanity_changed', mandatory: true, visibility: 'scene',
      ownerId: id, name: id === 'lu' ? '路明非' : '芬格尔', from, to,
    }];
    req.beat.id = `event:${id}`;
    req.beat.seed = id === 'lu' ? 73 : 91;
    return req;
  }

  it('uses a cue lane 04 recognises for down, up and flat', () => {
    for (const id of ['lu', 'fingel']) {
      const down = composeConstrainedBeat(sanityScene(50, 44, id)).text;
      expect(DOWN.some((cue) => down.includes(cue))).toBe(true);
      const up = composeConstrainedBeat(sanityScene(44, 50, id)).text;
      expect(UP.some((cue) => up.includes(cue))).toBe(true);
      const flat = composeConstrainedBeat(sanityScene(50, 50, id)).text;
      expect(FLAT.some((cue) => flat.includes(cue))).toBe(true);
    }
  });

  it('names the task owner next to the goal text, never a bare pronoun', () => {
    const result = composeConstrainedBeat(request('event', ['k1']));
    const sentence = result.text.split('。').find((part) => part.includes(goal)) ?? '';
    expect(sentence).toContain('路明非');
    expect(sentence.startsWith('他')).toBe(false);
    expect(sentence).toContain('「');
  });

  it('varies the same sanity beat between two actors', () => {
    const lu = composeConstrainedBeat(sanityScene(50, 44, 'lu')).text;
    const fingel = composeConstrainedBeat(sanityScene(50, 44, 'fingel')).text;
    expect(lu).not.toBe(fingel);
  });
});

describe('beat composer contract', () => {
  it('reports source=program, attempts=1 and never fakes progress', async () => {
    const composer = createBeatComposer();
    let progress = 0;
    const result = await composer(request('open', ['t1']), { onProgress: () => { progress += 1; } });
    expect(result.source).toBe('program');
    expect(result.attempts).toBe(1);
    expect(result.text.length).toBeGreaterThan(0);
    expect(progress).toBe(0);
  });

  it('honours an already-aborted signal', async () => {
    const composer = createBeatComposer();
    const controller = new AbortController();
    controller.abort();
    await expect(composer(request('open', ['t1']), { signal: controller.signal }))
      .rejects.toMatchObject({ name: 'AbortError' });
  });

  it('does not throw on an unknown fact; the caller can fall back', () => {
    const scene = request('event', ['x1']);
    scene.scene.facts.push({ id: 'x1', kind: 'future_kind', mandatory: true, visibility: 'scene' });
    expect(() => composeConstrainedBeat(scene)).not.toThrow();
    expect(composeConstrainedBeat(scene).text).toBe('');
  });

  it('keeps ids out of the prose and exposes the mapped beats for evidence', () => {
    const scene = sceneFromBeatRequest(request('move', ['m1', 'm2']));
    expect(scene.beats.length).toBeGreaterThanOrEqual(2);
    const result = composeConstrainedBeat(request('move', ['m1', 'm2']));
    expect(result.text).not.toContain('m1');
    expect(result.text).not.toContain('lu');
    expect(result.text).not.toContain('nono');
  });
});
