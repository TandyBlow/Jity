/** Python's `sorted(str)` compares Unicode code points. JavaScript's default
 * sort compares UTF-16 code units, which puts a supplementary character
 * before U+E000..U+FFFF even though its code point is larger. That difference
 * changes the order of non-BMP names and therefore the serialized bytes. */
export function compareCodePoints(left: string, right: string): number {
  const a = Array.from(left, (char) => char.codePointAt(0) as number);
  const b = Array.from(right, (char) => char.codePointAt(0) as number);
  const length = Math.min(a.length, b.length);
  for (let index = 0; index < length; index += 1) {
    if (a[index] !== b[index]) return a[index] - b[index];
  }
  return a.length - b.length;
}

export function sortedByCodePoints<T>(values: Iterable<T>, key: (value: T) => string): T[] {
  return [...values].sort((left, right) => compareCodePoints(key(left), key(right)));
}
