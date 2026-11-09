/** One local game session: a ControllerDriver over the browser-local transport.
 * The driver owns scheduling, group freezing, dice admission and the six-stage
 * loop; the transport owns state. No lease heartbeat is needed because the
 * local store cannot be taken over by another process, but the driver still
 * mints request ids and replays a retried write idempotently. */
import { ControllerDriver, initialMemory, type DriverStatus, type WorldModelPort } from '../controller';
import type { ControllerMemory } from '../schedule';
import type { Id, InitialTemplate, WorldContext, ControlState, PointWork, WorldState } from '../types';
import { LocalWorldTransport } from './transport';

export interface LocalGameSnapshot {
  transport: ReturnType<LocalWorldTransport['snapshot']>;
  commands: string[];
}

export class LocalGameSession {
  readonly transport: LocalWorldTransport;
  private readonly model: WorldModelPort;
  private readonly driver: ControllerDriver;
  private readonly initial: InitialTemplate | null;
  private readonly commands: string[];

  private constructor(transport: LocalWorldTransport, model: WorldModelPort, initial: InitialTemplate | null,
    commands: string[],
    state?: { world: WorldContext | null; control: ControlState; work: PointWork | null; activeInput: { advanceId: Id; inputId: Id; text: string } | null },
    memory?: ControllerMemory) {
    this.transport = transport;
    this.model = model;
    this.initial = initial;
    this.commands = commands;
    const prefix = `local_${Math.random().toString(36).slice(2, 10)}`;
    const seed = memory ?? initialMemory(prefix, `${prefix}_holder`);
    // New worlds carry the template; restored worlds are seeded from context.
    if (initial) seed.initialTemplate = structuredClone(initial);
    this.driver = new ControllerDriver({ transport, model }, seed, state ?? { world: null });
  }

  static async create(initial: InitialTemplate, model: WorldModelPort, options: { worldId?: Id; onPersist?: (snapshot: LocalGameSnapshot) => void; roll?: () => number } = {}): Promise<LocalGameSession> {
    const commands: string[] = [];
    const transport = await LocalWorldTransport.create(initial, {
      worldId: options.worldId,
      roll: options.roll,
      onPersist: (snapshot) => options.onPersist?.({ transport: snapshot, commands: [...commands] }),
    });
    return new LocalGameSession(transport, model, initial ?? null, commands);
  }

  static async restore(snapshot: LocalGameSnapshot, model: WorldModelPort, options: { onPersist?: (next: LocalGameSnapshot) => void; roll?: () => number } = {}): Promise<LocalGameSession> {
    const commands: string[] = [...snapshot.commands];
    const transport = await LocalWorldTransport.restore(snapshot.transport, {
      roll: options.roll,
      onPersist: (next) => options.onPersist?.({ transport: next, commands: [...commands] }),
    });
    const context = await transport.execute('get_context', {}, { worldId: transport.worldId });
    if (context.work) {
      throw new Error('local_recovery_work_in_progress');
    }
    return new LocalGameSession(transport, model, null, commands, {
      world: context.world, control: context.control, work: context.work, activeInput: context.activeInput,
    });
  }

  get worldId(): Id { return this.transport.worldId; }
  get commandsPlayed(): string[] { return [...this.commands]; }
  get snapshot(): LocalGameSnapshot { return { transport: this.transport.snapshot(), commands: [...this.commands] }; }
  get memory(): ControllerMemory { return this.driver.getMemory(); }

  async start(): Promise<DriverStatus> { return this.driver.run(); }

  /** A player command starts a new advance. The caller must await `run()` to
   * settle it; the promise resolves at handback/await, never mid-point. */
  async submit(text: string): Promise<DriverStatus> {
    const snapshot = this.transport.snapshot();
    const plan = snapshot.initial.characters;
    const order = Object.keys(plan).sort();
    const memory = this.driver.getMemory();
    const allocationKey = `command_${snapshot.round ? snapshot.round.roundId : 'new'}_${memory.requestId}`;
    const clear = Object.keys(memory.ids);
    this.driver.preparePlayerInput(text, order, {
      allocationKey,
      slots: [
        { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' },
        { slotKey: 'round', kind: 'round' }, { slotKey: 'point', kind: 'point' },
        ...order.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' as const })),
      ],
    }, clear);
    this.commands.push(text);
    return this.driver.run();
  }

  async pause(): Promise<DriverStatus> {
    this.driver.deliver({ kind: 'pause' });
    return this.driver.run();
  }

  async resume(): Promise<DriverStatus> {
    this.driver.deliver({ kind: 'resume' });
    return this.driver.run();
  }

  async cancel(reason = 'player_cancelled'): Promise<DriverStatus> {
    this.driver.deliver({ kind: 'cancel', reason });
    return this.driver.run();
  }

  async state(): Promise<WorldState> {
    const response = await this.transport.execute('get_state', {}, { worldId: this.transport.worldId });
    return response.data.state;
  }
}
