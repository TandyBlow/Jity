import { describe, expect, it } from 'vitest';
import type { EngineInfo } from '../../runtime/engine';
import type { ModelTask } from '../../schedule';
import type { Json } from '../../types';
import { buildTestWorld } from '../semantics/actions/fixtures';
import { createActionExecutionModel } from './port';

/** Deterministic engine: each test supplies the answers it wants to see and
 * the prompts are archived so assertions can inspect the actual scene. */
function fakeEngine(answers: { action?: string[]; targets?: string[]; reaction?: string[] }) {
  const prompts: { task: string; prompt: string }[] = [];
  const info: EngineInfo = { backend: 'fake', modelId: 'fake-instruct' };
  return {
    prompts,
    engine: {
      info,
      async load() {},
      async dispose() {},
      async complete(prompt: string): Promise<string> {
        const isAction = prompt.includes('角色行动判断器');
        const isTargets = prompt.includes('牵连判断器');
        const isReaction = prompt.includes('反应生成器');
        const task = isAction ? 'action' : isTargets ? 'targets' : isReaction ? 'reaction' : 'other';
        prompts.push({ task, prompt });
        const queue = isAction ? answers.action : isTargets ? answers.targets : answers.reaction;
        const next = queue?.length ? queue[(prompts.filter((entry) => entry.task === task).length - 1) % queue.length] : undefined;
        if (next === undefined) throw new Error(`fake engine has no answer for ${task}`);
        return next;
      },
    },
  };
}

function delegate(log: string[]): { generate(task: ModelTask, key: string, input: Json): Promise<Json> } {
  return {
    async generate(task: ModelTask) {
      log.push(task);
      return { delegated: task } as unknown as Json;
    },
  };
}

describe('ActionExecutionModel port', () => {
  it('freezes the player text verbatim even when it matches no command list', async () => {
    const { engine, prompts } = fakeEngine({});
    const log: string[] = [];
    const model = createActionExecutionModel(delegate(log), engine);
    const state = buildTestWorld();
    const input = {
      actor: 'hero',
      advance: { inputText: '我把护目镜推上去，盯着巷口，等阿宁先动。', intentStatus: 'pending' },
      workingState: state,
    } as unknown as Json;
    const value = await model.generate('action', 'hero', input) as { kind: string; text?: string };
    expect(value).toEqual({ kind: 'act', text: '我把护目镜推上去，盯着巷口，等阿宁先动。' });
    expect(prompts).toHaveLength(0);
    expect(model.evidence[0].source).toBe('program');
  });

  it('judges an unnamed same-room character from its own task, no name rule', async () => {
    const { engine, prompts } = fakeEngine({ action: [JSON.stringify({ kind: 'act', text: '阿宁把木门拉上，横过门栓。' })] });
    const log: string[] = [];
    const model = createActionExecutionModel(delegate(log), engine);
    // Player input never mentions 阿宁 and uses no keyword from the old
    // INTERACTION regex.
    const input = { actor: 'ally', advance: { inputText: '我盯着巷口。', intentStatus: 'pending' }, workingState: buildTestWorld() } as unknown as Json;
    const value = await model.generate('action', 'ally', input) as { kind: string; text?: string };
    expect(value.kind).toBe('act');
    expect(value.text).toContain('门栓');
    const prompt = prompts[0].prompt;
    expect(prompt).toContain('守住大厅木门');
    expect(prompt).toContain('被玩家点名不是行动前提');
    // The player's move is scene context, not a command the NPC must repeat.
    expect(prompt).toContain('我盯着巷口');
    expect(model.evidence[0].source).toBe('model');
    expect(await model.generate('results', 'g1', {} as Json)).toEqual({ delegated: 'results' });
  });

  it('rejects an NPC action that only echoes the player and falls back to skip', async () => {
    const echoed = JSON.stringify({ kind: 'act', text: '我把护目镜推上去，盯着巷口，等阿宁先动。' });
    const { engine } = fakeEngine({ action: [echoed, echoed] });
    const model = createActionExecutionModel(delegate([]), engine, { attempts: 2 });
    const input = { actor: 'ally', advance: { inputText: '我把护目镜推上去，盯着巷口，等阿宁先动。', intentStatus: 'pending' }, workingState: buildTestWorld() } as unknown as Json;
    const value = await model.generate('action', 'ally', input) as { kind: string };
    expect(value).toEqual({ kind: 'skip' });
    const evidence = model.evidence.at(-1)!;
    expect(evidence.fallback).toBe(true);
    expect(evidence.issues.some((issue) => issue.severity === 'error')).toBe(true);
    expect(model.evidence.at(-1)!.attempts).toBe(2);
  });

  it('accepts a target the model names by id and falls back when it invents one', async () => {
    const { engine } = fakeEngine({ targets: [JSON.stringify({ targets: [{ targetId: 'ally' }] })] });
    const model = createActionExecutionModel(delegate([]), engine);
    const input = { sourceId: 'hero', actionText: '路明非把木门推开，问阿宁还能不能走。', workingState: buildTestWorld() } as unknown as Json;
    expect(await model.generate('targets', 'hero', input)).toEqual({ targets: [{ targetId: 'ally' }] });

    const invented = fakeEngine({ targets: [JSON.stringify({ targets: [{ targetId: 'ghost' }] }), JSON.stringify({ targets: [{ targetId: 'ghost' }] })] });
    const second = createActionExecutionModel(delegate([]), invented.engine, { attempts: 2 });
    expect(await second.generate('targets', 'hero', input)).toEqual({ targets: [] });
    expect(second.evidence.at(-1)!.fallback).toBe(true);
  });

  it('rewrites a first-person reaction to the member instead of repairing it', async () => {
    const { engine } = fakeEngine({ reaction: ['我把门拉开，冲出去。'] });
    const model = createActionExecutionModel(delegate([]), engine, { attempts: 2 });
    const input = { sourceId: 'hero', sourceActionText: '路明非把木门推开，问阿宁还能不能走。', memberId: 'ally', workingState: buildTestWorld() } as unknown as Json;
    const value = await model.generate('reaction', 'hero', input);
    expect(String(value)).toBe('阿宁把门拉开，冲出去。');
    const result = model.evidence.at(-1)!;
    expect(result.calls).toHaveLength(1);
    expect(result.issues.map((issue) => issue.code)).toContain('first_person_rewritten');
    expect(result.issues.some((issue) => issue.code === 'reaction_first_person' && issue.severity === 'error')).toBe(false);
  });

  it('never lets the model write the protagonist as a reaction target', async () => {
    const { engine, prompts } = fakeEngine({});
    const model = createActionExecutionModel(delegate([]), engine);
    const input = { sourceId: 'ally', sourceActionText: '阿宁把木门拉上，横过门栓。', memberId: 'hero', workingState: buildTestWorld() } as unknown as Json;
    const value = await model.generate('reaction', 'ally', input);
    expect(String(value)).toContain('没有作出反应');
    expect(prompts).toHaveLength(0);
  });

  it('reports task evidence through the page-compatible onTask channel', async () => {
    const { engine } = fakeEngine({ action: [JSON.stringify({ kind: 'skip' })] });
    const reports: { task: ModelTask; fallback: boolean; source?: string }[] = [];
    const model = createActionExecutionModel(delegate([]), engine, {
      onTask: (task, _key, detail) => reports.push({ task, fallback: detail.fallback, source: detail.source }),
    });
    await model.generate('action', 'ally', { actor: 'ally', advance: { inputText: null, intentStatus: 'consumed' }, workingState: buildTestWorld() } as unknown as Json);
    expect(reports).toEqual([{ task: 'action', fallback: false, source: 'model' }]);
  });
});
