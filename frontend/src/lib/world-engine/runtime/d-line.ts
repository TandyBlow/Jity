/** D authority composition. A keeps dice, IDs, preview, stage and commit;
 * this port supplies proposals and never applies a world delta itself. */
import { ControllerDriver, type WorldModelPort } from '../controller';
import { updateStages, type ControllerMemory, type ModelTask, type UpdatesCall } from '../schedule';
import type { Json, WorldState } from '../types';
import type { WorldTransport } from '../transport';
import { decodeTaskOutput } from './structured-output';
import { buildTaskPrompt } from './prompts';

export type DApi = (instruction: string, input: Json) => Promise<Json>;
export type D03 = (input: Json) => Promise<{ targetIds: string[] }>;
const json = (value: unknown): Json => JSON.parse(JSON.stringify(value));
export class DIncomplete extends Error {}
const fields: Record<string, string[]> = {
  position: ['positionSet'], appearance: ['appearanceChanges'], tasks: ['tasksAchieved'],
  subtasks: ['subtasksAdded'], personality: ['personalityChanges'], sanity: ['sanitySet'],
};
const settlementInstruction = `仅输出简洁JSON {results:{人物ID:具体共同后果},updates:[{stage,changes}]}。
全组冻结行动及实际骰点是依据，未准入人物的判定也必须考虑；不得重掷或改写行动。
updates 必须按 position,appearance,tasks,subtasks,personality,sanity 六阶段全部返回。
每阶段changes为实体ID到增量的映射；无变化也返回空对象。依次考虑前序候选形成的状态。
positionSet={containerId,slotId:null,relativeTo:null}; appearanceChanges=[{id,text,supersedes:[]}];
tasksAchieved=[id]; subtasksAdded=[{id,ownerId,parentTaskId,goal,status}];
personalityChanges=[{id,text,supersedes:[]}]; sanitySet=数值。增量带entityId。
检查全部当前任务；个性仅在触发条件满足时改变，理智只对个性实际变化者提出。
不写故事或解释，结果不能仅写成功/失败。缺资料返回 {kind:"incomplete",reason:"..."}。`;

function object(value: Json): Record<string, Json> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new DIncomplete('Expected JSON object');
  if (value.kind === 'incomplete') throw new DIncomplete(String(value.reason ?? 'incomplete'));
  return value;
}
function checkedStage(value: Json, stage: string): UpdatesCall {
  const result = decodeTaskOutput('updates', JSON.stringify(value), { updatesSplitMode: true, updatesStage: stage }) as unknown as UpdatesCall;
  for (const delta of Object.values(result.changes)) {
    if (Object.keys(delta).some(k => k !== 'entityId' && !fields[stage].includes(k))) throw new DIncomplete(`Wrong field in ${stage}`);
  }
  return result;
}
interface Bundle { source: Json; results: Json; updates: Json[]; repairs: number }
export class DLinePort implements WorldModelPort {
  private bundles = new Map<string, Bundle>();
  apiCalls = 0;
  constructor(private api: DApi, private d03: D03, private narration: WorldModelPort,
    private repairBudget = 2, private initial?: () => Promise<Json>, private allocateRound?: () => Promise<string>) {}
  private async request(instruction: string, input: Json): Promise<Json> {
    this.apiCalls++;
    const result = await this.api(instruction, json(input));
    if (result && typeof result === 'object' && !Array.isArray(result) && result.kind === 'incomplete') object(result);
    return result;
  }
  private async bundle(key: string, input: Json, scan = false): Promise<Bundle> {
    const old = this.bundles.get(key);
    if (old) {
      if (JSON.stringify(old.source) !== JSON.stringify(input)) throw new DIncomplete('Settlement input changed; frozen bundle cannot be reused');
      return old;
    }
    const output = object(await this.request(settlementInstruction + (scan ? '\n纯时间扫描，无人物行动；results必须为空。' : ''), input));
    const results = decodeTaskOutput('results', JSON.stringify(output.results));
    const members = (input as { members?: { memberId: string }[] }).members ?? [];
    if (Object.keys(results as object).sort().join() !== members.map(m => m.memberId).sort().join()) throw new DIncomplete('Incomplete joint results coverage');
    if (!Array.isArray(output.updates) || output.updates.length !== 6) throw new DIncomplete('All six update stages required');
    // Stage bodies are checked just before preview, allowing suffix-only repair.
    const result = { source: json(input), results, updates: output.updates, repairs: 0 };
    this.bundles.set(key, result);
    return result;
  }
  async repairUpdates(key: string, prefix: UpdatesCall[], workingState: Json, reason: string): Promise<boolean> {
    const bundle = this.bundles.get(key);
    if (!bundle || bundle.repairs >= this.repairBudget) return false;
    bundle.repairs++;
    const start = prefix.length;
    const output = object(await this.request(settlementInstruction + `\n仅修复updates的后缀，从${updateStages[start]}起。保持results和已通过前缀不变。`,
      json({ frozen: bundle.source, results: bundle.results, acceptedPrefix: prefix, workingState,
        rejectedSuffix: bundle.updates.slice(start), error: reason })));
    if (!Array.isArray(output.updates) || output.updates.length !== 6 - start) throw new DIncomplete('Invalid repaired suffix');
    bundle.updates = [...prefix.map(json), ...output.updates];
    return true;
  }
  async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
    const data = input as { groupId?: string; mode?: string; stage?: string; workingState?: WorldState; sourceId?: string; actionText?: string };
    if (task === 'narration') return this.narration.generate(task, key, input);
    if (task === 'initial') {
      if (!this.initial) throw new DIncomplete('D01 initializer or confirmed initial template required');
      return decodeTaskOutput('initial', JSON.stringify(await this.initial()));
    }
    if (task === 'targets') {
      if (!data.workingState || !data.sourceId || !data.actionText) throw new DIncomplete('D03 missing frozen input');
      const result = await this.d03(input);
      const allowed = Object.keys(data.workingState.characters).filter(id => id !== data.sourceId);
      if (!Array.isArray(result.targetIds) || new Set(result.targetIds).size !== result.targetIds.length || result.targetIds.some(id => !allowed.includes(id))) throw new DIncomplete('D03 invalid target IDs');
      return json({ targets: result.targetIds.map(targetId => ({ targetId })) });
    }
    if (task === 'results') return (await this.bundle(key, input)).results;
    if (task === 'updates') {
      const bundleKey = data.groupId ?? key.split('#')[0];
      let bundle = this.bundles.get(bundleKey);
      if (!bundle && data.mode === 'time_scan') {
        const base = { ...(input as Record<string, Json>) }; delete base.stage;
        bundle = await this.bundle(bundleKey, base, true);
      }
      if (!bundle || !data.stage) throw new DIncomplete('D updates require frozen bundle and sequential preview');
      const index = updateStages.indexOf(data.stage as typeof updateStages[number]);
      if (index < 0) throw new DIncomplete('Unknown stage');
      return json(checkedStage(bundle.updates[index], data.stage));
    }
    if (task === 'reaction') {
      const response = object(await this.request('只输出JSON {action:"简短反应尝试"}；依据准入和实际判定，不宣布结果。资料不足返回kind=incomplete。', input));
      return decodeTaskOutput('reaction', typeof response.action === 'string' ? response.action : '');
    }
    if (task === 'continuation') {
      const response = object(await this.request('D07仅输出JSON {candidates:[{actorId,action,likely,relatedToProtagonist}]}。只根据实际最终状态和已提交变化判断；likely与relatedToProtagonist为布尔值，拟行动为简短尝试。没有后续则空列表；缺资料返回incomplete。不要生成轮次ID。', input));
      if (!Array.isArray(response.candidates)) throw new DIncomplete('D07 candidates missing');
      const current = (input as { workingState?: WorldState }).workingState;
      const ids: string[] = [];
      for (const raw of response.candidates) {
        const candidate = object(raw);
        if (typeof candidate.actorId !== 'string' || !current?.characters[candidate.actorId]
          || typeof candidate.action !== 'string' || !candidate.action.trim()
          || typeof candidate.likely !== 'boolean' || typeof candidate.relatedToProtagonist !== 'boolean') throw new DIncomplete('D07 malformed evidence');
        if (candidate.likely && candidate.relatedToProtagonist) ids.push(candidate.actorId);
      }
      if (!ids.length) return { kind: 'handback', closedBy: 'model', cancelReason: null };
      if (!this.allocateRound) throw new DIncomplete('Program round allocator required');
      const nextRoundId = await this.allocateRound();
      if (!nextRoundId) throw new DIncomplete('Round allocation failed');
      return { kind: 'continue', closedBy: 'model', cancelReason: null, candidateCharacterIds: [...new Set(ids)], nextRoundId };
    }
    // D07/D08 use fresh requests at their actual scheduling boundary. No
    // speculative cached advice can survive a preview or repair implicitly.
    const prompt = buildTaskPrompt(task, key, input) + '\n资料不足返回 {"kind":"incomplete","reason":"原因"}，不能冒充skip。';
    const response = await this.request(prompt + (task === 'pointPlan' ? '\nJSON对象模式：将上面的数组放在 {"plan":[...]} 中。' : ''), input);
    return decodeTaskOutput(task, JSON.stringify(task === 'pointPlan' ? object(response).plan : response));
  }
}

export function createDLineDriver(options: { transport: WorldTransport; memory: ControllerMemory;
  api: DApi; d03: D03; narration: WorldModelPort; initial?: () => Promise<Json>; allocateRound?: () => Promise<string>; repairBudget?: number }) {
  const memory = structuredClone(options.memory);
  memory.updatesStages = [...updateStages];
  memory.localTargets = true;
  const port = new DLinePort(options.api, options.d03, options.narration, options.repairBudget, options.initial, options.allocateRound);
  return { port, driver: new ControllerDriver({ transport: options.transport, model: port }, memory) };
}

/** Server-side/local desktop bridge only: never put API keys in the browser. */
export function dBridge(baseUrl: string, token: string) {
  const post = async (path: string, input: Json) => {
    const response = await fetch(`${baseUrl}${path}`, { method: 'POST', headers: {
      'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify(input) });
    if (!response.ok) throw new DIncomplete(`D bridge failed: ${response.status}`);
    return response.json();
  };
  return { api: ((instruction, input) => post('/api', { instruction, input })) as DApi,
    d03: ((input) => post('/d03', input)) as D03 };
}
