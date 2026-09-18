declare module "open-dice-dnd" {
  export type DiceConfig = {
    dice: "d4" | "d6" | "d8" | "d10" | "d12" | "d20" | "d100";
    rolled?: number;
    diceColor?: number;
    textColor?: string;
    backgroundColor?: string;
    isSecret?: boolean;
    effects?: unknown[];
  };

  export type DicePerDieResult = {
    type: string;
    value: number;
    visible: number;
    target?: number;
  };

  export type DiceBatchResult = {
    total: number;
    variances: { type: string; expected: number; visible: number }[];
    results: DicePerDieResult[];
  };

  export type DiceRollerOptions = {
    container: HTMLElement;
    width?: number;
    height?: number;
    throwSpeed?: number;
    throwSpin?: number;
    soundVolume?: number;
    sounds?: string[];
    effects?: unknown;
    onRollComplete?: (total: number, result: DiceBatchResult) => void;
    onBatchSettled?: (batch: unknown, result: DiceBatchResult, roller: DiceRoller) => void;
  };

  export type InternalDie = {
    body: {
      type: number;
      position: { x: number; y: number; z: number };
      velocity: { x: number; y: number; z: number; set(x: number, y: number, z: number): void };
      angularVelocity: { x: number; y: number; z: number; set(x: number, y: number, z: number): void };
    };
    mesh: {
      position: { x: number; y: number; z: number };
      scale: { setScalar(value: number): void };
    };
  };

  export class DiceRoller {
    constructor(options: DiceRollerOptions);
    dice: InternalDie[];
    walls: { position: { x: number; y: number; z: number } }[];
    camera: { zoom: number; updateProjectionMatrix(): void };
    roll(diceConfig: DiceConfig[]): Promise<number>;
    playEffect(spec: unknown, die: InternalDie, extras?: unknown): unknown;
    glow(die: InternalDie, options?: { color?: number; duration?: number; intensity?: number }): unknown;
    haloRing(die: InternalDie, options?: { color?: number; duration?: number; endRadius?: number }): unknown;
    reset(): Promise<void>;
    destroy(): void;
  }

  export function glow(options?: { color?: number; duration?: number; intensity?: number }): unknown;
  export function scalePulse(options?: { peak?: number; duration?: number }): unknown;
  export function haloRing(options?: { color?: number; duration?: number; endRadius?: number }): unknown;
  export function confetti(options?: { count?: number; duration?: number }): unknown;

  export const presets: {
    classicCrit: unknown;
  };
}
