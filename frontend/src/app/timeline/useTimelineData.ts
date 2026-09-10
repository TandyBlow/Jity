"use client";

import { useCallback, useEffect, useState } from "react";

import { getCampaign, getSessionProgress, listCampaigns } from "@/lib/api";
import type { CampaignArc, CampaignListItem, WorldFactMemory } from "@/types";

export type FilterMode = "all" | "known" | "suspected";

export function useTimelineData(sessionId: string) {
  const [campaigns, setCampaigns] = useState<CampaignListItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>("");
  const [arcs, setArcs] = useState<CampaignArc[]>([]);
  const [revealedAnchors, setRevealedAnchors] = useState<string[]>([]);
  const [worldFacts, setWorldFacts] = useState<WorldFactMemory[]>([]);
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      listCampaigns().catch(() => ({ campaigns: [] })),
      sessionId
        ? getSessionProgress(sessionId).catch(() => null)
        : Promise.resolve(null),
    ]).then(([list, progress]) => {
      setCampaigns(list.campaigns ?? []);
      if (progress) {
        setRevealedAnchors(progress.revealed_anchors ?? []);
        setWorldFacts(progress.world_facts ?? []);
      }
      // Auto-select first campaign
      const files = list.campaigns ?? [];
      if (files.length > 0) {
        const first = files[0].filename;
        setSelectedFile(first);
        getCampaign(first)
          .then((d) => setArcs(d.campaign?.arcs ?? []))
          .catch(() => setArcs([]));
      }
      setLoading(false);
    });
  }, [sessionId]);

  const handleSelectCampaign = useCallback((filename: string) => {
    setSelectedFile(filename);
    getCampaign(filename)
      .then((d) => setArcs(d.campaign?.arcs ?? []))
      .catch(() => setArcs([]));
  }, []);

  const isAnchorRevealed = (id: string) => revealedAnchors.includes(id);

  const filteredFacts =
    filterMode === "all"
      ? worldFacts
      : worldFacts.filter((f) =>
          filterMode === "known" ? f.status === "known" : f.status === "suspected"
        );

  return {
    campaigns, selectedFile, arcs, revealedAnchors, worldFacts,
    filterMode, setFilterMode, loading,
    handleSelectCampaign, isAnchorRevealed, filteredFacts,
  };
}

export type TimelineData = ReturnType<typeof useTimelineData>;
