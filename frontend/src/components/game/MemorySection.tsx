"use client";

import type { ItemMemory, NPCMemory, QuestMemory, WorldFactMemory } from "@/types";
import { memoryDetail } from "@/lib/game/format";

export function MemorySection({ title, items }: { title: string; items: string[] }) {
  return (
    <>
      <div className="section-title">{title}</div>
      <div className="memory-list">
        {items.filter(Boolean).length ? (
          items.filter(Boolean).map((item) => (
            <div className="memory-item" key={item}>
              {item}
            </div>
          ))
        ) : (
          <div className="memory-item">暂无记录</div>
        )}
      </div>
    </>
  );
}

export function MemoryObjects({
  title,
  items,
  kind,
}: {
  title: string;
  items: Array<ItemMemory | NPCMemory | QuestMemory | WorldFactMemory>;
  kind: "item" | "npc" | "quest" | "world_fact";
}) {
  return (
    <>
      <div className="section-title">{title}</div>
      <div className="memory-list">
        {items.length ? (
          items.map((item, index) => (
            <div className="memory-item" key={`${item.name}-${index}`}>
              <div className="memory-head">
                <strong>{item.name ?? "未命名"}</strong>
                {item.status ? <span className="memory-status">{item.status}</span> : null}
              </div>
              <div className="meta">{memoryDetail(item, kind)}</div>
            </div>
          ))
        ) : (
          <div className="memory-item">暂无记录</div>
        )}
      </div>
    </>
  );
}
