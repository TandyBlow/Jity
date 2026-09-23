"use client";

import { useMemo, useState } from "react";

import type { MemoryCategory, MemoryTraceNode, MemoryTraceResponse } from "@/types";

const CATEGORIES: Array<{ key: MemoryCategory; label: string }> = [
  { key: "items", label: "物品" },
  { key: "npcs", label: "NPC" },
  { key: "quests", label: "任务" },
  { key: "world_facts", label: "长期事实" },
];

type Lifetime = {
  name: string;
  declaredTurns: number[];
  heldTurns: number[];
};

function lifetimes(nodes: MemoryTraceNode[], category: MemoryCategory): Lifetime[] {
  const byName = new Map<string, Lifetime>();
  const ensure = (name: string) => {
    let entry = byName.get(name);
    if (!entry) {
      entry = { name, declaredTurns: [], heldTurns: [] };
      byName.set(name, entry);
    }
    return entry;
  };
  for (const node of nodes) {
    const bucket = node[category];
    for (const name of bucket.declared) {
      const entry = ensure(name);
      if (!entry.declaredTurns.includes(node.turn)) entry.declaredTurns.push(node.turn);
    }
    for (const name of bucket.held) {
      const entry = ensure(name);
      if (!entry.heldTurns.includes(node.turn)) entry.heldTurns.push(node.turn);
    }
  }
  for (const entry of byName.values()) {
    entry.declaredTurns.sort((a, b) => a - b);
    entry.heldTurns.sort((a, b) => a - b);
  }
  return [...byName.values()].sort((a, b) => firstTurn(a) - firstTurn(b));
}

const firstTurn = (entry: Lifetime) =>
  entry.heldTurns[0] ?? entry.declaredTurns[0] ?? Number.MAX_SAFE_INTEGER;

/**
 * Entity lifetimes across a run: when each name first landed, whether it is
 * still there, and every turn a declaration failed to land.
 *
 * The per-turn name lists come from the server, so this only arranges them.
 */
export function MemoryTraceBoard({
  trace,
  loading,
  error,
  onOpenNode,
}: {
  trace: MemoryTraceResponse | null;
  loading: boolean;
  error: string;
  onOpenNode: (nodeId: number, turn: number) => void;
}) {
  const [category, setCategory] = useState<MemoryCategory>("world_facts");
  const [selected, setSelected] = useState<string | null>(null);

  const nodes = useMemo(
    () => (trace?.nodes ?? []).filter((node) => node.is_on_active_path),
    [trace],
  );
  const lastTurn = nodes.length > 0 ? Math.max(...nodes.map((node) => node.turn)) : 0;

  const losses = useMemo(() => {
    const counts: Record<string, { turns: number; names: number }> = {};
    for (const { key } of CATEGORIES) {
      let turns = 0;
      let names = 0;
      for (const node of nodes) {
        const missed = node[key].declared.filter((name) => !node[key].held.includes(name));
        if (missed.length > 0) {
          turns += 1;
          names += missed.length;
        }
      }
      counts[key] = { turns, names };
    }
    return counts;
  }, [nodes]);

  const entries = useMemo(() => lifetimes(nodes, category), [nodes, category]);
  const active = entries.find((entry) => entry.name === selected) ?? entries[0];

  if (error) return <p className="empty-state">{error}</p>;
  if (!trace) return <p className="empty-state">{loading ? "加载中…" : "没有可显示的记忆轨迹。"}</p>;
  if (nodes.length === 0) return <p className="empty-state">当前会话还没有可显示的剧情节点。</p>;

  return (
    <div className="trace-board">
      <div className="trace-summary">
        {CATEGORIES.map(({ key, label }) => {
          const { turns, names } = losses[key];
          return (
            <span className={names > 0 ? "trace-summary-item has-loss" : "trace-summary-item"} key={key}>
              {label} 声明未落库 {names} 条 / {turns} 轮
            </span>
          );
        })}
      </div>
      <div className="trace-category" role="group" aria-label="记忆类别">
        {CATEGORIES.map(({ key, label }) => (
          <button
            className={category === key ? "active" : ""}
            key={key}
            onClick={() => { setCategory(key); setSelected(null); }}
            type="button"
          >
            {label}（{lifetimes(nodes, key).length}）
          </button>
        ))}
      </div>
      <div className="trace-layout">
        <ul className="trace-entities" aria-label="实体存续">
          {entries.map((entry) => {
            const first = entry.heldTurns[0] ?? null;
            const last = entry.heldTurns[entry.heldTurns.length - 1] ?? null;
            const everHeld = entry.heldTurns.length > 0;
            const goneAt = everHeld && last !== null && last < lastTurn ? last : null;
            return (
              <li key={entry.name}>
                <button
                  className={`trace-entity${active?.name === entry.name ? " selected" : ""}${everHeld ? "" : " never-held"}`}
                  onClick={() => setSelected(entry.name)}
                  type="button"
                >
                  <span className="trace-entity-name">{entry.name}</span>
                  <span className="meta">
                    {everHeld ? `T${first}–T${last}` : "从未落库"}
                    {goneAt !== null ? " · 已消失" : ""}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        <div className="trace-detail">
          {!active ? <p className="empty-state">这一类别还没有任何条目。</p> : (
            <>
              <div className="trace-detail-head">
                <strong>{active.name}</strong>
                <span className="meta">
                  {active.heldTurns.length > 0
                    ? `落库 T${active.heldTurns[0]}–T${active.heldTurns[active.heldTurns.length - 1]}`
                    : "声明过但从未落库"}
                </span>
              </div>
              <div className="trace-strip">
                {nodes.map((node) => {
                  const held = node[category].held.includes(active.name);
                  const declared = node[category].declared.includes(active.name);
                  const state = held ? "held" : declared ? "declared" : "absent";
                  return (
                    <button
                      aria-label={`第 ${node.turn} 轮：${state === "held" ? "在库" : state === "declared" ? "声明未落库" : "不在库"}`}
                      className={`trace-cell ${state}`}
                      key={node.node_id}
                      onClick={() => onOpenNode(node.node_id, node.turn)}
                      title={`T${node.turn}`}
                      type="button"
                    />
                  );
                })}
              </div>
              <p className="trace-legend meta">
                绿=在库　红=声明未落库　空=不在库　·点格子跳到该轮
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
