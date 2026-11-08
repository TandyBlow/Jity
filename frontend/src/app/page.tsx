"use client";

import { useEffect, useState } from "react";
import { GameConsole } from "@/components/game/GameConsole";
import { StartScreen } from "@/components/game/StartScreen";
import type { SessionResponse } from "@/types";

export default function Home() {
  const [entry, setEntry] = useState<{ session?: SessionResponse } | null>(null);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    // Only explicit deep links and timeline entry actions bypass the start page.
    if (params.get("session") || sessionStorage.getItem("campaign_entry")) setEntry({});
  }, []);
  return entry
    ? <GameConsole initialSession={entry.session} />
    : <StartScreen onEnter={(session) => setEntry({ session })} />;
}
