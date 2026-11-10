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
export const SENSE_NOUNS = [
  '枪声', '脚步声', '风声', '心跳声', '回声', '铃声', '钟声', '水滴声', '摩擦声', '声响', '响声',
  '硝烟', '气味', '香味', '木香', '血腥味', '臭味',
  // Light and air where the input says nothing about them. Measured against
  // the 71 reference scenes: none of these appears without its input saying so.
  '风中', '风里', '阳光', '月光', '灯光',
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

export interface SenseOptions {
  /** People with a committed move this point. Their own footsteps are a
   * consequence of the settled movement, not an invented sound. */
  movedNames?: readonly string[];
}

export function senseViolations(text: string, inputText: string, options: SenseOptions = {}): SenseViolation[] {
  const found: SenseViolation[] = [];
  const sources = licensedSources(inputText);
  for (const sentence of sentencesOf(text)) {
    for (const noun of SENSE_NOUNS) {
      if (!sentence.includes(noun)) continue;
      // The noun itself is in the input (e.g. the notes mention 声音).
      if (inputText.includes(noun)) continue;
      // A licensed source named in the same sentence («除湿机的声音»).
      const head = noun.replace(/(声|味)$/u, '');
      const sourced = sources.some((source) => source.length >= 2
        && (sentence.includes(source) && (source.includes(head) || head.includes(source))));
      if (sourced) continue;
      // A committed move licenses that person's own footsteps.
      // Any committed move in this point makes footsteps a consequence of the
      // settled action rather than an invented sound; a quiet point has none.
      if (noun === '脚步声' && (options.movedNames ?? []).length > 0) continue;
      found.push({ sentence, noun });
    }
  }
  return found;
}
