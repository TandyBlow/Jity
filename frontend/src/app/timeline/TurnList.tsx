"use client";

import type { TimelineData } from "@/app/timeline/useTimelineData";

/**
 * The active path as a flat, turn-ordered list. A linear run has no branches
 * to show, so the tree is a column of identical cards; this is what stays
 * readable across a few hundred turns.
 */
export function TurnList({ data }: { data: TimelineData }) {
  const path = data.timelineNodes
    .filter((node) => node.is_on_active_path)
    .sort((a, b) => a.turn - b.turn);
  const offPath = data.timelineNodes.length - path.length;

  return (
    <>
      {offPath > 0 ? (
        <p className="turn-list-note">另有 {offPath} 个分支节点不在当前路径上，切回分支树查看。</p>
      ) : null}
      <ol className="turn-list" aria-label="回合列表">
        {path.map((node) => (
          <li key={node.id}>
            <button
              className={`turn-list-item${data.selectedNodeId === node.id ? " selected" : ""}${node.is_active ? " active" : ""}`}
              data-node-id={node.id}
              onClick={() => data.selectNode(node.id)}
              type="button"
            >
              <span className="turn-list-turn">T{node.turn}</span>
              <span className="turn-list-action">{node.label}</span>
              <span className="turn-list-location">{node.location || "未知地点"}</span>
            </button>
          </li>
        ))}
      </ol>
    </>
  );
}
