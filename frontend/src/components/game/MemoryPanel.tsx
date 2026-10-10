"use client";

import { BookOpen, History, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { MemoryObjects, MemorySection, type FoldControl } from "@/components/game/MemorySection";
import type { GameSession } from "@/components/game/useGameSession";
import { shorten, sourceTypeLabel } from "@/lib/game/format";
import type { GameState, MemoryCategory, TurnReport } from "@/types";

const FOLD_STORAGE_KEY = "jity_memory_folds";

const CATEGORIES: Array<{ key: MemoryCategory; label: string }> = [
  { key: "items", label: "物品" },
  { key: "npcs", label: "NPC" },
  { key: "quests", label: "任务" },
  { key: "world_facts", label: "长期事实" },
];

/** Every section starts open: the panel is the observation window. */
function useFolds() {
  const [folds, setFolds] = useState<Record<string, boolean>>({});

  useEffect(() => {
    try {
      setFolds(JSON.parse(window.localStorage.getItem(FOLD_STORAGE_KEY) ?? "{}") as Record<string, boolean>);
    } catch {
      setFolds({});
    }
  }, []);

  const control = (id: string, suffix?: string): FoldControl => ({
    open: folds[id] ?? true,
    suffix,
    onToggle: (open: boolean) => {
      setFolds((current) => {
        const next = { ...current, [id]: open };
        try {
          window.localStorage.setItem(FOLD_STORAGE_KEY, JSON.stringify(next));
        } catch {
          // Storage is a convenience; losing it must not break the panel.
        }
        return next;
      });
    },
  });

  return control;
}

function occupancy(state: GameState | null, report: TurnReport | null, key: MemoryCategory) {
  const used = state?.[key]?.length ?? 0;
  const cap = report?.caps?.[key];
  if (cap === null) return `${used} · 无固定上限`;
  if (!cap) return String(used);
  return `${used}/${cap}${used >= cap ? " · 已满" : ""}`;
}

export function MemoryPanel({ session }: { session: GameSession }) {
  return (
    <aside className="memory-panel">
      <div className="section-title">
        <span>Context Memory</span>
        <Sparkles size={16} />
      </div>
      <MemoryPanelBody session={session} />
    </aside>
  );
}

/** Shared by the docked column and the narrow-screen drawer. */
export function MemoryPanelBody({ session }: { session: GameSession }) {
  const { sessionId, state, output, chunks, turnReport } = session;
  const fold = useFolds();

  return (
    <>
      <TurnMemory report={turnReport} state={state} />

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
          <span>血条</span>
          <strong>{state?.health ?? 100}</strong>
        </div>
        <div className="bar">
          <div className="bar-fill health" style={{ width: `${state?.health ?? 100}%` }} />
        </div>
      </div>

      <MemoryObjects
        fold={fold("npcs", occupancy(state, turnReport, "npcs"))}
        items={state?.npcs ?? []}
        kind="npc"
        title="同伴与 NPC"
      />
      <MemoryObjects
        fold={fold("items", occupancy(state, turnReport, "items"))}
        items={state?.items ?? []}
        kind="item"
        title="关键物品"
      />
      <MemoryObjects
        fold={fold("quests", occupancy(state, turnReport, "quests"))}
        items={state?.quests ?? []}
        kind="quest"
        title="任务"
      />
      <MemoryObjects
        fold={fold("world_facts", occupancy(state, turnReport, "world_facts"))}
        items={state?.world_facts ?? []}
        kind="world_fact"
        title="长期事实"
      />
      <MemorySection
        fold={fold("recent_events", String((state?.recent_events ?? []).length))}
        items={state?.recent_events ?? []}
        title="最近事件"
      />

      {session.autoPlay.enabled ? (
        <div className="autoplay-anchors">
          <div className="section-title"><span>战役锚点 · {session.autoPlay.revealedAnchors.length}</span></div>
          {session.autoPlay.revealedAnchors.length ? session.autoPlay.revealedAnchors.map((anchor) => (
            <div className={`memory-item${anchor.isNew ? " anchor-new" : ""}`} key={anchor.id}>
              {anchor.isNew ? "新触发 · " : "已揭示 · "}{anchor.name}
            </div>
          )) : <div className="memory-item">尚未触发锚点</div>}
          {sessionId ? <a className="autoplay-anchor-link" href={session.autoPlay.timelineUrl} target="_blank">打开实时锚点树 ↗</a> : null}
        </div>
      ) : null}

      <RagHits chunks={chunks} fold={fold("rag_hits", String(chunks.length))} />
    </>
  );
}

/**
 * What the model claimed it remembered this turn, against what state kept.
 *
 * The verdict is computed server side from the same fold `apply_output` uses,
 * so a name shown as missing really is missing. 36% of turns declare nothing,
 * and saying so is itself the finding.
 */
function TurnMemory({ report, state }: { report: TurnReport | null; state: GameState | null }) {
  if (!report) return null;

  const losses = CATEGORIES.reduce(
    (total, { key }) =>
      total + report.memory[key].declared.filter((name) => !report.memory[key].held.includes(name)).length,
    0,
  );
  const active = CATEGORIES.filter(({ key }) => report.memory[key].declared.length > 0);

  return (
    <section className="turn-memory">
      <div className="section-title">
        <span>本轮记忆变更{losses > 0 ? ` · ${losses} 条未落库` : ""}</span>
        <History size={16} />
      </div>
      {active.length === 0 ? (
        <div className="memory-item">这一轮没有声明任何记忆变更。</div>
      ) : (
        active.map(({ key, label }) => {
          const { declared, held } = report.memory[key];
          const used = state?.[key]?.length ?? 0;
          const cap = report.caps[key];
          return (
            <div className="turn-memory-group" key={key}>
              <div className="turn-memory-head">
                <span>{label}</span>
                <span className={cap !== null && used >= cap ? "turn-memory-cap full" : "turn-memory-cap"}>
                  落库 {used}{cap === null ? " · 无固定上限" : `/${cap}`}
                </span>
              </div>
              <div className="memory-list">
                {declared.map((name) => {
                  const missing = !held.includes(name);
                  return (
                    <div className={missing ? "memory-item missing" : "memory-item"} key={name}>
                      <div className="memory-head">
                        <strong>{name}</strong>
                        {missing ? <span className="memory-status">未落库</span> : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })
      )}
    </section>
  );
}

function RagHits({ chunks, fold }: { chunks: GameSession["chunks"]; fold: FoldControl }) {
  return (
    <details
      className="memory-fold"
      onToggle={(event) => fold.onToggle(event.currentTarget.open)}
      open={fold.open}
    >
      <summary className="memory-fold-summary">
        <span>RAG Hits</span>
        <span className="memory-fold-suffix">{fold.suffix}</span>
        <BookOpen size={16} />
      </summary>
      <div className="memory-fold-body">
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
      </div>
    </details>
  );
}
