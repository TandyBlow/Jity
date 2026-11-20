/** Sourced character gender for the current world.
 *
 * The 2026-11-11 decision: the prompt must not forbid 他/她; it must supply the
 * gender the project actually has evidence for. The data below is copied from
 * `results/product/evidence/05-kernel/character-gender-evidence.md` (checked
 * 2026-11-10 against the world file sha256 0a8b63be…), which quotes the world
 * JSON for each entry. Names are not evidence of gender, so anyone absent here
 * stays unknown and the prompt says nothing about them.
 *
 * This is prompt data, not a world-schema change: the world file keeps no
 * gender field, saves are untouched, and a different world simply finds nothing
 * here. Keep the list in sync with the evidence file, not with guesses.
 */
export type CharacterGender = 'male' | 'female';

export const SOURCED_GENDERS: Readonly<Record<string, CharacterGender>> = {
  路明非: 'male',
  诺诺: 'female',
  楚子航: 'male',
  林亦舟: 'male',
  沈澄: 'female',
};

/** «诺诺（女）» — the label the prompt prints next to a known character. */
export function genderLabel(name: string | null | undefined): string | null {
  if (!name) return null;
  const gender = SOURCED_GENDERS[name];
  if (!gender) return null;
  return `${name}（${gender === 'male' ? '男' : '女'}）`;
}

/** One prompt line that states what is known and leaves the rest open.
 *
 * It replaces the old ban («不要用「他」「她」指代人物»). Printing the known
 * genders lets the model write ordinary Chinese pronouns for the five people
 * with evidence; for everyone else it suggests the name, which is a preference,
 * not a prohibition. */
export function genderLine(
  names: readonly string[],
  extra: Readonly<Record<string, CharacterGender>> = {},
): string | null {
  const known = [...new Set(names)]
    .map((name) => {
      const gender = extra[name] ?? SOURCED_GENDERS[name];
      if (!gender) return null;
      return `${name}（${gender === 'male' ? '男' : '女'}）`;
    })
    .filter(Boolean) as string[];
  if (!known.length) return null;
  return `已知性别：${known.join('、')}；这些人可以用「他」「她」。其余人物没有资料，用名字最稳妥。`;
}
