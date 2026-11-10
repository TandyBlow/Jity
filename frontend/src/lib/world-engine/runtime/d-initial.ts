import type { InitialTemplate, Json, WorldTime } from '../types';
import type { DApi } from './d-line';
import { DIncomplete } from './d-line';

/** D01 is called once before create_world. Counts are a user/program choice;
 * all entity/task identities are allocated before the API fills their data.
 * A's create_world remains the final graph/schema authority and S0 writer. */
export async function generateDInitial(api: DApi, options: {
  brief: string; locations: number; items: number; characters: number; tasksPerCharacter: number;
  initialTime: WorldTime; allocate?: () => string;
}): Promise<Json> {
  for (const count of [options.locations, options.items, options.characters, options.tasksPerCharacter]) {
    if (!Number.isInteger(count) || count < 0 || count > 100) throw new DIncomplete('Invalid D01 batch size');
  }
  if (!options.locations || !options.characters) throw new DIncomplete('World requires locations and characters');
  const allocate = options.allocate ?? (() => `d_${crypto.randomUUID().replaceAll('-', '')}`);
  const ids = (count: number) => Array.from({ length: count }, allocate);
  const locationIds = ids(options.locations), itemIds = ids(options.items), characterIds = ids(options.characters);
  const taskIds = Object.fromEntries(characterIds.map(id => [id, ids(options.tasksPerCharacter)]));
  const all = [...locationIds, ...itemIds, ...characterIds, ...Object.values(taskIds).flat()];
  if (new Set(all).size !== all.length || all.some(id => !/^[A-Za-z0-9_-]{1,128}$/.test(id))) throw new DIncomplete('Invalid program identities');
  const draft: InitialTemplate = { engineVersion: 'world-engine-v1', schemaVersion: 1,
    protagonistId: characterIds[0], initialTime: options.initialTime, locations: {}, items: {}, characters: {} };
  for (const [kind, allocated] of [['locations', locationIds], ['items', itemIds], ['characters', characterIds]] as const) {
    const shape = kind === 'locations' ? '{id,name,parentLocationId:null或已有地点ID,initialAppearance,slots:[]}'
      : kind === 'items' ? '{id,name,initialPosition:{containerId,slotId:null,relativeTo:null},initialAppearance,slots:[]}'
      : '{id,name,initialPosition:{containerId,slotId:null,relativeTo:null},initialAppearance,slots:[],initialPersonality,initialSanity,tasks:{已分配任务ID:{id,ownerId,parentTaskId:null或同人物任务ID,goal,status:"pending"}}}';
    const result = await api(`D01开局分批草稿。仅输出本批${kind}的ID映射。每项格式${shape}。严格使用程序分配ID，不新增ID；不得产生位置或任务环。资料不足返回kind=incomplete。`,
      JSON.parse(JSON.stringify({ brief: options.brief, allocated, identities: { locationIds, itemIds, characterIds, taskIds }, draft })));
    if (!result || Array.isArray(result) || typeof result !== 'object' || Object.keys(result).sort().join() !== [...allocated].sort().join()) throw new DIncomplete(`D01 ${kind} coverage`);
    for (const id of allocated) if ((result[id] as { id?: string })?.id !== id) throw new DIncomplete('D01 identity changed');
    Object.assign(draft[kind], result);
  }
  // Structural graph preflight. Final deep schemas and state construction are A's.
  const parents = new Map<string, string | null>();
  for (const [id, loc] of Object.entries(draft.locations)) parents.set(id, loc.parentLocationId);
  for (const [id, entity] of Object.entries({ ...draft.items, ...draft.characters })) parents.set(id, entity.initialPosition.containerId);
  function acyclic(graph: Map<string, string | null>) {
    for (const id of graph.keys()) {
      const seen = new Set<string>(); let current: string | null = id;
      while (current !== null) {
        if (seen.has(current) || !graph.has(current)) throw new DIncomplete('D01 cyclic or unknown reference');
        seen.add(current); current = graph.get(current)!;
      }
    }
  }
  acyclic(parents);
  for (const [id, actor] of Object.entries(draft.characters)) {
    if (Object.keys(actor.tasks).sort().join() !== taskIds[id].sort().join()) throw new DIncomplete('D01 task coverage');
    const tree = new Map<string, string | null>();
    for (const [taskId, task] of Object.entries(actor.tasks)) {
      if (task.id !== taskId || task.ownerId !== id) throw new DIncomplete('D01 task ownership');
      tree.set(taskId, task.parentTaskId);
    }
    acyclic(tree);
  }
  return JSON.parse(JSON.stringify(draft));
}
