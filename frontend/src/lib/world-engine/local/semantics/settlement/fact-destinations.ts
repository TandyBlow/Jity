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

/** Registered location named by a text. A full-name match always wins over a
 * suffix match, even when the suffix appears later (西回廊 vs 东回廊). Suffix
 * matches need a unique location; 庭院→中央庭院 is allowed, 回廊 is ambiguous. */
export function matchLocation(state: WorldState, text: string): { id: Id; at: number; name: string } | null {
  const full: Array<{ id: Id; at: number; name: string }> = [];
  const suffix: Array<{ id: Id; at: number; name: string }> = [];
  for (const [id, location] of Object.entries(state.initial.locations)) {
    const name = location.name ?? '';
    if (name.length < 2) continue;
    const at = text.lastIndexOf(name);
    if (at >= 0) {
      full.push({ id, at, name });
      continue;
    }
    for (let cut = 1; cut <= name.length - 2; cut += 1) {
      const part = name.slice(cut);
      const index = text.lastIndexOf(part);
      if (index >= 0) { suffix.push({ id, at: index, name: part }); break; }
    }
  }
  if (full.length) {
    full.sort((left, right) => right.at - left.at);
    if (full.length > 1 && full[0].at === full[1].at) return null;
    return full[0];
  }
  if (!suffix.length) return null;
  suffix.sort((left, right) => right.at - left.at || right.name.length - left.name.length);
  if (suffix.length > 1 && (suffix[0].at === suffix[1].at || suffix[0].name === suffix[1].name)) return null;
  return suffix[0];
}

/** Wording that asserts a movement happened or was attempted. */
export const MOVEMENT_WORDS = ['走进', '走入', '走到', '走向', '进入', '来到', '回到', '退回', '退到', '跑到', '冲向', '赶到', '爬上', '走下', '走上', '上楼', '下楼', '钻出', '穿过', '递给', '交给', '塞给', '递到', '放进', '放到', '放在', '塞进', '送到'] as const;

/** Wording that says the attempt did not take effect; such a fact is a
 * confirmed no-change, not an uncertain one. */
export const FAILURE_WORDS = ['没有', '没能', '未能', '未', '被阻止', '拦住', '拦下', '被挡住', '失败', '落空', '无法'] as const;

/** Wording that could change an appearance; anything here is uncertain and
 * must go to the LLM appearance stage. */
export const APPEARANCE_WORDS = ['穿', '脱', '擦', '洗', '湿', '血', '沾', '脏', '破', '裂', '换', '戴', '摘', '缠', '绑', '挂', '撕', '染'] as const;
