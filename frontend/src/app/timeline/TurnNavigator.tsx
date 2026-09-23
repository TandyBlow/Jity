"use client";

import { useState } from "react";

import type { TimelineData } from "@/app/timeline/useTimelineData";

export type StoryView = "tree" | "list";

/**
 * Locating a turn by scrolling the tree is hopeless past a few dozen turns:
 * a linear run renders one card per turn, stacked. This is the primary way
 * to reach turn N.
 */
export function TurnNavigator({
  data,
  view,
  onViewChange,
}: {
  data: TimelineData;
  view: StoryView;
  onViewChange: (view: StoryView) => void;
}) {
  const [target, setTarget] = useState("");
  const [note, setNote] = useState("");

  const path = data.timelineNodes
    .filter((node) => node.is_on_active_path)
    .sort((a, b) => a.turn - b.turn);
  const index = path.findIndex((node) => node.id === data.selectedNodeId);

  const step = (offset: number) => {
    const next = index < 0 ? path[path.length - 1] : path[index + offset];
    if (next) data.selectNode(next.id);
  };

  const jump = () => {
    const turn = Number(target);
    if (!Number.isFinite(turn)) return;
    const matches = data.timelineNodes.filter((node) => node.turn === turn);
    if (matches.length === 0) {
      setNote(`没有第 ${turn} 轮`);
      return;
    }
    // Turns are not unique: a rewind leaves sibling branches sharing one.
    const picked = matches.find((node) => node.is_on_active_path) ?? matches[0];
    setNote(matches.length > 1 ? `第 ${turn} 轮有 ${matches.length} 个节点，已选活跃路径上的那个` : "");
    data.selectNode(picked.id);
  };

  return (
    <div className="turn-navigator">
      <div className="turn-nav-group" role="group" aria-label="剧情视图">
        <button className={view === "tree" ? "active" : ""} onClick={() => onViewChange("tree")} type="button">分支树</button>
        <button className={view === "list" ? "active" : ""} onClick={() => onViewChange("list")} type="button">回合列表</button>
      </div>
      <div className="turn-nav-group" role="group" aria-label="按轮次定位">
        <button onClick={() => step(-1)} disabled={index <= 0} type="button">上一轮</button>
        <input
          aria-label="跳转到轮次"
          className="turn-nav-input"
          inputMode="numeric"
          onChange={(event) => setTarget(event.target.value.replace(/[^0-9]/g, ""))}
          onKeyDown={(event) => { if (event.key === "Enter") jump(); }}
          placeholder="轮次"
          value={target}
        />
        <button onClick={jump} type="button">跳转</button>
        <button onClick={() => step(1)} disabled={index < 0 || index >= path.length - 1} type="button">下一轮</button>
      </div>
      {data.live ? (
        <button
          className={`turn-nav-follow${data.following ? " active" : ""}`}
          onClick={() => data.setFollowing(!data.following)}
          type="button"
        >
          {data.following ? "跟随最新一轮" : "已被选定轮次固定"}
        </button>
      ) : null}
      {note ? <span className="turn-nav-note">{note}</span> : null}
    </div>
  );
}
