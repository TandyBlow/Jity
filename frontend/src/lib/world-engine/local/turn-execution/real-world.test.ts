/** The product world, not a toy fixture: 14 characters, 26 locations, 74 items
 * and 73 tasks. The scripted answers are mechanical (one off-screen task is
 * marked achieved; every other task stays pending), but the world, the
 * projection, the controller and the transport are the real ones. The transport
 * itself refuses a group whose task/personality coverage is not the full cast,
 * so a green run here proves the six-stage scope on the real data.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ControllerDriver, initialMemory } from '../../controller';
import type { InferenceEngine } from '../../runtime/engine';
import type { ModelTask } from '../../schedule';
import type { InitialState, InitialTemplate, Json, WorldState } from '../../types';
import { buildInitialState } from '../state';
import { LocalWorldTransport } from '../transport';
import { createSettlementModelPort } from './index';
import { taskKeyIndex } from '../semantics/settlement/support';

function loadWorld(): { initial: InitialTemplate; state: WorldState } {
  const file = join(process.cwd(), 'public/worlds/dragon-raja-free-day.world.json');
  const world = JSON.parse(readFileSync(file, 'utf8'));
  // The product kernel validates worldId; keep the world file's own id instead
  // of stripping it (06's normalizeInitialState started requiring it).
  const source = structuredClone(world.initial) as InitialTemplate;
  const initial = source;
  return { initial, state: buildInitialState(source as unknown as InitialState) };
}

/** The task owner the protagonist cannot see (different room). */
const OFFSCREEN = 'chu';
const OFFSCREEN_TASK = 'task_chu_hatch';

function engineFor(state: WorldState, seen: string[]): InferenceEngine {
  return {
    info: { backend: 'scripted', modelId: 'real-world-full-cast' },
    async load() {},
    async dispose() {},
    async complete(prompt: string): Promise<string> {
      seen.push(prompt);
      if (prompt.includes('共同结算器')) {
        return JSON.stringify({
          judgments: [{ memberId: 'lu', label: 'partial', reason: '路明非问清了地下门闩的情况。', effects: [] }],
          facts: [{ text: '路明非问起地下检修门的门闩，楚子航说会去确认。', memberIds: ['lu'] }],
        });
      }
      if (prompt.includes('位置结算器')) return JSON.stringify({ changes: [] });
      if (prompt.includes('外貌结算器')) return JSON.stringify({ operations: [] });
      if (prompt.includes('任务条件核验器')) {
        return JSON.stringify({ judgments: [{
          characterId: OFFSCREEN, taskId: OFFSCREEN_TASK, satisfied: 'yes', reason: '地下门闩的事实已经满足任务条件。',
        }] });
      }
      if (prompt.includes('任务判定器')) {
        // One decision per character; achieved lists only newly achieved tasks.
        const owners = Object.entries(state.characters)
          .filter(([, character]) => Object.keys(character.tasks).length > 0)
          .map(([ownerId]) => ownerId);
        return JSON.stringify({
          unchanged: owners.filter((ownerId) => ownerId !== OFFSCREEN),
          achieved: [{ characterId: OFFSCREEN, tasks: [{ taskId: OFFSCREEN_TASK, basis: 'f1' }] }],
        });
      }
      if (prompt.includes('新增小任务判断器')) return JSON.stringify({ subtasks: [] });
      if (prompt.includes('个性变化判断器')) {
        const operations = Object.keys(state.characters).map((id) => (
          id === OFFSCREEN
            ? { entityId: id, op: 'add', recordIds: [], text: '把地下门当成必须亲自确认的责任。' }
            : { entityId: id, op: 'keep', recordIds: [], text: null }
        ));
        return JSON.stringify({ operations });
      }
      if (prompt.includes('理智重算器')) return JSON.stringify({ sanity: [{ characterId: OFFSCREEN, value: 70 }] });
      if (prompt.includes('自动推进判断器')) return JSON.stringify({ candidates: [] });
      throw new Error(`unexpected prompt ${prompt.slice(0, 40)}`);
    },
  };
}

describe('real product world through the real kernel', () => {
  it('decides and commits the full cast, including an off-screen owner', async () => {
    const { initial, state } = loadWorld();
    const order = Object.keys(initial.characters).sort();
    const seen: string[] = [];
    const engine = engineFor(state, seen);
    const settlement = createSettlementModelPort(engine);
    const transport = await LocalWorldTransport.create(initial, { roll: () => 13 });
    const memory = initialMemory('test_world', 'holder_world');
    memory.initialTemplate = initial;
    memory.playerInput = { text: '我问楚子航地下检修门的门闩到底会不会再插上。', order };
    memory.allocPlan = {
      allocationKey: 'test_world_command',
      slots: [
        { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' },
        { slotKey: 'round', kind: 'round' }, { slotKey: 'point', kind: 'point' },
        ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const })),
      ],
    };
    const model = {
      async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
        if (task === 'results' || task === 'updates' || task === 'continuation') return settlement.generate(task, key, input);
        if (task === 'pointPlan') {
          return [{ pointId: 'point_real_1', kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } }, actorIds: order }];
        }
        if (task === 'action') {
          const data = input as unknown as { actor: string; advance?: { inputText?: string | null; intentStatus?: string }; workingState: WorldState };
          if (data.actor === data.workingState.protagonistId && data.advance?.intentStatus === 'pending') {
            return { kind: 'act', text: data.advance.inputText ?? '路明非问起门闩。' };
          }
          return { kind: 'skip' };
        }
        if (task === 'targets') return { targets: [] };
        if (task === 'reaction') return { kind: 'skip' };
        if (task === 'narration') return '路明非问了一句门闩的事，没有得到回答，先把这句话记在心里。';
        throw new Error(`unexpected task ${task}`);
      },
    };
    const driver = new ControllerDriver({ transport, model }, memory);
    const status = await driver.run();
    expect(status.kind).not.toBe('error');
    const snapshot = transport.snapshot();
    const committed = snapshot.state.characters[OFFSCREEN];
    expect(committed.tasks[OFFSCREEN_TASK].status).toBe('achieved');
    expect(committed.personalityChanges.find((change) => change.active)?.text).toBe('把地下门当成必须亲自确认的责任。');
    expect(committed.sanity).toBe(70);
    // The dependency projection puts the off-screen fact owner in front of the
    // model, but does not re-send unrelated owners just to hear "unchanged".
    const taskPrompt = seen.find((prompt) => prompt.includes('任务判定器')) ?? '';
    expect(taskPrompt).toContain(`id=${OFFSCREEN}`);
    expect(taskPrompt).not.toContain('id=caesar');
    const taskIds = Object.values(state.characters).flatMap((character) => Object.keys(character.tasks));
    expect(taskIds).toHaveLength(73);
    const keys = taskKeyIndex(state);
    expect(keys.size).toBe(73);
    expect(taskPrompt.length).toBeLessThan(6000);
    // Same for appearance: the affected scene/fact entities are listed, not
    // all 114 rows.
    const appearancePrompt = seen.find((prompt) => prompt.includes('外貌结算器')) ?? '';
    expect(appearancePrompt).toContain(`id=${OFFSCREEN}`);
    expect(appearancePrompt).not.toContain('id=caesar');
    expect(appearancePrompt.length).toBeLessThan(8000);
    const personalityPrompt = seen.find((prompt) => prompt.includes('个性变化判断器')) ?? '';
    expect(personalityPrompt).toContain(`id=${OFFSCREEN}`);
    expect(personalityPrompt).not.toContain('id=caesar');
    expect(personalityPrompt.length).toBeLessThan(6000);
  });
});
