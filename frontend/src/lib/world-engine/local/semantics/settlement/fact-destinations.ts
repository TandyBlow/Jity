/** Structured destinations carried by settled facts (`去向=entity:container[/slot]`).
 * Pure text parsing so both the settlement runner and the micro updates port
 * read the same channel without importing the browser runtime. */
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

/** Wording that asserts a movement happened or was attempted. */
export const MOVEMENT_WORDS = ['走进', '走入', '走到', '走向', '进入', '来到', '回到', '退回', '退到', '跑到', '冲向', '赶到', '爬上', '走下', '钻出', '穿过', '递给', '交给', '塞给', '递到', '放进', '放到', '放在', '塞进', '送到'] as const;

/** Wording that says the attempt did not take effect; such a fact is a
 * confirmed no-change, not an uncertain one. */
export const FAILURE_WORDS = ['没有', '没能', '未能', '未', '被阻止', '阻止', '拦住', '拦下', '挡住', '失败', '落空', '无法'] as const;

/** Wording that could change an appearance; anything here is uncertain and
 * must go to the LLM appearance stage. */
export const APPEARANCE_WORDS = ['穿', '脱', '擦', '洗', '湿', '血', '沾', '脏', '破', '裂', '换', '戴', '摘', '缠', '绑', '挂', '撕', '染'] as const;
