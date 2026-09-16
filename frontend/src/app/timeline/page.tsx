"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useState } from "react";

import { AnchorTree } from "@/app/timeline/AnchorTree";
import { ClueBoard } from "@/app/timeline/ClueBoard";
import { StoryTimeline } from "@/app/timeline/StoryTimeline";
import { useTimelineData } from "@/app/timeline/useTimelineData";

function TimelineContent() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session") ?? "";
  const requestedNode = Number(searchParams.get("node")) || undefined;
  const preferActiveParent = searchParams.get("back") === "1";
  const isAutoPlayView = searchParams.get("autoplay") === "1";
  const data = useTimelineData(sessionId, requestedNode, preferActiveParent, isAutoPlayView);
  const requestedTab = searchParams.get("tab");
  const [tab, setTab] = useState<"story" | "anchors" | "clues">(
    requestedTab === "anchors" || requestedTab === "clues" ? requestedTab : (sessionId ? "story" : "anchors"),
  );
  const { campaigns, selectedFile, loading, handleSelectCampaign } = data;

  return (
    <div className="timeline-shell">
      <div className="timeline-header">
        <div>
          <Link
            href={isAutoPlayView
              ? `/?${new URLSearchParams({
                  autoplay: "1",
                  session: sessionId,
                  turns: searchParams.get("turns") ?? "300",
                  delay: searchParams.get("delay") ?? "200",
                  seed: searchParams.get("seed") ?? "20260616",
                }).toString()}`
              : "/"}
            className="back-link"
            onClick={(event) => {
              if (sessionId && typeof window !== "undefined") {
                window.localStorage.setItem("jity_active_session_id", sessionId);
                if (isAutoPlayView) {
                  event.preventDefault();
                  window.close();
                }
              }
            }}
          >
            ← {isAutoPlayView ? "关闭时间线" : "返回控制台"}
          </Link>
          <h1>发现时间线</h1>
          {!sessionId && (
            <p className="meta" style={{ marginTop: 8 }}>
              提示：从控制台打开此页面以查看实际进度。当前显示战役结构预览。
            </p>
          )}
          {isAutoPlayView ? <p className="meta" style={{ marginTop: 8 }}>实时观察模式：每 2 秒刷新，自动剧情在原页签继续运行。</p> : null}
        </div>
        {tab === "anchors" && campaigns.length > 0 && (
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
        <>
          <div className="timeline-tabs" role="tablist" aria-label="时间线视图">
            <button className={tab === "story" ? "active" : ""} onClick={() => setTab("story")} role="tab" type="button">剧情分支</button>
            <button className={tab === "anchors" ? "active" : ""} onClick={() => setTab("anchors")} role="tab" type="button">战役锚点</button>
            <button className={tab === "clues" ? "active" : ""} onClick={() => setTab("clues")} role="tab" type="button">世界线索</button>
          </div>
          <div className={`timeline-tab-panel ${tab}`}>
            {tab === "story" ? <StoryTimeline data={data} hasSession={!!sessionId} /> : null}
            {tab === "anchors" ? <AnchorTree data={data} /> : null}
            {tab === "clues" ? <ClueBoard data={data} /> : null}
          </div>
        </>
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
