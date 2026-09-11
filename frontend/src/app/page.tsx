"use client";

import { useEffect, useRef } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";

import { MemoryPanel } from "@/components/game/MemoryPanel";
import { SettingsMenu } from "@/components/game/SettingsMenu";
import { StoryPanel } from "@/components/game/StoryPanel";
import { useGameSession } from "@/components/game/useGameSession";

export default function Home() {
  const session = useGameSession();
  const shellRef = useRef<HTMLElement>(null);
  const animationFrameRef = useRef<number | null>(null);

  useEffect(() => () => {
    if (animationFrameRef.current !== null) cancelAnimationFrame(animationFrameRef.current);
  }, []);

  const moveBackground = (event: ReactPointerEvent<HTMLElement>) => {
    if (event.pointerType !== "mouse" || !session.backgroundUrl) return;

    const shell = shellRef.current;
    if (!shell) return;
    const bounds = shell.getBoundingClientRect();
    const shiftX = ((event.clientX - bounds.left) / bounds.width - 0.5) * -20;
    const shiftY = ((event.clientY - bounds.top) / bounds.height - 0.5) * -14;

    if (animationFrameRef.current !== null) cancelAnimationFrame(animationFrameRef.current);
    animationFrameRef.current = requestAnimationFrame(() => {
      shell.style.setProperty("--background-shift-x", `${shiftX.toFixed(2)}px`);
      shell.style.setProperty("--background-shift-y", `${shiftY.toFixed(2)}px`);
    });
  };

  const centerBackground = () => {
    const shell = shellRef.current;
    if (!shell) return;
    if (animationFrameRef.current !== null) cancelAnimationFrame(animationFrameRef.current);
    animationFrameRef.current = requestAnimationFrame(() => {
      shell.style.setProperty("--background-shift-x", "0px");
      shell.style.setProperty("--background-shift-y", "0px");
    });
  };

  return (
    <main
      className={`app-shell${session.backgroundUrl ? " has-scene-background" : ""}`}
      onPointerLeave={centerBackground}
      onPointerMove={moveBackground}
      ref={shellRef}
      style={session.backgroundUrl
        ? ({ "--scene-background": `url("${session.backgroundUrl}")` } as CSSProperties)
      : undefined}
    >
      <div aria-hidden="true" className="scene-background" />
      <div className="game-brand" aria-label="Jity">
        <span>Jity</span>
        <small>GM scenario console</small>
      </div>
      <SettingsMenu session={session} />
      <StoryPanel session={session} />
      <MemoryPanel session={session} />
    </main>
  );
}
