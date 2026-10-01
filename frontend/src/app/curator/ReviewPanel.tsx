"use client";

import type { CuratorEditor } from "@/app/curator/useCuratorEditor";

export function ReviewPanel({ editor }: { editor: CuratorEditor }) {
  const { campaign, reviewStats } = editor;

  return (
    <div className="clue-board">
      <h2>审查摘要</h2>
      <div className="curator-review-body">
        <div><strong>标题：</strong>{campaign.title || "未设置"}</div>
        <div><strong>版本：</strong>v{campaign.version}</div>
        <div><strong>叙事弧：</strong>{campaign.arcs.length}个</div>
        <div><strong>总幕数：</strong>{reviewStats.totalSessions}</div>
        <div><strong>总锚点：</strong>{reviewStats.totalAnchors}</div>
        <div className="curator-review-label"><strong>锚点：</strong></div>
        <ul className="curator-review-list">
          {reviewStats.allAnchors.slice(0, 15).map((a) => (
            <li key={a.id}>{a.name} (P{a.priority})</li>
          ))}
        </ul>
        {reviewStats.allAnchors.length > 15 && (
          <div className="curator-review-more">…还有更多</div>
        )}
      </div>
    </div>
  );
}
