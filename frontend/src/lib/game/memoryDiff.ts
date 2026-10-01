/**
 * Set-and-field comparison between two stored states.
 *
 * Safe to do here rather than server side: every memory entry in a stored
 * state has already been through the server's normalization, so both sides
 * carry the same keys with the same empty-value conventions. There is no
 * merge order to reproduce, only a comparison.
 */

export type MemoryDiff = {
  added: string[];
  removed: string[];
  changed: Array<{ name: string; fields: string[] }>;
};

type Entry = Record<string, unknown>;

function byName(entries: Entry[]): Map<string, Entry> {
  const map = new Map<string, Entry>();
  for (const entry of entries) {
    const name = entry?.name;
    if (name) map.set(String(name), entry);
  }
  return map;
}

export function diffMemory(before: Entry[], after: Entry[]): MemoryDiff {
  const from = byName(before);
  const to = byName(after);
  const added: string[] = [];
  const removed: string[] = [];
  const changed: MemoryDiff["changed"] = [];

  for (const name of to.keys()) {
    if (!from.has(name)) added.push(name);
  }
  for (const [name, entry] of from) {
    const next = to.get(name);
    if (!next) {
      removed.push(name);
      continue;
    }
    const fields = [...new Set([...Object.keys(entry), ...Object.keys(next)])].filter(
      (key) => key !== "name" && String(entry[key] ?? "") !== String(next[key] ?? ""),
    );
    if (fields.length > 0) changed.push({ name, fields });
  }

  return { added, removed, changed };
}
