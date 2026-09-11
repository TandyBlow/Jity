"use client";

import type { CampaignSession } from "@/types";
import type { TimelineData } from "@/app/timeline/useTimelineData";

export function AnchorTree({ data }: { data: TimelineData }) {
  const { arcs, campaigns, selectedFile, isAnchorRevealed } = data;

  if (arcs.length === 0) {
    return (
      <div className="anchor-tree">
        <div className="empty-state">
          {campaigns.length === 0
            ? "暂无可用战役。运行 /campaigns/generate 生成一个新战役。"
            : "选择一个战役以查看叙事弧和锚点。"}
        </div>
      </div>
    );
  }

  return (
    <div className="anchor-tree">
      {arcs.map((arc, ai) => (
        <div key={`arc-${ai}`} className="arc-group">
          <div className="arc-label">
            {arc.name}
            {arc.goal && <span className="meta" style={{ marginLeft: 8 }}>{arc.goal}</span>}
          </div>
          {arc.sessions?.map((session, si) => (
            <SessionGroup
              key={`session-${ai}-${si}`}
              session={session}
              arcIndex={ai}
              sessionIndex={si}
              selectedFile={selectedFile}
              isAnchorRevealed={isAnchorRevealed}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

function SessionGroup({
  session,
  arcIndex,
  sessionIndex,
  selectedFile,
  isAnchorRevealed,
}: {
  session: CampaignSession;
  arcIndex: number;
  sessionIndex: number;
  selectedFile: string;
  isAnchorRevealed: (id: string) => boolean;
}) {
  return (
    <div className="session-group">
      <div className="session-label">
        {session.name}
        <button
          className="start-here-btn"
          style={{ marginLeft: 12, fontSize: "0.8rem", padding: "2px 8px", cursor: "pointer" }}
          onClick={() => {
            if (typeof window !== "undefined") {
              sessionStorage.setItem("campaign_entry", JSON.stringify({
                campaignFilename: selectedFile,
                arcIndex,
                sessionIndex,
              }));
              window.location.href = "/";
            }
          }}
          title={`从 ${session.name} 开始新游戏`}
        >
          从此处开始
        </button>
      </div>
      <div className="anchor-list">
        {session.anchor_events?.map((anchor, ani) => {
          const revealed = isAnchorRevealed(anchor.id);
          return (
            <div key={anchor.id}>
              <AnchorCard anchor={anchor} revealed={revealed} />
              {ani < (session.anchor_events?.length ?? 0) - 1 && (
                <div className={`anchor-connector ${revealed && isAnchorRevealed(session.anchor_events?.[ani + 1]?.id ?? "") ? "" : "dim"}`} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AnchorCard({
  anchor,
  revealed,
}: {
  anchor: CampaignSession["anchor_events"][number];
  revealed: boolean;
}) {
  return (
    <div className={`anchor-card ${revealed ? "revealed" : "unrevealed"}`}>
      <div className="anchor-icon">
        {revealed ? (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent-2)" strokeWidth="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
        ) : (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#555" strokeWidth="2"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
        )}
      </div>
      <div className="anchor-body">
        <div className="anchor-name">
          {revealed ? anchor.name : "???"}
          <span className={revealed ? "badge-revealed" : "badge-unrevealed"} style={{ marginLeft: 8 }}>
            {revealed ? "已揭示" : "未揭示"}
          </span>
        </div>
        <div className="anchor-desc">
          {revealed ? anchor.description : "该锚点尚未在游戏中触发"}
        </div>
        {revealed && anchor.trigger_conditions && (
          <div className="anchor-tags">
            {anchor.trigger_conditions.location && (
              <span className="anchor-tag">📍 {anchor.trigger_conditions.location}</span>
            )}
            {anchor.trigger_conditions.npc_present && (
              <span className="anchor-tag">👤 {anchor.trigger_conditions.npc_present}</span>
            )}
            {anchor.trigger_conditions.item_held && (
              <span className="anchor-tag">📦 {anchor.trigger_conditions.item_held}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
