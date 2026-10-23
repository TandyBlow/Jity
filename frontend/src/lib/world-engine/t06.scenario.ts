/** T06 semantic acceptance uses B faults on a real controller session;
 * the shared T06 request-id/invalid-request teaching sequence remains in
 * the contract suite. The T01 oracle keeps its full business assertions,
 * model script and independent final projection/digest. */
import { ControllerDriver } from './controller';
import { FaultTransport, type FaultRule } from './fault-transport';
import { buildT01Scenario } from './t01.scenario';

export function buildT06Scenario(sampleId: string, rules: FaultRule[], retryLimit = 3) {
  const base = buildT01Scenario(sampleId);
  const advance = base.corpus.servedAfter.s5.world!.advance;
  const fault = new FaultTransport(base.transport, rules, {
    advanceId: advance.advanceId!, inputId: advance.inputId!, text: base.memory.playerInput!.text,
  });
  const driver = new ControllerDriver({ transport: fault, model: base.model }, base.memory, { world: null }, {
    retryLimit, identityAliases: { 'group:person_a': 'group' },
  });
  return { ...base, driver, fault };
}
