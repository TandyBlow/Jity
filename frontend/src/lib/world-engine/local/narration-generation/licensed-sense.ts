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
const SOUND_NOUNS = /(声|响|动静)/u;

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
      if (/(镜片后|戴着护目镜|护目镜[^。！？]{0,4}(戴|架在|盖在)|镜片上[^。！？]{0,3}(雾气|水汽))/u.test(sentence)) {
        found.push({ sentence, detail: 'the goggles hang on the chest, not over the eyes' });
      }
    }
  }
  return found;
}
