/** Reviewed gender table.
 *
 * Gender is a fact about the world, so it cannot be guessed from a name or from
 * a model's default pronoun. Every entry here needs a citable source recorded in
 * the project; the world file currently states no gender field, and its prose
 * uses 他/她 ambiguously, so most characters stay `unknown` on purpose.
 *
 * Consumers:
 *  - `reviewNarration({ genders: REVIEWED_GENDERS })` turns a wrong pronoun into
 *    `fact.gender` only when the binding is unambiguous (same clause as the
 *    name, or a single-person scene). Otherwise it stays `review.pronoun`.
 *  - An entry with `unknown` is not a licence to use either pronoun; the checker
 *    falls back to a review item.
 *
 * Adding an entry requires: the character name, the gender, and where the fact
 * is recorded (a review record, a world-file line, or a novel passage id).
 */

export type Gender = 'male' | 'female' | 'unknown';

export interface GenderEntry {
  gender: Gender;
  source: string;
}

export const REVIEWED_GENDERS: Record<string, GenderEntry> = {
  周宁: {
    gender: 'female',
    source: 'team-08-runtime.json humanReviewFindings: the 2026-11-10 product review recorded 周宁 being narrated as 他 as an error',
  },
};

/** Plain name -> gender map for `ReviewOptions.genders`. */
export function genderOptions(table: Record<string, GenderEntry> = REVIEWED_GENDERS): Record<string, 'male' | 'female'> {
  const result: Record<string, 'male' | 'female'> = {};
  for (const [name, entry] of Object.entries(table)) {
    if (entry.gender === 'male' || entry.gender === 'female') result[name] = entry.gender;
  }
  return result;
}

/** Characters with no recorded source. Kept explicit so a caller can log them. */
export function unknownGenders(names: string[], table: Record<string, GenderEntry> = REVIEWED_GENDERS): string[] {
  return names.filter((name) => !table[name] || table[name].gender === 'unknown');
}
