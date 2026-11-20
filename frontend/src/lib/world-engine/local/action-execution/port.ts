/** Product port for the action-family tasks.
 *
 * The integrated page's `LocalGameModel` answers `action`, `targets` and
 * `reaction` with short inline prompts that skip every character the player
 * did not name (`lastPlayerInput.includes(name)`) and every protagonist
 * action that fails a verb regex. That loses autonomous action and forced
 * reactions, which R06–R08 require. This port replaces exactly those three
 * tasks and delegates everything else (pointPlan, results, updates,
 * continuation, narration, time, initial) to the existing model untouched.
 *
 * Wiring contract for 06 (see design/parallel-handoff/03-actions-product.md):
 *
 *   const model = new ActionExecutionModel(existingLocalGameModel, engine, {
 *     onTask: (task, key, detail) => console.info(...),
 *     recentEvents: () => [lastResultsText],
 *   });
 *
 * It satisfies `WorldModelPort`, so the controller does not change.
 */
import type { Json, WorldState } from '../../types';
import type { InferenceEngine } from '../../runtime/engine';
import type { ModelTask } from '../../schedule';
import type { WorldModelPort } from '../../controller';
import { createActionHandlers, type ActionHandlers } from '../semantics/actions/index';
import type { ActionHandlerOptions, ActionIssue, HandlerResult } from '../semantics/actions/types';

/** Same shape the page already logs through `LocalGameModel.onTask`. */
export interface ActionTaskReport {
  task: ModelTask;
  key: string;
  ms: number;
  fallback: boolean;
  error?: string;
  raw?: string;
  promptChars?: number;
  /** Present for action-family tasks: what the guards concluded. */
  issues?: ActionIssue[];
  source?: HandlerResult['source'];
}

export interface ActionExecutionOptions extends ActionHandlerOptions {
  /** Called for every action-family result (accepted or fallback) and, when
   * the delegate already reports tasks, for the delegated ones too. */
  onTask?: (task: ModelTask, key: string, detail: ActionTaskReport) => void;
}

const ACTION_TASKS = new Set<ModelTask>(['action', 'targets', 'reaction']);

function errorSummary(issues: readonly ActionIssue[]): string | undefined {
  const errors = issues.filter((issue) => issue.severity === 'error');
  if (!errors.length) return undefined;
  return [...new Set(errors.map((issue) => issue.code))].join(',');
}

/** Compose the guarded handlers over the existing local model. The delegate
 * is called for every non-action task; it is never asked to answer these
 * three. */
export class ActionExecutionModel implements WorldModelPort {
  readonly handlers: ActionHandlers;
  readonly evidence: HandlerResult[] = [];

  constructor(
    private readonly delegate: WorldModelPort,
    engine: InferenceEngine,
    private readonly options: ActionExecutionOptions = {},
  ) {
    this.handlers = createActionHandlers({ engine, options });
  }

  async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
    if (!ACTION_TASKS.has(task)) return this.delegate.generate(task, key, input);
    const started = typeof performance !== 'undefined' ? performance.now() : Date.now();
    try {
      const result = task === 'action'
        ? await this.handlers.action(key, input)
        : task === 'targets'
          ? await this.handlers.targets(key, input)
          : await this.handlers.reaction(key, input);
      this.evidence.push(result);
      this.options.onTask?.(task, key, {
        task, key, ms: result.elapsedMs, fallback: result.fallback,
        error: errorSummary(result.issues), raw: result.raw,
        promptChars: result.calls.at(-1)?.promptChars,
        issues: result.issues, source: result.source,
      });
      return result.value;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.options.onTask?.(task, key, {
        task, key, ms: Math.round((typeof performance !== 'undefined' ? performance.now() : Date.now()) - started),
        fallback: true, error: message,
      });
      throw error;
    }
  }
}

export function createActionExecutionModel(
  delegate: WorldModelPort,
  engine: InferenceEngine,
  options: ActionExecutionOptions = {},
): ActionExecutionModel {
  return new ActionExecutionModel(delegate, engine, options);
}

/** The scene a handler would read, without calling the model. Round/order
 * probes use this to show exactly who is in scope. */
export function roundRoster(state: WorldState): { id: string; sanity: number; room: string | null }[] {
  return Object.keys(state.characters).map((id) => ({
    id,
    sanity: state.characters[id].sanity,
    room: state.characters[id].position.containerId,
  }));
}
