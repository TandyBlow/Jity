/** Constrained beat writer.
 *
 * One model call per beat, with only the licensed material for that beat in
 * the prompt. The model writes language; the fact list is frozen by the
 * planner. A reply that fails beat verification is retried once with the
 * missing facts named, then the caller falls back to `realizeBeat` — never to
 * a fact list.
 */
import type { InferenceEngine } from '../../../runtime/engine';
import { isAbortError } from '../../../runtime/engine';
import type { BeatDirective, SceneFact, SceneSkeleton } from './types';

export interface BeatPromptOptions {
  instruction?: string | null;
  sanityStyle: 'direction' | 'number';
  /** Longer detail budget for the beat prompt. */
  maxDetails?: number;
}

const UNIT_LABEL: Record<string, string> = {
  second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年',
};

export function factDirective(fact: SceneFact, sanityStyle: 'direction' | 'number'): string {
  switch (fact.kind) {
    case 'time': {
      const { amount, unit } = fact.advance.duration;
      const label = unit === 'hour' ? `${amount}小时` : unit === 'month' ? `${amount}个月` : `${amount}${UNIT_LABEL[unit]}`;
      return `本回合经过${label}（时间背景，不必写进正文；写到时长时不得改错）`;
    }
    case 'move': {
      // A location name can be missing when the packet only knows ids; an empty
      // «从到» would be copied verbatim by a small model («方向是从到»).
      const from = (fact.from ?? '').trim();
      const to = (fact.to ?? '').trim();
      const where = from && to ? `从${from}到${to}` : to ? `在${to}` : from ? `离开${from}` : '换了位置';
      return `${fact.name}${where}（${from && to ? '方向必须是从到；' : ''}${fact.entityKind === 'item' ? '这是物品' : '这是人物'}）`;
    }
    case 'task_achieved':
      return `「${fact.goal}」这件事，${fact.name}已经办完了（目标原话要出现，完成的意思要读得出来）`;
    case 'subtask_added':
      return `${fact.name}接下来还有一件事：${fact.goal}（这是新目标，还没有完成）`;
    case 'personality_changed':
      return fact.removed
        ? `${fact.name}现在不再${fact.supersededTexts.join('；')}`
        : `${fact.name}现在${fact.text}（直接写成人物当下的样子，不要写“个性变化”之类的说明）`;
    case 'appearance_changed':
      return fact.removed
        ? `${fact.name}现在不再是${fact.supersededTexts.join('；')}`
        : `${fact.name}现在${fact.text}（直接写看到的样子）`;
    case 'sanity_changed':
      return sanityStyle === 'number'
        ? `${fact.name}的精神数值从 ${fact.from} 变成 ${fact.to}（正文必须写出数值变化）`
        : `${fact.name}的精神状态${fact.to < fact.from ? '下降' : fact.to > fact.from ? '回升' : '没有变化'}（写成体感，不要写数字）`;
    case 'item_present':
      return `${fact.name}现在在${fact.container}`;
    case 'item_discovered':
      return `${fact.name}现在在${fact.container}，视角人物此前没有留意（不要写成他早已知晓）`;
    case 'result': {
      // With a structured record the verifier compares meaning (executor,
      // recipient, outcome direction), so the prompt asks for the outcome in
      // the model's own words instead of a verbatim copy. Free-text-only results
      // still need their sentence because there is nothing else to check.
      if (fact.structured) {
        const outcome = { completed: '行动完成', failed: '行动失败', blocked: '行动被阻止', unaffected: '目标没有受到影响' }[fact.structured.outcome];
        const who = fact.structured.actor ? `由${fact.structured.actor}` : '';
        const on = fact.structured.target ? `，对象是${fact.structured.target}` : '';
        const what = fact.structured.action ? `，动作是${fact.structured.action}` : '';
        return `结算结果：${who}${what}${on}，${outcome}（用自己的话写清谁做了什么、结果朝哪个方向；人、对象和方向不能改，措辞可以改）`;
      }
      return `结算原话：「${fact.text}」（正文要原样写出这一句，可以前后加动作或环境，但这句里的人、事、措辞都不要改）`;
    }
    case 'at':
      return `${fact.name}在${fact.location}`;
    default:
      return '';
  }
}

function clip(text: string, max: number): string {
  const clean = text.replace(/\s+/gu, ' ').trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max);
  const punctuation = Math.max(cut.lastIndexOf('，'), cut.lastIndexOf('、'), cut.lastIndexOf('；'));
  return `${(punctuation > max * 0.5 ? cut.slice(0, punctuation) : cut).replace(/[，、；]+$/u, '')}…`;
}

export function buildBeatPrompt(
  beat: BeatDirective,
  scene: SceneSkeleton,
  prior: string | null,
  options: BeatPromptOptions,
): string {
  const facts = beat.factIds
    .map((id) => scene.facts.find((fact) => fact.id === id))
    .filter((fact): fact is SceneFact => Boolean(fact))
    .map((fact) => factDirective(fact, options.sanityStyle))
    .filter(Boolean);
  const details = scene.licensed.details
    .map((detail) => clip(detail, 44))
    .filter((detail) => detail.length > 1)
    .slice(0, options.maxDetails ?? 10);
  // Keep the beat prompt scoped: 8 objects + 10 details made the 1.7B writer
  // enumerate the scene inventory instead of writing the beat's fact.
  const present = scene.present.slice(0, 3).map((person) => `${person.name}${person.note ? `（${clip(person.note, 24)}）` : ''}`);
  const objects = scene.objects.slice(0, 2).map((object) => `${object.name}${object.note ? `（${clip(object.note, 22)}）` : ''}`);
  const lastPrior = prior
    ? clip(prior.split(/\n+/u).filter(Boolean).slice(-1)[0] ?? '', 60)
    : '';
  const lines = [
    '你是中文小说叙事者。只写下面这一段，不要解释，不要写标题。',
    `本段必须写出的事实：${facts.length ? '' : '（本段只做场景过渡，不新增事实）'}`,
    ...(facts.length ? [] : ['本段只写视角人物此刻的一个动作或一处注意，一到两句就够，不要把场景材料清点一遍。']),
    ...facts.map((fact) => `- ${fact}`),
    ...(scene.time && !beat.factIds.some((id) => scene.facts.find((fact) => fact.id === id)?.kind === 'time')
      ? [factDirective({ id: 'time-context', kind: 'time', mandatory: false, visibility: 'scene', advance: scene.time }, options.sanityStyle)]
      : []),
    // The declared action comes after the facts. With the one-beat plan a single
    // call carries the time fact and this instruction; when the instruction was
    // printed first (926e/5810), the model wrote the action and dropped the time.
    // It is still an instruction, not an outcome: the attempt may be written, a
    // settled success may not.
    ...(beat.index === 0 && scene.previousAction
      ? [`玩家这一回合的指令：${String(scene.previousAction).replace(/^我(?!们)/u, scene.viewpoint.name)}`,
         '正文要写出他做了或试着做了这件事；结果只按上面已结算的事实写，没有结算成功的事不要写成成功。']
      : []),
    '',
    '场景材料（只可使用这些）：',
    `- 视角人物：${scene.viewpoint.name}`,
    `- 地点：${scene.place.name}${scene.place.note ? `；${clip(scene.place.note, 60)}` : ''}`,
    ...(present.length ? [`- 在场：${present.join('；')}`] : []),
    ...(objects.length ? [`- 可见物品：${objects.join('；')}`] : []),
    ...(details.length ? [`- 已登记细节：${details.join('；')}`] : []),
    ...(lastPrior ? [`已写内容（不要重复其中的句子）：${lastPrior}`] : []),
    '',
    '要求：',
    `- 只写 ${Math.max(1, Math.round(beat.minChars / 18))}-${Math.max(2, Math.round(beat.maxChars / 14))} 句，${beat.minChars}-${beat.maxChars} 字，短句，用句号收尾。`,
    '- 只表达上面的事实，不要新增人物、地点、物品、天气、家具、往事、线索或承诺。',
    '- 不要把「玩家这一回合的指令」写成已经办成的结果；结算里没有的结果就不要写。',
    '- 不要写“完成了一项任务”“个性发生了变化”“新增一条待办”这类状态说明，直接写发生了什么。',
    '- 「结算原话」要原样放进正文；不要换同义词，也不要把它拆成两句话。',
    '- 可以写细微动作和措辞润色；不知道性别时用名字或不写代词。',
    '- 不要复述上一段，不要写“他说”“她想”以外的解释性总结。',
    '- 把它写成一幕，不是写成清单：只挑一处此刻最显眼的细节，用视角人物的注意力带出来；不要把「可见物品」「已登记细节」逐条抄进正文。',
    options.instruction ? `- ${options.instruction}` : '',
    '',
    '只输出正文：',
  ].filter((line) => line !== '');
  return lines.join('\n');
}

export interface ModelBeatResult {
  text: string;
  raw: string;
  prompt: string;
  attempts: number;
  ms: number;
  feedback: string | null;
}

/** A small model often answers with a JSON object or a list even when asked for
 * prose. Take its text field when that is unambiguous; otherwise leave the raw
 * text for the beat gate to judge. */
function unwrapStructured(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return raw;
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    const pick = (value: unknown): string | null => {
      if (typeof value === 'string') return value;
      if (Array.isArray(value)) {
        const parts = value.map(pick).filter((part): part is string => Boolean(part && part.trim()));
        return parts.length ? parts.join(String.fromCharCode(10, 10)) : null;
      }
      if (value && typeof value === 'object') {
        const record = value as Record<string, unknown>;
        for (const key of ['text', 'narration', '正文', 'content', 'paragraphs']) {
          const found = pick(record[key]);
          if (found) return found;
        }
      }
      return null;
    };
    return pick(parsed) ?? raw;
  } catch {
    return raw;
  }
}

/** Strip wrappers a small model adds; the beat gate still checks the facts. */
const THREE_NEWLINES = new RegExp(String.fromCharCode(10) + '{3,}', 'gu');

export function sanitizeBeat(raw: string): string {
  const NL = String.fromCharCode(10);
  const marker = String.fromCharCode(0x3010) + '正文' + String.fromCharCode(0x3011);
  const afterMarker = raw.includes(marker) ? raw.split(marker).pop() ?? raw : raw;
  // Remove fence markers first, then read a structured answer: a fenced JSON
  // object is still the model's text, not a code sample to discard.
  const unfenced = afterMarker.replace(/```[a-zA-Z]*/gu, '').replace(/```/gu, '');
  const stripped = unwrapStructured(unfenced)
    .replace(/^\s*(正文|叙事|输出|片段)[:：]\s*/u, '')
    .replace(/【[^】]{1,10}】/gu, '')
    .replace(/\*\*/gu, '')
    .replace(/[ 	]+/gu, ' ')
    .replace(THREE_NEWLINES, NL + NL)
    .trim();
  return stripped;
}

export async function composeBeatWithModel(
  engine: InferenceEngine,
  beat: BeatDirective,
  scene: SceneSkeleton,
  prior: string | null,
  options: {
    sanityStyle: 'direction' | 'number';
    instruction?: string | null;
    maxTokens: number;
    temperature: number;
    timeoutMs: number;
    signal?: AbortSignal;
    onProgress?: (progress: { text: string; elapsedMs: number }) => void;
    feedback?: string | null;
  },
): Promise<ModelBeatResult> {
  const started = performance.now();
  const prompt = buildBeatPrompt(beat, scene, prior, {
    instruction: [options.instruction, options.feedback].filter(Boolean).join(' ') || null,
    sanityStyle: options.sanityStyle,
    // The 05e7 beats catalogued every licensed detail ("弹匣内剩3发…", "电量灯不亮…").
    // A beat needs the details its own facts name, not the whole scene inventory.
    maxDetails: 2,
  });
  const raw = await engine.complete(prompt, {
    maxTokens: options.maxTokens,
    temperature: options.temperature,
    timeoutMs: options.timeoutMs,
    signal: options.signal,
    onProgress: options.onProgress
      ? (progress) => options.onProgress?.({ text: sanitizeBeat(progress.raw), elapsedMs: performance.now() - started })
      : undefined,
  });
  return {
    text: sanitizeBeat(raw),
    raw,
    prompt,
    attempts: 1,
    ms: performance.now() - started,
    feedback: options.feedback ?? null,
  };
}

export { isAbortError };
