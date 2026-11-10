import { describe, expect, it } from 'vitest';
import { ControllerDriver, initialMemory, type WorldModelPort } from '../../../controller';
import type { InferenceEngine } from '../../../runtime/engine';
import type { ModelTask } from '../../../schedule';
import type { InitialTemplate, Json } from '../../../types';
import { SHORT_STATE } from '../../../runtime/b3-short-samples';
import { LocalWorldTransport } from '../../transport';
import { createSettlementHandlers, requireSettlementValue } from './index';

function template(): InitialTemplate {
  const initial = structuredClone(SHORT_STATE.initial) as InitialTemplate & { worldId?: string };
  delete initial.worldId;
  return initial;
}

function settlementEngine(): InferenceEngine {
  return {
    info: { backend: 'scripted', modelId: 'settlement-integration' },
    async load() {},
    async dispose() {},
    async complete(prompt: string): Promise<string> {
      if (prompt.includes('共同结算器')) {
        return JSON.stringify({
          judgments: [{ memberId: 'person_c', label: 'not_achieved', reason: '盒盖没有被打开。', effects: [] }],
          facts: [{ text: '周宁试着打开盒盖，但没有成功。', memberIds: ['person_c'] }],
        });
      }
      if (prompt.includes('位置结算器')) return JSON.stringify({ changes: [] });
      if (prompt.includes('外貌结算器')) return JSON.stringify({ operations: [] });
      if (prompt.includes('任务判定器')) {
        return JSON.stringify({ unchanged: [], achieved: [
          { characterId: 'person_a', tasks: [{ taskId: 'task_watch', basis: 'f1' }] },
        ] });
      }
      if (prompt.includes('新增小任务判断器')) return JSON.stringify({ subtasks: [] });
      if (prompt.includes('个性变化判断器')) {
        return JSON.stringify({ operations: [
          { entityId: 'person_a', op: 'add', recordIds: [], text: '比之前更警觉。' },
          { entityId: 'person_c', op: 'keep', recordIds: [], text: null },
        ] });
      }
      if (prompt.includes('理智重算器')) return JSON.stringify({ sanity: [{ characterId: 'person_a', value: 8 }] });
      if (prompt.includes('自动推进判断器')) return JSON.stringify({ candidates: [] });
      throw new Error(`unexpected settlement prompt: ${prompt.slice(0, 80)}`);
    },
  };
}

describe('settlement handlers through the real controller', () => {
  it('runs results, merged six-stage updates and continuation as a committed round', async () => {
    const initial = template();
    const order = Object.keys(initial.characters).sort();
    const transport = await LocalWorldTransport.create(initial, { roll: () => 13 });
    const settlement = createSettlementHandlers({ engine: settlementEngine() });
    const model: WorldModelPort = {
      async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
        if (task === 'pointPlan') {
          return [{ pointId: 'p1', kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, actorIds: order }];
        }
        if (task === 'action') {
          const data = input as { actor: string; workingState: { protagonistId: string }; advance: { inputText: string | null } };
          return data.actor === data.workingState.protagonistId
            ? { kind: 'act', text: data.advance.inputText ?? '我试着打开盒盖。' }
            : { kind: 'skip' };
        }
        if (task === 'targets') return { targets: [] };
        if (task === 'results') return requireSettlementValue(await settlement.results(key, input));
        if (task === 'updates') return requireSettlementValue(await settlement.updates(key, input)) as unknown as Json;
        if (task === 'continuation') return requireSettlementValue(await settlement.continuation(key, input));
        if (task === 'narration') return '周宁伸出手，指节在盒盖上停了一下。盒盖没有打开，走廊里只剩下两个人的呼吸声。';
        throw new Error(`unexpected task ${task}`);
      },
    };
    const memory = initialMemory('test_settlement', 'holder_settlement');
    memory.initialTemplate = initial;
    memory.playerInput = { text: '我试着打开盒盖。', order };
    memory.allocPlan = {
      allocationKey: 'test_settlement_command',
      slots: [
        { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' },
        { slotKey: 'round', kind: 'round' }, { slotKey: 'point', kind: 'point' },
        ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const })),
      ],
    };
    const driver = new ControllerDriver({ transport, model }, memory);
    const status = await driver.run();
    expect(status.kind).not.toBe('error');
    const snapshot = transport.snapshot();
    expect(snapshot.version).toBe(1);
    expect(snapshot.state.characters.person_c.position.containerId).toBe('corridor');
    expect(snapshot.state.characters.person_a.tasks.task_watch.status).toBe('achieved');
    expect(snapshot.state.characters.person_a.sanity).toBe(8);
    expect(snapshot.state.characters.person_a.personalityChanges.find((change) => change.active)?.text).toBe('比之前更警觉。');
    expect(snapshot.narrations.p1.status).toBe('ready');
    expect(snapshot.control.phase).toBe('complete');
  });
});
