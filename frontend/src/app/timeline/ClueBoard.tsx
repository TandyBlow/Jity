"use client";

import type { WorldFactMemory } from "@/types";
import type { FilterMode, TimelineData } from "@/app/timeline/useTimelineData";

export function ClueBoard({ data }: { data: TimelineData }) {
  const { filterMode, setFilterMode, filteredFacts } = data;

  return (
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
          filteredFacts.map((fact, i) => <ClueCard key={`fact-${i}`} fact={fact} />)
        )}
      </div>
    </div>
  );
}

function ClueCard({ fact }: { fact: WorldFactMemory }) {
  const isSuspected = fact.status === "suspected";
  return (
    <div className={`clue-card ${isSuspected ? "suspected" : "known"}`}>
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
}
