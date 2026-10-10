"use client";

import { memoryDetail } from "@/lib/game/format";
import type {
  ItemMemory,
  MemoryCategory,
  StoryDeltaEntry,
  TimelineNodeDetail,
} from "@/types";

/**
 * What this turn claimed it remembered, against what the resulting state holds.
 *
 * Both lists come from the server already folded in merge order. Rebuilding
 * that merge here would mean a second implementation of it, and a drift would
 * show up as a wrong research answer rather than a visible bug.
 */
const CATEGORIES: Array<{
  key: MemoryCategory;
  label: string;
  kind: "item" | "npc" | "quest" | "world_fact";
}> = [
  { key: "items", label: "物品", kind: "item" },
  { key: "npcs", label: "NPC", kind: "npc" },
  { key: "quests", label: "任务", kind: "quest" },
  { key: "world_facts", label: "长期事实", kind: "world_fact" },
];

export function MemoryDelta({ detail }: { detail: TimelineNodeDetail }) {
  if (!detail.output) return null;

  const active = CATEGORIES.filter(({ key }) => detail.memory[key].declared.length > 0);
  if (active.length === 0) {
    return (
      <section className="memory-delta">
        <h3>本轮记忆变更</h3>
        <p className="meta">这一轮没有声明任何记忆变更。</p>
      </section>
    );
  }

  return (
    <section className="memory-delta">
      <h3>本轮记忆变更</h3>
      {active.map(({ key, label, kind }) => {
        const { declared, held } = detail.memory[key];
        const missing = declared.filter((name) => !held.includes(name));
        const used = detail.state[key].length;
        const cap = detail.caps[key];
        const raw = detail.declared[key].upserted;
        return (
          <div className="memory-delta-category" key={key}>
            <div className="memory-delta-head">
              <span>{label}</span>
              <span className={cap !== null && used >= cap ? "memory-delta-cap full" : "memory-delta-cap"}>
                落库 {used}{cap === null ? " · 无固定上限" : `/${cap}${used >= cap ? " · 已满" : ""}`}
              </span>
            </div>
            <ul className="memory-delta-list">
              {declared.map((name) => (
                <li className={missing.includes(name) ? "missing" : ""} key={name}>
                  <span>{name}</span>
                  {missing.includes(name) ? <em>未落库</em> : null}
                </li>
              ))}
            </ul>
            <details className="memory-delta-raw">
              <summary>最终提交的声明（{raw.length} 条）</summary>
              <ul>
                {raw.map((entry: StoryDeltaEntry, index) => (
                  <li key={index}>
                    <strong>{String(entry.name ?? "未命名")}</strong>
                    <span className="meta">{memoryDetail(entry as ItemMemory, kind)}</span>
                  </li>
                ))}
              </ul>
            </details>
          </div>
        );
      })}
    </section>
  );
}
