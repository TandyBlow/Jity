/** Micro targets: rules first, then the int8 pair scorer; abstain to the LLM
 * when the scene leaves a mention unresolved. */
import type { Id } from '../../types';
import type { MicroTargetsFn, MicroTargetsRequest, MicroTargetsResult } from '../semantics/actions';
import { buildScene } from '../semantics/actions';
import { getMicroTokenizer } from './shared';
import { createMicroRuntime, scorePair, type MicroRuntime } from './runtime';

export interface MicroTargetsOptions {
  vocabUrl?: string;
  modelUrl?: string;
  threads?: number;
  threshold?: number;
  /** Evaluation arms: rulesOnly trusts the rule names without the scorer;
   * skipRules always asks the scorer over every visible name (threshold is
   * then the probability cut, default 0.5). */
  rulesOnly?: boolean;
  skipRules?: boolean;
  onStats?: (record: {
    source: 'rules' | 'model' | 'abstain';
    buildMs: number;
    tokenizeMs: number;
    inferMs: number;
    loadMs: number;
    calls: number;
  }) => void;
}

const ORDINALS = '一二三四五六';

export function resolveRuleTargets(
  actionText: string,
  scene: { visible: Array<{ id: Id; name: string }>; absent: Array<{ name: string }> },
  maxTargets: number,
): Id[] | null {
  // Negation changes who was actually touched; rules cannot tell, so abstain.
  if (/没有|没|未|谁也没/u.test(actionText)) return null;
  const named = scene.visible.filter((character) => actionText.includes(character.name));
  if (named.length) return named.slice(0, maxTargets).map((character) => character.id);
  if (scene.absent.some((character) => actionText.includes(character.name))) return null;
  if (/他们|她们|两人|两个人|在场的/u.test(actionText)) {
    return scene.visible.slice(0, maxTargets).map((character) => character.id);
  }
  const ordinal = actionText.match(/第([一二三四五六])个人?/u);
  if (ordinal) {
    const index = ORDINALS.indexOf(ordinal[1]);
    return scene.visible[index] ? [scene.visible[index].id] : null;
  }
  if (/他|她/u.test(actionText)) {
    return scene.visible.length === 1 ? [scene.visible[0].id] : null;
  }
  return [];
}

export function createMicroTargets(options: MicroTargetsOptions = {}): MicroTargetsFn {
  const runtime: MicroRuntime = createMicroRuntime({ threads: options.threads ?? 1 });
  async function ensure() {
    return {
      tok: await getMicroTokenizer(options.vocabUrl),
      session: await runtime.load(options.modelUrl ?? '/micro/pair-scorer-int8.onnx'),
    };
  }

  return async (request: MicroTargetsRequest): Promise<MicroTargetsResult | null> => {
    const buildStart = performance.now();
    const scene = buildScene(request.state, request.sourceId);
    const buildMs = performance.now() - buildStart;
    const actionText = request.actionText ?? '';
    const rule = options.skipRules ? [] : resolveRuleTargets(actionText, scene, request.maxTargets);
    // Rule abstention (negation, absent name, ambiguous pronoun) goes to the
    // LLM: the 2026-11-24 probe showed the raw scorer over-fires exactly there.
    if (rule === null) {
      options.onStats?.({ source: 'abstain', buildMs, tokenizeMs: 0, inferMs: 0, loadMs: 0, calls: 0 });
      return null;
    }
    if (options.rulesOnly) {
      options.onStats?.({ source: 'rules', buildMs, tokenizeMs: 0, inferMs: 0, loadMs: 0, calls: 0 });
      return { targets: rule.slice(0, request.maxTargets), source: 'rules' };
    }
    if (!rule.length && !options.skipRules) {
      options.onStats?.({ source: 'rules', buildMs, tokenizeMs: 0, inferMs: 0, loadMs: 0, calls: 0 });
      return { targets: [], source: 'rules' };
    }
    // Rules propose, the scorer verifies. A rule target the scorer does not
    // confirm is not trusted; the LLM decides instead.
    const names = new Map(scene.visible.map((character) => [character.id, character.name]));
    const loadBefore = runtime.stats().loadMs;
    const { tok, session } = await ensure();
    const loadMs = runtime.stats().loadMs - loadBefore;
    const actorName = typeof scene.actorName === 'string' ? scene.actorName : '';
    const normalized = actorName ? actionText.replace(/我(?!们)/gu, actorName) : actionText;
    const pairText = `行动：${normalized}\n在场：${scene.visible.map((character) => character.name).join('、')}`;
    let tokenizeMs = 0;
    let inferMs = 0;
    const candidates = options.skipRules ? [...names.keys()] : rule;
    const scored: Array<{ id: Id; score: number }> = [];
    for (const id of candidates) {
      const name = names.get(id);
      if (!name) continue;
      const tokenStart = performance.now();
      const { ids } = tok.encodePair(pairText, name);
      tokenizeMs += performance.now() - tokenStart;
      const inferStart = performance.now();
      const score = await scorePair(session, ids);
      inferMs += performance.now() - inferStart;
      scored.push({ id, score });
    }
    if (options.skipRules) {
      // Classifier arm: every visible name above the probability cut.
      const picked = scored.filter((row) => row.score >= (options.threshold ?? 0.5))
        .sort((left, right) => right.score - left.score)
        .slice(0, request.maxTargets)
        .map((row) => row.id);
      options.onStats?.({ source: 'model', buildMs, tokenizeMs, inferMs, loadMs, calls: scored.length });
      return { targets: picked, source: 'model' };
    }
    const minScore = scored.reduce((min, row) => Math.min(min, row.score), Number.POSITIVE_INFINITY);
    const threshold = options.threshold ?? 0;
    if (minScore > threshold) {
      options.onStats?.({ source: 'rules', buildMs, tokenizeMs, inferMs, loadMs, calls: rule.length });
      return { targets: rule, source: 'rules' };
    }
    options.onStats?.({ source: 'abstain', buildMs, tokenizeMs, inferMs, loadMs, calls: rule.length });
    return null;
  };
}
