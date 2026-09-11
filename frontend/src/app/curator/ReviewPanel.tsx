"use client";

import type { CuratorEditor } from "@/app/curator/useCuratorEditor";

export function ReviewPanel({ editor }: { editor: CuratorEditor }) {
  const { campaign, reviewStats } = editor;

  return (
    <div className="clue-board" style={{ position: "static" }}>
      <h2>审查摘要</h2>
      <div style={{ fontSize: 13, lineHeight: 1.8 }}>
        <div><strong>标题：</strong>{campaign.title || "未设置"}</div>
        <div><strong>版本：</strong>v{campaign.version}</div>
        <div><strong>叙事弧：</strong>{campaign.arcs.length}个</div>
        <div><strong>总幕数：</strong>{reviewStats.totalSessions}</div>
        <div><strong>总锚点：</strong>{reviewStats.totalAnchors}</div>
        <div style={{ marginTop: 12 }}><strong>锚点：</strong></div>
        <ul style={{ paddingLeft: 18, margin: "4px 0" }}>
          {reviewStats.allAnchors.slice(0, 15).map((a) => (
            <li key={a.id} style={{ fontSize: 12, color: "var(--muted)" }}>{a.name} (P{a.priority})</li>
          ))}
        </ul>
        {reviewStats.allAnchors.length > 15 && (
          <div style={{ fontSize: 12, color: "var(--muted)" }}>…还有更多</div>
        )}
      </div>
    </div>
  );
}
