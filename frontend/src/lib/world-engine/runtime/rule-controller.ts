/** A deliberately narrow application composition: one supported player
 * command, deterministic execution/updates, and committed template narration.
 * It uses the existing driver/allocator/preview/stage/commit path unchanged. */
import { ControllerDriver, initialMemory, type WorldModelPort } from '../controller';
import type { ModelTask, UpdatesCall } from '../schedule';
import type { WorldTransport } from '../transport';
import type { InitialTemplate, Json, PointWork, WorldContext, WorldState } from '../types';
import { projectCommittedNarration, renderCommittedNarration, type CommittedRead, type CommittedNarration } from './committed-narration';
import { RuleAuthority, decodeRuleAction, describeRuleDecision, encodeRuleAction, parseRuleCommand, type RulePolicy, type RuleReceipt } from './rule-facts';

export function createRuleController(options: { transport: WorldTransport; initial: InitialTemplate;
  command: string; policy: RulePolicy; prefix: string }) {
  const memory = initialMemory(options.prefix, `${options.prefix}_holder`);
  const order = Object.keys(options.initial.characters).sort();
  memory.initialTemplate = structuredClone(options.initial);
  memory.playerInput = { text: options.command, order };
  memory.allocPlan = { allocationKey: `${options.prefix}_command`, slots: [
    { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' },
    { slotKey: 'round', kind: 'round' }, { slotKey: 'point', kind: 'point' },
    ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const })),
  ] };
  const authority = new RuleAuthority(options.policy);
  const reads = new Map<string, CommittedRead>();
  const groups = new Map<string, { receipt: RuleReceipt; result: Record<string, string> }>();
  const decisions: ReturnType<RuleAuthority['inspect']>[] = [];
  const narrations: { packet: CommittedNarration; text: string }[] = [];
  const operations: string[] = [];
  let world: WorldContext | null = null;
  let work: PointWork | null = null;
  let activeInput: { advanceId: string; inputId: string; text: string } | null = null;
  const transport: WorldTransport = {
    async execute(operation, request, scope, signal) {
      const response = await options.transport.execute(operation, request, scope, signal);
      operations.push(operation);
      if ('world' in response) world = structuredClone(response.world);
      if ('work' in response) work = structuredClone(response.work);
      if ('activeInput' in response) activeInput = structuredClone(response.activeInput);
      if (operation === 'get_state') {
        const read = (response as { data: CommittedRead }).data;
        reads.set(read.pointId, structuredClone(read));
      }
      return response;
    },
  };
  // Assigned once, after the closures that read it are defined: a const here
  // would be in the closures' temporal dead zone (requireScope/model run only
  // after the driver exists).
  // eslint-disable-next-line prefer-const
  let driver: ControllerDriver;
  const requireScope = () => {
    if (!world || !work) throw new Error('rule_live_scope_missing');
    const held = driver.getMemory().playerAdvance ?? activeInput;
    if (!held || held.advanceId !== world.advance.advanceId || held.inputId !== world.advance.inputId) throw new Error('rule_input_identity_missing');
    return { world, work, inputText: held.text };
  };
  const model: WorldModelPort = {
    async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
      if (task === 'pointPlan') return [{ pointId: driver.getMemory().ids.point, kind: 'normal',
        timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'second' } }, actorIds: order }];
      if (task === 'action') {
        const data = input as unknown as { actor: string; advance: { inputText: string | null; intentStatus: string }; workingState: WorldState };
        const scope = requireScope();
        if (data.actor !== data.workingState.protagonistId || data.advance.intentStatus !== 'pending'
          || scope.world.advance.intentStatus !== 'pending') return { kind: 'skip' };
        if (data.advance.inputText !== scope.inputText) throw new Error('action_input_binding_changed');
        const proposal = parseRuleCommand(scope.inputText, data.workingState);
        return proposal ? { kind: 'act', text: encodeRuleAction(proposal) } : { kind: 'skip' };
      }
      if (task === 'targets') return { targets: [] }; // no reaction/dice rules in this subset
      if (task === 'results') {
        const data = input as unknown as { groupId: string; members: { memberId: string; actionText: string; rollRefs: unknown[] }[]; workingState: WorldState };
        if (data.members.length !== 1 || data.members[0].memberId !== data.workingState.protagonistId || data.members[0].rollRefs.length) throw new Error('unsupported_rule_group');
        const scope = requireScope();
        const receipt = authority.adjudicate({ proposal: decodeRuleAction(data.members[0].actionText), inputText: scope.inputText,
          world: scope.world, state: data.workingState, pointId: scope.work.pointId });
        const record = authority.inspect(receipt);
        const result = { [data.members[0].memberId]: describeRuleDecision(record.decision, data.workingState) };
        groups.set(data.groupId, { receipt, result });
        decisions.push(record);
        return result;
      }
      if (task === 'updates') {
        const data = input as unknown as { mode: string; groupId?: string; results?: unknown; stage?: string; workingState: WorldState };
        if (data.mode === 'time_scan') return data.stage ? { stage: data.stage, changes: {} } : [];
        const issued = data.groupId ? groups.get(data.groupId) : undefined;
        if (!issued) throw new Error('updates_without_rule_receipt');
        if (JSON.stringify(data.results) !== JSON.stringify(issued.result)) throw new Error('result_text_is_not_execution_authority');
        const scope = requireScope();
        const delta = authority.deltas(issued.receipt, scope.world, scope.work.pointId, data.workingState);
        const calls = Object.values(delta).flatMap<UpdatesCall>((change) => change.positionSet
          ? [{ stage: 'position', changes: { [change.entityId]: { entityId: change.entityId, positionSet: change.positionSet } } }]
          : [{ stage: 'tasks', changes: { [change.entityId]: { entityId: change.entityId, tasksAchieved: change.tasksAchieved } } },
            { stage: 'personality', changes: { [change.entityId]: { entityId: change.entityId, personalityChanges: change.personalityChanges } } },
            { stage: 'sanity', changes: { [change.entityId]: { entityId: change.entityId, sanitySet: change.sanitySet } } }]);
        return JSON.parse(JSON.stringify(data.stage ? calls.find((call) => call.stage === data.stage) ?? { stage: data.stage, changes: {} } : calls)) as Json;
      }
      if (task === 'narration') {
        const after = reads.get(key);
        if (!after) throw new Error('narration_requires_saved_point_read');
        const before = after.previousPointId ? reads.get(after.previousPointId) : null;
        if (before === undefined) throw new Error('narration_requires_saved_predecessor_read');
        const packet = projectCommittedNarration(after, before);
        const text = renderCommittedNarration(packet);
        narrations.push({ packet, text });
        return text;
      }
      if (task === 'continuation') return { kind: 'handback', closedBy: 'model', cancelReason: null };
      throw new Error(`unsupported_rule_task:${task}`);
    },
  };
  driver = new ControllerDriver({ transport, model }, memory);
  return { driver, model, authority, operations, decisions, narrations, reads,
    snapshot: () => ({ world: structuredClone(world), work: structuredClone(work) }) };
}
