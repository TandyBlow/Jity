"use client";

import { useEffect, useRef, useState } from "react";

import { MemoryDelta } from "@/app/timeline/MemoryDelta";
import { NodeCompare } from "@/app/timeline/NodeCompare";
import { TurnContextPanel } from "@/app/timeline/TurnContextPanel";
import { TurnList } from "@/app/timeline/TurnList";
import { TurnNavigator, type StoryView } from "@/app/timeline/TurnNavigator";
import type { TimelineData } from "@/app/timeline/useTimelineData";
import type { TimelineNodeSummary } from "@/types";

export function StoryTimeline({ data, hasSession }: { data: TimelineData; hasSession: boolean }) {
  const [view, setView] = useState<StoryView>("tree");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (data.selectedNodeId === null) return;
    const target = scrollRef.current?.querySelector(`[data-node-id="${data.selectedNodeId}"]`);
    // Nothing scrolled this surface before. Without it, jumping to a late turn
    // updates the detail pane while leaving the node itself tens of thousands
    // of pixels away.
    target?.scrollIntoView({ block: "nearest" });
  }, [data.selectedNodeId, view]);

  if (!hasSession) {
    return <p className="empty-state">请从游戏控制台打开时间线，以查看当前会话的剧情分支。</p>;
  }
  if (data.timelineNodes.length === 0) {
    // "No nodes" and "could not load" must not look the same; the banner above
    // the tabs already says which one it is.
    return data.loadError ? null : <p className="empty-state">当前会话还没有可显示的剧情节点。</p>;
  }

  const children = new Map<number | null, TimelineNodeSummary[]>();
  for (const node of data.timelineNodes) {
    const siblings = children.get(node.parent_id) ?? [];
    siblings.push(node);
    children.set(node.parent_id, siblings);
  }
  const roots = children.get(null) ?? [];

  const renderNode = (node: TimelineNodeSummary) => (
    <li key={node.id}>
      <button
        className={`story-node${node.is_active ? " active" : ""}${node.is_on_active_path ? " on-path" : ""}${data.selectedNodeId === node.id ? " selected" : ""}`}
        data-node-id={node.id}
        onClick={() => data.selectNode(node.id)}
        type="button"
      >
        <span className="story-node-turn">T{node.turn}</span>
        <strong>{node.label}</strong>
        <span>{node.location || "未知地点"}</span>
        {node.is_active ? <em>当前时间线</em> : null}
      </button>
      {(children.get(node.id)?.length ?? 0) > 0 ? (
        <ul>{children.get(node.id)?.map(renderNode)}</ul>
      ) : null}
    </li>
  );

  const detail = data.selectedNode;
  const state = detail?.state;
  const summary = detail ? data.timelineNodes.find((node) => node.id === detail.id) : undefined;
  return (
    <div className="story-timeline-layout">
      <div className="story-tree-column">
        <TurnNavigator data={data} onViewChange={setView} view={view} />
        <div className="story-tree-scroll" ref={scrollRef}>
          {view === "tree" ? (
            <div className="story-tree" aria-label="剧情分支树"><ul>{roots.map(renderNode)}</ul></div>
          ) : (
            <TurnList data={data} />
          )}
        </div>
      </div>
      <aside className="story-node-detail">
        {!detail ? <p className="empty-state">选择一个节点查看剧情和状态。</p> : (
          <>
            <div className="story-detail-heading">
              <div>
                <span className="meta">
                  {summary ? `第 ${summary.turn} 轮 · ` : ""}第 {detail.depth} 步
                </span>
                <h2>{detail.parent_id === null ? "会话起点" : detail.player_action}</h2>
              </div>
              {detail.id === data.activeNodeId ? <span className="timeline-current-badge">当前</span> : null}
            </div>
            {/* Kept at the top: pinning a base and clicking through turns is
                the whole interaction, and the result should not need scrolling. */}
            <div className="node-compare-actions">
              <button className="node-compare-pin" onClick={data.pinCompareNode} type="button">
                设为对比基准
              </button>
              <button
                className="node-compare-pin"
                disabled={!data.activeNodeId || data.activeNodeId === detail.id}
                onClick={() => { if (data.activeNodeId) void data.loadCompareNode(data.activeNodeId); }}
                type="button"
              >
                以当前进度为基准
              </button>
            </div>
            <NodeCompare currentTurn={summary?.turn} data={data} />
            {detail.output ? (
              <>
                <div className="story-detail-narration">{detail.output.narration}</div>
                {detail.output.dialogue.length > 0 ? (
                  <div className="story-detail-dialogue">
                    {detail.output.dialogue.map((line, index) => (
                      <p key={`${line.speaker}-${index}`}><strong>{line.speaker}：</strong>{line.text}</p>
                    ))}
                  </div>
                ) : null}
                <div className="story-detail-options">
                  <span className="meta">当时可选行动</span>
                  {detail.output.options.map((option) => <span key={option}>{option}</span>)}
                </div>
              </>
            ) : <p className="empty-state">这是会话开始前的初始状态。</p>}
            {state ? (
              <>
                <div className="story-state-preview">
                  <div><span>位置</span><strong>{state.current_location || "未知"}</strong></div>
                  <div><span>生命 / SAN</span><strong>{state.health} / {state.sanity}</strong></div>
                  <div><span>物品</span><strong>{state.items.length}</strong></div>
                  <div><span>NPC</span><strong>{state.npcs.length}</strong></div>
                  <div><span>任务</span><strong>{state.quests.length}</strong></div>
                  <div><span>事实</span><strong>{state.world_facts.length}</strong></div>
                </div>
                <StateList title="物品" entries={state.items.map((item) => `${item.name}${item.status ? ` · ${item.status}` : ""}`)} />
                <StateList title="NPC" entries={state.npcs.map((npc) => `${npc.name}${npc.relationship ? ` · ${npc.relationship}` : ""}`)} />
                <StateList title="任务" entries={state.quests.map((quest) => `${quest.name}${quest.status ? ` · ${quest.status}` : ""}`)} />
                <StateList title="关键事实" entries={state.world_facts.map((fact) => `${fact.name}${fact.status ? ` · ${fact.status}` : ""}`)} />
              </>
            ) : null}
            <MemoryDelta detail={detail} />
            <TurnContextPanel context={detail.context} />
            <button
              className="timeline-activate-button"
              disabled={data.activating || detail.id === data.activeNodeId}
              onClick={data.handleActivateNode}
              type="button"
            >
              {detail.id === data.activeNodeId ? "这里已是当前进度" : data.activating ? "正在恢复…" : "从此处继续"}
            </button>
          </>
        )}
      </aside>
    </div>
  );
}

function StateList({ title, entries }: { title: string; entries: string[] }) {
  if (entries.length === 0) return null;
  return (
    <div className="story-state-list">
      <span className="meta">{title}</span>
      <div>{entries.map((entry, index) => <span key={`${entry}-${index}`}>{entry}</span>)}</div>
    </div>
  );
}
