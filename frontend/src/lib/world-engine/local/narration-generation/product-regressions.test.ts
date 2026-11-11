/** Public development regressions taken from real product runs.
 *
 * Each case is a sentence or a passage that the product actually produced or
 * accepted, with the settled facts of that turn. The test asserts what the
 * generator must do with it. They are not a quality verdict: 01 still reads the
 * prose. They exist so a fix cannot quietly regress.
 *
 * Sources:
 * - results/product/evidence/09-one-legal-turn-f15d.json (185-character
 *   accepted page text: signboard sound, goggles in hand then empty hands,
 *   invented marks, smell)
 * - results/product/evidence/09-one-legal-turn-21c3.json (fallback that claims a
 *   completed task while the state says pending)
 * - results/quality/free-day-quiet-minute.json (the settled shape of the f15d
 *   turn: one minute, no entity deltas, two people in 西侧服务巷)
 * - results/quality/free-day-move-page.json (a settled move the passage must
 *   write)
 */
import { describe, expect, test } from 'vitest';
import type { CommittedNarration, NarrationFact } from '../../runtime/committed-narration';
import type { CompleteOptions, InferenceEngine } from '../../runtime/engine';
import { contradictionTarget, generateCommittedNarration, stateRepairLines } from './index';
import { resultSemantics, selfPossessiveRepair, selfReferenceRepair, settledViolationsFromScene } from './licensed-sense';
import type { NarrationPolicy } from './types';

type Step = { kind: 'text'; text: string } | { kind: 'throw'; error: Error };

class ScriptedEngine implements InferenceEngine {
  readonly info = { backend: 'scripted', modelId: 'scripted-regression' };
  readonly calls: { prompt: string; options: CompleteOptions }[] = [];
  constructor(private readonly steps: Step[]) {}
  async load(): Promise<void> {}
  async dispose(): Promise<void> {}
  async complete(prompt: string, options: CompleteOptions = {}): Promise<string> {
    const step = this.steps[Math.min(this.calls.length, this.steps.length - 1)];
    this.calls.push({ prompt, options });
    if (step.kind === 'throw') throw step.error;
    options.onProgress?.({ raw: step.text.slice(0, 12), elapsedMs: 1 });
    options.onProgress?.({ raw: step.text, elapsedMs: 2 });
    return step.text;
  }
}

/** The settled facts of 09 f15d point_round_3_1: one minute, nobody moved,
 * nobody finished a task. */
const quietFacts: NarrationFact[] = [
  { id: 'lu:at', actorId: 'lu', name: '路明非', kind: 'at', locationId: 'lane', location: '西侧服务巷' },
  { id: 'nono:at', actorId: 'nono', name: '诺诺', kind: 'at', locationId: 'lane', location: '西侧服务巷' },
];
const quiet: CommittedNarration = {
  anchor: { worldId: 'world_dragon_raja_free_day', pointId: 'point_round_3_1', version: 1, stateDigest: 'digest', previousPointId: 'root' },
  facts: quietFacts,
};

/** The serialized input the page built for that point, trimmed to the lines
 * these regressions depend on. Positions come from the world state. */
const quietInput = [
  '【地点】西侧服务巷：巷口的黄黑绳已放下，进入即算踏入演习区',
  '【人物】路明非：在西侧服务巷，精神值43。诺诺：在西侧服务巷，红发用发圈束在脑后，红色识别带缠在左臂。',
  '【物品】演习规则牌（墙上）：牌面写明 使用弗里嘉演习弹',
  '路明非的护目镜（挂在胸前）：镜片无裂纹',
  '路明非的演习背心（穿在身上）：前襟完好',
  '【变化】时间推进：一分钟。',
].join('\n');

const quietPolicy: NarrationPolicy = {
  mode: 'scene',
  minChars: 20,
  targetChars: 200,
  paragraphs: 1,
  viewpoint: { id: 'lu', name: '路明非' },
  roster: ['路明非', '诺诺'],
  locations: ['西侧服务巷', '中央庭院', '西回廊'],
  knownEntities: ['路明非', '诺诺', '西侧服务巷', '演习规则牌', '路明非的护目镜', '路明非的演习背心'],
  time: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
  requireTime: true,
  scene: {
    location: '西侧服务巷',
    placeNotes: ['巷口的黄黑绳已放下'],
    present: [{ name: '诺诺', note: '红发用发圈束在脑后' }],
    objects: [{ name: '演习规则牌', note: '牌面写明：使用弗里嘉演习弹' }],
  },
  writingContract: false,
};

/** The 185 characters 09 adopted on the real page (f15d). */
const F15D_PASSAGE = '路明非望着远处的钟楼，耳边传来风声拂过巷口的声响。他手中的护目镜微微晃动，镜片上映出诺诺的侧脸，她身上的红痕在阳光下泛着微光。'
  + '诺诺的短枪枪口压向地面，枪身上黄色的演习标记闪烁着。路明非注意到，诺诺的发圈在风中轻轻摆动，红发间夹杂着细小的尘埃。'
  + '空气中弥漫着泥土与金属混合的气味，远处传来演习规则牌的声响，提醒着他们时间已到。一分钟过去，他依旧站在原地，手中没有拿任何东西。';

const issuesOf = async (text: string, steps: Step[] = [{ kind: 'text', text }, { kind: 'text', text }]) => {
  const engine = new ScriptedEngine(steps);
  const result = await generateCommittedNarration({
    engine, committed: quiet, inputText: quietInput, priorText: null, policy: quietPolicy,
  });
  return { result, kinds: result.rawAttempts.flatMap((attempt) => attempt.issues.map((issue) => `${issue.severity}:${issue.kind}`)) };
};

describe('product regressions: the sounds and hands of the f15d turn', () => {
  test('a signboard does not make a sound, and the passage does not pass', async () => {
    const { kinds } = await issuesOf(F15D_PASSAGE);
    expect(kinds).toContain('hard:unlicensed_sense');
  });

  test('the goggles hang on the chest, so a hand on them is an invented action', async () => {
    const { kinds } = await issuesOf('路明非把护目镜拿在手里，镜片上映出巷口的灯。');
    expect(kinds).toContain('hard:unlicensed_action');
  });

  // Caveat: 诺诺's world state does carry «右袖的红痕» in her appearance. The
  // check below only fires when the *input* omits the mark, so this fixture is a
  // missing-brief case, not proof that the f15d page text invented the mark.
  test('a mark on a person that the input never states is an invented appearance', async () => {
    const { kinds } = await issuesOf('诺诺站在巷口，她右袖的红痕在阳光下泛着微光。');
    expect(kinds).toContain('hard:unlicensed_appearance');
  });

  test('a hand that was filled cannot be empty later in the same passage', async () => {
    const { kinds } = await issuesOf('他手中的护目镜微微晃动。一分钟过去，他依旧站在原地，手中没有拿任何东西。');
    expect(kinds).toContain('hard:self_contradiction');
  });

  test('a quiet minute is accepted without a time sentence', async () => {
    const draft = '路明非站在西侧服务巷，看着诺诺用发圈束住红发。他没说话，只是望着巷口。';
    const { result } = await issuesOf(draft, [
      { kind: 'text', text: draft },
      { kind: 'text', text: '一分钟过去。' },
    ]);
    expect(result.text).not.toContain('一分钟过去');
    expect(result.accepted).toBe(true);
  });
});

describe('product regressions: the outcome must be written', () => {
  const moveFact: NarrationFact = {
    id: 'lu:move', actorId: 'lu', name: '路明非', kind: 'moved',
    fromId: 'lane', from: '西侧服务巷', toId: 'yard', to: '中央庭院',
  };
  const movedFacts: NarrationFact[] = [moveFact, quietFacts[1]];

  test('a passage that stays in the alley omits the settled move and is rejected', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '路明非站在西侧服务巷，看着诺诺用发圈束住红发。风从巷口吹过。' },
      { kind: 'text', text: '路明非站在西侧服务巷，看着诺诺用发圈束住红发。风从巷口吹过。' },
    ]);
    const result = await generateCommittedNarration({
      engine, committed: { anchor: quiet.anchor, facts: movedFacts },
      inputText: quietInput, priorText: null, policy: quietPolicy,
    });
    expect(result.rawAttempts[0].issues.some((issue) => issue.kind === 'fact_omitted')).toBe(true);
    expect(result.accepted).toBe(false);
  });

  test('the same input with the move written is accepted', async () => {
    const engine = new ScriptedEngine([
      { kind: 'text', text: '一分钟过去，路明非从西侧服务巷走到中央庭院，脚下慢了半拍。诺诺留在巷口，没有跟上来。' },
    ]);
    const result = await generateCommittedNarration({
      engine, committed: { anchor: quiet.anchor, facts: movedFacts },
      inputText: quietInput, priorText: null, policy: quietPolicy,
    });
    expect(result.accepted).toBe(true);
  });
});

describe('product regressions: the previous ending must not come back', () => {
  const prior = '路明非站在西侧服务巷，风从巷口吹过，黄黑绳轻轻晃动。他把手插进兜里，没有再看诺诺。';

  test('a draft that repeats the previous closing sentence is rejected', async () => {
    const repeated = '诺诺先开了口，声音很轻。他把手插进兜里，没有再看诺诺。';
    const engine = new ScriptedEngine([{ kind: 'text', text: repeated }, { kind: 'text', text: repeated }]);
    const result = await generateCommittedNarration({
      engine, committed: quiet, inputText: quietInput, priorText: prior, policy: quietPolicy,
    });
    const kinds = result.rawAttempts.flatMap((attempt) => attempt.issues.map((issue) => issue.kind));
    expect(kinds).toContain('echo_prior');
  });
});

describe('product regressions: a worn item of a present character', () => {
  // 09 21c3 rejected a model passage for «诺诺的红色识别带» with
  // unprojected_entity, although the band is worn by a character in the scene.
  test('naming a visible object of the scene is background, not a new entity', async () => {
    const policy: NarrationPolicy = {
      ...quietPolicy,
      knownEntities: [...(quietPolicy.knownEntities ?? []), '诺诺的红色识别带'],
      scene: { ...quietPolicy.scene!, objects: [...(quietPolicy.scene?.objects ?? []), { name: '诺诺的红色识别带' }] },
    };
    const text = '诺诺站在巷口，红色识别带缠在左臂，她没有说话。一分钟过去，路明非还站在原地。';
    const engine = new ScriptedEngine([{ kind: 'text', text }]);
    const result = await generateCommittedNarration({
      engine, committed: quiet, inputText: quietInput, priorText: null, policy,
    });
    const hard = result.rawAttempts.flatMap((attempt) => attempt.issues.filter((issue) => issue.severity === 'hard'));
    expect(hard.map((issue) => issue.kind)).not.toContain('unlicensed_entity');
  });
});

describe('product regressions: what counts as a repeated ending', () => {
  const prior = '诺诺站在巷口，红发用发圈束在脑后。路明非把手插进兜里，没有再看诺诺。';

  test('a state sentence repeated in the middle is the same true fact', async () => {
    const text = '红发用发圈束在脑后。诺诺站在巷口，没有动。一分钟过去，风停了。';
    const engine = new ScriptedEngine([{ kind: 'text', text }]);
    const result = await generateCommittedNarration({
      engine, committed: quiet, inputText: quietInput, priorText: prior, policy: quietPolicy,
    });
    const kinds = result.rawAttempts.flatMap((attempt) => attempt.issues.map((issue) => issue.kind));
    expect(kinds).not.toContain('echo_prior');
  });

  test('the previous closing sentence repeated verbatim is an echo', async () => {
    const text = '诺诺先开了口，声音很轻，巷口很静。路明非把手插进兜里，没有再看诺诺。';
    const engine = new ScriptedEngine([{ kind: 'text', text }, { kind: 'text', text }]);
    const result = await generateCommittedNarration({
      engine, committed: quiet, inputText: quietInput, priorText: prior, policy: quietPolicy,
    });
    const kinds = result.rawAttempts.flatMap((attempt) => attempt.issues.map((issue) => issue.kind));
    expect(kinds).toContain('echo_prior');
  });
});

describe('product regressions: an object cannot be in a hand and hanging on the body', () => {
  // 09 e9a5 (page bdac63ec) wrote «她手中的短枪还挂在腰间» inside one sentence.
  test('a gun in the hand and at the waist in one sentence is a contradiction', async () => {
    const text = '诺诺站在不远处，她手中的短枪还挂在腰间，黄色的演习标记在阳光下闪烁。一分钟过去，路明非还站在原地。';
    const engine = new ScriptedEngine([{ kind: 'text', text }, { kind: 'text', text }]);
    const result = await generateCommittedNarration({
      engine, committed: quiet, inputText: quietInput, priorText: null, policy: quietPolicy,
    });
    const hard = result.rawAttempts.flatMap((attempt) => attempt.issues.filter((issue) => issue.severity === 'hard').map((issue) => issue.kind));
    expect(hard).toContain('self_contradiction');
  });
});

describe('product regressions: the batch-3 quiet passage', () => {
  // 09 ran the quiet fixture at 6d4236be and accepted a passage with
  // «她耳后有一道细小的红痕» although the fixture input has no 红痕. Locally the
  // same input and text are rejected, so this pins the local behaviour until
  // the difference in the run is explained.
  test('a mark the fixture input never states is rejected', async () => {
    const text = '路明非站在西侧服务巷，看着诺诺发髻间飘动的红发。她低头整理发圈，手指在发丝间轻轻滑动，仿佛在梳理某种情绪。'
      + '他注意到她耳后有一道细小的红痕，像是被什么轻敲过。诺诺转身时，路明非看见她裙摆扫过地面，带起一阵微凉的风。'
      + '他没说话，只是静静地看着她，心里浮起一丝疑惑。一分钟过去，他依旧站在原处，目光落在那张路线图上，眼神却落在诺诺身上，仿佛在等待什么。';
    const { kinds } = await issuesOf(text);
    expect(kinds).toContain('hard:unlicensed_appearance');
  });
});

describe('product regressions: a mark that belongs to another character', () => {
  // 09 95dc auto point: 诺诺's «右袖的红痕» was on the viewpoint's sleeve.
  test('a borrowed mark is a soft note, not a rejection', async () => {
    const policy: NarrationPolicy = {
      ...quietPolicy,
      knownEntities: [...(quietPolicy.knownEntities ?? []), '红痕'],
    };
    const input = `${quietInput}\n诺诺：右袖的红痕是扶过石墙时蹭上的。`;
    const text = '路明非站在西侧服务巷，低头看见袖口的红痕。一分钟过去，他没有动。';
    const engine = new ScriptedEngine([{ kind: 'text', text }]);
    const result = await generateCommittedNarration({
      engine, committed: quiet, inputText: input, priorText: null, policy,
    });
    const issues = result.rawAttempts.flatMap((attempt) => attempt.issues);
    expect(issues.some((issue) => issue.kind === 'unlicensed_appearance' && issue.severity === 'hard')).toBe(false);
    expect(issues.some((issue) => issue.severity === 'soft' && /belongs to another character/u.test(issue.detail ?? ''))).toBe(true);
  });
});

describe('product regressions: a wall prop in a hand', () => {
  // 09 batch-5 move scene: «演习规则牌在他手中，牌面写着…» while the fixture puts
  // the board on the wall.
  test('a scene prop in a hand is a soft note', async () => {
    const text = '路明非站在中央庭院，看着巷口的黄黑绳。他镜片无裂纹，确认它还在。演习规则牌在他手中，牌面写着「使用弗里嘉演习弹」。一分钟过去，他没有动。';
    const engine = new ScriptedEngine([{ kind: 'text', text }]);
    // The move fixture's input names the board without a place, like the page.
    const input = quietInput.replace('演习规则牌（墙上）', '演习规则牌');
    const result = await generateCommittedNarration({
      engine, committed: quiet, inputText: input, priorText: null, policy: quietPolicy,
    });
    const issues = result.rawAttempts.flatMap((attempt) => attempt.issues);
    expect(issues.some((issue) => /scene prop 演习规则牌 appears in a hand/u.test(issue.detail ?? ''))).toBe(true);
  });
});

describe('product regressions: a settled task the draft never says', () => {
  // 09 dense point: move and two minutes written, the finished task omitted in
  // both attempts, so the whole turn fell back to program text.
  test('one sentence about the outcome is appended instead of failing', async () => {
    const taskFact: NarrationFact = {
      id: 'lu:task', actorId: 'lu', name: '路明非', kind: 'task_achieved',
      taskId: 'task_books', goal: '把三份互相矛盾的登记簿比对完',
    };
    const movedFact: NarrationFact = {
      id: 'lu:position', actorId: 'lu', name: '路明非', kind: 'moved',
      fromId: 'lane', from: '西侧服务巷', toId: 'courtyard', to: '中央庭院',
    };
    const body = '路明非从西侧服务巷走到中央庭院。两分钟过去，他站在石阶上。';
    const engine = new ScriptedEngine([
      { kind: 'text', text: body },
      { kind: 'text', text: body },
      { kind: 'text', text: '登记簿比对完了。' },
    ]);
    const result = await generateCommittedNarration({
      engine, committed: { anchor: quiet.anchor, facts: [movedFact, taskFact] },
      inputText: quietInput.replace('演习规则牌（墙上）', '演习规则牌'),
      priorText: null,
      policy: {
        ...quietPolicy, targetChars: 40, minChars: 10,
        time: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } },
      },
    });
    expect(result.accepted).toBe(true);
    expect(result.text).toContain('登记簿比对完了');
    expect(result.assembly.appendedSentences).toContain('登记簿比对完了。');
  });
});

describe('product regressions: no state checklist in prose', () => {
  // The dense point was accepted at 127 chars only because the projector's own
  // sentence «路明非完成了任务「比对三份互相矛盾的登记簿」。» was appended. The
  // product must not read as a checklist, so that fallback is gone: a model that
  // cannot say the outcome leaves the draft rejected.
  test('the projector sentence is not appended when the model says nothing', async () => {
    const taskFact: NarrationFact = {
      id: 'lu:task', actorId: 'lu', name: '路明非', kind: 'task_achieved',
      taskId: 'task_books', goal: '把三份互相矛盾的登记簿比对完',
    };
    const movedFact: NarrationFact = {
      id: 'lu:position', actorId: 'lu', name: '路明非', kind: 'moved',
      fromId: 'lane', from: '西侧服务巷', toId: 'courtyard', to: '中央庭院',
    };
    const body = '路明非从西侧服务巷走到中央庭院。两分钟过去，他站在石阶上。';
    const engine = new ScriptedEngine([
      { kind: 'text', text: body }, { kind: 'text', text: body }, { kind: 'text', text: '' },
    ]);
    const result = await generateCommittedNarration({
      engine, committed: { anchor: quiet.anchor, facts: [movedFact, taskFact] },
      inputText: quietInput.replace('演习规则牌（墙上）', '演习规则牌'),
      priorText: null,
      policy: {
        ...quietPolicy, targetChars: 40, minChars: 10,
        time: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } },
      },
    });
    expect(result.accepted).toBe(false);
    expect(result.text).not.toContain('完成了任务');
  });
});

describe('product regressions: nobody-seen filler', () => {
  // 09 e9a5/95dc and the dense point all pad with «他没看到任何人，也没听见任何声音».
  test('saying nobody was seen while someone is present is a contradiction', async () => {
    const text = '路明非站在西侧服务巷。他没看到任何人，也没听见任何声音。一分钟过去，他没有动。';
    const { kinds } = await issuesOf(text);
    expect(kinds).toContain('hard:self_contradiction');
  });

  test('the same sentence is only a note in an empty courtyard', async () => {
    const text = '路明非站在中央庭院。他没看到任何人，也没听见任何声音。两分钟过去，他没有动。';
    const engine = new ScriptedEngine([{ kind: 'text', text }, { kind: 'text', text }]);
    const result = await generateCommittedNarration({
      engine, committed: quiet,
      inputText: quietInput.replace('演习规则牌（墙上）', '演习规则牌'),
      priorText: null,
      policy: {
        ...quietPolicy, targetChars: 40, minChars: 10,
        time: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } },
        scene: { ...quietPolicy.scene!, present: [], location: '中央庭院' },
      },
    });
    const hard = result.rawAttempts.flatMap((attempt) => attempt.issues.filter((issue) => issue.severity === 'hard'));
    expect(hard.map((issue) => issue.kind)).not.toContain('self_contradiction');
  });
});

describe('product regressions: a scene note read out loud', () => {
  // quiet-minute-5: «上面画着庭院、东西回廊、跨溪小桥» is the map note verbatim.
  test('copying a scene object note is a soft note', async () => {
    const text = '路明非站在西侧服务巷，看了一眼墙上的演习规则牌。牌面写明：使用弗里嘉演习弹。一分钟过去，他没有动。';
    const engine = new ScriptedEngine([{ kind: 'text', text }]);
    const result = await generateCommittedNarration({
      engine, committed: quiet, inputText: quietInput, priorText: null, policy: quietPolicy,
    });
    const issues = result.rawAttempts.flatMap((attempt) => attempt.issues);
    expect(issues.some((issue) => /reads out the note of/u.test(issue.detail ?? ''))).toBe(true);
  });
});

describe('product regressions: heard water, heard nothing', () => {
  // The exact accepted text of results/02-narration/real-qwen3-dense-point-4.json
  // (dense fixture: move + finished task + two minutes). «听着远处传来轻微的水声»
  // and «也没有听到任何声音» are in the same paragraph.
  const DENSE_ACCEPTED = '路明非站在中央庭院的石阶上，护目镜挂在胸前，镜片映出他紧绷的神情。'
    + '西侧服务巷的风穿过他肩头，带着一丝潮湿的凉意。他低头看了看手中的登记簿，指尖轻轻摩挲着纸页边缘。'
    + '两分钟过去，他没有移动，只是静静站在原地，听着远处传来轻微的水声。'
    + '他没有看到任何人，也没有听到任何声音，只是静静地注视着脚下那块被雨水打湿的青石。'
    + '路明非比对完了登记簿。';

  test('the accepted dense text is rejected for the hearing contradiction', async () => {
    const { kinds } = await issuesOf(DENSE_ACCEPTED);
    expect(kinds).toContain('hard:self_contradiction');
  });

  test('the repair targets the silent sentence, not the heard water', () => {
    const target = contradictionTarget(DENSE_ACCEPTED);
    expect(target).not.toBeNull();
    expect(target!.sentence).toContain('没有听到任何声音');
    expect(target!.lines.join(String.fromCharCode(10))).toContain('去掉「没有听到任何声音」');
    expect(target!.lines.join(String.fromCharCode(10))).toContain('听着远处传来轻微的水声');
  });
});

describe('product regressions: a repeated closing line', () => {
  // 09 d101/415c: the trained candidate was rejected for echo_prior and the page
  // fell back, although scene mode can trim the repeated closing line.
  const prior = '诺诺站在巷口，红发用发圈束在脑后。路明非把手插进兜里，没有再看诺诺。';

  test('the repeated closing line is trimmed, not turned into a rejection', async () => {
    const text = '路明非站在西侧服务巷，风从巷口吹过。一分钟过去，他没有动。路明非把手插进兜里，没有再看诺诺。';
    const engine = new ScriptedEngine([{ kind: 'text', text }]);
    const result = await generateCommittedNarration({
      engine, committed: quiet, inputText: quietInput, priorText: prior, policy: quietPolicy,
    });
    expect(result.accepted).toBe(true);
    expect(result.assembly.droppedSentences).toContain('路明非把手插进兜里，没有再看诺诺。');
    expect(result.text).not.toContain('没有再看诺诺');
  });
});

describe('product regressions: the rope that is already down', () => {
  // 09 f15d/e9a5 opened with «路明非站在西侧服务巷口，看着黄黑绳缓缓放下» while
  // the input says «巷口的黄黑绳已放下».
  test('re-enacting a state the input gives as already true is an action', async () => {
    const { kinds } = await issuesOf('路明非站在西侧服务巷口，看着黄黑绳缓缓放下。一分钟过去，他没有动。');
    expect(kinds).toContain('hard:unlicensed_action');
  });

  test('restating the same state is not an action', async () => {
    const { kinds } = await issuesOf('路明非站在西侧服务巷口，黄黑绳已放下。一分钟过去，他没有动。');
    expect(kinds).not.toContain('hard:unlicensed_action');
  });
});

describe('product regressions: repair wording for a re-enacted state', () => {
  test('the repair asks for a state, not for deleting the object', () => {
    const target = stateRepairLines({ sentence: '路明非站在西侧服务巷口，看着黄黑绳缓缓放下', word: '放下', object: '黄黑绳' });
    expect(target).not.toBeNull();
    expect(target!.lines.join(String.fromCharCode(10))).toContain('当成早就如此的状态来写');
    expect(target!.sentence).toContain('缓缓放下');
  });
});

describe('product regressions: the player action the state has no row for', () => {
  // 09 d101: the player walked into the lane and read the sign. Neither is a
  // state delta, so the projector's facts cannot carry it; the trained
  // candidate was never told, and only the legacy writer (which gets action
  // text) wrote it.
  test('the scene prompt names the declared action in third person', async () => {
    const engine = new ScriptedEngine([{ kind: 'text', text: '路明非沿着服务巷往里走，看清了墙上的演习规则牌。一分钟过去，他没有动。' }]);
    await generateCommittedNarration({
      engine, committed: quiet, inputText: quietInput, priorText: null,
      policy: {
        ...quietPolicy, promptShape: 'prose-facts',
        scene: { ...quietPolicy.scene!, previousAction: '我沿着服务巷往里走，先看清墙上的演习规则牌。' },
      },
    });
    const prompt = engine.calls[0].prompt;
    expect(prompt).toContain('【玩家这一回合的指令】路明非沿着服务巷往里走，先看清墙上的演习规则牌。');
    expect(prompt).toContain('结果只按上面已结算的事实写，没有结算成功的事不要写成成功');
  });
});

describe('product regressions: the declared action is missing from the prose', () => {
  test('a passage that only describes scenery is noted', async () => {
    const engine = new ScriptedEngine([{ kind: 'text', text: '风从巷口吹过，黄黑绳轻轻晃动。一分钟过去，他没有动。' }]);
    const result = await generateCommittedNarration({
      engine, committed: quiet, inputText: quietInput, priorText: null,
      policy: {
        ...quietPolicy, promptShape: 'prose-facts',
        scene: { ...quietPolicy.scene!, previousAction: '我沿着服务巷往里走，先看清墙上的演习规则牌。' },
      },
    });
    const notes = result.rawAttempts.flatMap((attempt) => attempt.issues);
    expect(notes.some((issue) => /declared action is not written/u.test(issue.detail ?? ''))).toBe(true);
  });

  test('a passage that writes the walk and the board is not noted', async () => {
    const engine = new ScriptedEngine([{ kind: 'text', text: '路明非沿着服务巷往里走，看清了墙上的演习规则牌。一分钟过去，他没有动。' }]);
    const result = await generateCommittedNarration({
      engine, committed: quiet, inputText: quietInput, priorText: null,
      policy: {
        ...quietPolicy, promptShape: 'prose-facts',
        scene: { ...quietPolicy.scene!, previousAction: '我沿着服务巷往里走，先看清墙上的演习规则牌。' },
      },
    });
    const notes = result.rawAttempts.flatMap((attempt) => attempt.issues);
    expect(notes.some((issue) => /declared action is not written/u.test(issue.detail ?? ''))).toBe(false);
  });
});

describe('product regressions: one writing contract in prose-facts', () => {
  // quiet-minute-6's attempts[0].prompt carried the scene contract (micro-actions,
  // dialogue, feelings allowed) and then a second contract that forbade unstated
  // postures, asked for «约200字，写成一段» after a different paragraph count, and
  // repeated the pronoun and background rules.
  test('composed prompt has the scene contract only', async () => {
    const engine = new ScriptedEngine([{ kind: 'text', text: '路明非站在西侧服务巷。一分钟过去，他没有动。' }]);
    await generateCommittedNarration({
      engine, committed: quiet, inputText: quietInput, priorText: null,
      policy: { ...quietPolicy, promptShape: 'prose-facts' },
    });
    const prompt = engine.calls[0].prompt;
    expect(prompt).toContain('细微动作、神态、对话、环境氛围都可以写');
    expect(prompt).not.toContain('【写法】');
    expect(prompt).not.toContain('不要写上面没有给出的姿势');
    // The pronoun rule appears once, not twice.
    const pronoun = prompt.match(/称呼人物时用名字或省略主语/gu) ?? [];
    expect(pronoun).toHaveLength(1);
  });

  test('the serialized shape still gets the writing contract', async () => {
    const engine = new ScriptedEngine([{ kind: 'text', text: '路明非站在西侧服务巷。一分钟过去，他没有动。' }]);
    await generateCommittedNarration({
      engine, committed: quiet, inputText: `${quietInput}
【正文】`, priorText: null,
      policy: { ...quietPolicy, writingContract: true },
    });
    expect(engine.calls[0].prompt).toContain('【写法】');
  });
});

describe('product regressions: the 2026-11-10 route batch (01 review)', () => {
  test("another person's settled hair colour is not the viewpoint's", async () => {
    const { kinds } = await issuesOf('路明非站在西侧服务巷，红发在风中晃动。一分钟过去。');
    expect(kinds).toContain('hard:self_contradiction');
  });

  test('the settled tied hair is not rewritten as loose', async () => {
    const { kinds } = await issuesOf('诺诺蹲在墙角，发圈垂落，红发轻垂。一分钟过去。');
    expect(kinds).toContain('hard:self_contradiction');
  });

  test('goggles settled on the chest are not worn over the eyes', async () => {
    const { kinds } = await issuesOf('路明非低头，镜片后的眼睛微微发亮。一分钟过去。');
    expect(kinds).toContain('hard:self_contradiction');
  });

  test('the same elapsed time in Chinese and Arabic is a duplicate', async () => {
    const { kinds } = await issuesOf('一分钟过去，他翻完登记簿。1分钟过去，他站在原地。');
    expect(kinds).toContain('hard:time_duplicate');
  });

  test('a Chinese-only duration is not a duplicate', async () => {
    const { kinds } = await issuesOf('一分钟过去，他翻完登记簿。他站在原地。');
    expect(kinds).not.toContain('hard:time_duplicate');
  });
});

describe('product regressions: the per-beat packet carries the same settled lines', () => {
  // 09-constrained-beats-11a7 accepted these two model beat sentences. The
  // scene path rejects them from the serialized input; the beat path had no
  // comparison at all. The adapter builds the settled text from the packet.
  const packet = {
    inputText: null,
    place: { name: '西侧服务巷', note: '巷口的黄黑绳已放下，进入即算踏入演习区。右墙贴着赛区图。' },
    present: [
      { name: '路明非', note: '护目镜挂在胸前，右手还空着。' },
      { name: '诺诺', note: '红发用发圈束在脑后，红色识别带缠在左臂。' },
    ],
    objects: [{ name: '演习规则牌', note: '牌面写明：使用弗里嘉演习弹。' }],
    inventory: [{ name: '路明非的护目镜', note: '镜片无裂纹，镜带松着，现挂在胸前而非戴在眼前。' }],
    viewpoint: { name: '路明非', note: '护目镜挂在胸前' },
  };

  test('the tied hair written loose is caught from the packet notes', () => {
    const found = settledViolationsFromScene('诺诺红发垂落，红色识别带缠在左臂。', packet);
    expect(found.some((violation) => /hair is tied/u.test(violation.detail))).toBe(true);
  });

  test('goggles fogged while settled on the chest are caught from the packet', () => {
    const found = settledViolationsFromScene('路明非的护目镜泛着雾气，演习规则牌在器材棚门口晃动。', packet);
    expect(found.some((violation) => /goggles hang on the chest/u.test(violation.detail))).toBe(true);
  });

  test('a correct beat sentence has no settled violation', () => {
    const found = settledViolationsFromScene('一分钟过去，路明非还站在西侧服务巷。', packet);
    expect(found).toHaveLength(0);
  });
});

describe('product regressions: the quiet-90 run', () => {
  // results/02-narration/real-qwen3-quiet-90.json, accepted at 77 chars:
  // «远处传来演习规则牌的嗡鸣» (a wall sign makes a sound) and
  // «他望着路明非的演习背心» (the viewpoint's own name as if another person).
  test('a wall sign that hums is an invented sound', async () => {
    const { kinds } = await issuesOf('一分钟过去，远处传来演习规则牌的嗡鸣。');
    expect(kinds).toContain('hard:unlicensed_sense');
  });

  test("the viewpoint's own name after 他 is rewritten to 自己的", async () => {
    const text = '一分钟过去，他望着路明非的演习背心，心里泛起一丝不安。';
    const repaired = selfReferenceRepair(text, '路明非');
    expect(repaired.text).toContain('他望着自己的演习背心');
    expect(repaired.repaired.length).toBe(1);
  });

  test('自己+物品 without 的 is repaired, not rejected', () => {
    const repaired = selfPossessiveRepair('他低头看着自己护目镜，镜片依旧清晰。', ['路明非的护目镜']);
    expect(repaired.text).toContain('自己的护目镜');
  });

  test('ordinary 自己 uses are untouched', () => {
    for (const sentence of ['她把答案攥在自己手里。', '他听见自己的呼吸越来越浅。', '诺诺先护住人，再自己探头。']) {
      const repaired = selfReferenceRepair(selfPossessiveRepair(sentence, ['路明非的护目镜']).text, '诺诺');
      expect(repaired.text).toBe(sentence);
      expect(repaired.repaired).toHaveLength(0);
    }
  });
});

describe('product regressions: 926e model beats', () => {
  // Close beat «路明非摘下护目镜，目光落在规则牌上»: the goggles are settled on
  // the chest and no fact changes that. Taking them off is a world change.
  test('taking off a settled item is an invented action', async () => {
    const { kinds } = await issuesOf('路明非摘下护目镜，目光落在规则牌上。');
    expect(kinds).toContain('hard:unlicensed_action');
  });

  test('pushing an object on the desk stays a micro-action', async () => {
    const { kinds } = await issuesOf('他把裁纸刀推到桌边，又推回来。');
    expect(kinds).not.toContain('hard:unlicensed_action');
  });

  // Scene beat «路明非低头检查护目镜边缘的雾气»: lenses fog only when worn.
  test('fog on the edge of chest-hung goggles is worn-goggles wording', async () => {
    const { kinds } = await issuesOf('路明非低头检查护目镜边缘的雾气。');
    expect(kinds).toContain('hard:self_contradiction');
  });
});

describe('product regressions: result semantics accept paraphrase, reject flips', () => {
  // NARRATION-BOUNDARY-20261111: a result is rewritten, not quoted. The bindings
  // are fixed (actor, target, direction); wording is free.
  const names = ['路明非', '诺诺', '登记簿'];

  test('a dropped negation is rejected (known miss)', () => {
    const check = resultSemantics('路明非比对完了登记簿，三处差额都对上了。',
      '路明非比对了登记簿，登记簿上的三处差额对不上。', undefined, names);
    expect(check.ok).toBe(false);
    expect(check.detail).toMatch(/claims it was completed/u);
  });

  test('a synonym rewrite of a completed result passes', () => {
    const check = resultSemantics('路明非站在原地，翻完登记簿，把差额记下。',
      '路明非比对了登记簿，三处差额对上了。', undefined, names);
    expect(check.ok).toBe(true);
    expect(check.unverified).toBeFalsy();
  });

  test('a failure kept with a micro-action passes', () => {
    const check = resultSemantics('诺诺拦在门口，路明非没能进去。',
      '路明非走到门口，被诺诺拦住，进不去。', undefined, names);
    expect(check.ok).toBe(true);
  });

  test('a reversed result is rejected', () => {
    const check = resultSemantics('路明非走到门口，被诺诺拦住。',
      '路明非比对了登记簿，三处差额对上了。', undefined, names);
    expect(check.ok).toBe(false);
  });

  test('structured outcome decides the direction and the target must appear', () => {
    const ok = resultSemantics('路明非把登记簿合上，没找到那处差额。', '对差额',
      { actor: '路明非', target: '登记簿', outcome: 'not_achieved' }, names);
    expect(ok.ok).toBe(true);
    const missingTarget = resultSemantics('路明非没找到那处差额。', '对差额',
      { actor: '路明非', target: '登记簿', outcome: 'not_achieved' }, names);
    expect(missingTarget.ok).toBe(false);
    expect(missingTarget.detail).toMatch(/登记簿/u);
  });

  test('undecidable free text is marked for review, not passed silently', () => {
    const check = resultSemantics('路明非站着。', '场面安静。', undefined, names);
    expect(check.ok).toBe(true);
    expect(check.unverified).toBe(true);
  });
});
