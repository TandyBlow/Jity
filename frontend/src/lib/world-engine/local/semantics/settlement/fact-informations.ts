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

/** Candidate clauses of one entity's appearance, split the same way the
 * program has always split them (；。，,). */
export function informationCandidates(state: WorldState, entityId: Id): string[] {
  const entity = state.initial.items[entityId] ?? state.initial.characters[entityId];
  const appearance = entity?.initialAppearance;
  if (!appearance) return [];
  return appearance.split(/[；。，,]/u).map((clause) => clause.trim()).filter(Boolean);
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
  const clauses = informationCandidates(state, entityId);
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
  for (let size = Math.min(left.length, right.length); size >= 2; size -= 1) {
    for (let start = 0; start + size <= left.length; start += 1) {
      if (right.includes(left.slice(start, start + size))) return size;
    }
  }
  return 0;
}

export interface InformationDecider {
  /** Scores each candidate clause for this action (higher = more likely). */
  extraction: (action: string, clauses: string[]) => Promise<Array<{ clause: string; score: number }> | null>;
  /** Existence gate; when absent the decision relies on extraction alone. */
  existence?: (text: string) => Promise<{ env: number; info: number } | null>;
  minScore?: number;
  minMargin?: number;
  minExistence?: number;
}

/** Model decision for a read action the program had no topic for: existence
 * gate -> candidate pointer -> verbatim support. Abstains unless the pointer
 * is confident and the chosen clause is one of the committed candidates. */
export async function decideInformation(
  text: string,
  entityIds: Id[],
  state: WorldState,
  label: string,
  decider: InformationDecider,
  existenceText = '',
  memberId?: Id,
  actorRoom?: Id,
  destination?: { containerId?: Id } | null,
): Promise<{ entityId: Id; text: string } | null> {
  if (label !== 'achieved' && label !== 'partial') return null;
  if (entityIds.length !== 1) return null;
  if (!READ.test(text)) return null;
  // 泛泛的「查看某物」没有问项，模型没有可判定的目标（审计实测会乱选分句）
  if (!/关于|想知道|有没有|能不能|是否|什么|哪|多少|几/u.test(text)) return null;
  const entityId = entityIds[0];
  const entity = state.initial.items[entityId] ?? state.initial.characters[entityId];
  if (!entity?.initialAppearance) return null;
  const arrival = destination?.containerId ? roomOf(state, destination.containerId) : null;
  if (memberId && roomOf(state, entityId) !== (arrival ?? actorRoom ?? roomOf(state, memberId))) return null;
  const clauses = informationCandidates(state, entityId);
  // 只有一个候选时没有「选择」可做，交给程序通道
  if (clauses.length < 2) return null;
  if (decider.existence) {
    const scores = await decider.existence(existenceText || text);
    if (!scores || scores.info < (decider.minExistence ?? 0.5)) return null;
  }
  const scored = await decider.extraction(text, clauses);
  if (!scored?.length) return null;
  const ranked = [...scored].sort((left, right) => right.score - left.score);
  const best = ranked[0];
  const margin = best.score - (ranked[1]?.score ?? 0);
  if (best.score < (decider.minScore ?? 0.6) || margin < (decider.minMargin ?? 0.15)) return null;
  // 支持核验：分句必须是已提交外貌的原句，程序不生成内容
  if (!clauses.includes(best.clause)) return null;
  return { entityId, text: best.clause };
}
