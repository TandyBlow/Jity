"use client";

import { useCallback, useEffect, useRef, useState } from "react";

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
  const [compareNodeId, setCompareNodeId] = useState<number | null>(null);
  const [compareNode, setCompareNode] = useState<TimelineNodeDetail | null>(null);
  // While watching a run the pane should track the head, not sit on whatever
  // turn happened to be selected first. Picking a node opts out.
  const [following, setFollowing] = useState(true);
  const [timelineError, setTimelineError] = useState("");
  // Page-level load failures live apart from per-node ones so refreshing a
  // node cannot wipe the reason the page came up empty.
  const [loadError, setLoadError] = useState("");
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

  const loadCompareNode = useCallback(async (nodeId: number) => {
    if (!sessionId) return;
    setCompareNodeId(nodeId);
    setTimelineError("");
    try {
      setCompareNode(await getTimelineNode(sessionId, nodeId));
    } catch (error) {
      setTimelineError(error instanceof Error ? error.message : "对比节点加载失败");
    }
  }, [sessionId]);

  const clearCompareNode = useCallback(() => {
    setCompareNodeId(null);
    setCompareNode(null);
  }, []);

  /** Pin the node already on screen; no refetch, the row cannot have changed. */
  const pinCompareNode = useCallback(() => {
    if (!selectedNode) return;
    setCompareNodeId(selectedNode.id);
    setCompareNode(selectedNode);
  }, [selectedNode]);

  const selectNode = useCallback((nodeId: number) => {
    setFollowing(false);
    void loadNode(nodeId);
  }, [loadNode]);

  // The poll must read these without being torn down and rebuilt every time
  // they change, or a 2s tick could never land during an active run.
  const followingRef = useRef(following);
  const selectedIdRef = useRef(selectedNodeId);
  useEffect(() => {
    followingRef.current = following;
    selectedIdRef.current = selectedNodeId;
  }, [following, selectedNodeId]);

  useEffect(() => {
    setLoading(true);
    // A failed fetch used to fall back to an empty value, which renders exactly
    // like a session that genuinely has nothing in it.
    const failed: string[] = [];
    const note = (message: string) => {
      failed.push(message);
      return null;
    };

    Promise.all([
      listCampaigns().catch(() => { note("战役列表加载失败"); return { campaigns: [] }; }),
      sessionId ? getSessionProgress(sessionId).catch(() => note("会话进度加载失败")) : Promise.resolve(null),
      sessionId ? getTimeline(sessionId).catch(() => note("剧情时间线加载失败")) : Promise.resolve(null),
    ]).then(([list, progress, timeline]) => {
      setLoadError(failed.join("；"));
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
          .catch(() => {
            note("战役结构加载失败");
            setArcs([]);
            setLoadError(failed.join("；"));
          });
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
        const head = timeline.active_node_id;
        // Committed turns never change, so re-fetching the selected node is
        // pointless. What goes stale is the selection itself, as the run walks
        // forward past it.
        if (followingRef.current && head && head !== selectedIdRef.current) {
          void loadNode(head);
        }
      }
    };
    const timer = window.setInterval(refresh, 2000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [live, sessionId, loadNode]);

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
    compareNodeId, compareNode, loadCompareNode, clearCompareNode, pinCompareNode,
    following, setFollowing, selectNode, live,
    timelineError, loadError, activating,
    filterMode, setFilterMode, loading,
    handleSelectCampaign, isAnchorRevealed, filteredFacts,
    loadNode, handleActivateNode,
  };
}

export type TimelineData = ReturnType<typeof useTimelineData>;
