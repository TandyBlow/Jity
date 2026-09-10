"use client";

import type { CSSProperties } from "react";

import { MemoryPanel } from "@/components/game/MemoryPanel";
import { SettingsMenu } from "@/components/game/SettingsMenu";
import { StoryPanel } from "@/components/game/StoryPanel";
import { useGameSession } from "@/components/game/useGameSession";

export default function Home() {
  const session = useGameSession();

  return (
    <main
      className={`app-shell${session.backgroundUrl ? " has-scene-background" : ""}`}
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
