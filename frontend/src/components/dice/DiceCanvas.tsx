"use client";

import { useEffect, useRef, useState } from "react";
import type { DiceBatchResult, DiceRoller } from "open-dice-dnd";

type DiceCanvasProps = {
  value: number;
  docking: boolean;
  onSettled: (result: DiceBatchResult) => void;
  onDocked: () => void;
  onError: (message: string) => void;
};

const DOCK_DURATION_MS = 1700;
const SETTLE_GRACE_MS = 500;
const FRUSTUM_SIZE = 18;
const DIE_CAMERA_ZOOM = 1.35;
const DIE_SAFE_RADIUS = 1;
const WALL_HALF_THICKNESS = 1;
const THROW_SPEED = 25;
const ROLLING_HEIGHT = 1.05;
const SPAWN_EDGE_GAP = 0.18;
const SETTLED_SPEED_SQUARED = 0.01;
const STILLNESS_POLL_MS = 50;
const ROLL_TIMEOUT_MS = 15000;

type DiceRollerWithSpawnPhysics = DiceRoller & {
  _applyDiePhysics?: (die: DiceRoller["dice"][number], seed: unknown) => void;
};

function getSafeViewportBounds(container: HTMLDivElement, cameraZoom: number) {
  const width = container.clientWidth || window.innerWidth;
  const height = container.clientHeight || window.innerHeight;
  if (!width || !height) return null;

  const visibleHalfHeight = FRUSTUM_SIZE / (2 * Math.max(cameraZoom, 1));
  const visibleHalfWidth = visibleHalfHeight * (width / height);

  return {
    left: -visibleHalfWidth + DIE_SAFE_RADIUS,
    right: visibleHalfWidth - DIE_SAFE_RADIUS,
    top: visibleHalfHeight - DIE_SAFE_RADIUS,
    bottom: -visibleHalfHeight + DIE_SAFE_RADIUS,
  };
}

function keepDieInsideViewport(roller: DiceRoller, container: HTMLDivElement) {
  if (roller.walls.length < 4) return;

  // The engine's default walls protect the die's center only. Move their inner
  // faces inward by the d20's visual radius so the whole mesh stays on-screen.
  const bounds = getSafeViewportBounds(container, roller.camera.zoom);
  if (!bounds) return;

  roller.walls[0].position.x = bounds.left - WALL_HALF_THICKNESS;
  roller.walls[1].position.x = bounds.right + WALL_HALF_THICKNESS;
  roller.walls[2].position.z = bounds.top + WALL_HALF_THICKNESS;
  roller.walls[3].position.z = bounds.bottom - WALL_HALF_THICKNESS;
}

function keepDieSpawnInsideViewport(roller: DiceRoller, container: HTMLDivElement) {
  const internalRoller = roller as DiceRollerWithSpawnPhysics;
  const originalApplyDiePhysics = internalRoller._applyDiePhysics;
  if (!originalApplyDiePhysics) return null;

  // open-dice-dnd spawns from a fixed, unzoomed frustum. Since this demo uses
  // a zoomed orthographic camera, wrap the package's own spawn method so both
  // its prediction pass and visible pass begin inside the same safe viewport.
  internalRoller._applyDiePhysics = (die, seed) => {
    originalApplyDiePhysics.call(roller, die, seed);

    const bounds = getSafeViewportBounds(container, roller.camera.zoom);
    if (!bounds) return;

    const spawnLeft = Math.min(bounds.left + DIE_SAFE_RADIUS + SPAWN_EDGE_GAP, bounds.right);
    const spawnBottom = Math.min(bounds.bottom + DIE_SAFE_RADIUS + SPAWN_EDGE_GAP, bounds.top);
    const spawnTop = Math.max(bounds.top - DIE_SAFE_RADIUS - SPAWN_EDGE_GAP, bounds.bottom);

    // Always enter from the left instead of occasionally spawning on a wall.
    // The extra gap keeps the collision body clear of the inset wall on frame 1.
    die.body.position.x = spawnLeft;
    die.body.position.z = Math.min(Math.max(die.body.position.z, spawnBottom), spawnTop);
    // The package's default spawn height (y=4..8) makes the die visibly fall
    // into the scene. Start it just above the floor so it rolls in directly.
    die.body.position.y = ROLLING_HEIGHT;
    die.body.velocity.set(die.body.velocity.x, 0, die.body.velocity.z);
    die.mesh.position.x = die.body.position.x;
    die.mesh.position.z = die.body.position.z;
    die.mesh.position.y = die.body.position.y;
  };

  return () => {
    internalRoller._applyDiePhysics = originalApplyDiePhysics;
  };
}

function getDockTarget(container: HTMLDivElement, dieCount: number, cameraZoom: number) {
  const width = container.clientWidth || window.innerWidth;
  const height = container.clientHeight || window.innerHeight;
  const isMobile = width <= 780;
  const targetBottom = isMobile ? 315 : 260;
  const targetScreenY = Math.max(80, height - targetBottom);
  const visibleFrustumSize = FRUSTUM_SIZE / cameraZoom;
  const targetZ = (targetScreenY / height - 0.5) * visibleFrustumSize;
  const spacing = isMobile ? 1.05 : 1.2;
  const center = (dieCount - 1) / 2;

  return {
    z: targetZ,
    x: (index: number) => (index - center) * spacing,
  };
}

export function DiceCanvas({ value, docking, onSettled, onDocked, onError }: DiceCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rollerRef = useRef<DiceRoller | null>(null);
  const settledRef = useRef(false);
  const settledResultRef = useRef<DiceBatchResult | null>(null);
  const dockStartedRef = useRef(false);
  const dockFrameRef = useRef<number | null>(null);
  const onSettledRef = useRef(onSettled);
  const onDockedRef = useRef(onDocked);
  const onErrorRef = useRef(onError);
  const [status, setStatus] = useState<"loading" | "ready" | "failed">("loading");

  useEffect(() => {
    onSettledRef.current = onSettled;
    onDockedRef.current = onDocked;
    onErrorRef.current = onError;
  }, [onDocked, onError, onSettled]);

  useEffect(() => {
    let disposed = false;
    let roller: DiceRoller | null = null;
    let resizeWalls: (() => void) | null = null;
    let restoreSpawnPhysics: (() => void) | null = null;
    let settleTimer: number | null = null;
    let settleScheduled = false;
    let watchdogTimer: number | null = null;
    let finalEffectFactories: {
      scalePulse: (options?: { peak?: number; duration?: number }) => unknown;
      confetti: (options?: { count?: number; duration?: number }) => unknown;
    } | null = null;
    settledRef.current = false;
    settledResultRef.current = null;
    dockStartedRef.current = false;
    if (dockFrameRef.current !== null) {
      cancelAnimationFrame(dockFrameRef.current);
      dockFrameRef.current = null;
    }

    const clearWatchdog = () => {
      if (watchdogTimer !== null) {
        window.clearTimeout(watchdogTimer);
        watchdogTimer = null;
      }
    };

    // The library only reports stillness through callbacks. If the physics keeps
    // jittering those callbacks never fire and the roll would hang forever, so a
    // hard deadline turns the hang into a retryable failure.
    const startWatchdog = () => {
      clearWatchdog();
      watchdogTimer = window.setTimeout(() => {
        watchdogTimer = null;
        if (disposed || settledRef.current) return;
        fail(new Error("3D 骰子超时未停稳"));
      }, ROLL_TIMEOUT_MS);
    };

    const areDiceStill = () => {
      if (!roller?.dice?.length) return false;

      return roller.dice.every((die) => {
        const linearSpeedSquared =
          die.body.velocity.x ** 2 + die.body.velocity.y ** 2 + die.body.velocity.z ** 2;
        const angularSpeedSquared =
          die.body.angularVelocity.x ** 2 +
          die.body.angularVelocity.y ** 2 +
          die.body.angularVelocity.z ** 2;
        return linearSpeedSquared < SETTLED_SPEED_SQUARED && angularSpeedSquared < SETTLED_SPEED_SQUARED;
      });
    };

    const freezeAndReveal = (result: DiceBatchResult) => {
      if (disposed || settledRef.current) return;
      settledRef.current = true;
      settledResultRef.current = result;
      clearWatchdog();

      const visible = result.results[0]?.visible;
      // Roll-under d20: natural 1 is the best face, natural 20 the worst.
      const isCritical = visible === 1;
      const isFumble = visible === 20;

      // Play result effects only after the final stillness check. The first
      // low-velocity report must remain visually neutral.
      const activeRoller = roller;
      if (activeRoller?.dice?.length) {
        activeRoller.dice.forEach((die) => {
          activeRoller.glow(die, {
            color: isCritical ? 0xfacc15 : isFumble ? 0xef4444 : 0xffd166,
            duration: DOCK_DURATION_MS + 1800,
            intensity: isCritical ? 1.6 : 2.2,
          });

          if (isCritical) {
            activeRoller.haloRing(die, { color: 0xfacc15, duration: 1400, endRadius: 2.6 });
            if (finalEffectFactories) {
              activeRoller.playEffect(finalEffectFactories.scalePulse({ peak: 1.5, duration: 700 }), die);
              activeRoller.playEffect(finalEffectFactories.confetti({ count: 70 }), die);
            }
          } else if (isFumble) {
            activeRoller.haloRing(die, { color: 0xef4444, duration: 1000, endRadius: 1.8 });
          }
        });
      }

      // Freeze the physical bodies only after a complete stillness window. The
      // dock animation below moves these same meshes, so the die itself travels
      // instead of the transparent canvas being resized.
      if (roller?.dice?.length) {
        roller.dice.forEach((die) => {
          // cannon-es uses 4 for KINEMATIC. This prevents gravity from pulling
          // the settled die away while the presentation animation is running.
          die.body.type = 4;
          die.body.velocity.set(0, 0, 0);
          die.body.angularVelocity.set(0, 0, 0);
        });
      }

      onSettledRef.current(result);
    };

    const pollForStillness = (result: DiceBatchResult) => {
      if (disposed || settledRef.current) return;
      settleTimer = window.setTimeout(() => {
        settleTimer = null;
        if (disposed || settledRef.current) return;

        if (areDiceStill()) {
          scheduleStabilityWindow(result);
        } else {
          pollForStillness(result);
        }
      }, STILLNESS_POLL_MS);
    };

    const scheduleStabilityWindow = (result: DiceBatchResult) => {
      if (disposed || settledRef.current) return;
      settleTimer = window.setTimeout(() => {
        settleTimer = null;
        if (disposed || settledRef.current) return;

        if (areDiceStill()) {
          freezeAndReveal(result);
        } else {
          pollForStillness(result);
        }
      }, SETTLE_GRACE_MS);
    };

    const finish = (result: DiceBatchResult) => {
      if (disposed || settledRef.current || settleScheduled) return;
      settleScheduled = true;

      // open-dice-dnd reports the first low-velocity frame as settled. Start a
      // 500ms confirmation window, then repeat the process if the die moves again.
      scheduleStabilityWindow(result);
    };

    const fail = (error: unknown) => {
      if (disposed) return;
      clearWatchdog();
      const message = error instanceof Error ? error.message : "3D 骰子初始化失败";
      setStatus("failed");
      onErrorRef.current(message);
    };

    const mountRoller = async () => {
      if (!containerRef.current) return;

      try {
        const { DiceRoller: OpenDiceRoller, scalePulse, confetti } = await import("open-dice-dnd");
        if (disposed || !containerRef.current) return;

        finalEffectFactories = { scalePulse, confetti };

        roller = new OpenDiceRoller({
          container: containerRef.current,
          throwSpeed: THROW_SPEED,
          throwSpin: 24,
          soundVolume: 0.45,
          effects: [],
          onRollComplete: (_total, result) => finish(result),
          onBatchSettled: (_batch, result) => finish(result),
        });
        rollerRef.current = roller;
        // Zoom the transparent dice scene uniformly. This makes the d20 easier
        // to read without stretching the canvas or changing any axis of the die.
        roller.camera.zoom = DIE_CAMERA_ZOOM;
        roller.camera.updateProjectionMatrix();
        restoreSpawnPhysics = keepDieSpawnInsideViewport(roller, containerRef.current);
        const applyWallBounds = () => {
          if (roller && containerRef.current) {
            keepDieInsideViewport(roller, containerRef.current);
          }
        };
        resizeWalls = applyWallBounds;
        applyWallBounds();
        window.addEventListener("resize", applyWallBounds);
        setStatus("ready");

        startWatchdog();
        await roller.roll([
          {
            dice: "d20",
            rolled: value,
            diceColor: 0x541923,
            textColor: "#fff7cf",
            backgroundColor: "#8f2f3a",
          },
        ]);
      } catch (error) {
        fail(error);
      }
    };

    void mountRoller();

    return () => {
      disposed = true;
      if (dockFrameRef.current !== null) {
        cancelAnimationFrame(dockFrameRef.current);
        dockFrameRef.current = null;
      }
      if (settleTimer !== null) {
        window.clearTimeout(settleTimer);
        settleTimer = null;
      }
      clearWatchdog();
      if (resizeWalls) {
        window.removeEventListener("resize", resizeWalls);
      }
      restoreSpawnPhysics?.();
      rollerRef.current = null;
      roller?.destroy();
    };
  }, [value]);

  useEffect(() => {
    if (!docking || dockStartedRef.current || !containerRef.current) return;

    const roller = rollerRef.current;
    const result = settledResultRef.current;
    if (!roller || !result || roller.dice.length === 0) return;

    dockStartedRef.current = true;
    const dice = roller.dice.slice();
    const target = getDockTarget(containerRef.current, dice.length, roller.camera.zoom);
    const starts = dice.map((die) => ({
      x: die.body.position.x,
      z: die.body.position.z,
    }));
    const startedAt = performance.now();

    const animateDock = (now: number) => {
      const progress = Math.min((now - startedAt) / DOCK_DURATION_MS, 1);
      const eased = 1 - Math.pow(1 - progress, 3);

      dice.forEach((die, index) => {
        const x = starts[index].x + (target.x(index) - starts[index].x) * eased;
        const z = starts[index].z + (target.z - starts[index].z) * eased;
        die.body.position.x = x;
        die.body.position.z = z;
        die.mesh.position.x = x;
        die.mesh.position.z = z;
        die.body.velocity.set(0, 0, 0);
        die.body.angularVelocity.set(0, 0, 0);
      });

      if (progress < 1) {
        dockFrameRef.current = requestAnimationFrame(animateDock);
        return;
      }

      dockFrameRef.current = null;
      onDockedRef.current();
    };

    dockFrameRef.current = requestAnimationFrame(animateDock);

    return () => {
      if (dockFrameRef.current !== null) {
        cancelAnimationFrame(dockFrameRef.current);
        dockFrameRef.current = null;
      }
    };
  }, [docking]);

  return (
    <div className="real-dice-wrapper">
      <div className={`real-dice-result-marker ${docking ? "visible" : ""}`} aria-hidden="true">
        <span />
      </div>
      <div className="real-dice-canvas-host" ref={containerRef} />
      {status === "loading" ? (
        <div className="real-dice-status">正在加载 Three.js 物理骰子…</div>
      ) : null}
      {status === "failed" ? (
        <div className="real-dice-status failed">3D 骰子加载失败，请重试。</div>
      ) : null}
    </div>
  );
}
