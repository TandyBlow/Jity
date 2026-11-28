/** 零参数叙事候选：玩家行动开场 + 只写增量事实 + 全部结算结果 + 时间收尾。
 *  输入是页面已经算好的事实句数组与结算原文，不调用任何模型。 */

const OUTCOME_PHRASE: Record<string, string> = {
  没有成功: '，却没有成功',
  只完成一部分: '，只完成了一部分',
  无法完成: '，没能完成',
  部分成功: '，只完成了一部分',
  失败: '，失败了',
};
const TIME = /^时间到了/u;
const SETTLE = '这一回合的结算结果';
const ACTION = /^玩家这回合让(.{1,4}?)做的事[：:](.+)$/u;

export interface RulesNarrationInput {
  /** instructNarrationInput 的 sentences：含行动行、时间行、世界事实与结算段。 */
  sentences: string[];
  resultsText: string;

  names: string[];
  protagonist: string;
}

function resultLine(raw: string): string | null {
  const line = raw.trim().replace(/^[；;]/u, '');
  if (!line || /^(?:去向|涉及|环境)=/u.test(line)) return null;
  const match = /^([^：:]{1,8})[：:](.+)$/u.exec(line);
  if (!match) return /^信息[=＝]/u.test(line) ? null : line.replace(/[。；]$/u, '');
  const actor = match[1].trim();
  const body = match[2].trim();
  const outcome = Object.keys(OUTCOME_PHRASE).find((key) => body.includes(key)) ?? '';
  const action = body.replace(/[（(][^）)]*[）)]/gu, '').replace(/[。；（(]+$/u, '').trim();
  if (!action) return null;
  return `${actor}${action}${outcome ? OUTCOME_PHRASE[outcome] : ''}`;
}

/** 开场句直接取已经过滤过地点与“我”的玩家行动行。 */
function openingOf(sentences: string[]): string | null {
  const line = sentences.find((part) => part.startsWith('玩家这回合'));
  if (!line) return null;
  const match = ACTION.exec(line);
  if (!match) return null;
  const name = match[1];
  const body = match[2].trim().replace(/[，,、；;。\s]+$/u, '');
  if (!body) return null;
  return body.startsWith(name) ? body : `${name}${body}`;
}

function grams(text: string): Set<string> {
  const chars = text.replace(/[^一-鿿]/gu, '');
  const out = new Set<string>();
  for (let i = 0; i + 1 < chars.length; i += 1) out.add(chars.slice(i, i + 2));
  return out;
}

/** 结算行已经写了同一动作时，开场不再复述。 */
function covers(result: string, opening: string): boolean {
  const source = grams(opening);
  if (!source.size) return false;
  const target = grams(result);
  let shared = 0;
  for (const gram of source) if (target.has(gram)) shared += 1;
  return shared / source.size >= 0.5;
}

function head(text: string, names: string[]): string | undefined {
  return names.find((name) => text.startsWith(name));
}

/** 相邻句同主语时并入一句，避免“路明非……。路明非……”。 */
function mergeSameHead(parts: string[], names: string[]): string[] {
  const out: string[] = [];
  for (const part of parts) {
    const last = out[out.length - 1];
    const name = head(part, names);
    if (last && name && head(last, names) === name) {
      out[out.length - 1] = `${last}，${part.slice(name.length)}`;
    } else {
      out.push(part);
    }
  }
  return out;
}

export function rulesNarration(input: RulesNarrationInput): string {
  // 每个 point 都写完整场景；跨 point 的重复句由页面在拼接时去掉。
  const facts = input.sentences.filter((part) => !part.startsWith('玩家这回合') && !TIME.test(part) && !part.startsWith(SETTLE));
  const results = input.resultsText.split(/[；]/u).map(resultLine).filter((line): line is string => Boolean(line));
  const time = input.sentences.find((part) => TIME.test(part)) ?? '';
  const declared = openingOf(input.sentences);
  const opening = declared && results.some((line) => covers(line, declared)) ? null : declared;
  const body: string[] = [];
  if (opening) body.push(opening);
  body.push(...results, ...facts);
  const merged = mergeSameHead(body.map((part) => part.replace(/。$/u, '')), input.names);
  const paragraphs: string[] = [];
  if (merged.length) paragraphs.push(`${merged.join('。')}。`);
  if (time) {
    if (paragraphs.length) paragraphs[paragraphs.length - 1] += time;
    else paragraphs.push(time);
  }
  return paragraphs.join('\n\n');
}
