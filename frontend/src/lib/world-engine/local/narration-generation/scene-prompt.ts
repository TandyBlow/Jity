/** Whole-scene prompt in the shape the product's deployable instruct model was
 * measured on (lane 08's reference candidate), with the four defects human
 * review found in its accepted prose named in the instructions.
 *
 * Why a separate shape exists at all: lane 01's serializer is the training
 * shape for the fine-tuned checkpoints and it is a *state record*
 * (`【视角】【地点】【人物】【变化】【正文】`). A 1.7B instruct model asked to
 * continue a state record recites it ("精神值43，未完成") and pads the rest
 * with invented connective events. The reference candidate showed that a
 * closed-book turn — scene, required events, who stayed, length — produces
 * fluent scenes on the same weights. This file rebuilds that turn from the
 * same committed packet and adds the rules for the real failures:
 *
 *   - gender / pronoun: the world file has no gender field, so the model
 *     guessed («她» for 路明非). Names or dropped subjects cannot be wrong;
 *   - invented sounds: footstep/rustle details with nothing behind them;
 *   - item misattribution: 诺诺's short gun was written into 路明非's hand;
 *   - repetition: the same closing beat returned every turn.
 *
 * It adds no fact: `projectProseFacts` only re-groups the caller's packet.
 */
import type { CommittedNarration, NarrationFact } from '../../runtime/committed-narration';
import type { TimeAdvance } from '../../types';
import type { BeatSceneContext, NarrationPolicy } from './types';

export interface ProseProjection {
  /** Facts the prose must state (a settled move or a settled task result). */
  required: NarrationFact[];
  /** Standing positions: true already, not an event; may be used, not recited. */
  positions: { name: string; location: string }[];
  /** Changes that belong in behaviour, never as numbers or quoted trait text. */
  hints: string[];
  /** Facts deliberately not required, kept for evidence. */
  withheld: NarrationFact[];
}

const REQUIRED: ReadonlySet<NarrationFact['kind']> = new Set(['moved', 'task_achieved']);
const MOVEMENT_VERBS = /(从|离开|走到|走向|走进|来到|进|到|去)/u;

/** Split the committed packet into required events, standing positions and
 * behaviour hints. Mirrors lane 08's `projectProseFacts` (the measured
 * reference), and keeps the same rule: a passage is never failed for not
 * reciting a number it was told not to write. */
export function projectProseFacts(committed: CommittedNarration): ProseProjection {
  const required: NarrationFact[] = [];
  const positions: { name: string; location: string }[] = [];
  const hints: string[] = [];
  const withheld: NarrationFact[] = [];
  for (const fact of committed.facts) {
    if (REQUIRED.has(fact.kind)) { required.push(fact); continue; }
    withheld.push(fact);
    if (fact.kind === 'at') positions.push({ name: fact.name, location: fact.location });
    else if (fact.kind === 'sanity_changed') {
      hints.push(`${fact.name}的心神变了：${fact.to < fact.from ? '更沉、更紧' : '缓了一些'}。只用动作、呼吸或视线表现，不要写出任何数值。`);
    } else if (fact.kind === 'personality_changed') {
      // The ledger makes a personality change a mandatory fact, and lane 01's
      // corpus requires it to be expressed. Leaving it as an optional hint made
      // the two sides disagree: the prompt said 'hint', the checker said 'omitted'.
      // It stays required, but it must be shown as behaviour, not as a label.
      required.push(fact);
      hints.push(`${fact.name}的性情有了变化（见必述）：${fact.text}。用一句行为或反应让人看出来，不要照抄这句话，也不要写「个性」两个字。`);
    }
  }
  return { required, positions, hints, withheld };
}

/** The system turn. Lane 08's rules, plus one line per defect human review
 * found in texts the automatic grader accepted. */
/** Background is not an event. The first three-arm run wrote a card that
 * spoke, a conditional trait as a present gunshot and a denied hit mark as a
 * shrapnel wound, in all three shapes. These lines name the rule once so the
 * whole-scene, serialized and beat prompts cannot drift apart. */
export const BACKGROUND_RULES = [
  '【背景】里的人物外貌、地点描写、物品状态和性格倾向只是背景：不要把它们变成这一回合的新动作、新声音、新气味或新物件。',
  '说明里写「没有 X」的，正文不要出现 X（例：背心「没有演习弹痕」，就不写被弹片击中的痕迹）。',
  '牌子、纸、告示上的字只是字，不会发出声音、不会说话；人物读过它，不等于它现在在提醒人。',
  '性格倾向要带条件：写「听见枪声会缩肩」不等于这一回合有枪声；没有已结算的触发事件，不要写这个反应，也不要写出触发它的声音。',
  '静物的朝向和开合保持不变（枪口压向地面就不要再抬起，盒盖紧闭就不要推开），除非本回合有对应事实。',
];

export const NARRATOR_SYSTEM_PROMPT = [
  '你是一位中文小说作者，为文字冒险游戏写这一段叙事正文。',
  '只输出正文，不要解释、不要列点、不要标题、不要用「玩家」「系统」这类游戏术语。',
  '正文用第三人称，贴着视角人物写，可以写动作、对话、环境与感受。',
  '必须写到下面列出的每一条已发生事实；不得反转方向、换人物、改数字。',
  '不得新增下面没有的人物、地点、物品、任务、往事或线索；不得替任何角色做出未提交的新行动。',

  '只写下面给出的声音、气味和物件；没有给出的脚步声、枪声、风声、心跳都不要补。',
  '名字是「某人的某物」的东西只属于那个人；不要把它写到别人手里，也不要让视角人物凭空握住或收起别人的东西。',
  '不要写上面没有写过的姿势（蹲下、坐下、靠墙、站起、躺下），也不要给人物换一个更戏剧化的站位；保持上面给出的姿态。',
  '不要把状态逐条念出来：不写「精神值」「任务」「未完成」这些字样，也不要用一句话复述场景说明。',
  '不要写「完成了一项任务」「个性发生了变化」「新增一条待办」这类报告句式，把结果写进动作或对话里。',
  '结尾停在这一刻，不要总结、不要陈词滥调的收束，也不要重复上一回合最后一句。',
  ...BACKGROUND_RULES,
].join('\n');

const UNIT_CN: Record<TimeAdvance['duration']['unit'], string> = {
  second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年',
};
const CN_DIGITS = ['零', '一', '两', '三', '四', '五', '六', '七', '八', '九', '十'];
const cnAmount = (value: number): string =>
  (Number.isInteger(value) && value >= 0 && value <= 10 ? CN_DIGITS[value] : String(value));

/** 「诺诺的短枪」→ 诺诺. Ownership is already visible in the display name, so
 * no second owner table is introduced. */
export function ownerOf(name: string): string | null {
  const match = /^(\S{1,4})的(.+)$/u.exec(name);
  return match ? match[1] : null;
}

function paragraphsOf(policy: NarrationPolicy): { count: number; min: number; max: number } {
  // Lane 01's 71 human short scenes are 61-158 chars and ALL single paragraph
  // (median 97). A 240-char, 2-3 paragraph default asked for a shape the
  // reference style never uses; the extra room is where filler appeared.
  const max = Math.max(60, Math.min(600, Math.round(policy.targetChars ?? 160)));
  const min = Math.max(40, Math.min(max, Math.round(policy.minChars ?? Math.round(max * 0.7))));
  const count = policy.paragraphs ?? (max > 300 ? 2 : 1);
  return { count: Math.max(1, Math.min(3, Math.round(count))), min, max };
}

export interface ProseUserArgs {
  committed: CommittedNarration;
  policy: NarrationPolicy;
  scene?: BeatSceneContext | null;
  /** Last sentence of the previous accepted scene; used only as an anti-repeat
   * hint, never as material to continue. */
  priorTail?: string | null;
  priorOpen?: string | null;
}

/** The user turn: scene, required events, time, standing, hints, length. */
export function renderProseFactsUser(args: ProseUserArgs): string {
  const { policy } = args;
  const scene = args.scene ?? policy.scene ?? null;
  const projected = projectProseFacts(args.committed);
  const view = policy.viewpoint?.name ?? null;
  const present = (scene?.present ?? []).filter((person) => person.name !== view);
  const presentNames = new Set(present.map((person) => person.name));
  const lines: string[] = [];

  if (view) lines.push(`视角人物：${view}。只写${view}看得见、听得见、知道的事。`);
  // Pronoun policy: the world file carries no gender, and a 1.7B model wrote
  // 她 for a male character in prose the grader accepted. `names` avoids that;
  // `model` keeps ordinary Chinese pronouns (53 of lane 01's 71 gold scenes
  // use 他/她), at the cost of that gender risk.
  const pronouns = policy.pronouns ?? 'names';
  if (pronouns === 'names') {
    lines.push('称呼人物时用名字或省略主语，不要用「他」「她」指代人物（这些人物没有给出性别）。');
  } else if (pronouns === 'map') {
    // Gender comes from an explicit map, never from a name. Only listed
    // characters may be referred to by pronoun; the rest keep the safe rule.
    const known = Object.entries(policy.genders ?? {})
      .map(([name, gender]) => `${name}（${gender === 'male' ? '男' : '女'}）`);
    lines.push(known.length
      ? `已知性别：${known.join('、')}。可以用「他」「她」指代这些人；没有列出性别的人仍然只用名字或省略主语。`
      : '称呼人物时用名字或省略主语，不要用「他」「她」指代人物（这些人物没有给出性别）。');
  }
  // Minimal background: one short clause per place/person/object. The real
  // runs used long static notes as material for new events, so the default
  // keeps only what is needed to place the scene; `full` is opt-in.
  const minimal = (policy.backgroundDetail ?? 'minimal') === 'minimal';
  const trimNote = (note: string | undefined, limit: number): string | null => {
    const clean = (note ?? '').replace(/[。.]+$/u, '').trim();
    if (!clean) return null;
    const clause = minimal ? clean.split(/[，,；;]/u)[0] : clean;
    const max = minimal ? Math.min(limit, 30) : limit;
    return clause.length > max ? `${clause.slice(0, max)}…` : clause;
  };
  if (scene?.location) {
    const notes = minimal
      ? [trimNote((scene.placeNotes ?? [])[0], 30)].filter(Boolean).join('')
      : (scene.placeNotes ?? []).slice(0, 2).map((note) => note.trim()).join(' ');
    lines.push(`【地点】${scene.location}${notes ? `：${notes}` : ''}`);
  }
  if (present.length) {
    lines.push('【在场】');
    for (const person of present) {
      const note = trimNote(person.note, 70);
      lines.push(`- ${person.name}${note ? `：${note}` : ''}`);
    }
  }
  const objects = [...(scene?.objects ?? [])].slice(0, 5);
  const inventory = (scene as (BeatSceneContext & { inventory?: { name: string; note?: string }[] }) | null)?.inventory ?? [];
  const held = [...objects, ...inventory].slice(0, 6);
  if (held.length) {
    lines.push('【可见物件与归属】');
    for (const object of held) {
      const owner = ownerOf(object.name);
      const note = object.note?.trim();
      const short = trimNote(object.note, 60);
      lines.push(`- ${object.name}${owner ? `（属于${owner}）` : ''}${short ? `：${short}` : ''}`);
    }
  }

  // A closed list of names is a stronger constraint than a general "do not
  // invent": the model can check each noun against it. Built only from what
  // the caller already licensed, so nothing new is introduced here.
  const allowedNames = [
    ...(view ? [view] : []),
    ...present.map((person) => person.name),
    ...held.map((object) => object.name),
    ...(scene?.location ? [scene.location] : []),
    ...(policy.knownPositions ?? []).map((position) => position.location),
  ].filter(Boolean);
  const uniqueNames = [...new Set(allowedNames)];
  if (uniqueNames.length) {
    lines.push(`【可用名字】这一回合只允许出现这些人和物的名字：${uniqueNames.join('、')}。`);
    lines.push('清单之外的人名、物名、声音、气味都不要写；需要指代时用上面的名字或省略主语。');
  }

  if (projected.required.length) {
    lines.push('这一小段时间里发生的事（必须写进正文，不能添加别的事件）：');
    for (const fact of projected.required) {
      if (fact.kind === 'moved') lines.push(`- ${fact.name}从${fact.from}移动到${fact.to}。`);
      else if (fact.kind === 'task_achieved') lines.push(`- ${fact.name}达成了任务「${fact.goal}」。`);
    }
    if (projected.required.some((fact) => fact.kind === 'moved')) {
      lines.push('移动要用一句明确写出人名和两个地点，不要只用「他走过去」代替。');
    }
    if (projected.required.some((fact) => fact.kind === 'task_achieved')) {
      lines.push('任务完成要让人看得出是这件事办完了，不要写出答案或下一件事。');
    }
  } else {
    lines.push('这一小段时间里没有实体变化：人物留在原地，不要走向、靠近、离开或转向任何地点，也不要写任务达成或新的行动。');
  }

  const time = policy.time ?? null;
  if (time && time.boundary === 'elapsed' && time.duration.amount > 0) {
    const amount = cnAmount(time.duration.amount);
    const unit = UNIT_CN[time.duration.unit];
    lines.push(`本回合经过的时间：${time.duration.amount}${unit}。正文里要明确写出「${amount}${unit}」这句话。`);
  }

  // Standing positions of the people the viewpoint can see. Only the ones in
  // this scene: 09's driver offers the whole roster, and a smaller model
  // recited it ("芬格尔在器材棚，楚子航在钟楼…") instead of writing a scene.
  const visible = [...projected.positions, ...(policy.knownPositions ?? [])];
  const merged: { name: string; location: string }[] = [];
  for (const entry of visible) {
    if (!entry.location) continue;
    if (!merged.some((other) => other.name === entry.name)) merged.push(entry);
  }
  const inScene = merged.filter((entry) => presentNames.has(entry.name) || entry.name === view);
  if (inScene.length) {
    lines.push('此刻的站位（已经如此，不必逐条复述）：');
    for (const entry of inScene) lines.push(`- ${entry.name}在${entry.location}。`);
  }
  const moved = new Set(projected.required.filter((fact) => fact.kind === 'moved').map((fact) => fact.name));
  // Only worth saying when somebody did move: otherwise the "no change"
  // sentence above already covers the whole scene.
  const still = [...presentNames].filter((name) => !moved.has(name));
  if (still.length && moved.size > 0) {
    lines.push(`本回合没有移动的人：${still.join('、')}。${still.length > 1 ? '他们' : '这个人'}留在原地。`);
  }

  if (projected.hints.length) {
    lines.push('另外的变化（用动作或神态表现，不要照抄原句、不要写数字）：');
    for (const hint of projected.hints) lines.push(`- ${hint}`);
  }
  lines.push('除了上面列出的，这一小段时间里没有别的事件：人物位置和物品都保持原样。');

  const { count, min, max } = paragraphsOf(policy);
  lines.push(count === 1
    ? `要求：写成一段，合计 ${min}～${max} 字，直接给正文，不要小标题，不要解释。`
    : `要求：写成 ${count} 段，合计 ${min}～${max} 字，段与段之间空一行，直接给正文，不要小标题，不要解释。`);
  lines.push('用具体的动作、环境和对话推进，不要把上面的清单逐条翻译成句子；场景说明只用来了解环境，不要整句照抄。');
  lines.push('视角人物只拿自己的物品，不要替别人做动作，也不要改变别人手里东西的位置。');
  // The opening is as reusable as the ending: a model that starts every scene
  // the same way reads as a template even when every sentence is true.
  if (args.priorOpen) lines.push(`上一回合的开头是「${args.priorOpen}…」，不要用同样的开头或句式。`);
  if (args.priorTail) lines.push(`上一回合的结尾是「…${args.priorTail}」，不要照抄，也不要重复同样的收尾。`);
  if (policy.instruction?.trim()) lines.push(`补充要求：${policy.instruction.trim()}`);
  return lines.join('\n');
}

/** One prompt string for engines that only take a single user turn. The
 * product page wraps this in its chat template like any other prompt. */
export function renderProseFactsPrompt(args: ProseUserArgs): string {
  return `${NARRATOR_SYSTEM_PROMPT}\n\n${renderProseFactsUser(args)}\n\n正文：`;
}

/** Whether a required fact is actually stated, judged only on content the
 * model could have derived from the required list (no new facts). Used for
 * repair guidance, not as the acceptance verdict (lane 01 owns that). */
export function missingRequired(facts: readonly NarrationFact[], text: string): NarrationFact[] {
  return facts.filter((fact) => {
    if (fact.kind === 'moved') {
      return !(text.includes(fact.name) && text.includes(fact.from) && text.includes(fact.to)
        && MOVEMENT_VERBS.test(text));
    }
    if (fact.kind === 'task_achieved') {
      return !text.includes(fact.goal);
    }
    return false;
  });
}
