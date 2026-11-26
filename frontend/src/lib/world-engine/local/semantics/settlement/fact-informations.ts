/** `信息=entity:clause` in settled facts: a read action's extracted content.
 * The clause is a verbatim slice of the entity's committed appearance, so the
 * program never invents knowledge; an action without a topic term abstains. */
import type { Id, WorldState } from '../../../types';
import { roomOf } from '../../prompt';

export interface FactInformation {
  entityId: Id;
  text: string;
}

export function readInformations(texts: string[]): FactInformation[] {
  const rows: FactInformation[] = [];
  for (const text of texts) {
    for (const match of text.matchAll(/信息[=＝]([^:：；\s]+)[:：]([^；。\n]+)/gu)) {
      const body = match[2].trim();
      const entityId = match[1].replace(/^<|>$/gu, '');
      if (body && entityId) rows.push({ entityId, text: body });
    }
  }
  return rows;
}

const READ = /读|念|查看|翻看|翻阅|核对|确认|检查|观察|看|听/;
const STOP = new Set('的了是把将在上里到和与及或为也就都又再被从向对给让这那其我你他她它们'.split(''));

function onlyStopChars(gram: string): boolean {
  return [...gram].every((char) => STOP.has(char));
}

/** Read/inspect one registered item -> its appearance clause that shares the
 * action's longest topic term. Null when there is no such term. */
export function informationHint(
  text: string,
  itemIds: Id[],
  state: WorldState,
  label = 'achieved',
  memberId?: Id,
  actorRoom?: Id,
  destination?: { containerId?: Id } | null,
): { entityId: Id; text: string } | null {
  if (label !== 'achieved' && label !== 'partial') return null;
  if (itemIds.length !== 1) return null;
  if (!READ.test(text)) return null;
  const entityId = itemIds[0];
  // 人物外貌同样可读（识别带颜色、伤势），规则与物品一致
  const item = state.initial.items[entityId] ?? state.initial.characters[entityId];
  if (!item?.initialAppearance) return null;
  // 移动+读取的复合动作按子动作到达房间判断
  const arrival = destination?.containerId ? roomOf(state, destination.containerId) : null;
  if (memberId && roomOf(state, entityId) !== (arrival ?? actorRoom ?? roomOf(state, memberId))) return null;
  const clauses = item.initialAppearance.split(/[；。，,]/u).map((clause) => clause.trim()).filter(Boolean);
  // 「关于X的说明」直接给出话题；只按 X 与外形的重叠挑分句
  const about = /关于(.{2,6}?)的/u.exec(text)?.[1] ?? null;
  if (about) {
    let best: { clause: string; overlap: number } | null = null;
    for (const clause of clauses) {
      if (item.name.includes(about)) continue;
      const overlap = longestShared(about, clause);
      if (overlap >= 2 && (!best || overlap > best.overlap)) best = { clause, overlap };
    }
    return best ? { entityId, text: best.clause } : null;
  }
  let best: { clause: string; length: number; at: number } | null = null;
  for (const clause of clauses) {
    let hit: { length: number; at: number } | null = null;
    for (let size = Math.min(6, clause.length); size >= 2 && !hit; size -= 1) {
      for (let start = 0; start + size <= clause.length; start += 1) {
        const gram = clause.slice(start, start + size);
        if (onlyStopChars(gram) || item.name.includes(gram)) continue;
        // 「图上」「桌上」是位置词，不是话题
        if (size === 2 && /[上下里中内外旁边]$/u.test(gram)) continue;
        const at = text.indexOf(gram);
        if (at >= 0) { hit = { length: size, at }; break; }
      }
    }
    if (!hit) continue;
    // 话题词越长越可信；同长取动作里先出现的
    if (!best || hit.length > best.length || (hit.length === best.length && hit.at < best.at)) {
      best = { clause, ...hit };
    }
  }
  if (!best) return null;
  return { entityId, text: best.clause };
}

/** Longest common substring length (both strings are short clauses). */
function longestShared(left: string, right: string): number {
  let best = 0;
  for (let size = Math.min(left.length, right.length); size > best; size -= 1) {
    for (let start = 0; start + size <= left.length; start += 1) {
      if (right.includes(left.slice(start, start + size))) return size;
    }
  }
  return best;
}
