"use client";

import { useEffect, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";

import { MemoryDrawer } from "@/components/game/MemoryDrawer";
import { MemoryPanel } from "@/components/game/MemoryPanel";
import { SettingsMenu } from "@/components/game/SettingsMenu";
import { StoryPanel } from "@/components/game/StoryPanel";
import { useGameSession } from "@/components/game/useGameSession";

/** Where the docked memory column gives way to the drawer. */
const DOCKED_MEMORY_QUERY = "(min-width: 1101px)";

export default function Home() {
  const session = useGameSession();
  const shellRef = useRef<HTMLElement>(null);
  const animationFrameRef = useRef<number | null>(null);
  const [memoryOpen, setMemoryOpen] = useState(false);

  useEffect(() => () => {
    if (animationFrameRef.current !== null) cancelAnimationFrame(animationFrameRef.current);
  }, []);

  // ?memory=1 opens the drawer on load, matching how the timeline reads its
  // own view state from the URL.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("memory") === "1") setMemoryOpen(true);
  }, []);

  // Widening past the breakpoint hides the drawer with display:none, which
  // would leave the focus trap live inside an invisible element.
  useEffect(() => {
    const query = window.matchMedia(DOCKED_MEMORY_QUERY);
    const closeWhenDocked = () => { if (query.matches) setMemoryOpen(false); };
    closeWhenDocked();
    query.addEventListener("change", closeWhenDocked);
    return () => query.removeEventListener("change", closeWhenDocked);
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
      <StoryPanel onOpenMemory={() => setMemoryOpen(true)} session={session} />
      <MemoryPanel session={session} />
      <MemoryDrawer onClose={() => setMemoryOpen(false)} open={memoryOpen} session={session} />
    </main>
  );
}
