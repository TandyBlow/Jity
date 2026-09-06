"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AnchorTree } from "@/app/timeline/AnchorTree";
import { ClueBoard } from "@/app/timeline/ClueBoard";
import { useTimelineData } from "@/app/timeline/useTimelineData";

function TimelineContent() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session") ?? "";
  const data = useTimelineData(sessionId);
  const { campaigns, selectedFile, loading, handleSelectCampaign } = data;

  return (
    <div className="timeline-shell">
      <div className="timeline-header">
        <div>
          <Link href="/" className="back-link">
            ← 返回控制台
          </Link>
          <h1>发现时间线</h1>
          {!sessionId && (
            <p className="meta" style={{ marginTop: 8 }}>
              提示：从控制台打开此页面以查看实际进度。当前显示战役结构预览。
            </p>
          )}
        </div>
        {campaigns.length > 0 && (
          <select
            className="select"
            style={{ maxWidth: 300 }}
            value={selectedFile}
            onChange={(e) => handleSelectCampaign(e.target.value)}
          >
            {campaigns.map((c) => (
              <option key={c.filename} value={c.filename}>
                {c.title} (v{c.version}, {c.arc_count}弧)
              </option>
            ))}
          </select>
        )}
      </div>

      {loading ? (
        <p className="empty-state">加载中…</p>
      ) : (
        <div className="timeline-layout">
          <AnchorTree data={data} />
          <ClueBoard data={data} />
        </div>
      )}
    </div>
  );
}

export default function TimelinePage() {
  return (
    <Suspense fallback={<div className="timeline-shell"><p className="empty-state">加载中…</p></div>}>
      <TimelineContent />
    </Suspense>
  );
}
