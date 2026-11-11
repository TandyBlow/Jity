/** Unlicensed sense nouns: a sound or smell the settled input never mentions.
 *
 * The real runs kept inventing wind, footsteps, gunshots and the smell of
 * exercise rounds in texts that passed the automatic gate. Prompt rules did not
 * stop it on a 1.7B model. This module is generation-side: it names the
 * offending sentence so the caller can ask for ONE bounded rewrite, and it lets
 * the caller reject the draft when the rewrite still invents a sense.
 *
 * It is deliberately narrow:
 * - a fixed noun list of sounds/smells, not a general "claim word" filter;
 * - a noun is licensed when the same noun appears in the serialized input, or
 *   when a licensed source (an entity named in the input) appears in the same
 *   sentence («除湿机的声音» is fine when the input mentions 除湿机);
 * - it does not judge actions, dialogue, posture or style.
 */
/** Sounds and smells that imply a specific event. The 71 reference scenes do
 * add ambient wind, light and generic smells on their own (3 rows invent wind,
 * 1 light, 7 a generic 声音), so those are not defects. What the human scenes
 * never do is assert an event-sound or a gore/explosion smell the input does
 * not have: a gunshot, footsteps, a bell, blood, cordite. Those are the ones
 * this list keeps. */
export const EVENT_SENSE_NOUNS = [
  // Only what implies a bodily event that did not happen: a shot, someone
  // moving, cordite, blood. Bell, echo, drip and generic friction are ambient
  // sound, like wind; two real drafts were failed for a distant bell, which
  // changes no world fact.
  '枪声', '脚步声', '硝烟', '血腥味',
] as const;

/** Ambient senses: allowed as style, reported only as a soft observation. */
export const AMBIENT_SENSE_NOUNS = [
  '风声', '风中', '风里', '风', '阳光', '月光', '灯光', '光',
  '气味', '香味', '木香', '臭味',
] as const;

export const APPEARANCE_MARK_NOUNS = [
  '红痕', '疤痕', '伤口', '淤青', '口红', '纹身', '血迹', '眼影', '胭脂', '唇印', '粉',
] as const;

/** A visible mark on a person that the input never states. The page's accepted
 * quiet turn wrote «她耳后有淡淡的粉»; an earlier one wrote «她身上的红痕».
 * In the 71 reference scenes every mark that appears («演习弹红痕») is also in
 * the input, so requiring the input gives 0 false positives there. */
export interface AppearanceViolation extends SenseViolation {
  /** The mark exists in the input but next to another person's name. */
  borrowed?: boolean;
}

/** The name closest to any occurrence of `noun`, with its distance. */
function nearestName(value: string, noun: string, names: readonly string[]): { name: string; distance: number } | null {
  let best: { name: string; distance: number } | null = null;
  for (const name of names) {
    if (name.length < 2) continue;
    let from = 0;
    for (;;) {
      const at = value.indexOf(noun, from);
      if (at < 0) break;
      const nameAt = value.lastIndexOf(name, at);
      const after = value.indexOf(name, at + noun.length);
      const distance = Math.min(
        nameAt < 0 ? Number.POSITIVE_INFINITY : at - nameAt,
        after < 0 ? Number.POSITIVE_INFINITY : after - at,
      );
      if (distance < (best?.distance ?? Number.POSITIVE_INFINITY)) best = { name, distance };
      from = at + noun.length;
    }
  }
  return best && best.distance <= 24 ? best : null;
}

/** A visible mark on a person that the input never states. The page's accepted
 * quiet turn wrote «她耳后有淡淡的粉»; an earlier one wrote «她身上的红痕».
 * In the 71 reference scenes every mark that appears («演习弹红痕») is also in
 * the input, so requiring the input gives 0 false positives there.
 *
 * 09 95dc then showed the second form: 诺诺's state carries «右袖的红痕», the
 * passage moved the mark onto the viewpoint («他伸手拂去袖口的红痕»). An
 * input-level check cannot see that, so `names` lets the caller pass the
 * roster: a mark stated only next to another name is `borrowed`, which the
 * caller treats as a soft note rather than a rejection. */
export function appearanceViolations(text: string, inputText: string, names: readonly string[] = []): AppearanceViolation[] {
  const found: AppearanceViolation[] = [];
  for (const sentence of sentencesOf(text)) {
    for (const noun of APPEARANCE_MARK_NOUNS) {
      if (!sentence.includes(noun)) continue;
      // «粉» is also a colour word and a common noun (粉笔灰, 花粉); only the
      // applied-to-a-person sense is a mark.
      if (noun === '粉' && !/(耳后|脸上|颊|腮|唇|眉|妆)/u.test(sentence)) continue;
      if (!inputText.includes(noun)) {
        found.push({ sentence, noun });
        continue;
      }
      if (!names.length) continue;
      const here = nearestName(sentence, noun, names);
      const there = nearestName(inputText, noun, names);
      if (here && there && here.name !== there.name) {
        found.push({ sentence, noun, borrowed: true });
      }
    }
  }
  return found;
}

export interface SenseViolation {
  sentence: string;
  noun: string;
}

const sentencesOf = (text: string): string[] =>
  text.split(/[。！？\n]+/gu).map((part) => part.trim()).filter(Boolean);

/** Words that appear in the serialized input and can therefore source a sound.
 * Kept as whole tokens: a substring match would license everything. */
function licensedSources(inputText: string): string[] {
  const names = new Set<string>();
  for (const match of inputText.matchAll(/[\u4e00-\u9fff]{2,6}/gu)) names.add(match[0]);
  return [...names];
}

/** Verbs that make a thing a speaker: something is heard, or it tells someone
 * something. A sign or a sheet of paper in a scene is not a speaker. */
const SPEAKING_VERBS = /(传来|响起|发出|飘来|回荡|作响|响了|响着|提醒|告诉|说道|喊道)/u;
// 嗡鸣/轰鸣 are sounds too; 11a7-class runs made a wall sign «传来…的嗡鸣».
const SOUND_NOUNS = /(声|响|动静|鸣)/u;

export interface SenseOptions {
  /** People with a committed move this point. Their own footsteps are a
   * consequence of the settled movement, not an invented sound. */
  movedNames?: readonly string[];
  /** Things in the scene that cannot speak: signs, papers, boards, ropes,
   * maps, weapons lying there. A real page run wrote «演习规则牌的声响…
   * 提醒着他们时间已到», which is an event the state does not have. */
  staticNames?: readonly string[];
}

export function senseViolations(text: string, inputText: string, options: SenseOptions = {}): SenseViolation[] {
  const found: SenseViolation[] = [];
  const sources = licensedSources(inputText);
  for (const sentence of sentencesOf(text)) {
    for (const noun of EVENT_SENSE_NOUNS) {
      if (!sentence.includes(noun)) continue;
      // The noun itself is in the input (e.g. the notes mention 声音).
      if (inputText.includes(noun)) continue;
      // A licensed source that the input itself says is making a noise:
      // «除湿机一直响着» licenses «除湿机的声音», but a name merely standing in
      // the same sentence does not (that loophole let «风» through when 诺诺
      // happened to be named in it).
      const sourced = sources.some((source) => {
        if (source.length < 2 || !sentence.includes(source)) return false;
        const at = inputText.indexOf(source);
        if (at < 0) return false;
        const near = inputText.slice(Math.max(0, at - 20), at + source.length + 20);
        return /响|嗡|鸣|滴|沙沙|吱|呼呼/u.test(near);
      });
      if (sourced) continue;
      // A committed move licenses that person's own footsteps.
      // Any committed move in this point makes footsteps a consequence of the
      // settled action rather than an invented sound; a quiet point has none.
      if (noun === '脚步声' && (options.movedNames ?? []).length > 0) continue;
      found.push({ sentence, noun });
    }
  }
  // A static thing as the speaker of a sound or a message.
  for (const sentence of sentencesOf(text)) {
    if (!SPEAKING_VERBS.test(sentence)) continue;
    for (const name of options.staticNames ?? []) {
      if (name.length < 2 || !sentence.includes(name)) continue;
      // The thing is named in a sentence that reports a sound or a message:
      // «传来…的声响», «…提醒着他们». Word order varies («远处传来演习规则牌
      // 的声响»), so the name only has to be in the same sentence as the verb.
      if (!SPEAKING_VERBS.test(sentence)) continue;
      if (!SOUND_NOUNS.test(sentence) && !/(提醒|告诉|说道|喊道)/u.test(sentence)) continue;
      // The input itself says this thing makes a noise (a radio, a machine):
      // then it is not a static prop for this sentence.
      const at = inputText.indexOf(name);
      const near = at < 0 ? '' : inputText.slice(Math.max(0, at - 20), at + name.length + 20);
      if (/响|嗡|鸣|滴|沙沙|吱|呼呼|播放|广播/u.test(near)) continue;
      found.push({ sentence, noun: name });
    }
  }
  return found;
}

/** Attributes that belong to one settled person, and settled looks that the
 * prose must not re-describe as another state. 01's independent review of the
 * 2026-11-10 prompt-route batch found three recurring classes in text the
 * automatic verifier accepted:
 *   - «路明非站在西侧服务巷，红发在风中晃动» (红发 is 诺诺's settled look)
 *   - «诺诺蹲在墙角，发圈垂落» (settled: 红发用发圈束在脑后)
 *   - «镜片后的眼睛微微发亮» (goggles settled 挂在胸前, not worn)
 * Each is a binding error against the serialized input, not a style opinion. */
export interface SettledViolation {
  sentence: string;
  detail: string;
}

const HAIR_COLOR_NOUNS = ['红发', '银发', '金发', '白发'] as const;

export function settledAppearanceViolations(
  text: string, inputText: string, names: readonly string[] = [],
  inventory: readonly { name: string; note?: string }[] = [],
): SettledViolation[] {
  const found: SettledViolation[] = [];
  // Some settled lines live in the scene packet, not the serialized input
  // (09 dense: «路明非的护目镜：挂在胸前» only in scene.inventory).
  const settledText = [inputText, ...inventory.map((item) => `${item.name}：${item.note ?? ''}`)].join(String.fromCharCode(10));
  const inputLines = settledText.split(new RegExp('\r?\n', 'u'));
  const ownerOf = (noun: string): string | null => {
    let best: { name: string; distance: number } | null = null;
    for (const line of inputLines) {
      if (!line.includes(noun)) continue;
      const here = nearestName(line, noun, names);
      if (here && here.distance < (best?.distance ?? Number.POSITIVE_INFINITY)) best = here;
    }
    return best?.name ?? null;
  };
  for (const sentence of sentencesOf(text)) {
    for (const noun of HAIR_COLOR_NOUNS) {
      if (!sentence.includes(noun)) continue;
      const owner = ownerOf(noun);
      if (!owner) continue;
      const here = nearestName(sentence, noun, names);
      if (here && here.name !== owner) {
        found.push({ sentence, detail: `${noun} belongs to ${owner}, not ${here.name}` });
      }
    }
    // The settled hair is tied: rewriting it loose changes how the person looks.
    if (settledText.includes('束在脑后')) {
      const loose = /(发圈|红发|发丝|长发)[^。！？]{0,6}(垂落|垂下|轻垂|散开|披散)/u.exec(sentence);
      if (loose) found.push({ sentence, detail: `the settled hair is tied (${loose[0]})` });
    }
    // Goggles settled on the chest are not worn over the eyes.
    const chest = new RegExp('(挂在胸前|胸前挂着|胸前[^\\n]{0,6}护目镜|护目镜[^\\n]{0,6}胸前)', 'u').test(settledText);
    if (chest && settledText.includes('护目镜')) {
      // «护目镜泛着雾气» (11a7) also treats the goggles as worn: lenses only fog
      // when they are over the eyes, and the settled line says they hang on the chest.
      if (/(镜片后|戴着护目镜|护目镜[^。！？]{0,4}(戴|架在|盖在|泛着雾气|蒙着雾|起雾|浮着雾气|边缘的雾气|上的雾气)|镜片上[^。！？]{0,3}(雾气|水汽))/u.test(sentence)) {
        found.push({ sentence, detail: 'the goggles hang on the chest, not over the eyes' });
      }
    }
  }
  return found;
}

/** Settled object/person states that the prose may not re-enact or move.
 *
 * 01's route review: «黄黑绳被风吹起» (rope settled 已放下), «水花在停水的喷泉池»
 * (pool settled 停水), «演习规则牌在脚下» (board settled on the wall), «诺诺站在
 * 他身后» (prior text has her 不远处). Each needs the input line, so this is a
 * comparison, not a word ban. */
export function settledStateViolations(
  text: string, inputText: string, priorText: string | null = null,
): SettledViolation[] {
  const found: SettledViolation[] = [];
  const NL = String.fromCharCode(10);
  const lines = inputText.split(NL);
  const prior = priorText ?? '';
  for (const sentence of sentencesOf(text)) {
    for (const line of lines) {
      // A completed «已放下» state is not lifted by wind.
      const down = /([一-鿿]{2,8})[^一-鿿]{0,3}已放下/u.exec(line);
      if (down) {
        const thing = down[1].replace(/^.*[【\s]/u, '');
        if (thing.length >= 2
          && new RegExp(`${thing}[^。！？]{0,10}(吹起|飘起|扬起|卷起|抬起)`, 'u').test(sentence)) {
          found.push({ sentence, detail: `${thing} is settled 已放下; lifting it again is a state change` });
        }
      }
      // A place written on the object line is where the object stays.
      const placed = /([一-鿿]{2,8})[（(](墙上|桌上|地上|架子上)[）)]/u.exec(line);
      if (placed) {
        const thing = placed[1];
        const elsewhere = /(脚下|脚边|手里|手中|怀里)/u.exec(sentence);
        if (elsewhere && sentence.includes(thing)) {
          found.push({ sentence, detail: `${thing} is settled on the ${placed[2]}, not ${elsewhere[1]}` });
        }
      }
    }
    // Water cannot be seen in a pool the state says has stopped.
    if (/停水/u.test(inputText) && /(水花|水面|水声|水珠|喷泉[^。！？]{0,4}(喷|涌|冒))/u.test(sentence)) {
      found.push({ sentence, detail: 'the pool is settled 停水; water contradicts it' });
    }
  }
  // A person the prior passage placed 不远处 is not standing 身后.
  for (const line of `${prior}${NL}${inputText}`.split(NL)) {
    if (!/不远处/u.test(line)) continue;
    for (const name of ['路明非', '诺诺']) {
      if (!line.includes(name)) continue;
      const moved = new RegExp(`${name}[^。！？]{0,8}(身后|背后)`, 'u').exec(text);
      if (moved) found.push({ sentence: moved[0], detail: `${name} is settled 不远处, not 身后` });
    }
  }
  return found;
}

/** A carried or scene accessory cannot be the actor of a human movement. 01's
 * route review: «路明非的护目镜在原地站了一会儿», «…没有马上再动». */
export function objectActorViolations(text: string, inputText: string): SettledViolation[] {
  const found: SettledViolation[] = [];
  const NL = String.fromCharCode(10);
  const items = new Set<string>();
  for (const line of inputText.split(NL)) {
    for (const match of line.matchAll(/([一-鿿]{2,10})(?:（|：|:)/gu)) {
      const name = match[1];
      if (name.includes('的')) items.add(name);
    }
  }
  const ACT = /(站了一会儿|站在原地|走了过来|走过去|跑|跳|转身|抬头|低头|再动|动了)/u;
  for (const sentence of sentencesOf(text)) {
    for (const item of items) {
      const at = sentence.indexOf(item);
      if (at < 0) continue;
      const after = sentence.slice(at + item.length, at + item.length + 12);
      const verb = ACT.exec(after);
      if (verb) found.push({ sentence, detail: `${item} is an object, not an actor (${verb[1]})` });
    }
  }
  return found;
}

/** The settled lines a scene packet carries, in one string.
 *
 * The scene-mode verifier reads the serialized input. The per-beat candidate is
 * not given that string directly; it carries the same material as
 * SceneSkeleton fields (inputText, place note, present notes, object notes,
 * inventory). Building the settled text from whichever is present lets both
 * paths run the same comparisons instead of the beat path having none.
 */
export interface SettledSceneLike {
  inputText?: string | null;
  place?: { name?: string; note?: string } | null;
  present?: readonly { name: string; note?: string }[];
  objects?: readonly { name: string; note?: string }[];
  inventory?: readonly { name: string; note?: string }[];
  viewpoint?: { name?: string; note?: string } | null;
}

export function settledTextOf(scene: SettledSceneLike): string {
  const NL = String.fromCharCode(10);
  const lines: string[] = [];
  if (scene.inputText) lines.push(scene.inputText);
  if (scene.place?.name) lines.push(`${scene.place.name}：${scene.place.note ?? ''}`);
  for (const person of scene.present ?? []) lines.push(`${person.name}：${person.note ?? ''}`);
  for (const object of scene.objects ?? []) lines.push(`${object.name}：${object.note ?? ''}`);
  for (const item of scene.inventory ?? []) lines.push(`${item.name}：${item.note ?? ''}`);
  if (scene.viewpoint?.name) lines.push(`${scene.viewpoint.name}：${scene.viewpoint.note ?? ''}`);
  return lines.join(NL);
}

/** All settled comparisons in one call, for a caller that has a scene packet
 * rather than the serialized input. Names come from the packet when the caller
 * does not pass them. Returns hard-worthy violations only. */
export function settledViolationsFromScene(
  text: string,
  scene: SettledSceneLike,
  names: readonly string[] = [],
): SettledViolation[] {
  const settled = settledTextOf(scene);
  if (!settled.trim()) return [];
  const roster = names.length
    ? names
    : [...(scene.present ?? []).map((person) => person.name), scene.viewpoint?.name ?? ''].filter(Boolean);
  return [
    ...settledAppearanceViolations(text, settled, roster, []),
    ...settledStateViolations(text, settled, null),
    ...objectActorViolations(text, settled),
    ...itemStateViolations(text, settled),
  ];
}

/** The viewpoint's own name used as if it were another person, after a third
 * person pronoun in the same sentence: «他望着路明非的演习背心» (real quiet-90
 * run), «他低头看着自己护目镜» (09 e9a5). The 71-row reference never does this
 * (its 9 uses of 自己 are all possessive or reflexive: 自己手里/自己的呼吸…).
 * This is a wording defect, not a fact error, so the caller repairs the wording
 * instead of rejecting the passage. */
export function selfReferenceRepair(text: string, viewpointName: string | undefined): { text: string; repaired: string[] } {
  if (!viewpointName || viewpointName.length < 2) return { text, repaired: [] };
  const repaired: string[] = [];
  const SENT = new RegExp('(?<=[。！？!?])|' + String.fromCharCode(92) + 'n+', 'u');
  const sentences = text.split(SENT);
  const out = sentences.map((sentence) => {
    // A pronoun subject followed later by the viewpoint's full name.
    if (!/(^|[，,；;])\s*[他她]/u.test(sentence)) return sentence;
    const pattern = new RegExp(`([他她][^。！？]{0,12}?)${viewpointName}的`, 'u');
    const match = pattern.exec(sentence);
    if (!match) return sentence;
    // Only when the pronoun is the subject of that clause, not when it is another
    // character acting on the viewpoint.
    if (/[他她][^。！？]{0,4}(看见|望着|看着|看向|盯着|朝|向|对|给|替|帮)/u.test(match[0]) === false) return sentence;
    repaired.push(`${match[0]}…`);
    return sentence.replace(pattern, `$1自己的`);
  });
  return { text: out.join(''), repaired };
}

/** «自己+物品» without 的 is ungrammatical: «看着自己护目镜». Insert 的 when the
 * next characters are a known item or person name. */
export function selfPossessiveRepair(text: string, names: readonly string[]): { text: string; repaired: string[] } {
  const repaired: string[] = [];
  let out = text;
  // «自己护目镜» uses the bare noun, while the registered name is
  // «路明非的护目镜»; both forms need the 的.
  const forms = new Set<string>();
  for (const name of names) {
    if (!name || name.length < 2) continue;
    forms.add(name);
    const own = name.split('的');
    if (own.length === 2 && own[1].length >= 2) forms.add(own[1]);
  }
  for (const name of forms) {
    const pattern = new RegExp(`自己${name}`, 'gu');
    if (!pattern.test(out)) continue;
    out = out.replace(new RegExp(`自己${name}`, 'gu'), `自己的${name}`);
    repaired.push(`自己${name}→自己的${name}`);
  }
  return { text: out, repaired };
}

/** A settled item cannot be put on, taken off or stowed unless the point says so.
 * 926e close beat: «路明非摘下护目镜，目光落在规则牌上» — the goggles are settled
 * on the chest and no fact changes that. Pushing an object on a desk (the reference's
 * «把裁纸刀推到桌边») is a micro-action and stays allowed; only wear-state and
 * stowing verbs are world changes. */
const ITEM_STATE_VERBS = ['摘下', '取下', '戴上', '系上', '解开', '收起', '装进', '塞进', '揣进', '放回', '收起'] as const;

/** Item names a settled line carries, both full («路明非的护目镜») and bare («护目镜»). */
function settledItemNames(settledText: string): string[] {
  const names = new Set<string>();
  for (const line of settledText.split(new RegExp(String.fromCharCode(10) + '|。', 'u'))) {
    let head = line.split(/[：:（(]/u)[0]?.trim() ?? '';
    if (!head) continue;
    // The serialized input prefixes item lines; a character or place line is not
    // an item, and 「某人的某物」 in a character note names an owned item only.
    const prefix = /^【([^】]+)】/u.exec(head);
    if (prefix) {
      if (!/物品|物件|随身/u.test(prefix[1])) continue;
      head = head.slice(prefix[0].length).trim();
    }
    if (!head) continue;
    for (const part of head.split('、')) {
      const clean = part.trim();
      if (clean.length < 2 || clean.length > 14) continue;
      names.add(clean);
      const own = clean.split('的');
      if (own.length === 2 && own[1].length >= 2) names.add(own[1]);
    }
  }
  return [...names].sort((a, b) => b.length - a.length);
}

export function itemStateViolations(text: string, settledText: string): SettledViolation[] {
  const found: SettledViolation[] = [];
  if (!settledText.trim()) return found;
  const items = settledItemNames(settledText);
  for (const sentence of sentencesOf(text)) {
    for (const verb of ITEM_STATE_VERBS) {
      let from = 0;
      for (;;) {
        const at = sentence.indexOf(verb, from);
        if (at < 0) break;
        from = at + verb.length;
        // The object of the verb is the noun right after it («摘下护目镜»), or the
        // 把-object before it («把护目镜戴上»).
        const after = sentence.slice(at + verb.length, at + verb.length + 12).replace(/^(了|下|掉)/u, '');
        const before = sentence.slice(Math.max(0, at - 10), at);
        const item = items.find((name) => after.startsWith(name))
          ?? items.find((name) => new RegExp(`把${name}$`, 'u').test(before));
        if (!item) continue;
        // The point itself may settle this verb for this item.
        const here = new RegExp(`${verb}[^。！？]{0,6}${item}|${item}[^。！？]{0,6}${verb}`, 'u').test(settledText);
        if (here) continue;
        found.push({ sentence, detail: `${verb}${item} changes a settled item state the point does not have` });
      }
    }
  }
  return found;
}
