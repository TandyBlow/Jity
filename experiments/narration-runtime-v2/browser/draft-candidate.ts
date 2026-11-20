// Lane 10 page-draft candidate: the page passes its settled-fact draft, the
// model rewrites it under the page's own instruction, and the result is checked
// for draft coverage and invention before it may replace the fallback.
//
// The prompt below is the page's `instructNarrationInput(..., draft)` string
// (worktrees/06-recovery frontend/src/lib/world-engine/local/prompt.ts) copied
// verbatim, and the model saw exactly this shape during training
// (src/build_page_pairs.py). If 06 changes that template, regenerate the
// training data; do not silently adapt the prompt here.
//
// Output contract is the shared runner's `generateCandidate` result. Quality is
// decided by 01's review of real page text, not by this file.

export const STRATEGY_VERSION = 'lane10-page-draft-v1';
export const MODEL_ID = 'qwen25-1.5b-page-draft-v1';

const SCENE_HEAD = '你是中文小说作者。请把下面这段已经结算的事实草稿改写成 {name} 视角的小说正文，160 到 240 字。';
const REPAIR_HEAD = '你是中文小说作者。上一稿没能全部落在已结算事实上。请只把下面这段草稿改写成 {name} 视角的小说正文，140 到 220 字。';
const DRAFT_RULES = '要求：只能使用草稿里明确写出的动作、位置、外观和结果；可以调整语序、连接词和短句节奏，'
  + '但不得新增任何动作、对白、物品、人物、地点、数字、伤情、往事、心理活动或比喻；'
  + '每个人物的伤势、衣物和物品只属于本人，不要用“他/她”把一个人的特征挪到另一个人身上；'
  + '不要逐条复述草稿，不要把人物外貌列成清单；以动作为主线写成一个连续场景，'
  + '环境和人物只保留与当前动作有关的一两笔；不要写标题、列表或 Markdown；分 2 到 3 段。';

export function buildPagePrompt(name: string, draft: string, mode: 'scene' | 'repair' = 'scene'): string {
  const head = (mode === 'repair' ? REPAIR_HEAD : SCENE_HEAD).replace('{name}', name);
  return [head, DRAFT_RULES, '事实草稿：', draft, '正文：'].join('\n');
}

const UNIT_CN = { second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年' };

/** Minimal stand-in for the page's `factualNarration`, used only when the page
 * does not hand over a draft. The page's own draft always wins. */
export function draftFromFacts(committed: any, timeAdvance: any): string {
  const parts = [];
  const duration = timeAdvance?.duration;
  const unit = UNIT_CN[duration.unit as keyof typeof UNIT_CN] ?? '';
  if (duration?.amount) parts.push(`时间过去了约${duration.amount}${unit}。`);
  for (const fact of committed?.facts ?? []) {
    if (fact.kind === 'moved') parts.push(`${fact.name}从${fact.from}走到${fact.to}。`);
    if (fact.kind === 'task_achieved') parts.push(`${fact.name}完成了「${fact.goal}」。`);
    if (fact.kind === 'personality_changed') parts.push(`${fact.name}多了一条个性：${fact.text}。`);
    if (fact.kind === 'sanity_changed') parts.push(`${fact.name}的精神值从${fact.from}变成${fact.to}。`);
  }
  return parts.join('');
}

function viewpointName(inputText: unknown): string {
  const match = /【视角】[^（(]*[（(]([^）)]+)[）)]/.exec(String(inputText ?? ''));
  return match ? match[1].trim() : '';
}

const FILLER = ['仿佛', '似乎', '像是', '好像', '某种', '不由得', '不禁'];

/** Conservative checks so a broken answer cannot silently replace the draft:
 * every draft sentence must survive, and no number may appear from nowhere. */
export function checkProse(text: unknown, { draft, name }: { draft: string; name: string }): string[] {
  const issues = [];
  const prose = String(text ?? '').trim();
  if (!prose) return ['empty'];
  if (prose.length > 320) issues.push('too_long');
  for (const clause of String(draft ?? '').split(/(?<=。)/).filter((part) => part.trim())) {
    const numbers = clause.match(/[0-9]+/g) ?? [];
    for (const number of numbers) {
      if (!prose.includes(number)) issues.push(`missing_fact:${clause.slice(0, 8)}`);
    }
    const goal = /「(.+?)」/.exec(clause);
    if (goal && !prose.includes(goal[1].slice(0, 6))) issues.push(`missing_task:${goal[1].slice(0, 6)}`);
    const move = /(.+?)从(.+?)走到(.+?)。/.exec(clause);
    if (move && !(prose.includes(move[2]) && prose.includes(move[3]))) issues.push('missing_move');
  }
  const allowed = new Set((String(draft ?? '').match(/[0-9]+/g) ?? []));
  for (const number of prose.match(/[0-9]+/g) ?? []) {
    if (!allowed.has(number)) issues.push(`invented_number:${number}`);
  }
  for (const word of FILLER) if (prose.includes(word)) issues.push(`filler:${word}`);
  if (/[「“『]/.test(prose) && !/[「“『]/.test(String(draft ?? ''))) issues.push('added_dialogue');
  if (name && !prose.includes(name)) issues.push('missing_viewpoint');
  return issues;
}

export async function generateCandidate(args: any): Promise<any> {
  const started = performance.now();
  const name = viewpointName(args.inputText) || (args.state ? '' : '');
  const draft = args.draft || draftFromFacts(args.committed, args.delta?.timeAdvance ?? null);
  const prompt = buildPagePrompt(name, draft, args.mode === 'repair' ? 'repair' : 'scene');
  const attempts = [];
  const issues = [];
  let text = '';
  for (let attempt = 0; attempt < 2 && !text; attempt += 1) {
    const asked = attempt === 0 ? prompt : `${prompt}\n纠正：上一稿没有照住草稿，只写这些事实：${draft}`;
    const before = performance.now();
    let raw = '';
    try {
      raw = await args.engine.complete(asked, {
        maxTokens: 320,
        temperature: attempt === 0 ? 0.4 : 0.2,
        signal: args.signal,
      });
    } catch (error) {
      if ((error as Error)?.name === 'AbortError') throw error;
      issues.push(`generation_failed:${(error as Error)?.message ?? error}`);
    }
    const candidate = String(raw ?? '').trim();
    const found = candidate ? checkProse(candidate, { draft, name }) : ['empty'];
    attempts.push({ attempt, prompt: asked, raw: candidate, issues: found,
      ms: Math.round(performance.now() - before) });
    args.onProgress?.({ status: 'draft', text: candidate || undefined,
      verified: found.length === 0, elapsedMs: performance.now() - started });
    if (candidate && found.length === 0) text = candidate;
    else issues.push(...found.map((issue) => `${issue}@${attempt}`));
  }
  const accepted = Boolean(text);
  if (!accepted) text = draft;
  return {
    text,
    accepted,
    rawAttempts: attempts,
    issues,
    timings: { totalMs: Math.round(performance.now() - started) },
    strategyVersion: STRATEGY_VERSION,
    draft,
  };
}
