/** Generation constraints for the first three B3 tasks. This guides the
 * sampler; structured-output.ts remains the controller's validation gate. */
import type { Json } from '../types';
import type { ModelTask } from '../schedule';
import { updateStages } from '../schedule';

const string = { type: 'string', minLength: 1 };
const strings = { type: 'array', items: string };
const object = (properties: Record<string, unknown>, required = Object.keys(properties)) =>
  ({ type: 'object', properties, required, additionalProperties: false });
const change = object({ id: string, text: { type: ['string', 'null'] }, supersedes: strings });
const relative = object({ entityId: string, relation: { enum: ['under', 'above', 'beside', 'in_front_of', 'behind'] } });
const fields: Record<string, Record<string, unknown>> = {
  position: { positionSet: { anyOf: [{ type: 'null' }, object({ containerId: string,
    slotId: { type: ['string', 'null'] }, relativeTo: { anyOf: [{ type: 'null' }, relative] } })] } },
  appearance: { appearanceChanges: { type: 'array', items: change } },
  tasks: { tasksAchieved: strings },
  subtasks: { subtasksAdded: { type: 'array', items: object({ id: string, ownerId: string,
    parentTaskId: { type: ['string', 'null'] }, goal: string, status: { enum: ['pending', 'achieved'] } }) } },
  personality: { personalityChanges: { type: 'array', items: change } },
  sanity: { sanitySet: { type: ['number', 'null'] } },
};

export function taskOutputSchema(task: ModelTask, input: Json): unknown | undefined {
  if (task === 'action') return { anyOf: [object({ kind: { const: 'skip' } }),
    object({ kind: { const: 'act' }, text: string })] };
  if (task !== 'updates') return undefined; // prose never goes through a JSON grammar
  const data = input as { stage?: string; workingState?: Record<string, unknown> };
  const state = data?.workingState ?? {};
  const ids = [...new Set(['characters', 'items', 'locations'].flatMap((kind) =>
    Object.keys((state[kind] ?? {}) as object)))].sort();
  const call = (stage: string) => {
    const delta = object(fields[stage]);
    const changes = ids.length ? object(Object.fromEntries(ids.map((id) => [id, delta])), [])
      : { type: 'object', additionalProperties: delta };
    return object({ stage: { const: stage }, changes });
  };
  if (data?.stage !== undefined) {
    if (!updateStages.includes(data.stage as typeof updateStages[number])) throw new Error(`unknown updates stage: ${data.stage}`);
    return call(data.stage);
  }
  return { type: 'array', items: { anyOf: updateStages.map(call) } };
}
