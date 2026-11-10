// Lane 10's browser candidate: one settled fact per model call.
//
// Self-contained on purpose: the shared runner imports this file directly and
// there is no import of another lane's tree. `engine.complete(prompt)` applies
// the GGUF chat template with a single user turn, which is exactly the shape
// the weights were trained with (Qwen2.5 default system message).
//
// The program owns the facts and the order. The model writes 1-2 sentences for
// the fact it is given. Every sentence is checked; a failed beat is retried
// once with a pointed correction, then replaced by a factual sentence and
// reported as `accepted: false`. Nothing here is a quality verdict.

const STRATEGY_VERSION = 'lane10-beat-v1';

const UNIT_CN = {
  second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年',
};

const EXAMPLES = {
  moved: ['诺诺从器材棚门外走进器材棚',
    '诺诺把枪口压低，从器材棚门外走进去，靴底碾过一层薄灰。'],
  task_achieved: ['芬格尔完成了「把相机收进柜子」',
    '芬格尔把相机塞进柜子，锁扣合上，这件事就算做完了。'],
  personality_changed: ['苏茜的个性多了一条：愿意在交火里先开口',
    '苏茜先开了口，声音不大，却没有再退。'],
  sanity_changed: ['凯撒的精神值从60变成54',
    '凯撒按住额角缓了一会儿，精神值落到54。'],
  time: ['时间过去5分钟', '五分钟过去，回廊尽头始终没有脚步声。'],
};

const WRITING = {
  moved: '写这个人从旧位置走到新位置的过程；可以带一个环境细节；不要写别的事、别人的动作或对白。',
  task_achieved: '写她做成这件事的结果或最后一个动作，让人看出这件事已经做完；不要写下一步，不要写别人。',
  personality_changed: '用一个动作或一句短话表现这个变化；不要写别的场景、别人的事。',
  sanity_changed: '写精神值从多少变成多少，两个数字都要出现，落在身体或感觉上；不要写别的场景。',
  time: '写出这段时间过去了，落在环境或动作上；不要写新的事情发生。',
};

const DONE = /(查清|找到|找着|查完|问清|完成|做完|搞定|办完|了结|核对完|比对完|确认|合上|放回|收好|对上|交出去|拿到|记下)/;
const MOVE = /(走到|走向|走进|走入|走上|走进来|进来|出去|回到|退到|退回|往.{0,6}走|下楼|上楼|转向|挪到|跨进|跨出|退开|离开|移到|过来|过去)/;
const STOP = new Set(['这个', '那个', '一件', '事情', '自己', '已经', '没有', '什么', '一直',
  '一个', '的是', '了的', '里的', '把', '了', '的', '在', '和', '与',
  '上', '下', '里', '个', '这', '那', '他', '她', '它', '们', '就', '也']);

const clip = (text, limit) => String(text ?? '').replace(/\s+/g, ' ').trim().slice(0, limit);

function pieces(text) {
  const out = [];
  for (let index = 0; index + 1 < text.length; index += 1) {
    const piece = text.slice(index, index + 2);
    if (!STOP.has(piece) && !/[，。、：；「」（）]/.test(piece)) out.push(piece);
  }
  return out;
}

function overlap(text, phrase, need = 2) {
  let hits = 0;
  for (const piece of pieces(phrase)) if (text.includes(piece)) hits += 1;
  return hits >= need;
}

function parseViewpoint(inputText) {
  const match = /【视角】[^（(]*[（(]([^）)]+)[）)]/.exec(String(inputText ?? ''));
  return match ? match[1].trim() : null;
}

function sceneOf(state, inputText) {
  const viewpoint = parseViewpoint(inputText);
  const names = {};
  for (const [id, entry] of Object.entries(state?.initial?.characters ?? {})) names[id] = entry.name;
  const viewpointId = Object.keys(names).find((id) => names[id] === viewpoint) ?? null;
  const containerId = viewpointId ? state.characters?.[viewpointId]?.position?.containerId ?? null : null;
  const location = containerId ? state.initial?.locations?.[containerId]?.name ?? null : null;
  const present = Object.entries(state?.characters ?? {})
    .filter(([id, actor]) => id !== viewpointId && actor.position?.containerId === containerId)
    .map(([id]) => names[id]).filter(Boolean);
  const objects = Object.entries(state?.items ?? {})
    .filter(([, item]) => item.position?.containerId === containerId)
    .map(([id]) => state.initial?.items?.[id]?.name).filter(Boolean);
  const notes = [];
  const placeNotes = state?.initial?.locations?.[containerId]?.appearance;
  if (Array.isArray(placeNotes)) notes.push(...placeNotes.map((note) => clip(note, 40)).slice(0, 2));
  return { viewpoint, location, present, objects: objects.slice(0, 3), notes };
}

function beatPrompt(scene, beat) {
  const lines = [];
  lines.push(`【本拍事实】${beat.phrase}`);
  lines.push(`【主体】${beat.subject}：这一段的动作属于${beat.subject}，不要换成别人。`);
  let where = scene.viewpoint ?? beat.subject;
  if (scene.location) where += `在${scene.location}`;
  lines.push(`【场景】${where}`);
  for (const note of scene.notes) lines.push(`　${scene.location ?? ''}：${note}`);
  const others = scene.present.filter((name) => name !== beat.subject);
  if (others.length) lines.push(`【在场】${others.join('、')}（只作为在场的人，不写他们的动作和对白）`);
  if (scene.objects.length) lines.push(`【手边】${scene.objects.join('、')}`);
  if (beat.time) lines.push(`【时间】${beat.time}过去了`);
  const [exampleFact, exampleText] = EXAMPLES[beat.kind];
  lines.push(`【示例】事实：${exampleFact}。正文：${exampleText}`);
  lines.push(`【写法】一到两句。${WRITING[beat.kind]}`);
  lines.push('【正文】');
  return lines.join('');
}

function check(beat, text) {
  const issues = [];
  const named = text.includes(beat.subject);
  if (!named) issues.push('subject_missing');
  if (beat.kind === 'moved') {
    if (!text.includes(beat.from)) issues.push('origin_missing');
    if (!text.includes(beat.to)) issues.push('target_missing');
    if (!MOVE.test(text)) issues.push('no_movement_verb');
  } else if (beat.kind === 'task_achieved') {
    if (!DONE.test(text)) issues.push('no_completion_verb');
    if (!overlap(text, beat.goal)) issues.push('goal_not_recognisable');
  } else if (beat.kind === 'personality_changed') {
    if (!overlap(text, beat.text)) issues.push('trait_not_recognisable');
  } else if (beat.kind === 'sanity_changed') {
    if (String(beat.to) !== '' && text.includes(String(beat.to))) {
      // number is the strongest form; nothing else needed
    } else {
      const up = /(回升|上升|恢复|稳住|松开|缓过来|散了|暖|安定|踏实)/.test(text);
      const down = /(下降|降到|落到|掉到|沉|发紧|发凉|收紧|压得|闷|散了一层|撑不住|发白)/.test(text);
      if (!(beat.to > beat.from ? up : down)) issues.push('direction_missing');
    }
  } else if (beat.kind === 'time') {
    if (!text.includes(String(beat.amount))) issues.push('amount_missing');
  }
  if (text.length > 120) issues.push('too_long');
  if (text.includes('\n')) issues.push('multiple_paragraphs');
  return issues;
}

function fallbackSentence(beat) {
  if (beat.kind === 'moved') return `${beat.subject}从${beat.from}走到${beat.to}。`;
  if (beat.kind === 'task_achieved') return `${beat.subject}把这件事做完了：${beat.goal}。`;
  if (beat.kind === 'personality_changed') return `${beat.subject}没有退，按新下的决心把这一步走完。`;
  if (beat.kind === 'sanity_changed') return `${beat.subject}缓了一会儿，精神值${beat.to}。`;
  return `${beat.time}过去，屋子里没有别的声音。`;
}

function toBeats(committed, delta, scene) {
  const beats = [];
  const facts = Array.isArray(committed?.facts) ? committed.facts : [];
  for (const fact of facts) {
    if (fact.kind === 'moved') {
      beats.push({
        id: fact.id, kind: 'moved', subject: fact.name, from: fact.from, to: fact.to,
        phrase: `${fact.name}从${fact.from}走到${fact.to}`,
      });
    } else if (fact.kind === 'task_achieved') {
      beats.push({
        id: fact.id, kind: 'task_achieved', subject: fact.name, goal: fact.goal,
        phrase: `${fact.name}完成了「${fact.goal}」`,
      });
    } else if (fact.kind === 'personality_changed') {
      beats.push({
        id: fact.id, kind: 'personality_changed', subject: fact.name, text: fact.text,
        phrase: `${fact.name}的个性多了一条：${fact.text}`,
      });
    } else if (fact.kind === 'sanity_changed') {
      beats.push({
        id: fact.id, kind: 'sanity_changed', subject: fact.name, from: fact.from, to: fact.to,
        phrase: `${fact.name}的精神值从${fact.from}变成${fact.to}`,
      });
    }
  }
  const duration = delta?.timeAdvance?.duration;
  if (duration && duration.amount > 0) {
    const subject = scene.viewpoint ?? beats[0]?.subject ?? '屋子里的人';
    beats.push({
      id: 'time', kind: 'time', subject, amount: duration.amount,
      time: `${duration.amount}${UNIT_CN[duration.unit]}`,
      phrase: `时间过去${duration.amount}${UNIT_CN[duration.unit]}`,
    });
  }
  return beats;
}

export async function generateCandidate(args) {
  const started = performance.now();
  const state = args.state;
  const delta = args.delta ?? null;
  const scene = sceneOf(state, args.inputText);
  const beats = toBeats(args.committed, delta, scene);
  const attempts = [];
  const issues = [];
  const sentences = [];
  let accepted = true;
  for (const beat of beats) {
    if (args.signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    const prompt = beatPrompt(scene, beat);
    let chosen = null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const correction = attempt === 0 ? '' : attempt === 1
        ? `【纠正】上一句没有守住事实；主语必须是${beat.subject}，事实是：${beat.phrase}。`
        : (beat.kind === 'task_achieved'
          ? `【纠正】把「${beat.goal}」这几个字原样写进句子，再写完成它的最后一个动作。`
          : beat.kind === 'personality_changed'
            ? `【纠正】把「${beat.text}」这几个字原样写进句子，用动作带出来。`
            : `【纠正】只写这一句事实：${beat.phrase}。主语是${beat.subject}。`);
      const asked = prompt + correction;
      const before = performance.now();
      let raw = '';
      try {
        raw = await args.engine.complete(asked, {
          maxTokens: 96,
          temperature: attempt === 0 ? 0.6 : 0.3,
          signal: args.signal,
        });
      } catch (error) {
        if (error?.name === 'AbortError') throw error;
        issues.push(`${beat.id}: generation_failed:${error?.message ?? error}`);
      }
      const text = clip(raw, 200);
      const found = check(beat, text);
      attempts.push({ beatId: beat.id, attempt, prompt: asked, raw: text,
        issues: found, ms: Math.round(performance.now() - before) });
      args.onProgress?.({ status: 'beat', text: text || undefined, verified: found.length === 0,
        elapsedMs: performance.now() - started, beatId: beat.id });
      if (text && found.length === 0) {
        chosen = text;
        break;
      }
      issues.push(...found.map((issue) => `${beat.id}: ${issue}`));
    }
    if (!chosen) {
      accepted = false;
      chosen = fallbackSentence(beat);
      issues.push(`${beat.id}: template_fallback`);
    }
    sentences.push(chosen);
  }
  return {
    text: sentences.join('\n\n'),
    accepted,
    rawAttempts: attempts,
    issues,
    timings: { totalMs: Math.round(performance.now() - started), beats: beats.length },
    strategyVersion: STRATEGY_VERSION,
    beats: beats.map((beat) => beat.id),
  };
}
