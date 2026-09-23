"use client";

import { useCallback, useEffect, useState } from "react";

import { getMemoryTrace } from "@/lib/api";
import type { MemoryTraceResponse } from "@/types";

/**
 * Fetched only while the trace tab is open. A few hundred turns of name lists
 * is not worth carrying on every timeline page load.
 */
export function useMemoryTrace(sessionId: string, enabled: boolean) {
  const [trace, setTrace] = useState<MemoryTraceResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const reload = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError("");
    try {
      setTrace(await getMemoryTrace(sessionId));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "记忆轨迹加载失败");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    if (enabled) void reload();
  }, [enabled, reload]);

  return { trace, error, loading, reload };
}
