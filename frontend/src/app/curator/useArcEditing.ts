"use client";

import type { CampaignSchema } from "@/types";

/** Immutable arc/session/anchor list-editing helpers for the curator editor. */
export function useArcEditing(setCampaign: (updater: (prev: CampaignSchema) => CampaignSchema) => void) {
  const updateField = (field: string, value: unknown) => {
    setCampaign((prev) => ({ ...prev, [field]: value }));
  };

  const updateArc = (ai: number, field: string, value: unknown) => {
    setCampaign((prev) => {
      const arcs = [...prev.arcs];
      arcs[ai] = { ...arcs[ai], [field]: value };
      return { ...prev, arcs };
    });
  };

  const addArc = () => {
    setCampaign((prev) => ({
      ...prev,
      arcs: [...prev.arcs, { name: "新弧", goal: "", sessions: [] }],
    }));
  };

  const addSession = (ai: number) => {
    setCampaign((prev) => {
      const arcs = [...prev.arcs];
      arcs[ai] = {
        ...arcs[ai],
        sessions: [...arcs[ai].sessions, { name: "新幕", opening_scene: "", max_turns_per_session: 30, anchor_events: [] }],
      };
      return { ...prev, arcs };
    });
  };

  const updateSession = (ai: number, si: number, field: string, value: unknown) => {
    setCampaign((prev) => {
      const arcs = [...prev.arcs];
      const sessions = [...arcs[ai].sessions];
      sessions[si] = { ...sessions[si], [field]: value };
      arcs[ai] = { ...arcs[ai], sessions };
      return { ...prev, arcs };
    });
  };

  const addAnchor = (ai: number, si: number) => {
    setCampaign((prev) => {
      const arcs = [...prev.arcs];
      const sessions = [...arcs[ai].sessions];
      sessions[si] = {
        ...sessions[si],
        anchor_events: [
          ...sessions[si].anchor_events,
          {
            id: `anchor-${Date.now()}`,
            name: "新锚点",
            description: "",
            priority: 3,
            trigger_conditions: {} as Record<string, string | null>,
          },
        ],
      };
      arcs[ai] = { ...arcs[ai], sessions };
      return { ...prev, arcs };
    });
  };

  const updateAnchor = (ai: number, si: number, ani: number, field: string, value: unknown) => {
    setCampaign((prev) => {
      const arcs = [...prev.arcs];
      const sessions = [...arcs[ai].sessions];
      const anchors = [...sessions[si].anchor_events];
      anchors[ani] = { ...anchors[ani], [field]: value };
      sessions[si] = { ...sessions[si], anchor_events: anchors };
      arcs[ai] = { ...arcs[ai], sessions };
      return { ...prev, arcs };
    });
  };

  const removeArc = (ai: number) => {
    setCampaign((prev) => ({
      ...prev,
      arcs: prev.arcs.filter((_, i) => i !== ai),
    }));
  };

  return { updateField, updateArc, addArc, addSession, updateSession, addAnchor, updateAnchor, removeArc };
}
