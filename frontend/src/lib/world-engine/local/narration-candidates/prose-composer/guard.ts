/** License checks for generated prose.
 *
 * The composer only builds sentences from the skeleton, but a template bug or
 * a hostile name can still smuggle in a new prop, a past event or a promise.
 * These checks are deliberately mechanical: they do not score style, they only
 * refuse content the skeleton did not license.
 */

import type { ProseActor, ProseItem, ProseLocation, ProseScene } from './types';
import { overlapRatio, splitSentences } from './support';

/** Props and weather that must exist in the supplied scene text before prose
 * may mention them. Body parts and abstract nouns are not listed. */
const PROP_NOUNS = [
  '椅子', '桌子', '桌上', '盒子', '杯子', '茶', '灯', '钟', '伞', '雨', '雪', '风',
  '阳光', '月光', '血', '伤口', '枪', '钥匙', '书', '纸', '笔', '电话', '地图',
  '旗', '绳', '担架', '相机', '电池', '刀', '烟', '酒', '花', '树', '云', '雾',
  '台阶', '走廊', '楼梯', '房间', '墙', '地板', '天花板', '喷泉', '桥', '车',
  '狗', '猫', '窗', '门', '床', '柜', '箱', '包', '袋', '照片', '信',
];

const PAST_MARKERS = [
  '十年前', '当年', '从前', '曾经', '小时候', '那年', '那天', '去年', '上次', '上回',
  '记得', '回忆', '后来', '早就', '幼时', '少年时',
];

const PROMISE_MARKERS = [
  '答应', '保证', '承诺', '发誓', '一定会', '我会', '明天', '下次', '以后',
  '等你', '等我', '说好', '约好',
];

/** Stock gestures that make every scene sound the same. The composer never
 * generates them; the guard catches accidental copies from input clauses. */
const STOCK_PHRASES = [
  '愣住', '愣了', '一怔', '一惊', '不由得', '不禁', '叹了口气', '深吸一口气',
  '心跳', '屏住呼吸', '苦笑', '皱了皱眉', '瞪大了眼睛', '猛地', '竟然', '居然',
  '仿佛', '似乎', '微微一笑', '点了点头',
];

export interface LicenseBook {
  /** Every licensed substring, used to clear a prop or marker. */
  text: string;
  actorNames: string[];
  locationNames: string[];
  itemNames: string[];
}

function joinText(parts: Array<string | null | undefined>): string {
  return parts.filter((part): part is string => Boolean(part)).join('\n');
}

function actorText(actor: ProseActor): string {
  return joinText([actor.name, actor.references?.join(''), actor.appearance?.join('')]);
}

function itemText(item: ProseItem): string {
  return joinText([item.name, item.details?.join('')]);
}

function locationText(location: ProseLocation | null | undefined): string {
  if (!location) return '';
  return joinText([location.name, location.parentName, location.details?.join('')]);
}

export function buildLicense(scene: ProseScene): LicenseBook {
  const beatText = scene.beats.map((beat) => {
    switch (beat.kind) {
      case 'scene': return joinText([beat.detail, beat.factText]);
      case 'move': return joinText([beat.from, beat.to, beat.manner, beat.factText]);
      case 'stay': return joinText([beat.location, beat.factText]);
      case 'leave': return joinText([beat.to, beat.factText]);
      case 'arrive': return joinText([beat.location, beat.factText]);
      case 'item': return joinText([beat.detail, beat.note, beat.container, beat.factText]);
      case 'task': return joinText([beat.label, beat.factText]);
      case 'subtask': return joinText([beat.goal, beat.parentGoal, beat.factText]);
      case 'personality': return joinText([beat.text, beat.factText]);
      case 'appearance': return joinText([beat.subjectName, beat.text, beat.previous, beat.factText]);
      case 'sanity': return beat.factText;
      case 'action': return beat.text;
      case 'line': return beat.text;
      case 'silence': return null;
      case 'time': return joinText([beat.text, beat.unit]);
      case 'noChange': return beat.text;
      default: return null;
    }
  });
  const text = joinText([
    locationText(scene.location),
    locationText(scene.parentLocation),
    scene.locationChange?.added?.join(''),
    scene.locationChange?.removed?.join(''),
    scene.cast.map(actorText).join('\n'),
    (scene.items ?? []).map(itemText).join('\n'),
    scene.toldFacts?.join('\n'),
    beatText.join('\n'),
  ]);
  return {
    text,
    actorNames: scene.cast.map((actor) => actor.name),
    locationNames: [scene.location.name, scene.parentLocation?.name].filter((name): name is string => Boolean(name)),
    itemNames: (scene.items ?? []).map((item) => item.name),
  };
}

export interface GuardFinding {
  kind: 'unlicensed_detail' | 'unlicensed_past' | 'unlicensed_promise' | 'stock_phrase';
  detail: string;
  sentence: string;
}

export function guardSentence(sentence: string, license: LicenseBook): GuardFinding | null {
  const body = sentence.trim();
  if (!body) return null;
  // Chinese has no word boundaries; strip a few closed-class collisions before
  // the prop check (分钟 is a duration, not a clock; 我们 is a pronoun, not a door).
  const probe = body
    .replace(/分钟/gu, '')
    .replace(/[我你他她它]们/gu, '');
  for (const word of STOCK_PHRASES) {
    if (body.includes(word) && !license.text.includes(word)) {
      return { kind: 'stock_phrase', detail: `stock phrase ${word}`, sentence: body };
    }
  }
  for (const noun of PROP_NOUNS) {
    if (probe.includes(noun) && !license.text.includes(noun)) {
      return { kind: 'unlicensed_detail', detail: `unlicensed prop ${noun}`, sentence: body };
    }
  }
  for (const marker of PAST_MARKERS) {
    if (body.includes(marker) && !license.text.includes(marker)) {
      return { kind: 'unlicensed_past', detail: `unlicensed past marker ${marker}`, sentence: body };
    }
  }
  for (const marker of PROMISE_MARKERS) {
    if (body.includes(marker) && !license.text.includes(marker)) {
      return { kind: 'unlicensed_promise', detail: `unlicensed promise ${marker}`, sentence: body };
    }
  }
  return null;
}

export function guardParagraph(
  paragraph: string,
  license: LicenseBook,
): { clean: string; findings: GuardFinding[] } {
  const findings: GuardFinding[] = [];
  const kept: string[] = [];
  for (const sentence of splitSentences(paragraph)) {
    const finding = guardSentence(sentence, license);
    if (finding) findings.push(finding);
    else kept.push(sentence);
  }
  return { clean: kept.join(''), findings };
}

/** Echo detection against the previous accepted turn. */
export function echoOfPrior(paragraph: string, priorText: string | null | undefined): number {
  if (!priorText) return 0;
  let worst = 0;
  for (const prior of splitSentences(priorText)) {
    if (prior.length < 8) continue;
    worst = Math.max(worst, overlapRatio(paragraph, prior));
  }
  return worst;
}
