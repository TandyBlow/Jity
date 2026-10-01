"use client";

import type { ReactNode } from "react";

import type { ItemMemory, NPCMemory, QuestMemory, WorldFactMemory } from "@/types";
import { memoryDetail } from "@/lib/game/format";

/**
 * Collapse state for one panel section, owned by the panel so it can persist
 * every section under a single key.
 */
export type FoldControl = {
  open: boolean;
  onToggle: (open: boolean) => void;
  /** Right-aligned in the summary line — occupancy, usually. */
  suffix?: string;
};

function Foldable({ fold, title, children }: { fold?: FoldControl; title: string; children: ReactNode }) {
  if (!fold) {
    return (
      <>
        <div className="section-title">{title}</div>
        {children}
      </>
    );
  }
  return (
    <details
      className="memory-fold"
      onToggle={(event) => fold.onToggle(event.currentTarget.open)}
      open={fold.open}
    >
      <summary className="memory-fold-summary">
        <span>{title}</span>
        {fold.suffix ? <span className="memory-fold-suffix">{fold.suffix}</span> : null}
      </summary>
      <div className="memory-fold-body">{children}</div>
    </details>
  );
}

export function MemorySection({
  title,
  items,
  fold,
}: {
  title: string;
  items: string[];
  fold?: FoldControl;
}) {
  return (
    <Foldable fold={fold} title={title}>
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
    </Foldable>
  );
}

export function MemoryObjects({
  title,
  items,
  kind,
  fold,
}: {
  title: string;
  items: Array<ItemMemory | NPCMemory | QuestMemory | WorldFactMemory>;
  kind: "item" | "npc" | "quest" | "world_fact";
  fold?: FoldControl;
}) {
  return (
    <Foldable fold={fold} title={title}>
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
    </Foldable>
  );
}
