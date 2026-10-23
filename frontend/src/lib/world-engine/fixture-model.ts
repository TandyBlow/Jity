import { equal } from './trace-runner';
import { ProtocolError } from './protocol';
import type { Json } from './types';

export type FixtureModelTask = 'action' | 'targets' | 'reaction' | 'results' | 'updates' | 'continuation' | 'narration' | 'initial' | 'time' | 'pointPlan';
export interface FixedModelCall { task: FixtureModelTask; key: string; input: Json; output: Json }

/** Fixed model port for B1 tests. Values are authored by the scenario, including
 * local references; the controller must bind preallocated IDs before submission.
 * This port never chooses IDs, rolls, admission, state or candidate defaults. */
export class FixtureModelOutputs {
  private index = 0;
  private readonly calls: FixedModelCall[];
  constructor(calls: readonly FixedModelCall[]) { this.calls = structuredClone([...calls]); }
  async generate(task: FixtureModelTask, key: string, input: Json): Promise<Json> {
    const call = this.calls[this.index];
    if (!call || call.task !== task || call.key !== key || !equal(call.input, input)) throw new ProtocolError('Unexpected fixed model task/input/order');
    this.index++;
    return structuredClone(call.output);
  }
  assertComplete(): void { if (this.index !== this.calls.length) throw new ProtocolError('Fixed model outputs not fully consumed'); }
}
