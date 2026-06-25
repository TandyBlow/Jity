"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import {
  getCampaign,
  getSessionProgress,
  listCampaigns,
} from "@/lib/api";
import type {
  CampaignAnchorEvent,
  CampaignArc,
  CampaignListItem,
  WorldFactMemory,
} from "@/types";

type FilterMode = "all" | "known" | "suspected";

function TimelineContent() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session") ?? "";
  const [campaigns, setCampaigns] = useState<CampaignListItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>("");
  const [arcs, setArcs] = useState<CampaignArc[]>([]);
  const [revealedAnchors, setRevealedAnchors] = useState<string[]>([]);
  const [worldFacts, setWorldFacts] = useState<WorldFactMemory[]>([]);
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      listCampaigns().catch(() => ({ campaigns: [] })),
      sessionId
        ? getSessionProgress(sessionId).catch(() => null)
        : Promise.resolve(null),
    ]).then(([list, progress]) => {
      setCampaigns(list.campaigns ?? []);
      if (progress) {
        setRevealedAnchors(progress.revealed_anchors ?? []);
        setWorldFacts(progress.world_facts ?? []);
      }
      // Auto-select first campaign
      const files = list.campaigns ?? [];
      if (files.length > 0) {
        const first = files[0].filename;
        setSelectedFile(first);
        getCampaign(first)
          .then((d) => setArcs(d.campaign?.arcs ?? []))
          .catch(() => setArcs([]));
      }
      setLoading(false);
    });
  }, [sessionId]);

  const handleSelectCampaign = useCallback((filename: string) => {
    setSelectedFile(filename);
    getCampaign(filename)
      .then((d) => setArcs(d.campaign?.arcs ?? []))
      .catch(() => setArcs([]));
  }, []);

  const isAnchorRevealed = (id: string) => revealedAnchors.includes(id);

  const filteredFacts =
    filterMode === "all"
      ? worldFacts
      : worldFacts.filter((f) =>
          filterMode === "known" ? f.status === "known" : f.status === "suspected"
        );

  return (
    <div className="timeline-shell">
      <div className="timeline-header">
        <div>
          <Link
            href="/"
            className="back-link"
            onClick={() => {
              if (sessionId && typeof window !== "undefined") {
                window.localStorage.setItem("jity_active_session_id", sessionId);
              }
            }}
          >
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
          {/* Anchor tree */}
          <div className="anchor-tree">
            {arcs.length === 0 ? (
              <div className="empty-state">
                {campaigns.length === 0
                  ? "暂无可用战役。运行 /campaigns/generate 生成一个新战役。"
                  : "选择一个战役以查看叙事弧和锚点。"}
              </div>
            ) : (
              arcs.map((arc, ai) => (
                <div key={`arc-${ai}`} className="arc-group">
                  <div className="arc-label">
                    {arc.name}
                    {arc.goal && <span className="meta" style={{ marginLeft: 8 }}>{arc.goal}</span>}
                  </div>
                  {arc.sessions?.map((session, si) => (
                    <div key={`session-${ai}-${si}`} className="session-group">
                      <div className="session-label">
                        {session.name}
                        <button
                          className="start-here-btn"
                          style={{ marginLeft: 12, fontSize: "0.8rem", padding: "2px 8px", cursor: "pointer" }}
                          onClick={() => {
                            if (typeof window !== "undefined") {
                              sessionStorage.setItem("campaign_entry", JSON.stringify({
                                campaignFilename: selectedFile,
                                arcIndex: ai,
                                sessionIndex: si,
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
                              {ani < (session.anchor_events?.length ?? 0) - 1 && (
                                <div className={`anchor-connector ${revealed && isAnchorRevealed(session.anchor_events?.[ani + 1]?.id ?? "") ? "" : "dim"}`} />
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              ))
            )}
          </div>

          {/* Clue board */}
          <div className="clue-board">
            <h2>线索板</h2>
            <div className="clue-filters">
              {(["all", "known", "suspected"] as FilterMode[]).map((mode) => (
                <button
                  key={mode}
                  className={`clue-filter ${filterMode === mode ? "active" : ""}`}
                  onClick={() => setFilterMode(mode)}
                >
                  {mode === "all" ? "全部" : mode === "known" ? "已确认" : "推测中"}
                </button>
              ))}
            </div>
            <div className="clue-list">
              {filteredFacts.length === 0 ? (
                <p className="empty-state">暂无已记录的线索</p>
              ) : (
                filteredFacts.map((fact, i) => {
                  const isSuspected = fact.status === "suspected";
                  return (
                    <div key={`fact-${i}`} className={`clue-card ${isSuspected ? "suspected" : "known"}`}>
                      <div className="clue-name">{fact.name}</div>
                      {isSuspected ? (
                        <div className="clue-placeholder">??? 尚未确认</div>
                      ) : (
                        <>
                          {fact.description && <div className="clue-desc">{fact.description}</div>}
                          {fact.source && <div className="clue-source">来源：{fact.source}</div>}
                        </>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
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
