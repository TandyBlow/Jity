/** The bundled defaults for the minimal world page: the short sample world
 * plus the bounded rule policy the review scripts validate. The initial
 * template only matters for NEW worlds — recovery derives it from the
 * server's saved state (get_state.data.state.initial), never from the
 * bundle. */
import { SHORT_STATE } from '../../lib/world-engine/runtime/b3-short-samples';
import type { RulePolicy } from '../../lib/world-engine/runtime/rule-facts';
import type { InitialState, InitialTemplate } from '../../lib/world-engine/types';

export const WORLD_POLICY: RulePolicy = {
  routes: [
    { from: 'corridor', to: 'hall', minimumSanity: 5 },
    { from: 'hall', to: 'corridor' },
  ],
  sanity: {
    minimum: 0,
    maximum: 10,
    effects: { strain: -2, recover: 1 },
    milestones: {
      strain: { taskId: 'task_pressure', goal: '完成压力试验', requiredLocationId: 'corridor',
        minimumElapsedSeconds: 1, personalityText: '经历压力试验后更谨慎' },
      recover: { taskId: 'task_recover', goal: '完成恢复练习', requiredLocationId: 'corridor',
        minimumElapsedSeconds: 1, personalityText: '完成恢复练习后更善于自我调节' },
    },
  },
};

export function defaultInitialTemplate(): InitialTemplate {
  const initial = structuredClone(SHORT_STATE.initial) as unknown as InitialState;
  const template: InitialTemplate = {
    engineVersion: initial.engineVersion,
    schemaVersion: initial.schemaVersion,
    protagonistId: initial.protagonistId,
    initialTime: initial.initialTime,
    locations: initial.locations,
    items: initial.items,
    characters: initial.characters,
  };
  for (const milestone of Object.values(WORLD_POLICY.sanity.milestones)) {
    template.characters.person_c.tasks[milestone.taskId] = {
      id: milestone.taskId, ownerId: 'person_c', parentTaskId: null, goal: milestone.goal, status: 'pending',
    };
  }
  return template;
}

/** Optional narration-polish experiment default: a small instruct model
 * already shipped under public/models. Any load or generation failure keeps
 * the committed template. */
export const DEFAULT_POLISH_MODEL = '/models/Qwen3-0.6B-Q4_K_M.gguf';
