/** Narrow N=1 viewpoint guard for lane 12's selector input.
 *
 * This is not a replacement for 01's checker and does not judge prose. It only
 * answers one deterministic question: does the text narrate in first person
 * while the settled viewpoint is a named third-person character? Dialogue in
 * quotes is ignored. If the settled viewpoint explicitly says first person, the
 * guard does not fire.
 */
export interface FirstPersonCheck {
  flagged: boolean;
  viewpoint: string | null;
  sentences: string[];
}

const QUOTE = /“[^”]*”|「[^」]*」|‘[^’]*’|"[^"]*"/gu;
const FIRST_PERSON_VIEWPOINT = /第一人称|我(?:们)?视角/u;
const NARRATIVE_FIRST_PERSON = /(^|[。！？；\n：])\s*我/u;

export function firstPersonNarration(
  input: Record<string, unknown>,
  text: string,
): FirstPersonCheck {
  const raw = typeof input['视角'] === 'string' ? input['视角'] : '';
  const viewpoint = raw.trim() || null;
  if (!viewpoint || FIRST_PERSON_VIEWPOINT.test(viewpoint)) {
    return { flagged: false, viewpoint, sentences: [] };
  }
  const narrative = text.replace(QUOTE, ' ');
  const sentences = narrative
    .split(/(?<=[。！？；\n])/u)
    .map((sentence) => sentence.trim())
    .filter((sentence) => NARRATIVE_FIRST_PERSON.test(sentence));
  return { flagged: sentences.length > 0, viewpoint, sentences };
}
