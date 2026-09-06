"use client";

import { MemoryPanel } from "@/components/game/MemoryPanel";
import { SidePanel } from "@/components/game/SidePanel";
import { StoryPanel } from "@/components/game/StoryPanel";
import { useGameSession } from "@/components/game/useGameSession";

export default function Home() {
  const session = useGameSession();

  return (
    <main className="app-shell">
      <SidePanel session={session} />
      <StoryPanel session={session} />
      <MemoryPanel session={session} />
    </main>
  );
}
