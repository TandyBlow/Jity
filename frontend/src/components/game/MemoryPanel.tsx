"use client";

import { BookOpen, Sparkles } from "lucide-react";

import type { GameSession } from "@/components/game/useGameSession";
import { MemoryObjects, MemorySection } from "@/components/game/MemorySection";
import { shorten, sourceTypeLabel } from "@/lib/game/format";

export function MemoryPanel({ session }: { session: GameSession }) {
  const { state, output, chunks } = session;

  return (
    <aside className="memory-panel">
      <div className="section-title">
        <span>Context Memory</span>
        <Sparkles size={16} />
      </div>

      <MemorySection
        title="当前状态"
        items={[
          `地点：${state?.current_location ?? output.current_location}`,
          `状态：${state?.player_status?.condition ?? "新生报到中"}`,
          `危险等级：${state?.player_status?.danger_level ?? "medium"}`,
          `当前目标：${state?.player_status?.current_goal ?? "完成卡塞尔学院入学报到"}`,
        ]}
      />

      <div className="stat-block">
        <div className="stat-row">
          <span>血统稳定</span>
          <strong>{state?.sanity ?? 80}</strong>
        </div>
        <div className="bar">
          <div className="bar-fill" style={{ width: `${state?.sanity ?? 80}%` }} />
        </div>
      </div>
      <div className="stat-block">
        <div className="stat-row">
          <span>体力</span>
          <strong>{state?.health ?? 100}</strong>
        </div>
        <div className="bar">
          <div className="bar-fill health" style={{ width: `${state?.health ?? 100}%` }} />
        </div>
      </div>

      <MemoryObjects title="同伴与 NPC" items={state?.npcs ?? []} kind="npc" />
      <MemoryObjects title="关键物品" items={state?.items ?? []} kind="item" />
      <MemoryObjects title="任务" items={state?.quests ?? []} kind="quest" />
      <MemoryObjects title="长期事实" items={state?.world_facts ?? []} kind="world_fact" />
      <MemorySection title="最近事件" items={state?.recent_events ?? []} />

      <RagHits chunks={chunks} />
    </aside>
  );
}

function RagHits({ chunks }: { chunks: GameSession["chunks"] }) {
  return (
    <>
      <div className="section-title">
        <span>RAG Hits</span>
        <BookOpen size={16} />
      </div>
      <div className="chunk-list">
        {chunks.length ? (
          chunks.map((chunk) => (
            <div className="chunk-item" key={chunk.id}>
              <div className="chunk-head">
                <span className={`chunk-badge ${chunk.source_type}`}>{sourceTypeLabel(chunk.source_type)}</span>
                <span className="chunk-score">score {chunk.score.toFixed(2)}</span>
              </div>
              <div className="chunk-title">{chunk.title}</div>
              <p>{shorten(chunk.content, 120)}</p>
              {chunk.keywords?.length ? (
                <div className="keyword-row">
                  {chunk.keywords.slice(0, 4).map((keyword) => (
                    <span className="keyword-chip" key={`${chunk.id}-${keyword}`}>
                      {keyword}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ))
        ) : (
          <div className="memory-item">首次生成后会显示检索命中的规则、NPC 和地点资料。</div>
        )}
      </div>
    </>
  );
}
