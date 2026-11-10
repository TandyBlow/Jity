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
