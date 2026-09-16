"use client";

import { useCallback, useEffect, useState } from "react";

import {
  activateTimelineNode,
  getCampaign,
  getSessionProgress,
  getTimeline,
  getTimelineNode,
  listCampaigns,
} from "@/lib/api";
import type {
  CampaignArc,
  CampaignListItem,
  TimelineNodeDetail,
  TimelineNodeSummary,
  WorldFactMemory,
} from "@/types";

export type FilterMode = "all" | "known" | "suspected";

export function useTimelineData(
  sessionId: string,
  requestedNodeId?: number,
  preferActiveParent = false,
  live = false,
) {
  const [campaigns, setCampaigns] = useState<CampaignListItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>("");
  const [arcs, setArcs] = useState<CampaignArc[]>([]);
  const [revealedAnchors, setRevealedAnchors] = useState<string[]>([]);
  const [worldFacts, setWorldFacts] = useState<WorldFactMemory[]>([]);
  const [timelineNodes, setTimelineNodes] = useState<TimelineNodeSummary[]>([]);
  const [activeNodeId, setActiveNodeId] = useState<number | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null);
  const [selectedNode, setSelectedNode] = useState<TimelineNodeDetail | null>(null);
  const [timelineError, setTimelineError] = useState("");
  const [activating, setActivating] = useState(false);
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [loading, setLoading] = useState(true);

  const loadNode = useCallback(async (nodeId: number) => {
    if (!sessionId) return;
    setSelectedNodeId(nodeId);
    setTimelineError("");
    try {
      setSelectedNode(await getTimelineNode(sessionId, nodeId));
    } catch (error) {
      setTimelineError(error instanceof Error ? error.message : "剧情节点加载失败");
    }
  }, [sessionId]);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      listCampaigns().catch(() => ({ campaigns: [] })),
      sessionId ? getSessionProgress(sessionId).catch(() => null) : Promise.resolve(null),
      sessionId ? getTimeline(sessionId).catch(() => null) : Promise.resolve(null),
    ]).then(([list, progress, timeline]) => {
      const files = list.campaigns ?? [];
      setCampaigns(files);
      if (progress) {
        setRevealedAnchors(progress.revealed_anchors ?? []);
        setWorldFacts(progress.world_facts ?? []);
      }

      if (timeline) {
        setTimelineNodes(timeline.nodes);
        setActiveNodeId(timeline.active_node_id);
        const active = timeline.nodes.find((node) => node.id === timeline.active_node_id);
        const parentId = active?.parent_id ?? timeline.active_node_id;
        const targetId = requestedNodeId
          ?? (preferActiveParent ? parentId ?? undefined : timeline.active_node_id ?? undefined);
        if (targetId) loadNode(targetId);
      }

      const campaignFile = timeline?.campaign_filename || files[0]?.filename || "";
      setSelectedFile(campaignFile);
      if (campaignFile) {
        getCampaign(campaignFile)
          .then((detail) => setArcs(detail.campaign?.arcs ?? []))
          .catch(() => setArcs([]));
      }
    }).catch((error) => {
      setTimelineError(error instanceof Error ? error.message : "时间线加载失败");
    }).finally(() => {
      setLoading(false);
    });
  }, [sessionId, requestedNodeId, preferActiveParent, loadNode]);

  useEffect(() => {
    if (!live || !sessionId) return;
    let disposed = false;
    const refresh = async () => {
      const [progress, timeline] = await Promise.all([
        getSessionProgress(sessionId).catch(() => null),
        getTimeline(sessionId).catch(() => null),
      ]);
      if (disposed) return;
      if (progress) {
        setRevealedAnchors(progress.revealed_anchors ?? []);
        setWorldFacts(progress.world_facts ?? []);
      }
      if (timeline) {
        setTimelineNodes(timeline.nodes);
        setActiveNodeId(timeline.active_node_id);
      }
    };
    const timer = window.setInterval(refresh, 2000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [live, sessionId]);

  const handleSelectCampaign = useCallback((filename: string) => {
    setSelectedFile(filename);
    getCampaign(filename)
      .then((detail) => setArcs(detail.campaign?.arcs ?? []))
      .catch(() => setArcs([]));
  }, []);

  const handleActivateNode = useCallback(async () => {
    if (!sessionId || !selectedNodeId) return;
    setActivating(true);
    setTimelineError("");
    try {
      await activateTimelineNode(sessionId, selectedNodeId);
      window.localStorage.setItem("jity_active_session_id", sessionId);
      window.location.href = "/";
    } catch (error) {
      setTimelineError(error instanceof Error ? error.message : "恢复剧情节点失败");
      setActivating(false);
    }
  }, [sessionId, selectedNodeId]);

  const isAnchorRevealed = (id: string) => revealedAnchors.includes(id);
  const filteredFacts = filterMode === "all"
    ? worldFacts
    : worldFacts.filter((fact) =>
        filterMode === "known" ? fact.status === "known" : fact.status === "suspected"
      );

  return {
    campaigns, selectedFile, arcs, revealedAnchors, worldFacts,
    timelineNodes, activeNodeId, selectedNodeId, selectedNode,
    timelineError, activating,
    filterMode, setFilterMode, loading,
    handleSelectCampaign, isAnchorRevealed, filteredFacts,
    loadNode, handleActivateNode,
  };
}

export type TimelineData = ReturnType<typeof useTimelineData>;
