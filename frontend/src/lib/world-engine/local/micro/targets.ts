/** Micro targets: rules first, then the int8 pair scorer; abstain to the LLM
 * when the scene leaves a mention unresolved. */
import type { Id } from '../../types';
import type { MicroTargetsFn, MicroTargetsRequest, MicroTargetsResult } from '../semantics/actions';
import { buildScene } from '../semantics/actions';
import { createBertTokenizer, type BertTokenizer } from './tokenizer';
import { createMicroRuntime, scorePair, type MicroRuntime } from './runtime';

export interface MicroTargetsOptions {
  vocabUrl?: string;
  modelUrl?: string;
  threads?: number;
  threshold?: number;
  onStats?: (record: {
    source: 'rules' | 'model';
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
  let tokenizer: Promise<BertTokenizer> | null = null;
  const runtime: MicroRuntime = createMicroRuntime({ threads: options.threads ?? 1 });
  async function ensure() {
    if (!tokenizer) {
      tokenizer = (async () => {
        const response = await fetch(options.vocabUrl ?? '/micro/minirbt-vocab.txt');
        if (!response.ok) throw new Error('micro_vocab_fetch_failed');
        return createBertTokenizer(await response.text());
      })();
    }
    return {
      tok: await tokenizer,
      session: await runtime.load(options.modelUrl ?? '/micro/pair-scorer-int8.onnx'),
    };
  }

  return async (request: MicroTargetsRequest): Promise<MicroTargetsResult | null> => {
    const buildStart = performance.now();
    const scene = buildScene(request.state, request.sourceId);
    const buildMs = performance.now() - buildStart;
    const actionText = request.actionText ?? '';
    const rule = resolveRuleTargets(actionText, scene, request.maxTargets);
    if (rule !== null) {
      options.onStats?.({ source: 'rules', buildMs, tokenizeMs: 0, inferMs: 0, loadMs: 0, calls: 0 });
      return { targets: rule, source: 'rules' };
    }
    if (!actionText) return null;
    const loadBefore = runtime.stats().loadMs;
    const { tok, session } = await ensure();
    const loadMs = runtime.stats().loadMs - loadBefore;
    let tokenizeMs = 0;
    let inferMs = 0;
    const scored: Array<{ id: Id; score: number }> = [];
    for (const character of scene.visible) {
      const tokenStart = performance.now();
      const { ids } = tok.encodePair(actionText, character.name);
      tokenizeMs += performance.now() - tokenStart;
      const inferStart = performance.now();
      const score = await scorePair(session, ids);
      inferMs += performance.now() - inferStart;
      scored.push({ id: character.id, score });
    }
    const threshold = options.threshold ?? 0;
    const targets = scored.filter((item) => item.score > threshold).map((item) => item.id).slice(0, request.maxTargets);
    options.onStats?.({ source: 'model', buildMs, tokenizeMs, inferMs, loadMs, calls: scene.visible.length });
    return { targets, source: 'model' };
  };
}
