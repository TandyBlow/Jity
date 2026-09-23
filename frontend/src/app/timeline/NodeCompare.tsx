"use client";

import { diffMemory } from "@/lib/game/memoryDiff";
import type { TimelineData } from "@/app/timeline/useTimelineData";
import type { MemoryCategory } from "@/types";

const CATEGORIES: Array<{ key: MemoryCategory; label: string }> = [
  { key: "items", label: "物品" },
  { key: "npcs", label: "NPC" },
  { key: "quests", label: "任务" },
  { key: "world_facts", label: "长期事实" },
];

/**
 * Two turns' states side by side.
 *
 * Entry-level diffing is safe here because stored state has already been
 * normalized by the server: both sides carry the same keys and the same
 * empty-value conventions.
 */
export function NodeCompare({ data, currentTurn }: { data: TimelineData; currentTurn?: number }) {
  const base = data.compareNode;
  const target = data.selectedNode;
  if (!base || !target) return null;

  if (base.id === target.id) {
    return (
      <section className="node-compare">
        <h3>状态对比</h3>
        <p className="meta">基准和当前是同一个节点。</p>
      </section>
    );
  }

  const turnOf = (id: number) => {
    const node = data.timelineNodes.find((candidate) => candidate.id === id);
    return node ? `T${node.turn}` : `#${id}`;
  };
  const baseTurn = data.timelineNodes.find((node) => node.id === base.id)?.turn;

  return (
    <section className="node-compare">
      <h3>
        状态对比 <span className="meta">{turnOf(base.id)} → {currentTurn !== undefined ? `T${currentTurn}` : turnOf(target.id)}</span>
      </h3>
      {CATEGORIES.map(({ key, label }) => {
        const diff = diffMemory(base.state[key], target.state[key]);
        if (diff.added.length === 0 && diff.removed.length === 0 && diff.changed.length === 0) {
          return (
            <div className="node-compare-category" key={key}>
              <div className="node-compare-head"><span>{label}</span><span className="meta">无变化</span></div>
            </div>
          );
        }
        return (
          <div className="node-compare-category" key={key}>
            <div className="node-compare-head">
              <span>{label}</span>
              <span className="meta">
                +{diff.added.length} −{diff.removed.length} ~{diff.changed.length}
              </span>
            </div>
            <ul>
              {diff.added.map((name) => (
                <li className="added" key={`a-${name}`}><span>{name}</span><em>新增</em></li>
              ))}
              {diff.removed.map((name) => (
                <li className="removed" key={`r-${name}`}><span>{name}</span><em>消失</em></li>
              ))}
              {diff.changed.map(({ name, fields }) => (
                <li className="changed" key={`c-${name}`}>
                  <span>{name}</span>
                  <em>{fields.join(" · ")}</em>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      <button className="node-compare-clear" onClick={data.clearCompareNode} type="button">
        清除基准（{baseTurn !== undefined ? `T${baseTurn}` : `#${base.id}`}）
      </button>
    </section>
  );
}
