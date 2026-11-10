/** Enumerates every size-N subset for the offline N-arm comparison.
 *
 * Keeping this pure makes the "no seed-prefix" rule testable: N=1 must produce
 * six different single seeds, N=2 fifteen pairs, N=4 fifteen four-subsets.
 */
export function combinations<T>(items: readonly T[], size: number): T[][] {
  if (size <= 0 || size > items.length) return [];
  const result: T[][] = [];
  const current: T[] = [];
  const walk = (startIndex: number): void => {
    if (current.length === size) {
      result.push([...current]);
      return;
    }
    for (let index = startIndex; index < items.length; index += 1) {
      current.push(items[index]);
      walk(index + 1);
      current.pop();
    }
  };
  walk(0);
  return result;
}
