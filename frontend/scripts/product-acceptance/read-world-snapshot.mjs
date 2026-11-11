/** Read the current product snapshot in the browser, preserving the older object contract. */
export function readWorldSnapshot() {
  const source = globalThis.__worldSnapshot;
  return typeof source === 'function' ? source() : (source ?? null);
}
