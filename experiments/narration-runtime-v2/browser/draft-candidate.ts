// Lane 10 draft-rewrite candidate: the page hands over its settled-fact draft,
// the model rewrites it as prose and may not add anything.
//
// The prompt is byte-identical to the one used for training
// (`src/build_draft_pairs.py`):  【事实草稿】/【地点】/【在场】/【要求】/【正文】
// The draft text itself is rendered by `draftFromFacts`, which mirrors the
// Python renderer; if these drift, the model sees a shape it was not trained on.
//
// Output contract is the shared runner's `generateCandidate` result. This file
// does not decide product quality; 09 runs it, 01 reads the prose.

const STRATEGY_VERSION = 'lane10-draft-v1';

const UNIT_CN = {
  second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年',
};

const REQUIREMENT_SHORT = '把草稿改写成正文，三句以内。只写草稿里的事实；'
  + '不新增人物、对白、物品、动作、往事、数字，不解释情绪。';

function draftLine(fact) {
  if (fact.kind === 'moved') return `${fact.name}从${fact.from}走到${fact.to}。`;
  if (fact.kind === 'task_achieved') return `${fact.name}完成了「${fact.goal}」。`;
  if (fact.kind === 'personality_changed') return `${fact.name}多了一条个性：${fact.text}。`;
  if (fact.kind === 'sanity_changed') return `${fact.name}的精神值从${fact.from}变成${fact.to}。`;
  return '';
}

export function draftFromFacts(committed, timeAdvance) {
  const parts = [];
  for (const fact of committed?.facts ?? []) {
    const line = draftLine(fact);
    if (line) parts.push(line);
  }
  const duration = timeAdvance?.duration;
  if (duration && duration.amount > 0) {
    parts.push(`时间过去${duration.amount}${UNIT_CN[duration.unit]}。`);
  }
  return parts.join('');
}

function sceneOf(state, inputText) {
  const match = /【视角】[^（(]*[（(]([^）)]+)[）)]/.exec(String(inputText ?? ''));
  const viewpoint = match ? match[1].trim() : null;
  const names = {};
  for (const [id, entry] of Object.entries(state?.initial?.characters ?? {})) names[id] = entry.name;
  const viewpointId = Object.keys(names).find((id) => names[id] === viewpoint) ?? null;
  const containerId = viewpointId ? state.characters?.[viewpointId]?.position?.containerId ?? null : null;
  const location = containerId ? state.initial?.locations?.[containerId]?.name ?? null : null;
  const present = Object.entries(state?.characters ?? {})
    .filter(([id, actor]) => id !== viewpointId && actor.position?.containerId === containerId)
    .map(([id]) => names[id]).filter(Boolean);
  return { viewpoint, location, present };
}

export function buildDraftPrompt({ draft, place, present }) {
  const lines = [`【事实草稿】${draft || '这一回合没有结算出变化。'}`];
  if (place) lines.push(`【地点】${place}`);
  if (present?.length) lines.push(`【在场】${present.join('、')}`);
  lines.push(`【要求】${REQUIREMENT_SHORT}`);
  lines.push('【正文】');
  return lines.join('\n');
}

const STOP_WORDS = ['空气里', '气氛', '仿佛', '似乎', '像是', '好像', '显得', '某种'];

/** Cheap, conservative checks. They are not the product gate (01 owns it):
 * a sentence must carry every draft fact and must not invent a name or a
 * number that the draft and the scene do not contain. */
export function checkDraftProse(text, { draft, place, present, licensed }) {
  const issues = [];
  const plain = String(text ?? '');
  if (!plain.trim()) issues.push('empty');
  if (plain.length > 220) issues.push('too_long');
  if (/\n{2,}/.test(plain)) issues.push('multiple_paragraphs');
  for (const fact of licensed?.facts ?? []) {
    if (fact.kind === 'moved' && (!plain.includes(fact.from) || !plain.includes(fact.to))) {
      issues.push(`missing_places:${fact.name}`);
    }
    if (fact.kind === 'task_achieved' && !plain.includes(fact.goal.slice(0, 6))) {
      issues.push(`missing_task:${fact.name}`);
    }
    if (fact.kind === 'personality_changed' && !plain.includes(fact.text.slice(0, 4))) {
      issues.push(`missing_trait:${fact.name}`);
    }
    if (fact.kind === 'sanity_changed'
      && !plain.includes(String(fact.to)) && !plain.includes(String(fact.from))) {
      issues.push(`missing_sanity:${fact.name}`);
    }
  }
  const allowedNumbers = new Set((String(plain).match(/[0-9]+/g) ?? []));
  const draftNumbers = new Set((`${draft} ${place ?? ''} ${(present ?? []).join('')}`.match(/[0-9]+/g) ?? []));
  for (const number of allowedNumbers) {
    if (!draftNumbers.has(number)) issues.push(`invented_number:${number}`);
  }
  for (const word of STOP_WORDS) {
    if (plain.includes(word)) issues.push(`filler:${word}`);
  }
  return issues;
}

export function fallbackProse(draft) {
  return draft || '这一回合没有结算出变化。';
}

export async function generateCandidate(args) {
  const started = performance.now();
  const scene = sceneOf(args.state, args.inputText);
  const draft = draftFromFacts(args.committed, args.delta?.timeAdvance ?? null);
  const prompt = buildDraftPrompt({ draft, place: scene.location, present: scene.present });
  const attempts = [];
  const issues = [];
  let text = '';
  for (let attempt = 0; attempt < 2 && !text; attempt += 1) {
    const asked = attempt === 0 ? prompt
      : `${prompt}【纠正】上一句没有照住草稿。只写这些事实：${draft}`;
    const before = performance.now();
    let raw = '';
    try {
      raw = await args.engine.complete(asked, {
        maxTokens: 160,
        temperature: attempt === 0 ? 0.5 : 0.3,
        signal: args.signal,
      });
    } catch (error) {
      if (error?.name === 'AbortError') throw error;
      issues.push(`generation_failed:${error?.message ?? error}`);
    }
    const candidate = String(raw ?? '').trim();
    const found = candidate ? checkDraftProse(candidate, {
      draft, place: scene.location, present: scene.present,
      licensed: { facts: args.committed?.facts ?? [] },
    }) : ['empty'];
    attempts.push({ attempt, prompt: asked, raw: candidate, issues: found,
      ms: Math.round(performance.now() - before) });
    args.onProgress?.({ status: 'draft', text: candidate || undefined,
      verified: found.length === 0, elapsedMs: performance.now() - started });
    if (candidate && found.length === 0) text = candidate;
    else issues.push(...found.map((issue) => `${issue}@${attempt}`));
  }
  const accepted = Boolean(text);
  if (!accepted) text = fallbackProse(draft);
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
