/** Structured destinations carried by settled facts (`去向=entity:container[/slot]`).
 * Pure text parsing so both the settlement runner and the micro updates port
 * read the same channel without importing the browser runtime. */
import type { Id, WorldState } from '../../../types';

export interface FactDestination {
  containerId: string;
  slotId: string | null;
}

export function readDestinations(texts: string[]): Map<string, FactDestination> {
  const map = new Map<string, FactDestination>();
  for (const text of texts) {
    for (const match of text.matchAll(/去向=([^:；\s]+):([^/\s；]+)(?:\/([^\s；]+))?/gu)) {
      map.set(match[1], { containerId: match[2], slotId: match[3] ?? null });
    }
  }
  return map;
}

/** Registered location named by a text. A full name wins; otherwise a suffix of
 * the name may match (the player says 庭院 for 中央庭院). Two locations matching
 * the same text are ambiguous and return null. */
export function matchLocation(state: WorldState, text: string): { id: Id; at: number; name: string } | null {
  const hits: Array<{ id: Id; at: number; name: string }> = [];
  for (const [id, location] of Object.entries(state.initial.locations)) {
    const name = location.name ?? '';
    if (name.length < 2) continue;
    let matched = name;
    let at = text.lastIndexOf(name);
    if (at < 0) {
      for (let cut = 1; cut <= name.length - 2; cut += 1) {
        const suffix = name.slice(cut);
        const index = text.lastIndexOf(suffix);
        if (index >= 0) { matched = suffix; at = index; break; }
      }
    }
    if (at >= 0) hits.push({ id, at, name: matched });
  }
  if (!hits.length) return null;
  hits.sort((left, right) => right.at - left.at || right.name.length - left.name.length);
  if (hits.length > 1 && hits[0].at === hits[1].at && hits[0].name.length === hits[1].name.length) return null;
  return hits[0];
}

/** Wording that asserts a movement happened or was attempted. */
export const MOVEMENT_WORDS = ['走进', '走入', '走到', '走向', '进入', '来到', '回到', '退回', '退到', '跑到', '冲向', '赶到', '爬上', '走下', '钻出', '穿过', '递给', '交给', '塞给', '递到', '放进', '放到', '放在', '塞进', '送到'] as const;

/** Wording that says the attempt did not take effect; such a fact is a
 * confirmed no-change, not an uncertain one. */
export const FAILURE_WORDS = ['没有', '没能', '未能', '未', '被阻止', '阻止', '拦住', '拦下', '挡住', '失败', '落空', '无法'] as const;

/** Wording that could change an appearance; anything here is uncertain and
 * must go to the LLM appearance stage. */
export const APPEARANCE_WORDS = ['穿', '脱', '擦', '洗', '湿', '血', '沾', '脏', '破', '裂', '换', '戴', '摘', '缠', '绑', '挂', '撕', '染'] as const;
