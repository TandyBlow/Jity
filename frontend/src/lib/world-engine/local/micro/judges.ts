/** Three candidate judges (task / personality / scene) in one int8 model. */
import { createBertTokenizer, type BertTokenizer } from './tokenizer';
import { createMicroRuntime } from './runtime';

export interface JudgeScores { task: number; personality: number; scene: number }
export type BehaviorJudgeFn = (pairs: Array<{ context: string; text: string }>) => Promise<JudgeScores[] | null>;

export interface MicroJudgeOptions {
  vocabUrl?: string;
  modelUrl?: string;
  onStats?: (record: { pairs: number; ms: number; loadMs: number }) => void;
}

export function createBehaviorJudge(options: MicroJudgeOptions = {}): BehaviorJudgeFn {
  let tokenizer: Promise<BertTokenizer> | null = null;
  const runtime = createMicroRuntime({ threads: 1 });
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
      session: await runtime.load(options.modelUrl ?? '/micro/judge-heads-int8.onnx'),
    };
  }
  return async (pairs) => {
    const started = performance.now();
    try {
      const { tok, session } = await ensure();
      const ort = await import('onnxruntime-web/wasm');
      const out: JudgeScores[] = [];
      for (const pair of pairs) {
        const { ids } = tok.encodePair(pair.context, pair.text, 128);
        const data = BigInt64Array.from(ids, (value) => BigInt(value));
        const mask = BigInt64Array.from(ids, () => 1n);
        const result = await session.run({
          input_ids: new ort.Tensor('int64', data, [1, ids.length]),
          attention_mask: new ort.Tensor('int64', mask, [1, ids.length]),
        });
        const sigmoid = (value: unknown) => 1 / (1 + Math.exp(-Number(value ?? 0)));
        out.push({
          task: sigmoid((result.task?.data as Float32Array | undefined)?.[0]),
          personality: sigmoid((result.personality?.data as Float32Array | undefined)?.[0]),
          scene: sigmoid((result.scene?.data as Float32Array | undefined)?.[0]),
        });
      }
      options.onStats?.({ pairs: pairs.length, ms: Math.round(performance.now() - started), loadMs: Math.round(runtime.stats().loadMs) });
      return out;
    } catch {
      return null;
    }
  };
}

/** Context order is the training order: the scene flags must survive truncation. */
export function judgeContext(input: {
  item: boolean; target: boolean; blocked: boolean; repeated: boolean;
  task: string; personality: string; actor: string; room: string;
}): string {
  return `现场：物品${input.item ? '在手边' : '不在手边'}；目标人物${input.target ? '在场' : '不在场'}；` +
    `道路${input.blocked ? '受阻' : '畅通'}；近期${input.repeated ? '刚做过同样的事' : '没有重复'}；` +
    `任务：${input.task.slice(0, 60)}；个性：${input.personality.slice(0, 60)}；角色：${input.actor}；位置：${input.room}`;
}
